#!/usr/bin/env bash
# Claude Code PostToolUse hook for Shoal heartbeat
# Called after every tool use with env vars set by Claude Code.

SESSION="${SHOAL_SESSION:-}"
TOOL="${CLAUDE_TOOL_NAME:-unknown}"

# If not in a Shoal session, skip
[ -z "$SESSION" ] && exit 0

# Push heartbeat via Shoal API
curl -s -X POST "http://localhost:${SHOAL_PORT:-8484}/sessions/${SESSION}/heartbeat" \
  -H "Content-Type: application/json" \
  -d "{\"status\": \"running\", \"summary\": \"Tool: ${TOOL}\", \"tool_name\": \"${TOOL}\"}" \
  > /dev/null 2>&1 &

# Also mark waiting after a short delay (end of turn approximation)
(sleep 2 && curl -s -X POST "http://localhost:${SHOAL_PORT:-8484}/sessions/${SESSION}/heartbeat" \
  -H "Content-Type: application/json" \
  -d '{"status": "waiting", "summary": "Turn complete"}' \
  > /dev/null 2>&1) &
