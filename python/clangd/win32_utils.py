# exported win32 api

from ctypes import WINFUNCTYPE, GetLastError, windll, pythonapi, cast, c_buffer
from ctypes import create_string_buffer, c_ushort, c_ubyte, c_char, c_short,\
                   c_int, c_uint, c_ulong, c_long, c_void_p, byref, c_char_p,\
                   Structure, Union, py_object, POINTER, pointer, sizeof,\
                   string_at

from ctypes.wintypes import HANDLE, ULONG, DWORD, BOOL, LPCSTR,\
                            LPCWSTR, UINT

from ctypes import sizeof as c_sizeof
from struct import unpack, pack

import os
import socket
from errno import EINTR

from msvcrt import open_osfhandle

try:
    from ctypes import WinError
except ImportError:
    from ctypes.wintypes import WinError

INVALID_HANDLE_VALUE = HANDLE(~0)
PIPE_NOWAIT = DWORD(0x00000001)
ERROR_NO_DATA = 232

NULL = c_ulong()
GROUP = SOCKET = UINT
LPDWORD = POINTER(DWORD)
PULONG_PTR = POINTER(c_ulong)

SOCKET = UINT
SERVICETYPE = UINT
GROUP = UINT


class _US(Structure):
    _fields_ = [('Offset', DWORD), ('OffsetHigh', DWORD)]


class _U(Union):
    _fields_ = [('s', _US), ('Pointer', c_void_p)]
    _anonymous_ = ('s', )


class OVERLAPPED(Structure):
    _fields_ = [('Internal', POINTER(ULONG)), ('InternalHIgh', POINTER(ULONG)),
                ('u', _U), ('hEvent', HANDLE), ('object', py_object)]
    _anonymous_ = ('u', )


LPOVERLAPPED = POINTER(OVERLAPPED)


def _bool_error_throw(result, func, args):
    if not result:
        raise WinError()
    return result


def _bool_error_check(result, func, args):
    if not result:
        return GetLastError()
    return 0


def _invalid_handle_throw(result, func, args):
    if result == HANDLE(-1):
        raise WinError()
    return result


def _zero_throw(result, func, args):
    if result != 0:
        raise WinError()
    return result


lowCloseHandle = windll.kernel32.CloseHandle
lowCloseHandle.argtype = HANDLE
lowCloseHandle.restype = BOOL
lowCloseHandle.errcheck = _bool_error_throw


def CloseHandle(hObject):
    lowCloseHandle(hObject)


lowWSAGetLastError = windll.ws2_32.WSAGetLastError
lowWSAGetLastError.argtype = []
lowWSAGetLastError.restype = c_int


def WSAGetLastError():
    return lowWSAGetLastError()


lowWSASocket = windll.ws2_32.WSASocketA
lowWSASocket.argtypes = (c_int, c_int, c_int, c_void_p, GROUP, DWORD)
lowWSASocket.restype = SOCKET
lowWSASocket.errcheck = _invalid_handle_throw


def WSASocket(af, socket_type, protocol, lpProtocol=None, g=0, dwFlags=0):
    s = lowWSASocket(af, socket_type, protocol, lpProtocol, g, dwFlags)
    return s


class _UN_b(Structure):
    _fields_ = [
        ('s_b1', c_ubyte),
        ('s_b2', c_ubyte),
        ('s_b3', c_ubyte),
        ('s_b4', c_ubyte),
    ]


class _UN_w(Structure):
    _fields_ = [
        ('s_w1', c_ushort),
        ('s_w2', c_ushort),
    ]


class _UN(Structure):
    _fields_ = [
        ('S_addr', c_ulong),
    ]


class in_addr(Union):
    _fields_ = [
        ('S_un', _UN),
        ('S_un_b', _UN_b),
        ('S_un_w', _UN_w),
    ]
    _anonymous_ = ('S_un', )


class sockaddr_in(Structure):
    _fields_ = [
        ('sin_family', c_short),
        ('sin_port', c_ushort),
        ('sin_addr', in_addr),
        ('sz_pads', c_char * 8),
    ]


class WSABUF(Structure):
    _fields_ = [('len', ULONG), ('buf', c_char_p)]


LPWSABUF = POINTER(WSABUF)


class FLOWSPEC(Structure):
    _fields_ = [
        ('TokenRate', ULONG),
        ('TokenBucketSize', ULONG),
        ('PeakBandwidth', ULONG),
        ('Latency', ULONG),
        ('DelayVariation', ULONG),
        ('ServiceType', SERVICETYPE),
        ('MaxSduSize', ULONG),
        ('MinimumPolicedSize', ULONG),
    ]


LPQOS = POINTER(FLOWSPEC)

lowWSAConnect = windll.ws2_32.WSAConnect
lowWSAConnect.argtypes = (SOCKET, POINTER(sockaddr_in), c_int, LPWSABUF,
                          LPWSABUF, LPQOS, LPQOS)
lowWSAConnect.restype = c_int
lowWSAConnect.errcheck = _zero_throw


