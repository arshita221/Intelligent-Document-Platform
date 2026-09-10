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
