import os
from app.core.config import Settings

def test_settings_environment_loading_safe():
    # Test placeholder detection
    s = Settings(GROQ_API_KEY="your_groq_api_key_here")
    assert s.GROQ_API_KEY == ""
    assert s.is_groq_api_key_configured is False

    # Test quote stripping
    s_quoted = Settings(GROQ_API_KEY='"gsk_TestKeyForUnitTestingOnly12345"')
    assert s_quoted.GROQ_API_KEY == "gsk_TestKeyForUnitTestingOnly12345"
    assert s_quoted.is_groq_api_key_configured is True

    # Test default model setting
    s_model = Settings(GROQ_MODEL="qwen/qwen3.8-27b")
    assert s_model.GROQ_MODEL == "qwen/qwen3.8-27b"

    # Test empty key
    s_empty = Settings(GROQ_API_KEY="")
    assert s_empty.GROQ_API_KEY == ""
    assert s_empty.is_groq_api_key_configured is False


def test_groq_429_token_limit_and_single_retry(monkeypatch):
    from app.services.groq_service import extract_with_groq
    from app.schemas.extraction import RawTextPage

    calls = []

    class MockCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                # Simulate 429 output token limit error on 1st attempt
                raise Exception("Request too large for model qwen/qwen3.8-27b: Limit 1000, Requested 950. Please reduce max_tokens.")
            else:
                # Success on 2nd attempt
                class Choice:
                    message = type("Message", (), {"content": '{"document_type": "invoice", "fields": []}'})
                return type("Response", (), {"choices": [Choice()]})

    class MockGroqClient:
        def __init__(self, api_key):
            self.chat = type("Chat", (), {"completions": MockCompletions()})

    monkeypatch.setattr("groq.Groq", MockGroqClient)
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk_TestKeyForUnitTestingOnly12345")

    ext = extract_with_groq("invoice", [RawTextPage(page_number=1, text="Invoice #123")], [])

    assert len(calls) == 2
    assert calls[0]["max_tokens"] == 950
    assert calls[1]["max_tokens"] == 700
    assert ext.document_type == "invoice"

