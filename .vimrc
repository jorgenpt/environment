"""""""""""""""""""""""""""""""""""""""""""""
" Jørgen's .vimrc                           "
" (c) Jørgen P. Tjernø <jorgenpt@gmail.com> "
"""""""""""""""""""""""""""""""""""""""""""""

let mapleader = ","

" vi sucks ;)
set nocompatible

runtime bundle/vim-pathogen/autoload/pathogen.vim

" Needed on some linux distros.
" see http://www.adamlowe.me/2009/12/vim-destroys-all-other-rails-editors.html
filetype on
filetype off
call pathogen#helptags()
call pathogen#infect()

" Button binds :)
map <F11> :set nu!<CR>
" map <F12> :w !perl -wc<CR>
map <F12> :make<CR>

" Proper backspaces.
set backspace=indent,eol,start

" Proper indents
set expandtab
set shiftwidth=2
set softtabstop=2

" Abbreviations!
iabbrev xSub sub {<CR><CR>}<UP><UP><RIGHT><RIGHT>
iabbrev xCred (c) Jørgen P. Tjernø <jorgenpt@gmail.com>
iabbrev xName Jørgen P. Tjernø
iabbrev xBZFooter <F10>// Local Variables: ***<CR>// mode:C++ ***<CR>// tab-width: 8 ***<CR>// c-basic-offset: 2 ***<CR>// indent-tabs-mode: t ***<CR>// End: ***<CR>// ex: shiftwidth=2 tabstop=8<F10>
iabbrev xBZHeader <F10>/* bzflag<CR> * Copyright (c) 1993 - 2007 Tim Riker<CR> *<CR> * This package is free software;  you can redistribute it and/or<CR> * modify it under the terms of the license found in the file<CR> * named COPYING that should have accompanied this file.<CR> *<CR> * THIS PACKAGE IS PROVIDED ``AS IS'' AND WITHOUT ANY EXPRESS OR<CR> * IMPLIED WARRANTIES, INCLUDING, WITHOUT LIMITATION, THE IMPLIED<CR> * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.<CR> */<F10>

" If using a version 6 vim, enable folding
if version >= 600
 set foldenable
 set foldmethod=marker
endif

" Enable hilighting (if default is off)
syntax enable

set t_Co=256
" let g:solarized_termcolors=16
" Wee, manxome.vim :)
colorscheme manxome
"colorscheme solarized
"colorscheme zellner

" Looks
set background=dark

" For taglist.vim
let Tlist_Auto_Open = 0
let Tlist_Ctags_Cmd = "/usr/bin/ctags-exuberant"
let Tlist_Exit_OnlyWindow = 1
let Tlist_Inc_Winwidth = 0
let Tlist_Compact_Format = 0
nnoremap <silent> <F9> :TlistSync<CR>
nnoremap <silent> <F8> :Tlist<CR>

" Use perl compiler for all *.pl and *.pm files.
autocmd BufNewFile,BufRead *.p? compiler perl

augroup mkd
    autocmd BufRead *.{mkd,md,markdown}  set ai formatoptions=tcroqn2 comments=n:&gt;
augroup END

autocmd BufNewFile,BufRead svn-commit.* setf svn

set viminfo='20,<500,h
set modelines=5

" Undo in insert mode.
imap <c-z> <c-o>u
" Execute current file.
let g:ConqueTerm_ExecFileKey = '<c-r>'
let g:ConqueTerm_SendVisKey = '<D-x>'
let g:ConqueTerm_CWInsert = 1
let g:ConqueTerm_InsertOnEnter = 1

" filetype indent on
" filetype plugin on

" autocmd BufRead *.py set smartindent
autocmd BufRead *.py set smartindent cinwords=if,elif,else,for,while,try,except,finally,def,class foldmethod=indent foldnestmax=2
autocmd BufRead *.py inoremap # X<c-h>#

autocmd BufWritePre *.{py,cpp,cc,c,cxx,C,rb,pl} normal m`:%s/\s\+$//e ``

setlocal spelllang=en
autocmd BufRead *.tex set spell

set history=100

set autoindent nocindent nosmartindent
"set smartindent
set title
set ruler

" Make p in Visual mode replace the selected text with the "" register.
vnoremap p <Esc>:let current_reg = @"<CR>gvdi<C-R>=current_reg<CR><Esc>
set termencoding=utf-8
set encoding=utf-8
set lazyredraw                  " don't update the display while executing macros
set laststatus=2                " tell VIM to always put a status line in, even
                                "    if there is only one window
set cmdheight=1                 " use a
                                "    status bar that is 2 rows high

function PasteStatus()
  if &paste
    return "[paste]"
  else
    return ""
  endif
endfunction
" Set an awesome status line
set statusline=#%n\ %F%m%r%h%w%y%{PasteStatus()}\ (hex=\%02.2B)\ %=%{fugitive#statusline()}\ (%l/%L,%v)

set formatoptions+=o    " Insert comment header when starting new line
set formatoptions-=t    " Do not auto-wrap text using textwidth
set formatoptions+=c    " Do auto-wrap comments using textwidth
set formatoptions+=q    " Allow formatting of comments with gq

" This makes it autowrap at 80 characters wide, and allows you to type e.g. gqq
" in Normal mode to reindent the current paragraph.
set textwidth=80

" This shows "bad" whitespaces, i.e. whitespace at the end of a line or mixed
" spaces & tabs.
highlight ExtraWhitespace ctermbg=red guibg=red
autocmd Syntax * syn match ExtraWhitespace /\s\+$\| \+\ze\t/ containedin=ALL

" This switches between pastemode and normal mode when you press F10.
" Pastemode makes vim do as little processing as possible on the stuff you input,
" like indenting, wrapping, etc.
set pastetoggle=<F10>

" These make it so that if you're searching in all lowercase, then it is done
" case insensitive.
set ignorecase smartcase

" This makes it so that all the hits for your current search is hilighted.
" Note that if you've searched but no longer want the hits to be hilighted,
" use :noh in Normal mode (short for nohlsearch) to turn them off until
" you search again, or use the bind below and press space.
set hlsearch

" Press space to cancel search highlight.
nnoremap <silent> <Space> :nohlsearch<Bar>:echo<CR>

" This makes searching incremental, so as soon as you start typing, it starts
" searching for the currently entered text. Remember to press Enter if you're
" happy with the hit so far to move the cursor there (Esc moves it back to your
" original position).
set incsearch

" Changes directory to the directory that contains the file you open,
" every time you open a file. Some find this annoying.
" autocmd BufRead * cd %:p:h

autocmd BufNewFile,BufRead *.eml set textwidth=72

" GUI font selection
set guifont=Consolas\ for\ Powerline:h14

" Use fancy powerline.
let g:Powerline_symbols = 'fancy'

let g:tmux_sessionname = $TSLIME_SESSION
let g:tmux_windowname = $TSLIME_WINDOW
let g:tmux_panenumber = $TSLIME_PANE

" Clipboard and mouse stuff
set mouse=a
set clipboard=unnamed

set wildignore+=*.o,*.a,*.so,*.d
set wildignore+=*.class,*.jar
set wildignore+=*.dex,*.ap?
set wildignore+=*.png,*.jpg,*.gif

function! StartUp()
    if 0 == argc()
        NERDTree
    end
endfunction

autocmd VimEnter * call StartUp()
