# LSP Client
# https://github.com/Microsoft/language-server-protocol/blob/master/protocol.md
from clangd.jsonrpc import JsonRPCClient, TimedOutError
from subprocess import check_output, CalledProcessError, Popen
import clangd.glog as log
import os

Initialize_REQUEST = 'initialize'
Shutdown_REQUEST = 'shutdown'
Exit_NOTIFICATION = 'exit'

Completion_REQUEST = 'textDocument/completion'
Formatting_REQUEST = 'textDocument/formatting'
RangeFormatting_REQUEST = 'textDocument/rangeFormatting'
OnTypeFormatting_REQUEST = 'textDocument/onTypeFormatting'

Initialized_NOTIFICATION = 'initialized'
DidOpenTextDocument_NOTIFICATION = 'textDocument/didOpen'
DidChangeTextDocument_NOTIFICATION = 'textDocument/didChange'
DidSaveTextDocument_NOTIFICATION = 'textDocument/didSave'
DidCloseTextDocument_NOTIFICATION = 'textDocument/didClose'

PublishDiagnostics_NOTIFICATION = 'textDocument/publishDiagnostics'

MAX_CLIENT_ERRORS = 100
MAX_CLIENT_TIMEOUTS = 5000

class WinSocket(object):
    def __init__(self, handle = None):
        import socket
        from clangd.iocp import WSASocket
        from msvcrt import open_osfhandle
        if not handle:
            handle = WSASocket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self._file_handle = handle
        self._file_no = open_osfhandle(self._file_handle, 0)

    def close(self):
        from clangd.iocp import CloseHandle
        CloseHandle(self._file_handle)

    def fileno(self):
        return self._file_no

    def filehandle(self):
        return self._file_handle

    def bind(self, addr):
        from clangd.iocp import _bind
        _bind(self._file_handle, addr)

    def listen(self, backlog):
        from clangd.iocp import _listen
        _listen(self._file_handle, backlog)

    def accept(self):
        from clangd.iocp import WSAAccept
        s, addr = WSAAccept(self._file_handle)
        return WinSocket(s), addr

    def connect(self, addr):
        from clangd.iocp import WSAConnect
        WSAConnect(self._file_handle, addr)

    def getsockname(self):
        from clangd.iocp import _getsockname
        return _getsockname(self._file_handle)

# tcp-emulated socketpair
def win32_socketpair():
    localhost = '127.0.0.1'
    listener = WinSocket()
    listener.bind((localhost, 0))
    listener.listen(1)
    addr = listener.getsockname()
    client = WinSocket()
    client.connect(addr)
    server, server_addr = listener.accept()
    client_addr = client.getsockname()
    if server_addr != client_addr:
        raise OSError('win32 socketpair failure')
    listener.close()
    return server, client

