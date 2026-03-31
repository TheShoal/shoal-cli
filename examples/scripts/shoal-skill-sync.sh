#!/usr/bin/env bash
# shoal-skill-sync.sh — Transpile .shoal/skills/ into tool-native formats.
#
# Called by Shoal as a post_worktree_create hook with the worktree
# absolute path as $1.  Can also be run manually.
#
# Supports: Claude Code, OpenCode, omp
#
# Usage in a template:
#   [template.worktree]
#   post_worktree_create = "examples/scripts/shoal-skill-sync.sh"

set -euo pipefail

WT="${1:-.}"
GIT_ROOT="$(git -C "$WT" rev-parse --show-toplevel 2>/dev/null || echo "$WT")"
SKILLS_SRC="$GIT_ROOT/.shoal/skills"

[ -d "$SKILLS_SRC" ] || exit 0

echo "[shoal-skill-sync] Syncing skills from $SKILLS_SRC → $WT"

# ---------------------------------------------------------------------------
# Claude Code: symlink each skill directory
# ---------------------------------------------------------------------------
if command -v claude >/dev/null 2>&1; then
    mkdir -p "$WT/.claude/skills"
    for skill_dir in "$SKILLS_SRC"/*/; do
        [ -d "$skill_dir" ] || continue
        name="$(basename "$skill_dir")"
        if [ ! -e "$WT/.claude/skills/$name" ]; then
            ln -sfn "$skill_dir" "$WT/.claude/skills/$name"
            echo "  [claude] linked $name"
        fi
    done
fi

# ---------------------------------------------------------------------------
# OpenCode: add skill files as instructions in .opencode.json
# ---------------------------------------------------------------------------
if command -v opencode >/dev/null 2>&1; then
    instructions=""
    for skill_dir in "$SKILLS_SRC"/*/; do
        [ -d "$skill_dir" ] || continue
        [ -f "$skill_dir/SKILL.md" ] || continue
        name="$(basename "$skill_dir")"
        rel=".shoal/skills/$name/SKILL.md"
        instructions="${instructions:+$instructions, }\"$rel\""
    done

    if [ -n "$instructions" ]; then
        if [ -f "$WT/.opencode.json" ]; then
            # Preserve existing config — only add instructions if missing
            if ! grep -q '"instructions"' "$WT/.opencode.json" 2>/dev/null; then
                # Simple merge: add instructions key
                sed -i.bak 's/^{/{\"instructions\": ['"$instructions"'],/' "$WT/.opencode.json"
                rm -f "$WT/.opencode.json.bak"
                echo "  [opencode] injected instructions into existing .opencode.json"
            fi
        else
            echo "{\"instructions\": [$instructions]}" > "$WT/.opencode.json"
            echo "  [opencode] created .opencode.json with instructions"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# omp: concatenate skills into a context file for @file injection
# ---------------------------------------------------------------------------
if command -v omp >/dev/null 2>&1; then
    context_dir="$WT/.shoal/context"
    mkdir -p "$context_dir"
    context_file="$context_dir/skills.md"

    {
        echo "# Shoal Skills"
        echo ""
        echo "The following skills are available. Use them when relevant."
        echo ""
        for skill_dir in "$SKILLS_SRC"/*/; do
            [ -d "$skill_dir" ] || continue
            [ -f "$skill_dir/SKILL.md" ] || continue
            echo "---"
            echo ""
            cat "$skill_dir/SKILL.md"
            echo ""
        done
    } > "$context_file"
    echo "  [omp] wrote $context_file"
fi

echo "[shoal-skill-sync] Done"
