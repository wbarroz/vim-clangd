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
    from clangd_support.poller import Win32Poller as Poller
    from clangd_support.win32_utils import SetNonBlock, EstimateUnreadBytes, WriteUtf8, ReadUtf8
else:
    from clangd_support.poller import PosixPoller as Poller
    from clangd_support.posix_utils import SetNonBlock, EstimateUnreadBytes, WriteUtf8, ReadUtf8

DEFAULT_TIMEOUT_MS = 1000
IDLE_INTERVAL_MS = 25
MAX_IDLE_TIMES = 10

class TimedOutError(OSError):
    pass

def isNumber(c):
    return ord('0') <= ord(c) and ord(c) <= ord('9')

class JsonRPCClientThread(Thread):
    def __init__(self, input_fd, output_fd, read_queue, write_queue):
        Thread.__init__(self)
        self._is_stop = False
        self._input_fd = input_fd
        self._output_fd = output_fd
        self._read_queue = read_queue
        self._write_queue = write_queue
        self._writebuf = u''
        self._readbuf = u''
        SetNonBlock(input_fd)
        SetNonBlock(output_fd)
        self._poller = Poller([self._output_fd], [])

    def shutdown(self):
        log.warn('io thread shutdown')
        self._poller.shutdown()

    def _FlushSendBuffer(self):
        while self._writebuf:
            written = WriteUtf8(self._input_fd, self._writebuf)
            if not written:
                break
            self._writebuf = self._writebuf[written:]
            log.debug('written %d bytes remains %d bytes' % (written, len(self._writebuf)))

    def _FetchRecvBuffer(self, buffer_len = 256):
        while buffer_len:
            chunk = ReadUtf8(self._output_fd, buffer_len)
            if not chunk:
                break
            log.debug('read %d bytes with buffer %d bytes' % (len(chunk), buffer_len))
            buffer_len -= len(chunk)
            self._readbuf += chunk

    def _SendMsg(self, r):
        request = json.dumps(r, separators=(',', ':'), sort_keys=True)
        self._writebuf += u'Content-Length: %d\r\n\r\n' % len(request)
        self._writebuf += request

    def _RecvMsg(self):
        PREFIX = 'Content-Length: '
        if len(self._readbuf) < len(PREFIX):
            return None
        if not self._readbuf.startswith(PREFIX):
            raise OSError('bad protocol')
        i = len(PREFIX)
        while i < len(self._readbuf):
            if i - len(PREFIX) >= 23:  # sys.maxint + 4
                raise OSError('bad protocol')
            if not isNumber(self._readbuf[i]):
                break
            i += 1
        if len(self._readbuf) < i + 4:
            return None
        if self._readbuf[i:i + 4] != u'\r\n\r\n':
            raise OSError('bad protocol')
        length = int(self._readbuf[len(PREFIX):i])
        if len(self._readbuf) < i + 4 + length:
            return None
        msg = self._readbuf[i + 4:i + 4 + length]
        try:
            rr = json.loads(msg)
        except Exception:
            raise OSError('bad protocol')
        self._readbuf = self._readbuf[i + 4 + length:]
        return rr

    def _OnWentWrong(self):
        self._is_stop = True
        self._read_queue.put(OSError('shutdown unexcepted'))

    def run(self):
        log.warn('io thread starts')
        try:
            self._RunEventLoop()
        except:
            log.exception('fatal error, io thread')
        self.shutdown()

    def _RunEventLoop(self):
        long_idle = 0
        while not self._is_stop:
            rlist, _ = self._poller.poll(IDLE_INTERVAL_MS * long_idle)

            if rlist:
                buffer_len = EstimateUnreadBytes(self._output_fd)
                # ticky to detect clangd's failure
                if buffer_len == 0:
                    self._OnWentWrong()
                    break

            if rlist or len(self._readbuf):
                long_idle = 0

                if rlist:
                    buffer_len = EstimateUnreadBytes(self._output_fd)
                    self._FetchRecvBuffer(buffer_len)

                try:
                    rr = self._RecvMsg()
                except OSError as e:
                    self._OnWentWrong()
                    break

                if rr:
                    self._read_queue.put(rr)

            while True:
                try:
                    r = self._write_queue.get_nowait()
                except queue.Empty:
                    break
                # receive shutdown sentinel
                if r == None:
                    self._is_stop = True
                    break
                try:
                    self._SendMsg(r)
                    long_idle = 0
                except OSError as e:
                    self._OnWentWrong()
                    break
            self._FlushSendBuffer()

            if long_idle < MAX_IDLE_TIMES:
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
        # put stop sentinel to io thread
        self._write_queue.put(None)
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
        while timeout_ms >= IDLE_INTERVAL_MS:
            if self._is_stop:
                self._observer.onServerDown()
                raise OSError('client is down')

            try:
                rr = self._read_queue.get_nowait()
            except queue.Empty:
                sleep(IDLE_INTERVAL_MS * 0.001)
                timeout_ms -= IDLE_INTERVAL_MS
                continue
            if rr == None:
                self._observer.onServerDown()
                raise OSError('io thread stopped')
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
        log.info('send notifications: %s' % method)

    def handleRecv(self):
        while True:
            if self._is_stop:
                raise OSError('client is down')
            try:
                rr = self._read_queue.get_nowait()
            except queue.Empty:
                break
            if rr == None:
                self._observer.onServerDown()
                raise OSError('io thread stopped')
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
        log.info('recv notification: %s' % request['method'])
        self._observer.onNotification(request['method'], request['params'])

    def OnRequest(self, request):
        log.info('recv request: %s' % request['method'])
        self._observer.onRequest(request['method'], request['params'])

    def OnResponse(self, request, response):
        log.debug('recv response from: %s' % request['method'])
        self._observer.onResponse(request, response['result'])
