## vim-clangd
[![Build Status](https://travis-ci.org/Chilledheart/vim-clangd.svg?branch=master)](http://travis-ci.org/Chilledheart/vim-clangd)

## Demo

![gif](http://i.imgur.com/I9cO6Ve.gif)

## Features

|C/C++ Editor feature                |Clangd    |vim-clangd|
|------------------------------------|----------|----------|
|Formatting                          |Yes       |Yes       |
|Completion                          |Yes       |Yes       |
|Diagnostics                         |Yes       |Yes       |
|Fix-its                             |Yes       |No        |
|Go to Definition                    |No        |No        |
|Source hover                        |No        |No        |
|Signature Help                      |No        |No        |
|Find References                     |No        |No        |
|Document Highlights                 |No        |No        |
|Rename                              |No        |No        |
|Code Lens                           |No        |No        |
|Syntax and Semantic Coloring        |No        |No        |
|Code folding                        |No        |No        |
|Call hierarchy                      |No        |No        |
|Type hierarchy                      |No        |No        |
|Organize Includes                   |No        |No        |
|Quick Assist                        |No        |No        |
|Extract Local Variable              |No        |No        |
|Extract Function/Method             |No        |No        |
|Hide Method                         |No        |No        |
|Implement Method                    |No        |No        |
|Gen. Getters/Setters                |No        |No        |

## How to use vim-clangd plugins

1. use vunble or other vim plugin manager to add vim-clangd in vimrc file
such as
```
Plugin 'Chilledheart/vim-clangd'
```

2. setup clangd
you can do it by run this script
```
./script/build-clangd.sh
```
vim-clangd will search builtin clangd and then fallback to clangd in the path.
however there is no simple way to get a binary clangd yet including llvm
official apt repo.

if you are using ubuntu, you can refer to [docker/Dockerfile.xenial](https://github.com/Chilledheart/vim-clangd/blob/master/docker/Dockerfile.xenial) as well.

see more at [clang docs](https://clang.llvm.org/get_started.html) but "extra Clang tools" is not optional.

3. start vim and enjoy

## Advanced Usage

### Specify other clangd instance
if you have clangd not in the path
you can specify clangd binary in vimrc file such as
```
let g:clangd#clangd_executable = '~/build-llvm/bin/clangd'
```

make sure you have clang headers in the right directory

### Turn off auto completion
Sometimes completion is slow. there is a way to turn it off.

Put this in your vimrc file
```
let g:clangd#completions_enabled = 0
```

### Tune auto completion speed
Sometimes completion is slow. vim-clangd will detect the slow code completion and skip to let you go.
the condition is tunable where default is 100ms.

Put this in your vimrc file to save your waiting time to 10ms
```
let g:clangd#codecomplete_timeout = 10
```

### Turn off autorestart behavior
vim-clangd will detect the crashed clangd and restart it again as soon as possible.
maybe you just don't need this and want to turn it off.

Put this in your vimrc file
```
let g:clangd#restart_after_crash = 0
```

### Code format the selected code

you can use `:<C-u> ClangdFormat` to code format the specified code

and you can specify shortcuts for it, such as

```
au FileType c,cpp,objc,objcpp nnoremap <buffer><Leader>cf :ClangdFormat<CR>
au FileType c,cpp,objc,objcpp vnoremap <buffer><Leader>cf :<C-u>ClangdFormat<CR>
```

### Specify python version
vim-clangd will recognize your builtin python support of vim and
will choose python3 as default.

you might want to specify python version forcely

```
let g:clangd#py_version = 2
```
this will force vim-clangd to use python2

### Use along with neocomplete

make sure you have neocomplete installed. you should disable vim-clangd's
autocompletion and configure neocomplete correctly. below is an example:

```
let g:clangd#completions_enabled = 0
if !exists('g:neocomplete#force_omni_input_patterns')
    let g:neocomplete#force_omni_input_patterns = {}
endif
let g:neocomplete#force_omni_input_patterns.c = '[^.[:digit:] *\t]\%(\.\|->\)\w*'
let g:neocomplete#force_omni_input_patterns.cpp = '[^.[:digit:] *\t]\%(\.\|->\)\w*\|\h\w*::\w*'
autocmd FileType c,cpp,objc,objcpp setlocal omnifunc=clangd#OmniCompleteAt
```
