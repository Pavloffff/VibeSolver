from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapter.config import Settings
from app.adapter.sandbox_executor import (
    DockerSandboxCommandBuilder,
    SandboxDisabledError,
    SandboxPlanError,
)
from app.domain.sandbox import SandboxExecutionConfig, SandboxExecutionRequest


def test_sandbox_is_disabled_by_default() -> None:
    config = SandboxExecutionConfig(image="registry.example/test@sha256:" + "a" * 64)
    builder = DockerSandboxCommandBuilder(config)
    request = SandboxExecutionRequest(snapshot_path=".", command=["pytest", "-q"])

    with pytest.raises(SandboxDisabledError):
        builder.build(request)


def test_backend_sandbox_flag_defaults_to_disabled() -> None:
    assert Settings(_env_file=None).experimental_sandbox_enabled is False


def test_command_builder_uses_enabled_runtime_settings() -> None:
    image = "registry.example/test@sha256:" + "c" * 64
    settings = Settings(
        _env_file=None,
        experimental_sandbox_enabled=True,
        experimental_sandbox_image=image,
        experimental_sandbox_memory_mb=1024,
    )
    request = SandboxExecutionRequest(snapshot_path=str(Path(__file__).parent), command=["pytest"])

    plan = DockerSandboxCommandBuilder.from_settings(settings).build(request)

    assert image in plan.argv
    assert "--memory=1024m" in plan.argv


def test_docker_plan_has_required_isolation_and_keeps_argv_boundaries() -> None:
    config = SandboxExecutionConfig(
        enabled=True,
        image="registry.example/test@sha256:" + "a" * 64,
    )
    request = SandboxExecutionRequest(
        snapshot_path=str(Path(__file__).parent), command=["pytest", "-k", "case with spaces"]
    )

    plan = DockerSandboxCommandBuilder(config).build(request)
    argv = plan.argv

    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert "--rm" in argv
    assert "--pull=never" in argv
    assert "--cap-drop=ALL" in argv
    assert "--security-opt=no-new-privileges" in argv
    assert "--user=65532:65532" in argv
    assert "--cpus=1.0" in argv
    assert "--memory=512m" in argv
    assert "--pids-limit=128" in argv
    assert any(value.startswith("type=bind,source=") and value.endswith(",target=/input,readonly") for value in argv)
    assert any(
        value.startswith("/workspace:rw,exec,nosuid,nodev,uid=65532,gid=65532,mode=0755,size=")
        for value in argv
    )
    assert argv[-3:] == ("pytest", "-k", "case with spaces")
    assert plan.timeout_seconds == 60
    assert plan.max_output_bytes == 65_536


def test_docker_plan_rejects_unpinned_images() -> None:
    config = SandboxExecutionConfig(enabled=True, image="python:3.12-slim")
    request = SandboxExecutionRequest(snapshot_path=str(Path(__file__).parent), command=["pytest"])

    with pytest.raises(SandboxPlanError, match="digest"):
        DockerSandboxCommandBuilder(config).build(request)


def test_docker_plan_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        SandboxExecutionConfig(enabled=True, image="image@sha256:" + "b" * 64, memory_mb=0)


def test_sandbox_request_rejects_nul_in_command() -> None:
    with pytest.raises(ValidationError):
        SandboxExecutionRequest(snapshot_path=".", command=["pytest\x00"])
