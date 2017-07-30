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
import json
import os
from sys import platform as sys_platform
from clangd import glog as log
from threading import Thread
from time import sleep
# try to keep compatibily with old 2.7
try:
    import queue
except ImportError:
    import Queue as queue

# platform specific
if sys_platform == 'win32':
    from clangd.poller import Win32Poller as Poller
    from clangd.win32_utils import SetNonBlock, EstimateUnreadBytes, WriteUtf8, ReadUtf8
else:
    from clangd.poller import PosixPoller as Poller
    from clangd.posix_utils import EstimateUnreadBytes, WriteUtf8, ReadUtf8

DEFAULT_TIMEOUT_MS = 1000
IDLE_INTERVAL_MS = 25

class TimedOutError(OSError):
    pass


class JsonRPCClientThread(Thread):
    def __init__(self, input_fd, output_fd, read_queue, write_queue):
        Thread.__init__(self)
        self._is_stop = False
        self._input_fd = input_fd
        self._output_fd = output_fd
        self._read_queue = read_queue
        self._write_queue = write_queue
        if sys_platform == 'win32':
            SetNonBlock(input_fd)
            SetNonBlock(output_fd)
        self._poller = Poller([self._output_fd], [])

    def shutdown(self):
        log.warn('io thread shutdown')
        self._poller.shutdown()

    def _SendMsg(self, r):
        request = json.dumps(r, separators=(',', ':'), sort_keys=True)
        WriteUtf8(self._input_fd,
                   u'Content-Length: %d\r\n\r\n' % len(request))
        WriteUtf8(self._input_fd, request)

    def _RecvMsgHeader(self):
        ReadUtf8(self._output_fd, len('Content-Length: '))
        msg = u''
        msg += ReadUtf8(self._output_fd, 4)
        while True:
            if msg.endswith('\r\n\r\n'):
                break
            if len(msg) >= 23:  # sys.maxint + 4
                raise OSError('bad protocol')
            msg += ReadUtf8(self._output_fd, 1)

        msg = msg[:-4]
        length = int(msg)
        return length

    def _RecvMsg(self):
        msg_length = self._RecvMsgHeader()
        msg = ReadUtf8(self._output_fd, msg_length)

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

class JsonRPCClient(object):
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
