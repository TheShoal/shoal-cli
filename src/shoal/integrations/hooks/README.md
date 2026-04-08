# Pisces Heartbeat Hook

This hook allows Pisces agents to push their status updates to the Shoal dashboard at the end of every turn and when the agent finishes.

## Enabling the Hook

To enable this hook in your Pisces agent configuration, add the `shoal_heartbeat.ts` module to your agent's hook pipeline.

The hook expects the following environment variables to be set:
- `SHOAL_SESSION`: The current Shoal session ID.
- `SHOAL_PORT`: The port Shoal is running on (defaults to 8484).
