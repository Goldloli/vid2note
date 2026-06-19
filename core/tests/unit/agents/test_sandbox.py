from vid2note_core.agents.sandbox import SandboxPolicy


def test_sandbox_profile_denies_live_vault_and_allows_only_run_writes(tmp_path):
    vault = tmp_path / "vault"
    workspace = tmp_path / "workspace"
    runtime_home = tmp_path / "runtime-home"
    policy = SandboxPolicy(vault, workspace, runtime_home)

    profile = policy.profile()

    assert f'(deny file-read* file-write* (subpath "{vault}"))' in profile
    assert f'(allow file-read* file-write* (subpath "{workspace}"))' in profile
    assert f'(allow file-read* file-write* (subpath "{runtime_home}"))' in profile


def test_external_runtime_is_disabled_without_platform_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr("vid2note_core.agents.sandbox.shutil.which", lambda _: None)
    policy = SandboxPolicy(tmp_path / "vault", tmp_path / "work", tmp_path / "home")

    assert not policy.available
    assert policy.unavailable_reason == "sandbox_unavailable"