def WSAConnect(s, addr):
    sa_addr = sockaddr_in()
    host, port = addr
    sa_addr.sin_family = socket.AF_INET
    sa_addr.sin_port = socket.htons(port)
    sa_addr.sin_addr.S_addr = unpack('<i', socket.inet_aton(host))[0]

    lowWSAConnect(s, byref(sa_addr), c_sizeof(sa_addr), None, None, None, None)


lowWSAAccept = windll.ws2_32.WSAAccept
lowWSAAccept.argtypes = (SOCKET, POINTER(sockaddr_in), POINTER(c_int),
                         c_void_p, POINTER(DWORD))
lowWSAAccept.restype = SOCKET
lowWSAAccept.errcheck = _invalid_handle_throw


def WSAAccept(s):
    sa_addr = sockaddr_in()
    sa_addr_len = c_int(c_sizeof(sa_addr))
    rc = lowWSAAccept(s, byref(sa_addr), byref(sa_addr_len), None, None)

    port = socket.ntohs(sa_addr.sin_port)
    host = socket.inet_ntoa(pack('<i', sa_addr.sin_addr.S_addr))
    addr = (host, port)
    return (rc, addr)


low_bind = windll.ws2_32.bind
low_bind.argtypes = (SOCKET, POINTER(sockaddr_in), c_int)
low_bind.restype = c_int
low_bind.errcheck = _zero_throw


def _bind(s, addr):
    sa_addr = sockaddr_in()
    host, port = addr
    sa_addr.sin_family = socket.AF_INET
    sa_addr.sin_port = socket.htons(port)
    sa_addr.sin_addr.S_addr = unpack('<i', socket.inet_aton(host))[0]

    low_bind(s, byref(sa_addr), c_sizeof(sa_addr))


low_listen = windll.ws2_32.listen
low_listen.argtypes = (SOCKET, c_int)
low_listen.restype = c_int
low_listen.errcheck = _zero_throw


def _listen(s, backlog):
    low_listen(s, backlog)


low_getsockname = windll.ws2_32.getsockname
low_getsockname.argtypes = (SOCKET, POINTER(sockaddr_in), POINTER(c_int))
low_getsockname.restype = c_int
low_getsockname.errcheck = _zero_throw


def _getsockname(s):
    sa_addr = sockaddr_in()
    sa_addr_len = c_int(c_sizeof(sa_addr))
    low_getsockname(s, byref(sa_addr), byref(sa_addr_len))

    port = socket.ntohs(sa_addr.sin_port)
    host = socket.inet_ntoa(pack('<i', sa_addr.sin_addr.S_addr))
    addr = (host, port)
    return addr


# from windows sdk
FIONREAD = 0x4004667f
FIONBIO = 0x8004667e

low_ioctlsocket = windll.ws2_32.ioctlsocket
low_ioctlsocket.argtypes = (SOCKET, c_long, POINTER(c_ulong))
low_ioctlsocket.restype = c_int
low_ioctlsocket.errcheck = _zero_throw


def _ioctlsocket(s, cmd, arg=0):
    ul_arg = c_ulong(arg)
    low_ioctlsocket(s, cmd, byref(ul_arg))
    return unpack('<L', ul_arg)[0]


class WinSocket(object):
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def __init__(self, handle=None):
        if not handle:
            handle = WSASocket(socket.AF_INET, socket.SOCK_STREAM,
                               socket.IPPROTO_TCP)
        self._file_handle = handle
        self._file_no = open_osfhandle(self._file_handle, 0)

    def close(self):
        CloseHandle(self._file_handle)

    def fileno(self):
        return self._file_no

    def filehandle(self):
        return self._file_handle

    def bind(self, addr):
        _bind(self._file_handle, addr)

    def listen(self, backlog):
        _listen(self._file_handle, backlog)

    def accept(self):
        s, addr = WSAAccept(self._file_handle)
        return WinSocket(s), addr

    def connect(self, addr):
        WSAConnect(self._file_handle, addr)

    def getsockname(self):
        return _getsockname(self._file_handle)


# tcp-emulated socketpair, might fail
def Win32SocketPair():
    localhost = '127.0.0.1'
    with WinSocket() as listener:
        listener.bind((localhost, 0))
        listener.listen(1)
        addr = listener.getsockname()
        client = WinSocket()
        client.connect(addr)
        server, server_addr = listener.accept()
        client_addr = client.getsockname()
        if server_addr != client_addr:
            client.close()
            server.close()
            raise OSError('win32 socketpair failure')
    return server, client


def SetNonBlock(winsocket, enabled=True):
    int_enabled = int(enabled)
    _ioctlsocket(winsocket.filehandle(), FIONBIO, int_enabled)


def EstimateUnreadBytes(winsocket):
    return int(_ioctlsocket(winsocket.filehandle(), FIONREAD))


def WriteUtf8(winsocket, data):
    msg = data.encode('utf-8')
    fd = winsocket.fileno()
    while len(msg):
        try:
            written = os.write(fd, msg)
            if written == 0:
                raise OSError('broken pipe')
            msg = msg[written:]
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg


def ReadUtf8(winsocket, length):
    msg = bytes()
    fd = winsocket.fileno()
    while length:
        try:
            buf = os.read(fd, length)
            if len(buf) == 0:
                raise OSError('broken pipe')
            length -= len(buf)
            msg += buf
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg.decode('utf-8')
