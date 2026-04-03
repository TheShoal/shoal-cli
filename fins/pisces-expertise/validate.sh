#!/usr/bin/env bash
# pisces-expertise fin — validate entrypoint
#
# Checks that all runtime dependencies are importable and that an LLM backend
# is configured.  Exits non-zero with a descriptive message if validation fails.
#
# SHOAL_PYTHON is injected by the shoal fin runtime and points to the same
# interpreter that is running shoal, ensuring venv isolation is respected.
set -euo pipefail

PY="${SHOAL_PYTHON:-python3}"

"$PY" - <<'PYEOF'
import sys

# Core shoal modules required at runtime
try:
    import shoal.services.ai_client
    import shoal.core.journal
    import shoal.core.db
    import shoal.core.config
except ImportError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)

# Soft check: warn if no LLM backend is configured (doesn't fail — let run time surface it)
from shoal.core.config import load_config
cfg = load_config()
ai = cfg.dreamer.ai
if ai.provider == "stub":
    print("WARNING: dreamer.ai.provider is 'stub' — expertise summaries will be placeholders.")
elif ai.provider in ("auto", "bedrock"):
    try:
        import boto3  # noqa: F401
    except ImportError:
        print("WARNING: boto3 not installed; Bedrock backend unavailable.")
        if not ai.endpoint:
            print("WARNING: No AI Gateway endpoint configured either. Summaries will fail at runtime.")

print("validate: checks passed")
PYEOF
