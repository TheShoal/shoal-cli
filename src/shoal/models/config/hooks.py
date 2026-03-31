"""Project-local lifecycle hook model (.shoal/hooks.toml)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class ProjectHookEntry(BaseModel):
    """One entry from .shoal/hooks.toml [[hooks]] array.

    event: LifecycleEvent name (e.g. ``status_changed``, ``session_completed``).
    when_status: if set, the hook only fires when new_status matches this value.
               Only meaningful for ``status_changed`` events.
    command: shell command string executed via ``sh -c``.  The following
             environment variables are injected before execution:

             SHOAL_EVENT          — the LifecycleEvent name
             SHOAL_SESSION_ID     — session UUID
             SHOAL_SESSION_NAME   — session display name
             SHOAL_OLD_STATUS     — previous status (status_changed only)
             SHOAL_NEW_STATUS     — new status (status_changed only)
    """

    model_config = ConfigDict(extra="forbid")

    event: str
    when_status: str = ""
    command: str

    @field_validator("event")
    @classmethod
    def validate_event(cls, v: str) -> str:
        if v not in _LIFECYCLE_EVENT_VALUES:
            raise ValueError(
                f"Unknown lifecycle event '{v}'. Valid: {sorted(_LIFECYCLE_EVENT_VALUES)}"
            )
        return v

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("command must not be empty")
        return v


# Sentinel set populated at module level to avoid a circular import in the
# field_validator above.  LifecycleEvent is defined in models.state which does
# not import models.config, so this is safe.
_LIFECYCLE_EVENT_VALUES: set[str] = set()  # filled by _init_lifecycle_event_values()


def _init_lifecycle_event_values() -> None:  # called once at bottom of this file
    from shoal.models.state import LifecycleEvent

    _LIFECYCLE_EVENT_VALUES.update(e.value for e in LifecycleEvent)


_init_lifecycle_event_values()
