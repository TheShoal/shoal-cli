"""Pydantic model for Claw runtime configuration."""

from pydantic import BaseModel, ConfigDict


class ClawConfig(BaseModel):
    """Configuration for Claw runtime integration.

    This config is loaded from the [claw] section in config.toml.
    grpcio is an optional dependency - all imports must be guarded.

    Attributes:
        grpc_addr: Default gRPC address for Claw connections.
        jwt_secret: Secret for minting JWTs for Claw authentication.
        employee_id: Default employee ID for Claw operations.
        tls: Whether to use TLS for gRPC connections.
        known_claws: Dictionary mapping claw names to gRPC addresses.
    """

    model_config = ConfigDict(extra="forbid")

    grpc_addr: str = "localhost:50051"
    jwt_secret: str = ""
    employee_id: str = ""
    tls: bool = False
    known_claws: dict[str, str] = {}  # name → grpc_addr
