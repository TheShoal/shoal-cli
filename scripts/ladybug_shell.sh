#!/bin/bash
# Launch LadybugDB interactive shell for Pantheon knowledge graph

set -e

DB_PATH="${LADYBUG_DB_PATH:-$HOME/.local/share/shoal/pantheon_kg.ladybug}"

echo "Opening LadybugDB shell at: $DB_PATH"
lbug "$DB_PATH"
