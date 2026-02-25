function shoal-remote --description "Interactively connect to a remote host and attach to a session"
    # Pick a remote host
    set -l host (shoal remote ls --format plain 2>/dev/null | fzf \
        --prompt="  Remote host > " \
        --header="Select a remote host" \
        --height=40%)

    if test -z "$host"
        return
    end

    # Auto-connect tunnel if not already connected
    if not shoal remote status $host >/dev/null 2>&1
        echo "Connecting to $host..."
        shoal remote connect $host
        if test $status -ne 0
            echo "Failed to connect to $host"
            return 1
        end
    end

    # Pick a remote session
    set -l session (shoal remote sessions $host --format plain 2>/dev/null | fzf \
        --prompt="  Session on $host > " \
        --header="Select a session on $host" \
        --height=40%)

    if test -z "$session"
        return
    end

    # Attach to the selected session
    shoal remote attach $host $session
end
