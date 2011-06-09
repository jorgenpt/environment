Setup
=====

Check out code
--------------

    git clone git@github.com:jorgenpt/environment.git "$HOME/Environment"
    if [[ -d "$HOME/Dropbox/Repositories/environment.git" ]]; then 
      pushd "$HOME/Environment"
      git remote -m origin github
      git remote add origin "$HOME/Dropbox/Repositories/environment.git"
      popd
    fi

Set up symlinks etc
-------------------

    pushd "$HOME"
    Environment/setup
    popd
