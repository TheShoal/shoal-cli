function shoal-quick-attach --description "Quickly attach to a shoal session using fzf"
    # Get list of sessions and let user pick with fzf
    set -l session (shoal ls --format plain 2>/dev/null | fzf \
        --prompt="Select session > " \
        --header="Shoal Sessions" \
        --preview="shoal info {}" \
        --preview-window=right:50% \
        --height=40%)
    
    # If a session was selected, attach to it
    if test -n "$session"
        shoal attach $session
    end
end
