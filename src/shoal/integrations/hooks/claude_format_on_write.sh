#!/usr/bin/env bash
# Format-on-write hook for Claude Code sessions managed by Shoal.
# Triggered after every Write or Edit tool call.
# Usage: Set as a PostToolUse hook in Claude Code settings.

set -euo pipefail

FILE="${CLAUDE_TOOL_OUTPUT_FILE:-}"
if [[ -z "$FILE" ]]; then
    exit 0
fi

ext="${FILE##*.}"

case "$ext" in
    py)
        if command -v ruff &>/dev/null; then
            ruff format --quiet "$FILE" 2>/dev/null || true
            ruff check --fix --quiet "$FILE" 2>/dev/null || true
        fi
        ;;
    ts|tsx|js|jsx)
        if command -v prettier &>/dev/null; then
            prettier --write --log-level silent "$FILE" 2>/dev/null || true
        fi
        ;;
    json)
        if command -v jq &>/dev/null; then
            tmp=$(mktemp)
            jq . "$FILE" > "$tmp" 2>/dev/null && mv "$tmp" "$FILE" || rm -f "$tmp"
        fi
        ;;
    toml)
        if command -v taplo &>/dev/null; then
            taplo fmt "$FILE" 2>/dev/null || true
        fi
        ;;
esac
