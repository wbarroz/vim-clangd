#!/usr/bin/env python

import vimsupport, vim
from lsp_client import LSPClient, TimedOutError
from trie import Trie

import glog as log
import os
from os.path import dirname, abspath, join, isfile
from subprocess import check_output, CalledProcessError, Popen


def GetUriFromFilePath(file_path):
    return 'file://%s' % file_path


def GetFilePathFromUri(uri):
    return uri[7:]


# m,f,c,v,t
# ordered
def GetCompletionItemKinds():
    return ['m', 'f', 'c', 'v', 't', 'k']


def CompletionItemKind(kind):
    ##export const Text = 1;
    if kind == 1:
        return 'm'
##export const Method = 2;
    elif kind == 2:
        return 'f'
##export const Function = 3;
    elif kind == 3:
        return 'f'
##export const Constructor = 4;
    elif kind == 4:
        return 'f'
##export const Field = 5;
    elif kind == 5:
        return 'v'
##export const Variable = 6;
    elif kind == 6:
        return 'v'
##export const Class = 7;
    elif kind == 7:
        return 'c'
##export const Interface = 8;
    elif kind == 8:
        return 'c'
##export const Module = 9;
    elif kind == 9:
        return 'm'
##export const Property = 10;
    elif kind == 10:
        return 'v'
##export const Unit = 11;
    elif kind == 11:
        return 't'
##export const Value = 12;
    elif kind == 12:
        return 'v'
##export const Enum = 13;
    elif kind == 13:
        return 'c'
##export const Keyword = 14;
    elif kind == 14:
        return 'k'
##export const Snippet = 15;
    elif kind == 15:
        return 'k'
##export const Color = 16;
    elif kind == 16:
        return 'k'
##export const File = 17;
    elif kind == 17:
        return 'k'

##export const Reference = 18;
    elif kind == 18:
        return 't'
    return ''


