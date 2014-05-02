fun! s:DetectP4Change()
    if getline(1) == '# A Perforce Change Specification.'
        set noexpandtab sw=8 st=8 sts=8 nowrap
    endif
endfun

autocmd BufNewFile,BufRead * call s:DetectP4Change()
