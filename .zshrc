# Path to your oh-my-zsh configuration.
export ZSH=$HOME/Environment/oh-my-zsh

# Set name of the theme to load.
# Look in ~/.oh-my-zsh/themes/
# Optionally, if you set this to "random", it'll load a random theme each
# time that oh-my-zsh is loaded.
export ZSH_THEME="bira" # "robbyrussell"

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
plugins=(vcsinfo ruby gem rbenv)

source $ZSH/oh-my-zsh.sh

export EDITOR=vim

export P4CONFIG=.p4cfg

alias irc='ssh -t arach screen -rd irc'
alias scpresume="rsync --partial --progress --rsh=ssh"
alias merge='git mergetool -t opendiff'
alias brake='bundle exec rake'

export RI="-f ansi" RI_PAGER="less -R"

[[ -s "$HOME/Environment/.zshrc.local" ]] && source "$HOME/Environment/.zshrc.local"

unsetopt correct_all

# Fixes path showing as ~rvm_rvmrc_cwd
unsetopt auto_name_dirs

# Fixes parallel ZSH session interfering with each other. Ideally, we'd make it
# so that arrow up / down will only pull from local buffer.
unsetopt sharehistory