def StartProcess(executable_name, clangd_log_path=None):
    if not clangd_log_path or not log.logger.isEnabledFor(log.DEBUG):
        clangd_log_path = os.devnull
    fdClangd = open(clangd_log_path, 'w+')

    # fix executable file name under windows (both cygwin and native win32)
    if os.name == 'nt' and not executable_name.endswith('.exe'):
        executable_name += '.exe'

    # apply platform-specific hacks
    if sys.platform == 'win32':
        # for posix or cygwin
        from os import pipe
        import fcntl
        fdInRead, fdInWrite = pipe()
        fdOutRead, fdOutWrite = pipe()
        fcntl.fcntl(fdInWrite, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
        fcntl.fcntl(fdOutRead, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
    else:
        # only native win32
        fdInRead, fdInWrite = win32_socketpair()
        fdOutRead, fdOutWrite = win32_socketpair()
    cwd = os.path.dirname(executable_name)
    # apply native win32's hack
    if sys.platform == 'win32':
        # we need hide this subprocess's window under windows, or it opens a new visible window
        import subprocess
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags = subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        clangd = Popen(
            executable_name,
            stdin=fdInRead,
            stdout=fdOutWrite,
            stderr=fdClangd,
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            startupinfo=startupinfo)
    else:
        clangd = Popen(
            executable_name,
            stdin=fdInRead,
            stdout=fdOutWrite,
            stderr=fdClangd,
            cwd=cwd)

    return clangd, fdInWrite, fdOutRead, fdClangd


class LSPClient():
    def __init__(self, clangd_executable, clangd_log_path, manager):
        clangd, fdRead, fdWrite, fdClangd = StartProcess(
            clangd_executable, clangd_log_path)
        log.info('clangd started, pid %d' % clangd.pid)
        self._clangd = clangd
        self._input_fd = fdRead
        self._output_fd = fdWrite
        self._clangd_logfd = fdClangd
        self._rpcclient = JsonRPCClient(self, fdRead, fdWrite)
        self._client_errs = 0
        self._client_timeouts = 0
        self._is_alive = True
        self._manager = manager

    def CleanUp(self):
        if self._clangd.poll() == None:
            self._clangd.terminate()
        if self._clangd.poll() == None:
            self._clangd.kill()
        log.info('clangd stopped, pid %d' % self._clangd.pid)
        self._clangd_logfd.close()
        if sys.platform == 'win32':
            # only native win32
            self._input_fd.close()
            self._output_fd.close()
        else:
            # posix or cygwin
            os.close(self._input_fd)
            os.close(self._output_fd)

    def isAlive(self):
        return self._is_alive and self._clangd.poll(
        ) == None and self._client_errs < MAX_CLIENT_ERRORS and self._client_timeouts < MAX_CLIENT_TIMEOUTS

    def onNotification(self, method, params):
        if method == PublishDiagnostics_NOTIFICATION:
            self.onDiagnostics(params['uri'], params['diagnostics'])
        pass

    def onRequest(self, method, params):
        pass

    def onResponse(self, request, response):
        if request['method'] == Completion_REQUEST:
            params = request['params']
            self.onCodeCompletions(params['textDocument']['uri'],
                                   params['position']['line'],
                                   params['position']['character'], response)
        pass

    def onServerDown(self):
        if self._is_alive:
            log.warn('rpcclient is down with errors %d, timeouts %d' %
                     (self._client_errs, self._client_timeouts))
            self._is_alive = False
            self._manager.on_server_down()

    def initialize(self):
        try:
            rr = self._SendRequest(Initialize_REQUEST, {
                'processId': os.getpid(),
                'rootUri': 'file://' + os.getcwd(),
                'capabilities': {},
                'trace': 'off'
            }, timeout_ms = 5000)
        except TimedOutError as e:
            log.exception('initialize timedout')
            # ignore timedout
            rr = {'capabilities': ''}
            pass
        log.info('clangd connected with piped fd')
        log.info('clangd capabilities: %s' % rr['capabilities'])
        self._manager.on_server_connected()
        return rr

    def onInitialized(self):
        return self._SendNotification(Initialized_NOTIFICATION)

    def shutdown(self):
        try:
            return self._SendRequest(Shutdown_REQUEST, nullResponse=True)
        except OSError:
            log.exception('failed to send shutdown request')

    def exit(self):
        try:
            self._SendNotification(Exit_NOTIFICATION)
        except OSError:
            log.exception('failed to send exception request')
        self._rpcclient.stop()
        self._is_alive = False

    def handleClientRequests(self):
        if not self.isAlive():
            self.onServerDown()
            return
        self._rpcclient.handleRecv()

    def _SendNotification(self, method, params={}):
        try:
            return self._rpcclient.sendNotification(method, params)
        except OSError as e:
            if isinstance(e, TimedOutError):
                self._client_timeouts += 1
            else:
                self._client_errs += 1
                log.exception("send notification %s with params %s" % (method,
                                                                       params))
            raise

    def _SendRequest(self,
                     method,
                     params={},
                     nullResponse=False,
                     timeout_ms=None):
        try:
            return self._rpcclient.sendRequest(method, params, nullResponse,
                                               timeout_ms)
        except OSError as e:
            if isinstance(e, TimedOutError):
                self._client_timeouts += 1
            else:
                self._client_errs += 1
                log.exception("send request %s with params %s" % (method,
                                                                  params))
            raise

    # notifications
    def didOpenTestDocument(self, uri, text, file_type):
        return self._SendNotification(DidOpenTextDocument_NOTIFICATION, {
            'textDocument': {
                'uri': uri,
                'languageId': file_type,
                'version': 1,
                'text': text
            }
        })

    def didChangeTestDocument(self, uri, version, content):
        return self._SendNotification(DidChangeTextDocument_NOTIFICATION, {
            'textDocument': {
                'uri': uri,
                'version': version
            },
            'contentChanges': [{
                'text': content
            }]
        })

    def didCloseTestDocument(self, uri):
        return self._SendNotification(DidCloseTextDocument_NOTIFICATION,
                                      {'textDocument': {
                                          'uri': uri
                                      }})

    def didSaveTestDocument(self, uri):
        return self._SendNotification(DidSaveTextDocument_NOTIFICATION,
                                      {'textDocument': {
                                          'uri': uri
                                      }})

    def onDiagnostics(self, uri, diagnostics):
        self._manager.onDiagnostics(uri, diagnostics)

    def onCodeCompletions(self, uri, line, column, completions):
        self._manager.onCodeCompletions(uri, line, column, completions)

    def codeCompleteAt(self, uri, line, character, timeout_ms):
        return self._SendRequest(
            Completion_REQUEST, {
                'textDocument': {
                    'uri': uri,
                },
                'position': {
                    'line': line,
                    'character': character
                }
            },
            timeout_ms=timeout_ms)

    def format(self, uri):
        return self._SendRequest(Formatting_REQUEST,
                                 {'textDocument': {
                                     'uri': uri,
                                 }})

    def rangeFormat(self, uri, start_line, start_character, end_line,
                    end_character):
        return self._SendRequest(RangeFormatting_REQUEST, {
            'textDocument': {
                'uri': uri,
            },
            'range': {
                'start': {
                    'line': start_line,
                    'character': start_character,
                },
                'end': {
                    'line': end_line,
                    'character': end_character,
                },
            }
        })

    def onTypeFormat(self, uri, line, character, ch=None):
        # clangd don't use ch yet
        return self._SendRequest(OnTypeFormatting_REQUEST, {
            'textDocument': {
                'uri': uri,
            },
            'position': {
                'line': line,
                'character': character
            }
        })
