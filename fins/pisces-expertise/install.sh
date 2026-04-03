#!/usr/bin/env bash
# pisces-expertise fin — install entrypoint
#
# Verifies that the shoal Python package is importable and that the AWS Bedrock
# or AI Gateway backend will be available at runtime. Does not make any network
# calls — just checks import availability.
#
# SHOAL_PYTHON is injected by the shoal fin runtime and points to the same
# interpreter that is running shoal, ensuring venv isolation is respected.
set -euo pipefail

PY="${SHOAL_PYTHON:-python3}"

"$PY" -c "import shoal" 2>/dev/null || {
    echo "ERROR: shoal Python package is not importable." >&2
    echo "       Run 'pip install shoal-cli' or activate the shoal virtualenv." >&2
    exit 1
}

"$PY" -c "import shoal.services.ai_client, shoal.core.journal, shoal.core.db" 2>/dev/null || {
    echo "ERROR: Required shoal submodules not importable." >&2
    exit 1
}

echo "install: ok"
