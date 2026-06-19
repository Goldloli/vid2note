from enum import StrEnum
from typing import Literal


class AutonomyMode(StrEnum):
    APPROVAL = "approval"
    AUTO_REVERTIBLE = "auto-revertible"
    HIGH_AUTONOMY = "high-autonomy"


PolicyDecision = Literal["require_approval", "auto_apply", "no_action"]


class AutonomyPolicy:
    def __init__(self, mode: AutonomyMode = AutonomyMode.APPROVAL):
        self.mode = mode

    def decide(self, kind: str) -> PolicyDecision:
        if kind == "duplicate":
            return "no_action"
        if self.mode is AutonomyMode.APPROVAL:
            return "require_approval"
        if kind in {"contradiction", "correction"}:
            return "require_approval"
        return "auto_apply"
