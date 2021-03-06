let s:save_cpo = &cpo
set cpo&vim

fu! s:restore_cpo()
  let &cpo = s:save_cpo
  unlet s:save_cpo
endf

let s:script_folder_path = escape(expand('<sfile>:p:h'), '\')
let s:old_cursor_position = []
let s:omnifunc_mode = 0
let s:cursor_moved = 0

" Main Entrance
fu! clangd#Enable()
  if &diff
    return
  endif

  let g:clangd#backend_loaded = 0
  call s:SetUpFirstRun()
  call s:SetUpPython()
  if !g:clangd#backend_loaded
      let g:clangd#autostart = 0
      let g:clangd#completions_enabled = 0
      return
  endif
  call s:TurnOffSyntasticForCFamily()
  call s:SetUpSyntasticSigns()
  call s:SetUpSyntasticHl()
  augroup clangd
    autocmd!
    "autocmd TabEnter *
    autocmd VimLeave * call s:VimLeave()
    autocmd BufReadPost * call s:BufferReadPost(escape(expand('<afile>:p'), '\'))
    autocmd FileType * call s:FileType()
    autocmd BufWritePost * call s:BufferWritePost(escape(expand('<afile>:p'), '\'))
    autocmd BufUnload * call s:BufferUnload(escape(expand('<afile>:p'), '\'))
    autocmd BufDelete * call s:BufferDelete(escape(expand('<afile>:p'), '\'))
    autocmd CursorMoved * call s:CursorMove()
    autocmd CursorMovedI * call s:CursorMoveInsertMode()
    autocmd CursorHold,CursorHoldI * call s:CursorHold()
    autocmd InsertEnter * call s:InsertEnter()
    autocmd InsertLeave * call s:InsertLeave()
    autocmd TextChanged,TextChangedI * call s:TextChanged()
  augroup END
  call s:VimEnter()
endf

" Sub Entrances
fu! s:SetUpPython() abort
  exec s:PyUntilEOF
import sys, os, vim
sys.path.insert(0, os.path.join(vim.eval('s:script_folder_path'), '..', 'python'))

def SetUpLogging():
    global log
    import clangd.glog as log
    try:
      log_level = str(vim.eval('g:clangd#log_level'))
      log_path = os.path.expanduser(str(vim.eval('g:clangd#log_path')))
      if not os.path.exists(log_path):
          os.makedirs(log_path)
      log.init(log_level, os.path.join(log_path, 'vim-clangd.log'))
    except Exception as e:
      err = e
      return False
    return True

def SetUpEventHandler():
    try:
      global handler, FilterFileName, FilterCurrentFile
      from clangd.clangd_manager import FilterFileName, FilterCurrentFile
      from clangd.event_dispatcher import EventDispatcher
      handler = EventDispatcher()
    except Exception as e:
      log.exception('failed to set up python')
      err = e
      return False
    return True

backend_loaded = SetUpLogging() and SetUpEventHandler()
if log:
  log.debug('let g:clangd#backend_loaded = %d' % int(backend_loaded))
vim.command('let g:clangd#backend_loaded = %d' % int(backend_loaded))

EOF
endf

fu! s:TurnOffSyntasticForCFamily()
  let g:syntastic_cpp_checkers = []
  let g:syntastic_c_checkers = []
  let g:syntastic_objc_checkers = []
  let g:syntastic_objcpp_checkers = []
endf

fu! s:SetUpSyntasticSigns()
  if !hlexists('clangdErrorSign')
    if hlexists('SyntasticErrorSign')
      highlight link clangdErrorSign SyntasticErrorSign
    else
      highlight link clangdErrorSign error
    endif
  endif

  if !hlexists('clangdWarningSign')
    if hlexists('SyntasticWarningSign')
      highlight link clangdWarningSign SyntasticWarningSign
    else
      highlight link clangdWarningSign todo
    endif
  endif

  if !hlexists('clangdErrorLine')
    highlight link clangdErrorLine SyntasticErrorLine
  endif

  if !hlexists('clangdWarningLine')
    highlight link clangdWarningLine SyntasticWarningLine
  endif

  let l:error_symbol = get(g:, 'syntastic_error_symbol', '>>')
  let l:warning_symbol = get(g:, 'syntastic_warning_symbol', '>>')
  exe 'sign define clangdError text=' . l:error_symbol .
        \ ' texthl=clangdErrorSign linehl=clangdErrorLine'
  exe 'sign define clangdWarning text=' . l:warning_symbol .
        \ ' texthl=clangdWarningSign linehl=clangdWarningLine'
endf


fu! s:SetUpSyntasticHl()
  if !hlexists('clangdErrorSection')
    if hlexists('SyntasticError')
      highlight link clangdErrorSection SyntasticError
    else
      highlight link clangdErrorSection SpellBad
    endif
  endif

  if !hlexists('clangdWarningSection')
    if hlexists('SyntasticWarning')
      highlight link clangdWarningSection SyntasticWarning
    else
      highlight link clangdWarningSection SpellCap
    endif
  endif
endf

fu! s:SetUpFirstRun()
    if !exists('g:clangd#clangd_executable')
       let g:clangd#clangd_executable = ''
    endif
    if !exists('g:clangd#completions_enabled')
       let g:clangd#completions_enabled = 1
    endif
    if !exists('g:clangd#autostart')
       let g:clangd#autostart = 1
    endif
    if !exists('g:clangd#log_level')
       let g:clangd#log_level = 'warn'
    endif
    if !exists('g:clangd#log_path')
       let g:clangd#log_path = '~/.config/clangd/logs/'
    endif
    if !exists('g:clangd#py_version')
       if has('python3')
          let g:clangd#py_version = 3
       else
          let g:clangd#py_version = 2
       endif
    endif
    if !exists('g:clangd#restart_after_crash')
       let g:clangd#restart_after_crash = 1
    endif
    if !exists('g:clangd#codecomplete_timeout')
       let g:clangd#codecomplete_timeout = 100
    endif

    " Python Setup
    if g:clangd#py_version == 3
        let s:python_version = 3
        let cmd_exec = 'python3'
        let s:PyUntilEOF = 'python3 << EOF'
    else
        let s:python_version = 2
        let cmd_exec = 'python'
        let s:PyUntilEOF = 'python << EOF'
    endif
    exe 'command! -nargs=1 Python '.cmd_exec.' <args>'
endf

" Watchers

fu! s:VimEnter()
  Python handler.OnVimEnter()
  " fix a bug it won't call buffer enter the very first file
  call s:FileType()
  func
  if has('timers')
      fu! OnTimerCallback(timer)
        Python handler.OnTimerCallback()
      endf
      let s:timer = timer_start(5000, 'OnTimerCallback', { 'repeat': -1 })
  endif
endf

fu! s:VimLeave()
  if has('timers')
      exec timer_stop(s:timer)
  endif
  Python handler.OnVimLeave()
endf

fu! s:BufferRead()
  Python handler.OnBufferRead()
endf

fu! s:BufferReadPost(file_name)
  if s:FilterFileName(a:file_name)
    return
  endif
  Python handler.OnBufferReadPost(vim.eval('a:file_name'))
endf

fu! s:FileType()
  if s:FilterCurrentFile()
    return
  endif
  call s:SetCompletionCallback()
  Python handler.OnFileType()
endf

fu! s:BufferWritePost(file_name)
  if s:FilterFileName(a:file_name)
    return
  endif
  Python handler.OnBufferWritePost(vim.eval('a:file_name'))
endf

fu! s:BufferUnload(file_name)
  if s:FilterFileName(a:file_name)
    return
  endif
  Python handler.OnBufferUnload(vim.eval('a:file_name'))
endf

fu! s:BufferDelete(file_name)
  if s:FilterFileName(a:file_name)
    return
  endif
  Python handler.OnBufferDelete(vim.eval('a:file_name'))
endf

fu! s:CursorMove()
  if s:FilterCurrentFile()
    return
  endif
  let current_position = getpos('.')
  let s:cursor_moved = current_position != s:old_cursor_position
  Python handler.OnCursorMove()
  let s:old_cursor_position = current_position
endf

fu! s:CursorMoveInsertMode()
  if s:FilterCurrentFile()
    return
  endif
  call s:CursorMove()
  call s:InvokeCompletion()
endf

fu! s:CursorHold()
  if s:FilterCurrentFile()
    return
  endif
  Python handler.OnCursorHold()
endf

fu! s:InsertEnter()
  if s:FilterCurrentFile()
    return
  endif
  let s:old_cursor_position = []
  let s:omnifunc_mode = 0
  Python handler.OnInsertEnter()
endf

fu! s:InsertLeave()
  if s:FilterCurrentFile()
    return
  endif
  Python handler.OnInsertLeave()
endf

fu! s:TextChanged()
  if s:FilterCurrentFile()
    return
  endif
  Python handler.OnTextChanged()
endf

" Helpers
fu! s:FilterCurrentFile()
  return s:PyEval('FilterCurrentFile()')
endf

fu! s:FilterFileName(file_name)
  return s:PyEval('FilterFileName("'. a:file_name . '")')
endf

fu! s:ShowDiagnostics()
  let diags = s:PyEval('handler.GetDiagnosticsForCurrentFile()')
  if !empty(diags)
    call setloclist(0, diags)

    lopen
  else
    echom "No warnings or errors detected"
  endif
endf

fu! s:ForceCompile()
  Python handler.ForceCompile()
endf

fu! clangd#CodeCompleteAt(findstart, base)
  if s:omnifunc_mode
    return clangd#OmniCompleteAt(a:findstart, a:base)
  endif
  if a:findstart
    let ret = s:PyEval('handler.CodeCompleteAtCurrent()')
    if empty(ret)
      return -2
    endif
    if !s:cursor_moved
      return -2
    endif
    let l:column = ret
    return l:column - 1
  endif

  " return completions
  let ret = s:PyEval('handler.GetCompletions()')
  if empty(ret)
    return []
  endif
  " Report a result.
  if complete_check()
    return []
  endif
  let l:completions = ret
  return l:completions
endf

fu! clangd#OmniCompleteAt(findstart, base)
  if a:findstart
    let ret = s:PyEval('handler.CodeCompleteAtCurrent()')
    if empty(ret)
      return -2
    endif
    let l:column = ret
    let s:omnifunc_mode = 1
    return l:column
  endif

  " return completions
  let l:completions = s:PyEval('handler.GetCompletions()')
  if empty(l:completions)
    return []
  return l:completions
endf

fu! s:InvokeCompletion()
  if &completefunc != "clangd#CodeCompleteAt"
    return
  endif
  let is_blank = s:PyEval('not vim.current.line or vim.current.line.isspace()')
  if is_blank
    return
  endif

  if !s:cursor_moved
    return
  endif
  call feedkeys("\<C-X>\<C-U>\<C-P>", 'n')
endf

fu! s:SetCompletionCallback()
  if !g:clangd#completions_enabled
    return
  endif
  set completeopt-=menu
  set completeopt+=menuone
  set completeopt-=longest
  let &l:completefunc = 'clangd#CodeCompleteAt'
  setlocal omnifunc=clangd#OmniCompleteAt
endf

fu! s:GotoDefinition()
  Python handler.GotoDefinition()
endf

fu! s:ShowDetailedDiagnostic()
  Python handler.EchoDetailedErrorMessage()
endf

fu! s:ShowCursorDetail()
  Python handler.ShowCursorDetail()
endf

fu! s:StartServer()
  Python handler.StartServer()
endf

fu! s:StopServer()
  Python handler.StopServer()
endf

fu! s:RestartServer()
  Python handler.RestartServer()
endf

fu! s:Format()
  " Determine range or format current buffer
  Python handler.format()
endf

fu! s:DownloadBinary()
  Python handler.OnRequestDownloadBinary(os.path.join(vim.eval('s:script_folder_path'), '..', 'script'))
endf

fu! s:PyEval(line)
    if s:python_version == 3
        return py3eval(a:line)
    else
        return pyeval(a:line)
    endif
endf

fu! ClangdStatuslineFlag()
  return s:PyEval('handler.ErrorStatusForCurrentLine()')
endf

" Setup Commands
command! ClangdCodeComplete call feedkeys("\<C-X>\<C-U>\<C-P>", 'n')
command! ClangdDiags call s:ShowDiagnostics()
command! ClangdShowDetailedDiagnostic call s:ShowDetailedDiagnostic()
command! ClangdForceCompile call s:ForceCompile()
" command! ClangdGotoDefinition call s:GotoDefinition()
" command! ClangdShowCursorDetail call s:ShowCursorDetail()
command! ClangdStartServer call s:StartServer()
command! ClangdStopServer call s:StopServer()
command! ClangdRestartServer call s:RestartServer()
command! ClangdFormat call s:Format()
command! ClangdInstallBinary call s:DownloadBinary()

call s:restore_cpo()
