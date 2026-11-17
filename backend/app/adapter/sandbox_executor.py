import re
from pathlib import Path

from app.adapter.config import Settings
from app.domain.sandbox import (
    SandboxExecutionConfig,
    SandboxExecutionPlan,
    SandboxExecutionRequest,
)

_DIGEST_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$")
_CONTAINER_PRELUDE = (
    'cp -R /input/. /workspace/ && chmod -R u+rwX /workspace '
    '&& cd /workspace && exec "$@"'
)


class SandboxDisabledError(RuntimeError):
    pass


class SandboxPlanError(ValueError):
    pass


class DockerSandboxCommandBuilder:
    def __init__(self, config: SandboxExecutionConfig) -> None:
        self._config = config

    @classmethod
    def from_settings(cls, settings: Settings) -> "DockerSandboxCommandBuilder":
        return cls(
            SandboxExecutionConfig(
                enabled=settings.experimental_sandbox_enabled,
                image=settings.experimental_sandbox_image,
                cpus=settings.experimental_sandbox_cpus,
                memory_mb=settings.experimental_sandbox_memory_mb,
                pids_limit=settings.experimental_sandbox_pids_limit,
                timeout_seconds=settings.experimental_sandbox_timeout_seconds,
                workspace_mb=settings.experimental_sandbox_workspace_mb,
                max_output_bytes=settings.experimental_sandbox_max_output_bytes,
            )
        )

    def build(self, request: SandboxExecutionRequest) -> SandboxExecutionPlan:
        if not self._config.enabled:
            raise SandboxDisabledError("experimental sandbox execution is disabled")
        if not _DIGEST_IMAGE.fullmatch(self._config.image):
            raise SandboxPlanError("sandbox image must be pinned by a sha256 digest")

        snapshot = Path(request.snapshot_path).expanduser().resolve(strict=True)
        if not snapshot.is_dir():
            raise SandboxPlanError("sandbox input must be an existing snapshot directory")
        workspace_source = str(snapshot).replace("\\", "/")
        if "," in workspace_source:
            raise SandboxPlanError("sandbox snapshot paths cannot contain commas")

        argv = (
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--read-only",
            f"--cpus={self._config.cpus}",
            f"--memory={self._config.memory_mb}m",
            f"--pids-limit={self._config.pids_limit}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65532:65532",
            "--mount",
            f"type=bind,source={workspace_source},target=/input,readonly",
            "--tmpfs",
            f"/workspace:rw,exec,nosuid,nodev,uid=65532,gid=65532,mode=0755,size={self._config.workspace_mb}m",
            "--workdir",
            "/workspace",
            self._config.image,
            "/bin/sh",
            "-c",
            _CONTAINER_PRELUDE,
            "sandbox-runner",
            *request.command,
        )
        return SandboxExecutionPlan(
            argv=argv,
            timeout_seconds=self._config.timeout_seconds,
            max_output_bytes=self._config.max_output_bytes,
        )
