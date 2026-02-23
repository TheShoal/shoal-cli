#!/bin/sh
# Hook: PostToolUse Edit|Write — remind about tests for source file changes
# Light-touch: injects context, doesn't block

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only trigger for source files (not __init__.py, __main__.py, tests, configs)
case "$FILE_PATH" in
    */src/shoal/*.py)
        case "$FILE_PATH" in
            *__init__.py|*__main__.py) exit 0 ;;
        esac
        ;;
    *) exit 0 ;;
esac

# Extract module name for test file hint
MODULE=$(basename "$FILE_PATH" .py)

jq -n --arg mod "$MODULE" \
    '{"additionalContext": ("Source file modified. Run targeted tests: uv run pytest tests/test_" + $mod + ".py -x -q")}'
