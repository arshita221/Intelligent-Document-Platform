import os
from app.core.config import Settings

def test_settings_environment_loading_safe():
    # Test placeholder detection
    s = Settings(GEMINI_API_KEY="your_gemini_api_key_here")
    assert s.GEMINI_API_KEY == ""
    assert s.is_gemini_api_key_configured is False

    # Test quote stripping
    s_quoted = Settings(GEMINI_API_KEY='"AIzaSyTestKeyForUnitTestingOnly12345"')
    assert s_quoted.GEMINI_API_KEY == "AIzaSyTestKeyForUnitTestingOnly12345"
    assert s_quoted.is_gemini_api_key_configured is True

    # Test default model setting
    s_model = Settings(GEMINI_MODEL="gemini-3.6-flash")
    assert s_model.GEMINI_MODEL == "gemini-3.6-flash"

    # Test empty key
    s_empty = Settings(GEMINI_API_KEY="")
    assert s_empty.GEMINI_API_KEY == ""
    assert s_empty.is_gemini_api_key_configured is False
