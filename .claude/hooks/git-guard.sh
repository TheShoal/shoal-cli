#!/bin/sh
# Hook: PreToolUse Bash — block destructive git commands
# Allows --force-with-lease (safer variant)

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check git commands
case "$COMMAND" in
    *git*) ;;
    *) exit 0 ;;
esac

# Allow --force-with-lease (safe force push)
case "$COMMAND" in
    *--force-with-lease*) exit 0 ;;
esac

# Block destructive operations
BLOCKED=""
case "$COMMAND" in
    *"push --force"*|*"push -f "*) BLOCKED="git push --force (use --force-with-lease instead)" ;;
    *"reset --hard"*) BLOCKED="git reset --hard (destroys uncommitted work)" ;;
    *"branch -D "*) BLOCKED="git branch -D (force-deletes branch)" ;;
    *"clean -f"*) BLOCKED="git clean -f (deletes untracked files)" ;;
    *"checkout -- ."*|*"checkout ."*) BLOCKED="git checkout . (discards all changes)" ;;
    *"restore ."*) BLOCKED="git restore . (discards all changes)" ;;
esac

if [ -n "$BLOCKED" ]; then
    jq -n --arg reason "Blocked: $BLOCKED. Use with explicit user confirmation only." \
        '{"decision": "deny", "reason": $reason}'
    exit 0
fi

exit 0
