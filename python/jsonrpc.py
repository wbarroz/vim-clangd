# simple jsonrpc client over raw socket
# https://github.com/Microsoft/language-server-protocol/blob/master/protocol.md
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
import json, os
import glog as log
from threading import Thread
from errno import EINTR
from time import sleep
import queue
IDLE_INTERVAL=0.01


def EstimateUnreadBytes(fd):
    from array import array
    from fcntl import ioctl
    from termios import FIONREAD
    buf = array('i', [0])
    ioctl(fd, FIONREAD, buf, 1)
    return buf[0]

def write_utf8(fd, data):
    msg = data.encode('utf-8')
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

    def _SendMsg(self, r):
        request = json.dumps(r, separators=(',',':'), sort_keys=True)
        write_utf8(self._input_fd, u'Content-Length: %d\r\n\r\n' % len(request))
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

    def run(self):
        long_idle = 0
        while not self._is_stop:
            while True:
                try:
                    r = self._write_queue.get_nowait()
                except queue.Empty:
                    break

                if isinstance(r, Exception):
                    self._is_stop = True
                    break

                try:
                    self._SendMsg(r)
                    long_idle = 0
                except OSError as e:
                    self._read_queue.put(e)
                    self._is_stop = True
                    break
            if self._is_stop:
                break
            while EstimateUnreadBytes(self._output_fd) > 0:
                try:
                    rr = self._RecvMsg()
                    long_idle = 0
                except OSError as e:
                    self._read_queue.put(e)
                    self._is_stop = True
                    break
                self._read_queue.put(rr)
            if long_idle < 100:
                long_idle += 1
            sleep(IDLE_INTERVAL * long_idle)
        pass


class JsonRPCClient:
    def __init__(self, request_observer, input_fd, output_fd):
        self._no = 0
        self._requests = {}
        self._observer = request_observer
        self._read_queue = queue.Queue()
        self._write_queue = queue.Queue()
        self._io_thread = JsonRPCClientThread(input_fd, output_fd, self._read_queue, self._write_queue)
        self._io_thread.start()
        self._is_stop = False

    def stop(self):
        if self._is_stop:
            return
        self._read_queue.put(OSError('stop'))
        self._is_stop = True
        self._io_thread.join()

    def sendRequest(self, method, params={}, nullResponse=False):
        Id = self._no
        self._no = self._no + 1
        r = self.SendMsg(method, params, Id=Id)
        if nullResponse:
            return None
        while True:
            if self._is_stop:
                self._observer.onServerDown()
                raise OSError('client is down')

            try:
                rr = self._read_queue.get_nowait()
            except queue.Empty:
                sleep(IDLE_INTERVAL)
                continue
            if isinstance(rr, Exception):
                self._observer.onServerDown()
                raise rr
            rr = self.RecvMsg(rr)
            if 'id' in rr and rr['id'] == Id:
                if 'error' in rr:
                    raise Exception('bad error_code %d' % rr['error'])
                return rr['result']
        return None

    def sendNotification(self, method, params={}):
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
            if isinstance(rr, Exception):
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
