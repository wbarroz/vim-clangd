from array import array
import fcntl
from fcntl import ioctl
from sys import platform as sys_platform
from errno import EINTR
from clangd.vimsupport import PY2
try:
    from termios import FIONREAD
except ImportError:
    # happens in cygwin or not defined
    if sys_platform == 'msys':
        """ _IOR('f', 127, u_long) """
        if PY2:
            FIONREAD = long(0x4008667f)
        else:
            FIONREAD = 0x4008667f
    else:
        raise
from os import pipe, read, write


def EstimateUnreadBytes(fd):
    buf = array('i', [0])
    ioctl(fd, FIONREAD, buf, 1)
    return buf[0]


def SetCloseOnExec(fd):
    fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.FD_CLOEXEC)


def Pipe():
    return pipe()


def WriteUtf8(fd, data):
    msg = data.encode('utf-8')
    while len(msg):
        try:
            written = write(fd, msg)
            if written == 0:
                raise OSError('broken pipe')
            msg = msg[written:]
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg


def ReadUtf8(fd, length):
    msg = bytes()
    while length:
        try:
            buf = read(fd, length)
            if len(buf) == 0:
                raise OSError('broken pipe')
            length -= len(buf)
            msg += buf
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg.decode('utf-8')
