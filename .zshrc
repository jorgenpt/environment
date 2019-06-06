# Path to your oh-my-zsh configuration.
export ZSH=$HOME/Environment/oh-my-zsh

# Set name of the theme to load.
# Look in ~/.oh-my-zsh/themes/
# Optionally, if you set this to "random", it'll load a random theme each
# time that oh-my-zsh is loaded.
if [ ! -z "$SCHROOT_CHROOT_NAME" ]; then
  export ZSH_THEME="robbyrussell"
else
  export ZSH_THEME="bira"
fi

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
plugins=(ruby gem rbenv)

source $ZSH/oh-my-zsh.sh

export EDITOR=vim

export P4CONFIG=.p4cfg

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

# These are from oh-my-zsh's 'directory' lib, and they're annoying.
# The first one especially when you use p4.
unalias '...'
unalias '....'
unalias '.....'
unalias '......'

# Set up pyenv & pyenv-virtualenv
if which pyenv > /dev/null; then eval "$(pyenv init -)"; fi
if which pyenv-virtualenv-init > /dev/null; then eval "$(pyenv virtualenv-init -)"; fi

if [[ -d "$HOME/.rvm/bin" ]]; then
    # Add RVM to PATH for scripting. Make sure this is the last PATH variable change.
    export PATH="$PATH:$HOME/.rvm/bin"
fi
