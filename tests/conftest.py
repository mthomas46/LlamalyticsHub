import os
import pytest
from fastapi.testclient import TestClient
from fastapi_app import app
from unittest.mock import patch

@pytest.fixture(scope="session", autouse=True)
def set_testing_env():
    os.environ["TESTING"] = "true"

@pytest.fixture
def client():
    with patch('fastapi_app.rate_limiter') as mock_limiter:
        mock_limiter.is_allowed.return_value = True
        yield TestClient(app)

@pytest.fixture
def mock_llm(monkeypatch):
    from ollama_code_llama import OllamaCodeLlama
    monkeypatch.setattr(OllamaCodeLlama, "generate", lambda self, prompt: "Mocked LLM response")
    return OllamaCodeLlama() 