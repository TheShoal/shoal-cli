#!/usr/bin/env bash
# pisces-expertise fin — configure entrypoint
#
# No interactive configuration required.  The fin reads LLM backend settings
# from ~/.config/shoal/config.toml ([dreamer.ai] section) at run time.
set -euo pipefail

echo "configure: ok"
