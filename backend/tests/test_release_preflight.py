"""开源发布预检脚本的安全回归测试。"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "release_preflight.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("release_preflight", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_secret_scan_reports_fingerprint_without_plaintext():
    module = _load_module()
    secret = "sk-" + "not-a-real-provider-fixture-12345"
    findings = module.scan_secret_patterns("fixture.txt", secret.encode())

    assert len(findings) == 1
    finding = findings[0]
    assert finding.fingerprint == hashlib.sha256(secret.encode()).hexdigest()[:16]
    assert secret not in finding.render()


def test_known_fixture_fingerprint_is_classified_as_allowed():
    module = _load_module()
    secret = "sk-" + "not-a-real-provider-fixture-12345"
    fingerprint = hashlib.sha256(secret.encode()).hexdigest()[:16]
    findings = module.scan_secret_patterns(
        "fixture.txt",
        secret.encode(),
        allowed_fingerprints={fingerprint},
    )

    assert findings[0].allowed is True
    assert module.actionable(findings) == []


def test_personal_paths_are_blocking_but_generic_paths_are_allowed():
    module = _load_module()
    tracked = {
        "private.md": (
            b"cd /Users/" + b"gejiawei/project\n/Volumes/" + b"worknie/media"
        ),
        "public.md": b"cd <repo>\n/app/data\n<workspace>/media",
    }

    findings = module.check_personal_paths(tracked)

    assert {(item.path, item.rule) for item in findings} == {
        ("private.md", "personal_path"),
    }


def test_sensitive_runtime_files_are_rejected_but_env_example_is_allowed():
    module = _load_module()
    findings = module.check_sensitive_paths(
        [".env", ".env.example", "data/config/master.key", "README.md"]
    )

    assert {item.path for item in findings} == {
        ".env",
        "data/config/master.key",
    }


def test_dependency_gate_rejects_pymupdf_and_agpl_node_package():
    module = _load_module()
    lock = {
        "packages": {
            "": {},
            "node_modules/permissive": {"version": "1.0.0", "license": "MIT"},
            "node_modules/restricted": {"version": "2.0.0", "license": "AGPL-3.0"},
        }
    }

    findings = module.check_dependency_manifests(
        "pypdf==6.14.2\nPyMuPDF==1.28.0\n",
        lock,
    )

    assert {item.rule for item in findings} == {
        "restricted_python_dependency",
        "restricted_node_license",
    }
