# Path to your oh-my-zsh configuration.
TEMPLATE_SOURCE="$HOME/$(dirname "$(readlink "$HOME/.zshrc")")"
export ZSH="$TEMPLATE_SOURCE/oh-my-zsh"

# Set name of the theme to load.
# Look in ~/.oh-my-zsh/themes/
# Optionally, if you set this to "random", it'll load a random theme each
# time that oh-my-zsh is loaded.
if [ ! -z "$SCHROOT_CHROOT_NAME" ]; then
  export ZSH_THEME="robbyrussell"
else
  export ZSH_THEME="bira"
fi

zstyle ':completion:*' auto-description 'specify: %d'
zstyle ':completion:*' completer _expand _complete _correct _approximate
zstyle ':completion:*' format 'Completing %d'
zstyle ':completion:*' group-name ''
zstyle ':completion:*' menu select=2
if command -v 'dircolors' > /dev/null; then
    eval "$(dircolors -b)"
fi
zstyle ':completion:*:default' list-colors ${(s.:.)LS_COLORS}
zstyle ':completion:*' list-colors ''
zstyle ':completion:*' list-prompt %SAt %p: Hit TAB for more, or the character to insert%s
zstyle ':completion:*' matcher-list '' 'm:{a-z}={A-Z}' 'm:{a-zA-Z}={A-Za-z}' 'r:|[._-]=* r:|=* l:|=*'
zstyle ':completion:*' menu select=long
zstyle ':completion:*' select-prompt %SScrolling active: current selection at %p%s
zstyle ':completion:*' use-compctl false
zstyle ':completion:*' verbose true

zstyle ':completion:*:*:kill:*:processes' list-colors '=(#b) #([0-9]#)*=0=01;31'
zstyle ':completion:*:kill:*' command 'ps -u $USER -o pid,%cpu,tty,cputime,cmd'

# Set to this to use case-sensitive completion
# export CASE_SENSITIVE="true"

# Comment this out to disable weekly auto-update checks
# export DISABLE_AUTO_UPDATE="true"

# Uncomment following line if you want to disable colors in ls
# export DISABLE_LS_COLORS="true"

# Uncomment following line if you want to disable autosetting terminal title.
# Autosetting terminal title messes with tmux.
# export DISABLE_AUTO_TITLE="true"

# Which plugins would you like to load? (plugins can be found in ~/.oh-my-zsh/plugins/*)
# Example format: plugins=(rails git textmate ruby lighthouse)
plugins=()

source $ZSH/oh-my-zsh.sh

export EDITOR=vim

export P4CONFIG=.p4config.txt

export MOSH_TITLE_NOPREFIX=1

alias scpresume="rsync --partial --progress --rsh=ssh"
alias merge='git mergetool -t opendiff'
alias brake='bundle exec rake'
alias pstree='pstree -g 3'

export RI="-f ansi" RI_PAGER="less -R"

[[ -s "$HOME/.zshrc_local" ]] && source "$HOME/.zshrc_local"

unsetopt correct_all

# Fixes path showing as ~rvm_rvmrc_cwd
unsetopt auto_name_dirs

# Fixes parallel ZSH session interfering with each other. Ideally, we'd make it
# so that arrow up / down will only pull from local buffer.
unsetopt sharehistory

setopt histignorealldups

# Keep 1000 lines of history within the shell and save it to ~/.zsh_history:
HISTSIZE=1000
SAVEHIST=1000
HISTFILE=~/.zsh_history

# Use modern completion system
autoload -Uz compinit
compinit

# These are from oh-my-zsh's 'directory' lib, and they're annoying.
# The first one especially when you use p4.
unalias '...'
unalias '....'
unalias '.....'
unalias '......'

# Set up pyenv & pyenv-virtualenv
if which pyenv > /dev/null; then eval "$(pyenv init -)"; fi
if which pyenv-virtualenv-init > /dev/null; then eval "$(pyenv virtualenv-init -)"; fi

export PATH="$PATH:$HOME/bin"
