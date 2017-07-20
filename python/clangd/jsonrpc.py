# simple jsonrpc client over raw socket
# http://www.jsonrpc.org/specification
# Content-Length: ...\r\n
# \r\n
# {
#   'jsonrpc': '2.0',
#     'id': 1,
#       'method': 'textDocument/didOpen',
#         'params': {
#             ...
#               }
#               }
#
import json, os, sys
import clangd.glog as log
from clangd.vimsupport import PyVersion
from threading import Thread
from errno import EINTR
from time import sleep
# try to keep compatibily with old 2.7
try:
    import queue
except ImportError:
    import Queue as queue

DEFAULT_TIMEOUT_MS = 1000
IDLE_INTERVAL_MS = 25

class Poller(object):
    def __init__(self, rfds, wfds):
        self._rfds = rfds
        self._wfds = wfds

    def shutdown(self):
        pass

    def poll(self, timeout_ms):
        raise NotImplementedError('not okay')

# FIXME this Win32Poller doesn't really work on non-overlapped io
# class Win32Poller(Poller):
#     def __init__(self, rfds, wfds):
#         from clangd.iocp import CreateIoCompletionPort, GetQueuedCompletionStatus, INVALID_HANDLE_VALUE, CloseHandle
#         from msvcrt import get_osfhandle
#         if PyVersion() == 2:
#             super(Win32Poller, self).__init__(rfds, wfds)
#         else:
#             super().__init__(rfds, wfds)
#         self._rhandles = [ rfd.filehandle() for rfd in rfds ]
#         self._whandles = [ rfd.filehandle() for wfd in wfds ]
#         self._completion_port = CreateIoCompletionPort(INVALID_HANDLE_VALUE, 0, 0, 0)
#         log.info('completion port created, %d' % self._completion_port)
#         for rhandle in self._rhandles:
#             CreateIoCompletionPort(rhandle, self._completion_port, rhandle, 0)
#         for whandle in self._whandles:
#             CreateIoCompletionPort(whandle, self._completion_port, whandle + 4096, 0)
#
#     def shutdown(self):
#         if self._completion_port:
#             CloseHandle(self._completion_port)
#             log.info('completion port destroyed, %d' % self._completion_port)
#
#     def poll(self, timeout_ms):
#         if not self._completion_port:
#             return [], []
#         rc, numOfBytes, completion_key, overlapped = GetQueuedCompletionStatus(self._completion_port, timeout_ms)
#         if not rc:
#             return [], []
#         if completion_key >= 4096:
#             return [], [completion_key - 4096]
#         return [completion_key], []

class Win32Poller(Poller):
    def __init__(self, rfds, wfds):
        if PyVersion() == 2:
            super(Win32Poller, self).__init__(rfds, wfds)
        else:
            super().__init__(rfds, wfds)
        self._rhandles = [ rfd.filehandle() for rfd in rfds ]
        self._whandles = [ rfd.filehandle() for wfd in wfds ]

    def poll(self, timeout_ms):
        from select import select
        rs, ws, _ = select(self._rhandles, self._whandles, [], timeout_ms)
        # FIXME convert to fd
        return rs, ws

class PosixPoller(Poller):
    def __init__(self, rfds, wfds):
        if PyVersion() == 2:
            super(PosixPoller, self).__init__(rfds, wfds)
        else:
            super().__init__(rfds, wfds)

    def poll(self, timeout_ms):
        from select import select
        rfds, wfds = select(self._rfds, self._wfds, [], timeout_ms)
        return rfds, wfds

class TimedOutError(OSError):
    pass

def EstimateUnreadBytes(fd):
    from array import array

    if sys.platform == 'win32':
        from iocp import _ioctlsocket, FIONREAD
        return _ioctlsocket(fd.filehandle(), FIONREAD)
    else:
        from fcntl import ioctl
        from termios import FIONREAD
        buf = array('i', [0])
        ioctl(fd, FIONREAD, buf, 1)
        return buf[0]


def write_utf8(fd, data):
    msg = data.encode('utf-8')
    if sys.platform == 'win32':
        fd = fd.fileno()
    while len(msg):
        try:
            written = os.write(fd, msg)
            msg = msg[written:]
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg


def read_utf8(fd, length):
    msg = bytes()
    if sys.platform == 'win32':
        fd = fd.fileno()
    while length:
        try:
            buf = os.read(fd, length)
            length -= len(buf)
            msg += buf
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg.decode('utf-8')