class ClangdManager():
    def __init__(self):
        self.lined_diagnostics = {}
        self.state = {}
        self._client = None
        self._in_shutdown = False
        self._documents = {}
        autostart = bool(vim.eval('g:clangd#autostart'))
        if autostart:
            self.startServer(confirmed=True)
        self._ClearLastCompletions()

    def _ClearLastCompletions(self):
        self._last_completions = self._GetEmptyCompletions()
        self._last_completions_pos = (-1, -1)

    def _GetEmptyCompletions(self):
        completions_tries = {}
        for kind in GetCompletionItemKinds():
            completions_tries[kind] = Trie()
        return completions_tries

    def isAlive(self):
        return self._client and self._client.isAlive()

    def startServer(self, confirmed=False):
        if self._client:
            vimsupport.EchoMessage(
                'clangd is connected, please stop it first!')
            return
        if confirmed or vimsupport.PresentYesOrNoDialog(
                'Should we start clangd?'):
            clangd_executable = str(vim.eval('g:clangd#clangd_executable'))
            clangd_executable = os.path.expanduser(clangd_executable)
            clangd_log_path = os.path.expanduser(
                vim.eval('g:clangd#log_path') + '/clangd.log')
            try:
                self._client = LSPClient(clangd_executable, clangd_log_path,
                                         self)
            except:
                log.exception('failed to start clangd')
                vimsupport.EchoMessage('failed to start clangd executable')
                return
            self._client.initialize()

    def stopServer(self, confirmed=False):
        if confirmed or vimsupport.PresentYesOrNoDialog(
                'Should we stop clangd?'):
            try:
                if self._client:
                    client = self._client
                    self._client = None
                    client.shutdown()
                    client.exit()
            except:
                log.exception('failed to stop clangd')
                return

    def restartServer(self):
        log.info('restart clangd')
        self.stopServer(confirmed=True)
        self.startServer(confirmed=True)

    def on_server_connected(self):
        log.info('clangd up')
        self._client.onInitialized()
        # wipe all exist documents
        self._documents = {}

    def on_server_down(self):
        log.warn('clangd down unexceptedly')

        self.lined_diagnostics = {}
        vimsupport.ClearClangdSyntaxMatches()
        vimsupport.UnplaceAllSigns()

        if not self._in_shutdown:
            self.stopServer(confirmed=True)
            if bool(vim.eval('g:clangd#restart_after_crash')):
                self.startServer(confirmed=True)

    def on_bad_message_received(self, wc, message):
        log.info('observer: bad message')

    def FilterFileName(self, file_name):
        log.info('filter file %s' % file_name)
        for buf in vim.buffers:
            if buf.name == file_name:
                if buf.options['filetype'] in ['c', 'cpp', 'objc', 'objcpp']:
                    return False
                return True
        return True

    def FilterCurrentFile(self):
        file_types = vimsupport.CurrentFileTypes()
        if not file_types:
            return True
        for file_type in file_types:
            if file_type in ['c', 'cpp', 'objc', 'objcpp']:
                return False
        return True

    def OpenFile(self, file_name):
        if not self.isAlive():
            return True

        uri = GetUriFromFilePath(file_name)
        try:
            buf = vimsupport.GetBufferByName(file_name)
            self.didOpenFile(buf)
        except:
            log.exception('failed to open %s' % file_name)
            vimsupport.EchoTruncatedText('unable to open %s' % file_name)
            return False

        return True

    def OpenCurrentFile(self):
        file_name = vimsupport.CurrentBufferFileName()
        if not file_name:
            return False
        if not self.OpenFile(file_name):
            return False
        return True

    def SaveFile(self, file_name):
        if not self.isAlive():
            return True

        uri = GetUriFromFilePath(file_name)
        try:
            self._client.didSaveTestDocument(uri)
        except:
            log.exception('unable to save %s' % file_name)
            return False
        log.info('file %s saved' % file_name)
        return True

    def SaveCurrentFile(self):
        file_name = vimsupport.CurrentBufferFileName()
        if not file_name:
            return True
        return self.SaveFile(file_name)

    def CloseFile(self, file_name):
        if not self.isAlive():
            return True

        uri = GetUriFromFilePath(file_name)
        if not uri in self._documents:
            return
        version = self._documents.pop(uri)['version']
        try:
            self._client.didCloseTestDocument(uri)
        except:
            log.exception('failed to close file %s' % file_name)
            return False
        log.info('file %s closed' % file_name)
        return True

    def CloseCurrentFile(self):
        file_name = vimsupport.CurrentBufferFileName()
        if not file_name:
            return True
        return self.CloseFile(file_name)

    def onDiagnostics(self, uri, diagnostics):
        if uri not in self._documents:
            return
        log.info('diagnostics for %s is updated' % uri)
        self._documents[uri]['diagnostics'] = diagnostics

    def HandleClientRequests(self):
        if self._client:
            self._client.handleClientRequests()

    def GetDiagnostics(self, buf):
        if not self.isAlive():
            return []

        file_name = buf.name
        uri = GetUriFromFilePath(file_name)
        needReopen = False
        if not self.OpenFile(file_name):
            return []
        try:
            self._client.handleClientRequests()
        except:
            log.exception('failed to get diagnostics %s' % file_name)
            return []
        if not uri in self._documents or not 'diagnostics' in self._documents[uri]:
            return []
        response = self._documents[uri]['diagnostics']
        return vimsupport.ConvertDiagnosticsToQfList(file_name, response)

    def GetDiagnosticsForCurrentFile(self):
        if not self.isAlive():
            return []

        lined_diagnostics = {}
        diagnostics = self.GetDiagnostics(vimsupport.CurrentBuffer())
        for diagnostic in diagnostics:
            if not diagnostic['lnum'] in lined_diagnostics:
                lined_diagnostics[diagnostic['lnum']] = []
            lined_diagnostics[diagnostic['lnum']].append(diagnostic)

        # if we hit the cache, simple ignore
        if lined_diagnostics == self.lined_diagnostics:
            return diagnostics
        # clean up current diagnostics
        self.lined_diagnostics = lined_diagnostics
        vimsupport.ClearClangdSyntaxMatches()
        vimsupport.UnplaceAllSigns()

        for diagnostic in diagnostics:
            vimsupport.AddDiagnosticSyntaxMatch(
                diagnostic['lnum'],
                diagnostic['col'],
                is_error=diagnostic['severity'] >= 3)

        vimsupport.PlaceSignForErrorMessageArray(self.lined_diagnostics)
        return diagnostics

    def NearestDiagnostic(self, line, column):
        if len(self.lined_diagnostics[line]) == 1:
            return self.lined_diagnostics[line][0]

        sorted_diagnostics = sorted(
            self.lined_diagnostics[line],
            key=lambda diagnostic: abs(diagnostic['col'] - column))
        return sorted_diagnostics[0]

    def ErrorStatusForCurrentLine(self):
        if not self.isAlive():
            return ''
        current_line, current_column = vimsupport.CurrentLineAndColumn()
        if not current_line in self.lined_diagnostics:
            return ''
        diagnostic = self.NearestDiagnostic(current_line, current_column)
        serverity_strings = [
            'ignored',
            'note',
            'warning',
            'error',
            'fatal',
        ]
        return serverity_strings[int(diagnostic['severity'])]

    def EchoErrorMessageForCurrentLine(self):
        vimsupport.EchoText('')
        if not self.isAlive():
            return
        current_line, current_column = vimsupport.CurrentLineAndColumn()
        if not current_line in self.lined_diagnostics:
            return ''
        diagnostic = self.NearestDiagnostic(current_line, current_column)
        vimsupport.EchoTruncatedText(diagnostic['text'])

    def EchoDetailedErrorMessage(self):
        if not self.isAlive():
            return
        current_line, _ = vimsupport.CurrentLineAndColumn()
        if not current_line in self.lined_diagnostics:
            return
        full_text = ''
        for diagnostic in self.lined_diagnostics[current_line]:
            full_text += 'L%d:C%d %s\n' % (diagnostic['lnum'],
                                           diagnostic['col'],
                                           diagnostic['text'])
        vimsupport.EchoText(full_text[:-1])

    def didOpenFile(self, buf):
        file_name = buf.name
        uri = GetUriFromFilePath(buf.name)
        if uri in self._documents:
            return
        file_type = buf.options['filetype'].decode('utf-8')
        text = vimsupport.ExtractUTF8Text(buf)
        self._documents[uri] = {}
        self._documents[uri]['version'] = 1
        self._client.didOpenTestDocument(uri, text, file_type)
        log.info('file %s opened' % file_name)

    def didChangeFile(self, buf):
        file_name = buf.name
        uri = GetUriFromFilePath(buf.name)
        if not uri in self._documents:
            # not sure why this happens
            self.didOpenFile(buf)
            return
        version = self._documents[uri][
            'version'] = self._documents[uri]['version'] + 1
        textbody = vimsupport.ExtractUTF8Text(buf)
        self._client.didChangeTestDocument(uri, version, textbody)

    def UpdateSpecifiedBuffer(self, buf):
        if not self.isAlive():
            return
        # FIME we need to add a temp name for every unamed buf?
        if not buf.name:
            return
        if not buf.options['modified']:
            if (len(buf) > 1) or (len(buf) == 1 and len(buf[0])):
                return
        self.didChangeFile(buf)

    def UpdateCurrentBuffer(self):
        if not self.isAlive():
            return
        buf = vimsupport.CurrentBuffer()
        try:
            self.UpdateSpecifiedBuffer(buf)
        except:
            log.exception('failed to update curent buffer')
            vimsupport.EchoTruncatedText('unable to update curent buffer')

    def _CalculateStartColumnAt(self, column, line):
        start_column = min(column, len(line))
        while start_column:
            c = line[start_column - 1]
            if not (str.isalnum(c) or c == '_'):
                break
            start_column -= 1
        return start_column, line[start_column:column]

    def onCodeCompletions(self, uri, line, column, completions):
        if uri not in self._documents:
            return
        if uri != GetUriFromFilePath(vimsupport.CurrentBufferFileName()):
            return
        if not self._last_completions_pos == (line, column):
            return
        tries = self._GetEmptyCompletions()

        log.info('performed clang codecomplete at %d:%d, result %d items' %
                 (line, column, len(completions)))

        for completion in completions:
            if not 'kind' in completion:
                continue
            kind = CompletionItemKind(completion['kind'])
            # insertText is missing from old clangd, we try to keep compatibility here
            word = completion[
                'insertText'] if 'insertText' in completion else completion[
                    'label']
            # description
            info = completion[
                'detail'] if 'detail' in completion else completion['label']
            # actual results to feed vim
            tries[kind].insert(
                word,
                {
                    'word':  # The actual completion
                    word,
                    'kind':  # The type of completion, one character
                    kind,
                    'info': info,  # description
                    'icase': 1,  # ignore case
                    'dup': 1  # allow duplicates
                })
        # update cache
        self._last_completions = tries

    def CodeCompleteAtCurrent(self):
        if not self.isAlive():
            return -1
        if not self.OpenCurrentFile():
            return -1

        line, column = vimsupport.CurrentLineAndColumn()
        start_column, start_word = self._CalculateStartColumnAt(
            column, vimsupport.CurrentLine())

        trigger_word = None
        if start_column:
            trigger_word = vimsupport.CurrentLine()[start_column - 1]

        # skip from ';' and '}'
        if trigger_word == ';' or trigger_word == '}':
            return -1

        if not self._last_completions_pos == (line - 1, start_column):
            timeout_ms = int(vim.eval('g:clangd#codecomplete_timeout'))
            try:
                self._last_completions_pos = (line - 1, start_column)
                uri = GetUriFromFilePath(vimsupport.CurrentBufferFileName())
                self._client.codeCompleteAt(
                    uri, line - 1, start_column, timeout_ms=timeout_ms)
            except TimedOutError:
                log.warn('perform clang codecomplete timed out at %d:%d' %
                         (line, column))

        # fetch cachable completions
        tries = self._last_completions

        flat_completions = []
        for kind, trie in tries.items():
            flat_completions.extend(trie.searchPrefix(start_word)[0:10])

        self._computed_completions_words = flat_completions
        return start_column + 1

    def GetCompletions(self):
        if len(self._last_completions) == 0:
            return {'words': [], 'refresh': 'always'}
        _, column = vimsupport.CurrentLineAndColumn()
        words = self._computed_completions_words
        return {'words': words, 'refresh': 'always'}

    def GotoDefinition(self):
        if not self.isAlive():
            return

        line, column = vimsupport.CurrentLineAndColumn()
        #TODO we may want to reparse source file actively here or by-pass the
        # reparsing to incoming source file monitor?

        response = self.wc.GetDefinition(vimsupport.CurrentBufferFileName(),
                                         line, column)
        if not response:
            log.warning('unable to get definition at %d:%d' % (line, column))
            vimsupport.EchoTruncatedText('unable to get definition at %d:%d' %
                                         (line, column))
            return
        location = response.location
        file_name = location.file_name
        line = location.line
        column = location.column
        vimsupport.GotoBuffer(file_name, line, column)

    def ShowCursorDetail(self):
        if not self.isAlive():
            return

        line, column = vimsupport.CurrentLineAndColumn()
        #TODO we may want to reparse source file actively here or by-pass the
        # reparsing to incoming source file monitor?
        response = self.wc.GetCursorDetail(vimsupport.CurrentBufferFileName(),
                                           line, column)
        if not response:
            vimsupport.EchoTruncatedText('unable to get cursor at %d:%d' %
                                         (line, column))
            log.warning('unable to get cursor at %d:%d' % (line, column))
            return
        detail = response.detail
        message = 'Type: %s Kind: %s' % (detail.type, detail.kind)
        brief_comment = detail.brief_comment
        if brief_comment:
            message += '   '
            message += brief_comment
        vimsupport.EchoText(message)

    def CloseAllFiles(self):
        if not self.isAlive():
            return
        try:
            for uri in list(self._documents.keys()):
                self._client.didCloseTestDocument(uri)
        except OSError:
            log.exception('failed to close all files')

    def _UpdateBufferByTextEdits(self, buf, textedits):
        text = vimsupport.ExtractUTF8Text(buf)
        l = 0
        c = 0
        n = 0
        for textedit in textedits:
            start_line = textedit['range']['start']['line']
            start_column = textedit['range']['start']['character']
            end_line = textedit['range']['end']['line']
            end_column = textedit['range']['end']['character']
            while not (l == start_line and c == start_column):
                if n + 1 >= len(text):
                    break
                n += 1
                if text[n - 1] == u'\n':
                    l += 1
                    c = 0
                else:
                    c += 1
            # unexcepted result
            if n + 1 >= len(text):
                break
            bn = n
            while not (l == end_line and c == end_column):
                if n + 1 >= len(text):
                    n += 1
                    break
                n += 1
                if text[n - 1] == u'\n':
                    l += 1
                    c = 0
                else:
                    c += 1
            nn = bn + len(textedit['newText'])
            text = text[0:bn] + textedit['newText'] + text[n:]
            n = nn
        vim.current.buffer[:] = text.split('\n')

    def format(self):
        buf = vim.current.buffer
        if buf.mark('<') is None or buf.mark('<') is None:
            self._FormatBuffer(buf)
        else:
            self._FormatOnRange(buf, buf.mark('<'), buf.mark('>'))

    def _FormatBuffer(self, buf):
        uri = GetUriFromFilePath(buf.name)

        try:
            # synchronize before format
            self.didChangeFile(buf)

            # actual format rpc
            textedits = self._client.format(uri)
        except OSError as e:
            vimsupport.EchoMessage("clangd refuse to perform code format")
            log.info(e)
            return

        self._UpdateBufferByTextEdits(buf, textedits)

    def _FormatOnRange(self, buf, start, end):
        (start_line, start_column) = start
        start_column = min(
            len(buf[start_line - 1]) - 1
            if len(buf[start_line - 1]) > 0 else 0, start_column)
        (end_line, end_column) = end
        end_column = min(
            len(buf[end_line - 1]) - 1
            if len(buf[end_line - 1]) > 0 else 0, end_column)
        uri = GetUriFromFilePath(vimsupport.CurrentBufferFileName())
        try:
            # synchronize before format
            self.didChangeFile(buf)

            # actual format rpc
            textedits = self._client.rangeFormat(uri, start_line - 1, start_column,
                                                 end_line - 1, end_column)
        except OSError as e:
            vimsupport.EchoMessage("clangd refuse to perform code format")
            log.info(e)
            return

        self._UpdateBufferByTextEdits(buf, textedits)
