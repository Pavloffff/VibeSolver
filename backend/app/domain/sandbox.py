from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SandboxExecutionConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    enabled: bool = False
    image: str = ""
    cpus: float = Field(default=1.0, gt=0, le=4)
    memory_mb: int = Field(default=512, ge=128, le=8192)
    pids_limit: int = Field(default=128, ge=1, le=256)
    timeout_seconds: int = Field(default=60, ge=1, le=1800)
    workspace_mb: int = Field(default=512, ge=32, le=2048)
    max_output_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)


class SandboxExecutionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    snapshot_path: str = Field(min_length=1, max_length=4096)
    command: list[str] = Field(min_length=1, max_length=64)

    @field_validator("command")
    @classmethod
    def validate_command(cls, command: list[str]) -> list[str]:
        if any(not argument or "\x00" in argument or len(argument) > 4096 for argument in command):
            raise ValueError("sandbox command arguments must be non-empty and contain no NUL")
        if sum(len(argument) for argument in command) > 16_384:
            raise ValueError("sandbox command is too long")
        return command


class SandboxExecutionPlan(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    argv: tuple[str, ...]
    timeout_seconds: int
    max_output_bytes: int


class SandboxExecutionResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxExecutor(Protocol):
    async def execute(self, request: SandboxExecutionRequest) -> SandboxExecutionResult: ...