class JsonRPCClientThread(Thread):
    def __init__(self, input_fd, output_fd, read_queue, write_queue):
        Thread.__init__(self)
        self._is_stop = False
        self._input_fd = input_fd
        self._output_fd = output_fd
        self._read_queue = read_queue
        self._write_queue = write_queue
        if sys.platform == 'win32':
            # from iocp import _ioctlsocket, FIONBIO
            # _ioctlsocket(input_fd.filehandle(), FIONBIO, 1)
            # _ioctlsocket(output_fd.filehandle(), FIONBIO, 1)
            self._poller = Win32Poller([self._output_fd], [])
        else:
            self._poller = PosixPoller([self._output_fd], [])

    def shutdown(self):
        log.warn('io thread shutdown')
        self._poller.shutdown()

    def _SendMsg(self, r):
        request = json.dumps(r, separators=(',', ':'), sort_keys=True)
        write_utf8(self._input_fd,
                   u'Content-Length: %d\r\n\r\n' % len(request))
        write_utf8(self._input_fd, request)

    def _RecvMsgHeader(self):
        read_utf8(self._output_fd, len('Content-Length: '))
        msg = u''
        msg += read_utf8(self._output_fd, 4)
        while True:
            if msg.endswith('\r\n\r\n'):
                break
            if len(msg) >= 23:  # sys.maxint + 4
                raise OSError('bad protocol')
            msg += read_utf8(self._output_fd, 1)

        msg = msg[:-4]
        length = int(msg)
        return length

    def _RecvMsg(self):
        msg_length = self._RecvMsgHeader()
        msg = read_utf8(self._output_fd, msg_length)

        rr = json.loads(msg)
        return rr

    def _OnWentWrong(self):
        self._is_stop = True
        self._read_queue.put(OSError('shutdown unexcepted'))

    def run(self):
        log.warn('io thread starts')
        try:
            self._Run()
        except:
            log.exception('failed io thread')
        self.shutdown()

    def _Run(self):
        long_idle = 0
        while not self._is_stop:
            while True:
                try:
                    r = self._write_queue.get_nowait()
                except queue.Empty:
                    break

                # receive shutdown notification
                # FIXME use better class?
                if isinstance(r, OSError):
                    self._is_stop = True
                    break

                try:
                    self._SendMsg(r)
                    long_idle = 0
                except OSError as e:
                    self._OnWentWrong()
                    break
            if self._is_stop:
                break
            # Note that on Windows, it (select) only works for sockets;
            rlist, _ = self._poller.poll(IDLE_INTERVAL_MS * long_idle)

            # ticky to detect clangd's failure
            if rlist and EstimateUnreadBytes(self._output_fd) == 0:
                self._OnWentWrong()
                break

            if rlist:
                long_idle = 0

            if rlist and EstimateUnreadBytes(
                    self._output_fd) > len('Content-Length: '):
                try:
                    rr = self._RecvMsg()
                except OSError as e:
                    self._OnWentWrong()
                    break
                self._read_queue.put(rr)
            if long_idle < 100:
                long_idle += 1

class JsonRPCClient:
    def __init__(self, request_observer, input_fd, output_fd):
        self._no = 0
        self._requests = {}
        self._observer = request_observer
        self._read_queue = queue.Queue()
        self._write_queue = queue.Queue()
        self._io_thread = JsonRPCClientThread(
            input_fd, output_fd, self._read_queue, self._write_queue)
        self._io_thread.start()
        self._is_stop = False

    def stop(self):
        if self._is_stop:
            return
        self._write_queue.put(OSError('stop'))
        self._is_stop = True
        self._io_thread.join()

    def sendRequest(self, method, params, nullResponse, timeout_ms):
        Id = self._no
        self._no = self._no + 1
        r = self.SendMsg(method, params, Id=Id)
        if nullResponse:
            return None
        log.debug('send request: %s' % r)

        if timeout_ms is None:
            timeout_ms = DEFAULT_TIMEOUT_MS
        while timeout_ms > 0:
            if self._is_stop:
                self._observer.onServerDown()
                raise OSError('client is down')

            try:
                rr = self._read_queue.get_nowait()
            except queue.Empty:
                sleep(IDLE_INTERVAL_MS * 0.001)
                timeout_ms -= IDLE_INTERVAL_MS
                continue
            if isinstance(rr, OSError):
                self._observer.onServerDown()
                raise rr
            rr = self.RecvMsg(rr)
            if 'id' in rr and rr['id'] == Id:
                if 'error' in rr:
                    raise OSError('bad error_code %d' % rr['error'])
                return rr['result']
        raise TimedOutError('msg timeout')
        return None

    def sendNotification(self, method, params):
        try:
            r = self.SendMsg(method, params)
        except OSError:
            self._observer.onServerDown()
            raise
        log.debug('send notifications: %s' % r)

    def handleRecv(self):
        while True:
            if self._is_stop:
                raise OSError('client is down')
            try:
                rr = self._read_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(rr, OSError):
                raise rr
            self.RecvMsg(rr)

    def SendMsg(self, method, params={}, Id=None):
        r = {}
        r['jsonrpc'] = '2.0'
        r['method'] = str(method)
        r['params'] = params
        if Id is not None:
            r['id'] = Id
            self._requests[Id] = r
        if self._is_stop:
            raise OSError('client is down')
        self._write_queue.put(r)
        return r

    def RecvMsg(self, rr):
        if not 'id' in rr:
            self.OnNotification(rr)
        elif not rr['id'] in self._requests:
            self.OnRequest(rr)
        else:
            self.OnResponse(self._requests[rr['id']], rr)
            self._requests.pop(rr['id'])
        return rr

    def OnNotification(self, request):
        log.debug('recv notification: %s' % request)
        self._observer.onNotification(request['method'], request['params'])

    def OnRequest(self, request):
        log.debug('recv request: %s' % request)
        self._observer.onRequest(request['method'], request['params'])

    def OnResponse(self, request, response):
        log.debug('recv response: %s' % response)
        self._observer.onResponse(request, response['result'])
