def test_openapi_exposes_typed_task_event_and_error(client):
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]

    assert "TaskEvent" in components
    assert "ErrorEnvelope" in components
    assert components["ErrorEnvelope"]["required"] == [
        "code",
        "message",
        "user_message",
        "retryable",
        "component",
        "operation",
    ]
