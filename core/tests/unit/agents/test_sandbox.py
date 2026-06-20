import platform
import subprocess

import pytest
from vid2note_core.agents.sandbox import SandboxPolicy


def test_sandbox_profile_denies_live_vault_and_allows_only_run_writes(tmp_path):
    vault = tmp_path / "vault"
    workspace = vault / ".vid2note" / "agent-runs" / "run_0123456789ab" / "workspace"
    runtime_home = workspace.parent / "runtime-home"
    executable = tmp_path / "Applications" / "Codex.app" / "codex"
    policy = SandboxPolicy(
        vault,
        workspace,
        runtime_home,
        proxy_port=43123,
        executable=executable,
    )

    profile = policy.profile()

    assert "(deny default)" in profile
    assert "(allow default)" not in profile
    assert "(allow network*)" not in profile
    assert '(remote tcp "localhost:43123")' in profile
    assert f'(allow file-read* (literal "{executable}"))' in profile
    assert f'(allow file-read-metadata (literal "{executable.parent}"))' in profile
    assert f'(subpath "{executable.parent}")' not in profile
    assert f'(allow file-read* file-write* (subpath "{workspace}"))' in profile
    assert f'(allow file-read* file-write* (subpath "{runtime_home}"))' in profile


@pytest.mark.skipif(platform.system() != "Darwin", reason="sandbox-exec is macOS-only")
def test_real_sandbox_allows_nested_run_dirs_but_denies_vault_and_external_paths(tmp_path):
    vault = tmp_path / "vault"
    workspace = vault / ".vid2note" / "agent-runs" / "run_0123456789ab" / "workspace"
    runtime_home = workspace.parent / "runtime-home"
    vault.mkdir()
    workspace.mkdir(parents=True)
    runtime_home.mkdir()
    vault_secret = vault / "secret.md"
    external_secret = tmp_path / "outside.md"
    vault_secret.write_text("vault secret", encoding="utf-8")
    external_secret.write_text("external secret", encoding="utf-8")
    custom_cli = tmp_path / "user-bin" / "agent"
    custom_cli.parent.mkdir()
    custom_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    custom_cli.chmod(0o755)
    policy = SandboxPolicy(vault, workspace, runtime_home, executable=custom_cli)

    assert policy.available

    def run(script: str):
        command, args = policy.wrap("/bin/sh", ["-c", script])
        return subprocess.run([command, *args], capture_output=True, check=False)

    assert run(f'/usr/bin/touch "{workspace / "created.md"}"').returncode == 0
    assert run(f'/usr/bin/touch "{runtime_home / "state.json"}"').returncode == 0
    assert run(f'/bin/cat "{vault_secret}"').returncode != 0
    assert run(f'/bin/cat "{external_secret}"').returncode != 0
    assert run(f'/usr/bin/touch "{tmp_path / "escaped"}"').returncode != 0
    assert run("/usr/bin/nc -z -G 1 1.1.1.1 443").returncode != 0
    command, args = policy.wrap(str(custom_cli), [])
    assert subprocess.run([command, *args], capture_output=True, check=False).returncode == 0


def test_external_runtime_is_disabled_without_platform_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr("vid2note_core.agents.sandbox.shutil.which", lambda _: None)
    policy = SandboxPolicy(tmp_path / "vault", tmp_path / "work", tmp_path / "home")

    assert not policy.available
    assert policy.unavailable_reason == "sandbox_unavailable"
