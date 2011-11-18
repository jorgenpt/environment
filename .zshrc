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
# export DISABLE_AUTO_TITLE="true"

# Which plugins would you like to load? (plugins can be found in ~/.oh-my-zsh/plugins/*)
# Example format: plugins=(rails git textmate ruby lighthouse)
plugins=(git osx brew ruby gem rvm)

source $ZSH/oh-my-zsh.sh

export ANDROID_NDK_ROOT=$HOME/Android/ndk
export EDITOR=vim

alias irc='ssh -t arach screen -rd irc'
alias scpresume="rsync --partial --progress --rsh=ssh"

export RI="-f ansi" RI_PAGER="less -R"

# Customize to your needs...
export PATH=$PATH:$HOME/bin:$HOME/Android/sdk/tools:$HOME/Android/sdk/platform-tools:/usr/local/mysql/bin:$ANDROID_NDK_ROOT

[[ -s "$HOME/Environment/.zshrc.local" ]] && source "$HOME/Environment/.zshrc.local"

unsetopt correct_all

# Fixes path showing as ~rvm_rvmrc_cwd
unsetopt auto_name_dirs
[[ -s "$HOME/.rvm/scripts/rvm" ]] && source "$HOME/.rvm/scripts/rvm"  # This loads RVM into a shell session.
