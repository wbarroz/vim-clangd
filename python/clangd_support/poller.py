""" poller for cross-platform """

from select import select
from clangd_support.python_utils import PY2

class Poller(object):
    def __init__(self, rfds, wfds):
        self._rfds = rfds
        self._wfds = wfds

    def shutdown(self):
        pass

    def poll(self, timeout_ms):
        raise NotImplementedError('not okay')


class Win32Poller(Poller):
    def __init__(self, rfds, wfds):
        if PY2:
            super(Win32Poller, self).__init__(rfds, wfds)
        else:
            super().__init__(rfds, wfds)
        self._rhandles = [ rfd.filehandle() for rfd in rfds ]
        self._whandles = [ rfd.filehandle() for wfd in wfds ]

    def poll(self, timeout_ms):
        rs, ws, _ = select(self._rhandles, self._whandles, [], timeout_ms * 0.001)
        # FIXME convert to fd
        return rs, ws

class PosixPoller(Poller):
    def __init__(self, rfds, wfds):
        if PY2:
            super(PosixPoller, self).__init__(rfds, wfds)
        else:
            super().__init__(rfds, wfds)

    def poll(self, timeout_ms):
        rfds, wfds, _ = select(self._rfds, self._wfds, [], timeout_ms * 0.001)
        return rfds, wfds

