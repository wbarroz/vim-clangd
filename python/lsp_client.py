# LSP Client
# https://github.com/Microsoft/language-server-protocol/blob/master/protocol.md
from jsonrpc import JsonRPCClient, TimedOutError
from subprocess import check_output, CalledProcessError, Popen
import glog as log
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
MAX_CLIENT_TIMEOUTS = 1000


def StartProcess(name, clangd_log_path=None):
    from os import pipe, devnull
    if not clangd_log_path or not log.logger.isEnabledFor(log.DEBUG):
        clangd_log_path = devnull
    fdClangd = open(clangd_log_path, 'w+')
    fdInRead, fdInWrite = pipe()
    fdOutRead, fdOutWrite = pipe()
    cwd = os.path.dirname(clangd_log_path)
    clangd = Popen(
        name, stdin=fdInRead, stdout=fdOutWrite, stderr=fdClangd, cwd=cwd)
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
        rr = self._SendRequest(Initialize_REQUEST, {
            'processId': os.getpid(),
            'rootUri': 'file://' + os.getcwd(),
            'capabilities': {},
            'trace': 'off'
        })
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
