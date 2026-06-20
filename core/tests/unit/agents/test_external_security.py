from vid2note_core.agents.external import RUNTIME_NETWORK_TARGETS
from vid2note_core.agents.registry import RUNTIME_AUTH_ENV


def test_external_runtimes_have_explicit_auth_and_network_allowlists():
    assert RUNTIME_AUTH_ENV["codex"] == {"OPENAI_API_KEY", "CODEX_API_KEY"}
    assert RUNTIME_AUTH_ENV["claude"] == {"ANTHROPIC_API_KEY"}
    assert RUNTIME_NETWORK_TARGETS["codex"] == {
        ("api.openai.com", 443),
        ("chatgpt.com", 443),
        ("auth.openai.com", 443),
    }
    assert RUNTIME_NETWORK_TARGETS["claude"] == {("api.anthropic.com", 443)}
