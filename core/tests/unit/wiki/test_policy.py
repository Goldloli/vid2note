import pytest
from vid2note_core.wiki.policy import AutonomyMode, AutonomyPolicy


@pytest.mark.parametrize(
    ("mode", "kind", "decision"),
    [
        ("approval", "enhancement", "require_approval"),
        ("auto-revertible", "enhancement", "auto_apply"),
        ("high-autonomy", "contradiction", "require_approval"),
        ("high-autonomy", "correction", "require_approval"),
    ],
)
def test_policy(mode, kind, decision):
    assert AutonomyPolicy(AutonomyMode(mode)).decide(kind) == decision


def test_default_autonomy_mode_is_approval():
    assert AutonomyPolicy().mode is AutonomyMode.APPROVAL
