#!/usr/bin/env python3
"""开源发布前的本地安全与合规预检。

脚本只输出文件、规则和不可逆短指纹，永不回显凭据原文。依赖漏洞仍由
``pip-audit`` 与 ``npm audit`` 负责；这里负责仓库内容、许可证元数据和密钥历史。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


MAX_BLOB_BYTES = 50_000_000
KNOWN_FIXTURE_FINGERPRINTS = frozenset({"96ad4cc42109c038"})
PERSONAL_MARKERS = (
    b"/Users/" + b"gejiawei",
    b"/Volumes/" + b"worknie",
)
RESTRICTED_LICENSE = re.compile(r"(?:AGPL|SSPL|BUSL|COMMONS[ -]CLAUSE)", re.I)
SENSITIVE_NAME = re.compile(r"(?:api.?key|token|secret|password|cookie)", re.I)
PLACEHOLDER = re.compile(
    rb"(?i)^(?:your[-_ ]?key|changeme|change[-_ ]?me|example|placeholder|"
    rb"dummy|test|xxx+|none|null|<.*>|\$\{.*\})$"
)
SECRET_PATTERNS = (
    ("provider_sk", re.compile(rb"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("google_api_key", re.compile(rb"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{30,}")),
    ("aws_access_key", re.compile(rb"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])")),
    ("slack_token", re.compile(rb"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private_key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


class Finding:
    """不携带原始秘密值的预检发现。"""

    __slots__ = ("rule", "path", "line", "fingerprint", "allowed", "severity", "detail")

    def __init__(
        self,
        rule: str,
        path: str,
        *,
        line: int = 0,
        fingerprint: str = "",
        allowed: bool = False,
        severity: str = "error",
        detail: str = "",
    ) -> None:
        self.rule = rule
        self.path = path
        self.line = line
        self.fingerprint = fingerprint
        self.allowed = allowed
        self.severity = severity
        self.detail = detail

    def to_dict(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "path": self.path,
            "line": self.line,
            "fingerprint": self.fingerprint,
            "allowed": self.allowed,
            "severity": self.severity,
            "detail": self.detail,
        }

    def render(self) -> str:
        location = self.path + (f":{self.line}" if self.line else "")
        fingerprint = f" fingerprint={self.fingerprint}" if self.fingerprint else ""
        allowed = " allowed=true" if self.allowed else ""
        detail = f" {self.detail}" if self.detail else ""
        return f"[{self.severity}] {self.rule} {location}{fingerprint}{allowed}{detail}"


def _fingerprint(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()[:16]


def actionable(findings: Iterable[Finding]) -> list[Finding]:
    return [item for item in findings if not item.allowed and item.severity == "error"]


def scan_secret_patterns(
    path: str,
    data: bytes,
    *,
    allowed_fingerprints: set[str] | frozenset[str] = frozenset(),
) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str, int]] = set()
    for rule, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(data):
            fingerprint = _fingerprint(match.group(0))
            line = data.count(b"\n", 0, match.start()) + 1
            identity = (rule, fingerprint, line)
            if identity in seen:
                continue
            seen.add(identity)
            allowed = fingerprint in allowed_fingerprints
            findings.append(
                Finding(
                    rule,
                    path,
                    line=line,
                    fingerprint=fingerprint,
                    allowed=allowed,
                    severity="info" if allowed else "error",
                )
            )
    return findings


def check_personal_paths(tracked: Mapping[str, bytes]) -> list[Finding]:
    findings: list[Finding] = []
    for path, data in tracked.items():
        offsets = [data.find(marker) for marker in PERSONAL_MARKERS]
        offsets = [offset for offset in offsets if offset >= 0]
        if offsets:
            offset = min(offsets)
            findings.append(
                Finding("personal_path", path, line=data.count(b"\n", 0, offset) + 1)
            )
    return findings


def check_sensitive_paths(paths: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        name = path.name.lower()
        is_env = name == ".env" or (name.startswith(".env.") and name != ".env.example")
        is_runtime_secret = name in {"credentials.enc", "master.key"}
        is_private_key = path.suffix.lower() in {".p12", ".pfx", ".key"}
        if is_env or is_runtime_secret or is_private_key:
            findings.append(Finding("tracked_sensitive_path", raw_path))
    return findings


def check_dependency_manifests(
    requirements_text: str,
    package_lock: Mapping[str, object],
) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, raw_line in enumerate(requirements_text.splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0]
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized == "pymupdf":
            findings.append(
                Finding(
                    "restricted_python_dependency",
                    "backend/requirements.txt",
                    line=line_number,
                    detail="PyMuPDF 使用 AGPL/商业双许可",
                )
            )

    packages = package_lock.get("packages", {})
    if isinstance(packages, Mapping):
        for package_path, metadata in packages.items():
            if not package_path or not isinstance(metadata, Mapping):
                continue
            license_name = str(metadata.get("license") or "")
            if RESTRICTED_LICENSE.search(license_name):
                findings.append(
                    Finding(
                        "restricted_node_license",
                        str(package_path),
                        detail=f"license={license_name}",
                    )
                )
    return findings


def _git(repo_root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo_root,
        input=input_bytes,
        stderr=subprocess.DEVNULL,
    )


def tracked_files(repo_root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for raw_path in _git(
        repo_root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", "replace")
        file_path = repo_root / path
        try:
            if file_path.stat().st_size <= MAX_BLOB_BYTES:
                result[path] = file_path.read_bytes()
        except OSError:
            continue
    return result


def reachable_blobs(repo_root: Path) -> list[tuple[str, list[str], bytes]]:
    paths_by_sha: dict[str, set[str]] = defaultdict(set)
    object_ids: list[str] = []
    for line in _git(repo_root, "rev-list", "--objects", "--all").decode().splitlines():
        sha, separator, path = line.partition(" ")
        object_ids.append(sha)
        if separator:
            paths_by_sha[sha].add(path)

    unique_ids = list(dict.fromkeys(object_ids))
    if not unique_ids:
        return []
    batch = ("\n".join(unique_ids) + "\n").encode()
    checks = _git(
        repo_root,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=batch,
    ).decode().splitlines()
    blobs: list[tuple[str, list[str], bytes]] = []
    for line in checks:
        sha, object_type, size_text = line.split(" ", 2)
        if object_type != "blob" or int(size_text) > MAX_BLOB_BYTES:
            continue
        data = _git(repo_root, "cat-file", "blob", sha)
        paths = sorted(paths_by_sha.get(sha) or {"<historical-blob>"})
        blobs.append((sha, paths, data))
    return blobs


def _add_local_secret(target: dict[str, bytes], label: str, value: object) -> None:
    if not isinstance(value, (str, bytes)):
        return
    raw = value.encode() if isinstance(value, str) else value
    raw = raw.strip().strip(b"\"'")
    if len(raw) >= 8 and not PLACEHOLDER.match(raw):
        target[label] = raw


def load_local_secrets(repo_root: Path) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    env_path = repo_root / ".env"
    if env_path.is_file():
        for line in env_path.read_bytes().splitlines():
            line = line.strip()
            if not line or line.startswith(b"#") or b"=" not in line:
                continue
            key, value = line.split(b"=", 1)
            name = key.decode("utf-8", "replace").strip()
            if SENSITIVE_NAME.search(name):
                _add_local_secret(values, f"env:{name}", value)

    credentials_path = repo_root / "data/config/credentials.enc"
    key_path = repo_root / "data/config/master.key"
    if credentials_path.is_file() and key_path.is_file():
        try:
            from cryptography.fernet import Fernet

            plaintext = Fernet(key_path.read_bytes().strip()).decrypt(
                credentials_path.read_bytes()
            )
            document = json.loads(plaintext.decode("utf-8"))
        except Exception:  # noqa: BLE001 - 预检只报告不可读，不输出异常内容
            return values

        def walk(item: object, prefix: str = "credentials") -> None:
            if isinstance(item, Mapping):
                for key, value in item.items():
                    walk(value, f"{prefix}:{key}")
            elif isinstance(item, list):
                for index, value in enumerate(item):
                    walk(value, f"{prefix}:{index}")
            elif SENSITIVE_NAME.search(prefix):
                _add_local_secret(values, prefix, item)

        walk(document)
    return values


def check_governance(repo_root: Path) -> list[Finding]:
    required = (
        "LICENSE",
        "NOTICE",
        "README.md",
        "README_EN.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
    )
    findings = [
        Finding("missing_governance_file", path)
        for path in required
        if not (repo_root / path).is_file()
    ]
    markdown_link = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
    for path in required:
        if not path.lower().endswith(".md"):
            continue
        file_path = repo_root / path
        if not file_path.is_file():
            continue
        text = file_path.read_text(encoding="utf-8")
        for match in markdown_link.finditer(text):
            target = match.group(1).split("#", 1)[0]
            if target and not (file_path.parent / target).exists():
                findings.append(
                    Finding(
                        "broken_relative_link",
                        path,
                        line=text.count("\n", 0, match.start()) + 1,
                        detail=f"target={target}",
                    )
                )
    return findings


def run_preflight(repo_root: Path, *, scan_history: bool = True) -> list[Finding]:
    tracked = tracked_files(repo_root)
    findings: list[Finding] = []
    findings.extend(check_sensitive_paths(sorted(tracked)))
    findings.extend(check_personal_paths(tracked))
    findings.extend(check_governance(repo_root))

    requirements = (repo_root / "backend/requirements.txt").read_text(encoding="utf-8")
    package_lock = json.loads(
        (repo_root / "frontend/package-lock.json").read_text(encoding="utf-8")
    )
    findings.extend(check_dependency_manifests(requirements, package_lock))

    for path, data in tracked.items():
        findings.extend(
            scan_secret_patterns(
                path,
                data,
                allowed_fingerprints=KNOWN_FIXTURE_FINGERPRINTS,
            )
        )

    if scan_history:
        local_secrets = load_local_secrets(repo_root)
        seen_pattern_hits: set[tuple[str, str, str]] = set()
        for sha, paths, data in reachable_blobs(repo_root):
            display_path = paths[0]
            for item in scan_secret_patterns(
                display_path,
                data,
                allowed_fingerprints=KNOWN_FIXTURE_FINGERPRINTS,
            ):
                identity = (item.rule, item.fingerprint, sha)
                if identity not in seen_pattern_hits:
                    seen_pattern_hits.add(identity)
                    item.detail = f"blob={sha[:12]}"
                    findings.append(item)
            for label, secret in local_secrets.items():
                if secret in data:
                    findings.append(
                        Finding(
                            "local_secret_exact_match",
                            display_path,
                            fingerprint=_fingerprint(secret),
                            detail=f"source={label} blob={sha[:12]}",
                        )
                    )

    emails = set(_git(repo_root, "log", "--all", "--format=%ae").decode().splitlines())
    if any(email and not email.endswith("@users.noreply.github.com") for email in emails):
        findings.append(
            Finding(
                "public_author_email",
                "<git-history>",
                severity="warning",
                detail="存在非 noreply 提交邮箱，需所有者确认是否接受公开",
            )
        )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="vid2note 开源发布预检")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-history", action="store_true", help="仅扫描当前跟踪树")
    parser.add_argument("--json", action="store_true", help="输出不含秘密原文的 JSON")
    args = parser.parse_args(argv)

    findings = run_preflight(args.repo.resolve(), scan_history=not args.no_history)
    errors = actionable(findings)
    payload = {
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": sum(item.severity == "warning" for item in findings),
        "allowed_count": sum(item.allowed for item in findings),
        "findings": [item.to_dict() for item in findings],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"release-preflight: {'PASS' if payload['ok'] else 'FAIL'} "
            f"errors={payload['error_count']} warnings={payload['warning_count']} "
            f"allowed={payload['allowed_count']}"
        )
        for item in findings:
            print(item.render())
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
