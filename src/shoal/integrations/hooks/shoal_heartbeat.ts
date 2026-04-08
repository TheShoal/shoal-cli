// Shoal heartbeat hook for Pisces agents
// Called at turn_end and agent_end to push status to Shoal

const SHOAL_PORT = parseInt(process.env.SHOAL_PORT || "8484", 10);
const SHOAL_SESSION = process.env.SHOAL_SESSION || "";

async function sendHeartbeat(status: string, summary: string, turnNumber?: number) {
  if (!SHOAL_SESSION) return;

  try {
    await fetch(`http://localhost:${SHOAL_PORT}/sessions/${SHOAL_SESSION}/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status,
        summary: summary.slice(0, 200),
        turn_number: turnNumber,
      }),
    });
  } catch {
    // Non-critical: heartbeat failure should not disrupt the agent
  }
}

export async function turnEnd(ctx: { summary?: string; turnNumber?: number }) {
  await sendHeartbeat("waiting", ctx.summary || "Turn complete", ctx.turnNumber);
}

export async function agentEnd() {
  await sendHeartbeat("stopped", "Agent finished");
}
