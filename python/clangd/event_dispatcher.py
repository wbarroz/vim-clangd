from time import time
from clangd import glog as log
from clangd.vimsupport import GetBoolValue, EchoText, CurrentFileTypes
from clangd.clangd_manager import FilterFileName, FilterCurrentFile, ClangdManager
from clangd_support.python_utils import PY_VERSION, PY2


class EmulateTimer(object):
    def __init__(self, observer, interval=5):
        self._interval = interval
        self._observer = observer

    def start(self):
        self._last_timestamp = time()

    def stop(self):
        self._last_timestamp = None

    def poll(self):
        if not self._last_timestamp:
            return
        now = time()
        if now - self._last_timestamp >= self._interval:
            self._last_timestamp = now
            self._observer.OnTimerCallback()

def check_loaded(f):
    def wrapper(self, *args):
        if not self._loaded:
            return
        assert self._manager
        return f(self, *args)
    return wrapper

def filter_current_file(f):
    def wrapper(self, *args):
        if FilterCurrentFile():
            return
        return f(self, *args)
    return wrapper

def check_timer(f):
    def wrapper(self, *args):
        if self._timer:
            self._timer.poll()
        return f(self, *args)
    return wrapper

class EventDispatcher(object):
    def __init__(self):
        log.debug('using python %d' % PY_VERSION)
        self._timer = None
        self._loaded = False

    def _InitTimer(self):
        native_timer = GetBoolValue('has("s:timer")')
        if native_timer:
            log.debug('vim native timer support found and used')
            # FIXME use abstract timer
        else:
            self._timer = EmulateTimer(self)

    def OnVimEnter(self):
        log.debug('VimEnter')
        autostart = GetBoolValue('g:clangd#autostart')
        if autostart:
            self.StartServer()
            return

    def OnVimLeave(self):
        log.debug('VimLeave')
        self.StopServer()

    @check_loaded
    @filter_current_file
    @check_timer
    def OnBufferReadPost(self, file_name):
        log.debug('BufferReadPost %s' % file_name)

    @check_loaded
    @check_timer
    def OnFileType(self):
        log.debug('Current FileType Changed To %s' % CurrentFileTypes()[0])
        self._manager.CloseCurrentFile()
        self._manager.OpenCurrentFile()
        self._manager.GetDiagnosticsForCurrentFile()

    @check_loaded
    @check_timer
    def OnBufferWritePost(self, file_name):
        # FIXME should we use buffer_number?
        self._manager.SaveFile(file_name)
        log.debug('BufferWritePost %s' % file_name)

    @check_loaded
    @check_timer
    def OnBufferUnload(self, file_name):
        log.debug('BufferUnload %s' % file_name)
        self._manager.CloseFile(file_name)

    @check_loaded
    @check_timer
    def OnBufferDelete(self, file_name):
        log.debug('BufferDelete %s' % file_name)
        self._manager.CloseFile(file_name)

    @check_loaded
    @check_timer
    def OnCursorMove(self):
        self._manager.EchoErrorMessageForCurrentLine()

    @check_loaded
    @check_timer
    def OnCursorHold(self):
        self._manager.EchoErrorMessageForCurrentLine()

    @check_loaded
    @check_timer
    def OnInsertEnter(self):
        log.debug('InsertEnter')

    @check_loaded
    @check_timer
    def OnInsertLeave(self):
        log.debug('InsertLeave')

    @check_loaded
    @check_timer
    def OnTextChanged(self):
        # After a change was made to the text in the current buffer in Normal mode.
        log.debug('TextChanged')
        self._manager.UpdateCurrentBuffer()

    @check_loaded
    def OnTimerCallback(self):
        log.debug('OnTimer')
        self._manager.HandleClientRequests()
        if FilterCurrentFile():
            return
        self._manager.GetDiagnosticsForCurrentFile()
        self._manager.EchoErrorMessageForCurrentLine()

    @check_loaded
    @filter_current_file
    def ErrorStatusForCurrentLine(self):
        self._manager.ErrorStatusForCurrentLine()

    @check_loaded
    @filter_current_file
    def GetDiagnosticsForCurrentFile(self):
        return self._manager.GetDiagnosticsForCurrentFile()

    @check_loaded
    @filter_current_file
    def ForceCompile(self):
        self._manager.ReparseCurrentFile()
        self._manager.GetDiagnosticsForCurrentFile()
        self._manager.EchoErrorMessageForCurrentLine()

    @check_loaded
    @filter_current_file
    def CodeCompleteAtCurrent(self):
        log.info('CodeCompleteAtCurrent')
        ret = self._manager.CodeCompleteAtCurrent()
        if ret < 0:
            return
        return ret

    @check_loaded
    @filter_current_file
    def GetCompletions(self):
        log.info('GetCompletions')
        return self._manager.GetCompletions()

    @check_loaded
    @filter_current_file
    def GotoDefinition(self):
        self._manager.GotoDefinition()

    @check_loaded
    @filter_current_file
    def EchoDetailedErrorMessage(self):
        self._manager.EchoDetailedErrorMessage()

    @check_loaded
    @filter_current_file
    def ShowCursorDetail(self):
        self._manager.ShowCursorDetail()

    def StartServer(self):
        if self._loaded:
            return
        self._manager = ClangdManager()
        self._InitTimer()
        if self._timer:
            self._timer.start()
        try:
            self._manager.startServer(confirmed=True)
        except:
            log.exception('failed to start backend')
            return
        log.warn('vim-clangd backend fully loaded')
        self._loaded = True

    @check_loaded
    def StopServer(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._manager.in_shutdown = True
        try:
            # BufUnload won't be called at exit, you need to call it yourself
            self._manager.CloseAllFiles()
            log.warn('vim-clangd closed all files')
        except TimedOutError:
            # safe to ignore
            log.exception("close all files timeout")

        try:
            self._manager.stopServer(confirmed=True, in_shutdown=True)
        except OSError:
            log.exception("clangd refused to shutdown")
        log.warn('vim-clangd backend fully unloaded')
        self._loaded = False
        self._manager = None

    @check_loaded
    def RestartServer(self):
        self.StopServer()
        self.StartServer()

    @check_loaded
    def Format(self):
        self._manager.Format()

    def OnRequestDownloadBinary(self, script_path):
        from clangd.binary_downloader import BinaryDownloader
        self.StopServer()

        downloader = BinaryDownloader()
        downloader.downloadBinary(script_path)

        self.StartServer()
