Setup
=====

Check out code
--------------

    git clone --recursive git@github.com:jorgenpt/environment.git "$HOME/Environment"
    pushd "$HOME/Environment"
    git remote rename origin github
    if [[ -d "$HOME/Dropbox/Repositories/environment.git" ]]; then
      git remote add dropbox "$HOME/Dropbox/Repositories/environment.git"
    fi
    popd

Set up symlinks etc
-------------------

    pushd "$HOME"
    Environment/setup
    popd
