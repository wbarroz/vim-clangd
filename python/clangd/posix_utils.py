from array import array
import fcntl
from fcntl import ioctl
from termios import FIONREAD
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
            length -= len(buf)
            msg += buf
        except OSError as e:
            if e.errno != EINTR:
                raise
    return msg.decode('utf-8')