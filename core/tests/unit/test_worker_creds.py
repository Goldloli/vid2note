"""测试 worker._resolve_llm_creds（provider→API key/model 解析）。"""

from vid2note_core.worker import _resolve_llm_config, _resolve_llm_creds


def test_qwen_reads_dashscope_key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123")
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    key, model = _resolve_llm_creds("qwen")
    assert key == "sk-test-123"
    assert model == "qwen-turbo"


def test_model_overridable_via_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-x")
    monkeypatch.setenv("QWEN_MODEL", "qwen-max")
    _, model = _resolve_llm_creds("qwen")
    assert model == "qwen-max"


def test_glm_reads_zhipu_key(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")
    monkeypatch.delenv("GLM_MODEL", raising=False)
    key, model = _resolve_llm_creds("glm")
    assert key == "zhipu-key"
    assert model == "glm-4-flash"


def test_missing_key_returns_empty_string(monkeypatch):
    """环境变量未设置时应返回空串（而非抛错，交给 LLM 构造时失败）。"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    key, _ = _resolve_llm_creds("qwen")
    assert key == ""


def test_unknown_provider_falls_back(monkeypatch):
    """未知 provider 用 {PROVIDER}_API_KEY 兜底。"""
    monkeypatch.setenv("FOO_API_KEY", "foo-key")
    key, _ = _resolve_llm_creds("foo")
    assert key == "foo-key"


def test_baidu_reads_api_key(monkeypatch):
    monkeypatch.delenv("BAICHUAN_API_KEY", raising=False)
    monkeypatch.setenv("BAIDU_API_KEY", "baidu-key")
    key, _ = _resolve_llm_creds("baidu")
    assert key == "baidu-key"


def test_baidu_reads_secret_key(monkeypatch):
    monkeypatch.setenv("BAIDU_API_KEY", "baidu-key")
    monkeypatch.setenv("BAIDU_SECRET_KEY", "baidu-secret")

    config = _resolve_llm_config("baidu")

    assert config["api_key"] == "baidu-key"
    assert config["secret_key"] == "baidu-secret"
