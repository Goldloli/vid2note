"""macOS Keychain 适配"""
import subprocess
from typing import Optional


class KeychainStore:
    """用 macOS security 命令存取敏感数据"""
    SERVICE = "vid2note"

    def set(self, key: str, value: str) -> None:
        subprocess.run(
            ["security", "add-generic-password", "-s", self.SERVICE, "-a", key, "-w", value, "-U"],
            check=True, capture_output=True,
        )

    def get(self, key: str) -> Optional[str]:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", self.SERVICE, "-a", key, "-w"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def delete(self, key: str) -> None:
        subprocess.run(
            ["security", "delete-generic-password", "-s", self.SERVICE, "-a", key],
            check=False, capture_output=True,
        )
