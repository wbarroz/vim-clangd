from time import time
from clangd import glog as log
from clangd.vimsupport import GetBoolValue, PY_VERSION, PY2, EchoText, CurrentFileTypes


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


class EventDispatcher(object):
    def __init__(self, manager):
        log.info('using python %d' % PY_VERSION)
        self.manager = manager
        self._timer = None

    def _LazyInit(self):
        native_timer = GetBoolValue('has("s:timer")')
        if native_timer:
            log.info('vim native timer found and used')
            # FIXME use abstract timer
        else:
            self._timer = EmulateTimer(self)

    def OnVimEnter(self):
        autostart = GetBoolValue('g:clangd#autostart')
        if autostart and not self.manager.isAlive():
            EchoText('vim-clanged is not running')
            return

        self._LazyInit()

        if self._timer:
            self._timer.start()

        log.warn('vim-clangd plugin fully loaded')

    def OnVimLeave(self):
        log.debug('VimLeave')
        self.manager.in_shutdown = True
        if self._timer:
            self._timer.stop()
        try:
            # BufUnload won't be called at exit, you need to call it yourself
            self.manager.CloseAllFiles()
            log.warn('vim-clangd closed all files')
        except TimedOutError:
            # safe to ignore
            log.exception("close all files refused")

        try:
            self.manager.stopServer(confirmed=True)
        except OSError:
            log.exception("clangd refused to shutdown")
        log.warn('vim-clangd plugin fully unloaded')

    def OnBufferReadPost(self, file_name):
        if self._timer:
            self._timer.poll()
        log.info('BufferReadPost %s' % file_name)

    def OnFileType(self):
        log.info('Current FileType Changed To %s' %
                 CurrentFileTypes()[0])
        if self._timer:
            self._timer.poll()
        self.manager.CloseCurrentFile()
        self.manager.OpenCurrentFile()
        self.manager.GetDiagnosticsForCurrentFile()

    def OnBufferWritePost(self, file_name):
        # FIXME should we use buffer_number?
        if self._timer:
            self._timer.poll()
        self.manager.SaveFile(file_name)
        log.info('BufferWritePost %s' % file_name)

    def OnBufferUnload(self, file_name):
        if self._timer:
            self._timer.poll()
        log.info('BufferUnload %s' % file_name)
        self.manager.CloseFile(file_name)

    def OnBufferDelete(self, file_name):
        if self._timer:
            self._timer.poll()
        log.info('BufferDelete %s' % file_name)
        self.manager.CloseFile(file_name)

    def OnCursorMove(self):
        if self._timer:
            self._timer.poll()

    def OnCursorHold(self):
        if self._timer:
            self._timer.poll()

    def OnInsertEnter(self):
        if self._timer:
            self._timer.poll()
        log.debug('InsertEnter')

    def OnInsertLeave(self):
        if self._timer:
            self._timer.poll()
        log.debug('InsertLeave')

    def OnTextChanged(self):
        if self._timer:
            self._timer.poll()
        # After a change was made to the text in the current buffer in Normal mode.
        log.debug('TextChanged')
        self.manager.UpdateCurrentBuffer()

    def OnTimerCallback(self):
        log.debug('OnTimer')
        self.manager.HandleClientRequests()
        if self.manager.FilterCurrentFile():
            return
        self.manager.GetDiagnosticsForCurrentFile()
        self.manager.EchoErrorMessageForCurrentLine()

    def OnRequestDownloadBinary(self, script_path):
        from clangd.binary_downloader import BinaryDownloader
        self.manager.stopServer(confirmed=True, in_shutdown=True)

        downloader = BinaryDownloader()
        downloader.downloadBinary(script_path)

        self.manager._in_shutdown = False
        self.manager.startServer(confirmed=True)
