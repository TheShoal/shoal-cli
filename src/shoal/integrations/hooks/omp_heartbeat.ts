/**
 * Shoal heartbeat extension for omp (oh-my-pi) agents.
 *
 * Pushes status updates to the Shoal API at the end of every turn and
 * when the agent finishes.  Silent-fails on all fetch errors so the
 * agent is never disrupted by heartbeat issues.
 *
 * Install: copy/symlink to ~/.omp/agent/extensions/omp_heartbeat.ts
 * then add to ~/.omp/agent/config.yml:
 *
 *   extensions:
 *     - ~/.config/shoal/hooks/omp_heartbeat.ts
 *
 * Environment variables:
 *   SHOAL_SESSION  — Shoal session name or ID (required; hook is a no-op if unset)
 *   SHOAL_PORT     — Port the Shoal HTTP API listens on (default: 8080)
 */

const SHOAL_PORT = parseInt(process.env.SHOAL_PORT || "8080", 10);
const SHOAL_SESSION = process.env.SHOAL_SESSION || "";

async function sendHeartbeat(
  status: string,
  summary?: string,
  turnNumber?: number,
): Promise<void> {
  if (!SHOAL_SESSION) return;

  try {
    await fetch(
      `http://localhost:${SHOAL_PORT}/sessions/${SHOAL_SESSION}/heartbeat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          summary: summary ? summary.slice(0, 200) : undefined,
          turn_number: turnNumber,
        }),
      },
    );
  } catch {
    // Non-critical: heartbeat failure must not disrupt the agent
  }
}

// ---------------------------------------------------------------------------
// omp Extension API (default export)
// ---------------------------------------------------------------------------

interface TurnEndContext {
  summary?: string;
  turnNumber?: number;
}

interface AgentEndContext {
  summary?: string;
}

/**
 * omp Extension object.  omp loads extensions via their default export
 * and calls the registered event handlers at the appropriate lifecycle
 * points.
 */
const ShoalHeartbeatExtension = {
  name: "shoal-heartbeat",

  async onTurnEnd(ctx: TurnEndContext): Promise<void> {
    await sendHeartbeat(
      "waiting",
      ctx.summary || "Turn complete",
      ctx.turnNumber,
    );
  },

  async onAgentEnd(ctx: AgentEndContext): Promise<void> {
    await sendHeartbeat("stopped", ctx.summary || "Agent finished");
  },
};

export default ShoalHeartbeatExtension;

// ---------------------------------------------------------------------------
// Legacy named exports (backward compatibility with older hook-module API)
// ---------------------------------------------------------------------------

export async function turnEnd(ctx: TurnEndContext): Promise<void> {
  await ShoalHeartbeatExtension.onTurnEnd(ctx);
}

export async function agentEnd(ctx: AgentEndContext): Promise<void> {
  await ShoalHeartbeatExtension.onAgentEnd(ctx);
}
