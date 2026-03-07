/**
 * shoal-dev — Project-level quality gates for shoal-cli
 *
 * Layered on top of the global devtools extension. devtools already handles:
 *   - ruff format on .py edits (fire-and-forget)
 *   - uv sync on pyproject.toml changes
 *   - bash safety policy (dd, mkfs, git reset --hard, rm -rf, git push --force)
 *
 * This extension adds:
 *   1. ruff check --fix after .py edits (lint, not just format)
 *   2. mypy --strict on edited src/shoal/ files (type gate)
 *   3. Block pip install (enforce uv)
 */

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { exec as execCb } from "child_process";
import { promisify } from "util";

const exec = promisify(execCb);

export default function shoalDev(pi: ExtensionAPI): void {
  pi.setLabel("shoal-dev");

  // ── 1. ruff check --fix after .py edits ──────────────────────────────────
  //
  // devtools runs `ruff format` (format only). This adds `ruff check --fix`
  // (lint + auto-fix) for immediate feedback on rule violations.
  // Fire-and-forget: output shown if there are unfixable issues.
  pi.on("tool_result", async (event) => {
    if (event.isError) return;
    if (event.toolName !== "edit" && event.toolName !== "write") return;

    const filePath = (event.input as Record<string, unknown>)?.path as string | undefined;
    if (!filePath?.endsWith(".py")) return;

    try {
      const { stdout, stderr } = await exec(
        `uv run ruff check --fix "${filePath}" 2>&1 | head -8`,
        { timeout: 15_000, shell: "/bin/sh" }
      );
      const output = (stdout + stderr).trim();
      if (output) {
        return {
          details: { "ruff check": output },
        };
      }
    } catch {
      // ruff not available or file transiently missing — not a hard error
    }
  });

  // ── 2. mypy --strict on edited src/shoal/ files ──────────────────────────
  //
  // Only runs on files under src/shoal/ (source, not tests or examples).
  // Reports first 8 errors for immediate feedback. Fire-and-forget on failure.
  pi.on("tool_result", async (event) => {
    if (event.isError) return;
    if (event.toolName !== "edit" && event.toolName !== "write") return;

    const filePath = (event.input as Record<string, unknown>)?.path as string | undefined;
    if (!filePath?.endsWith(".py")) return;

    // Only type-check files inside src/shoal/
    if (!filePath.includes("src/shoal/")) return;

    try {
      const { stdout, stderr } = await exec(
        `uv run mypy --strict --no-error-summary "${filePath}" 2>&1 | head -8`,
        { timeout: 30_000, shell: "/bin/sh" }
      );
      const output = (stdout + stderr).trim();
      if (output && !output.includes("Success:")) {
        return {
          details: { "mypy --strict": output },
        };
      }
    } catch {
      // mypy not available or transient failure — not a hard error
    }
  });

  // ── 3. Block pip install — enforce uv ────────────────────────────────────
  //
  // shoal uses uv exclusively. pip install in this project is always wrong.
  pi.on("tool_call", async (event) => {
    if (event.toolName !== "bash") return;

    const cmd = String((event.input as Record<string, unknown>)?.command ?? "");

    if (/\bpip\s+install\b/.test(cmd) && !/\buv\s+pip\b/.test(cmd)) {
      return {
        block: true,
        reason: "shoal uses uv, not pip. Use `uv add <package>` or `uv sync` instead.",
      };
    }
  });
}
