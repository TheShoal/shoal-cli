function shoal-quick-attach --description "Quickly attach to a shoal session using fzf"
    # Get list of sessions and let user pick with fzf
    set -l session (shoal ls --format plain 2>/dev/null | fzf \
        --prompt="  > " \
        --preview='env COLUMNS=$FZF_PREVIEW_COLUMNS LINES=$FZF_PREVIEW_LINES shoal info --color=always -- {}' \
        --preview-window=right:65% \
        --height=100%)

    # If a session was selected, attach to it
    if test -n "$session"
        shoal attach -- $session
    end
end
