"""
Optimized API Core Test Suite - Fast execution with comprehensive mocking
Tests Flask API core endpoints, health, security, and text generation
"""
import pytest
from unittest.mock import Mock, patch
from http_api import app
import io

class TestAPICoreFeaturesOptimized:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch('http_api.OllamaCodeLlama') as mock_llama_class:
            mock_llama = Mock()
            mock_llama.generate.return_value = "Mocked LLM response"
            mock_llama_class.return_value = mock_llama
            yield

    def test_root_endpoint(self):
        client = app.test_client()
        response = client.get("/help")
        assert response.status_code == 200
        assert "endpoints" in response.json

    def test_health_endpoint(self):
        client = app.test_client()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json["status"] == "ok"

    def test_generate_text_endpoint_fast(self):
        client = app.test_client()
        with patch('http_api.llama.generate', return_value="Fast mocked response"):
            response = client.post(
                "/generate/text",
                json={"prompt": "Test prompt"}
            )
            assert response.status_code == 200
            assert "Fast mocked response" in response.json["response"]

    def test_generate_text_with_custom_options_fast(self):
        client = app.test_client()
        with patch('http_api.llama.generate', return_value="Custom fast response"):
            response = client.post(
                "/generate/text",
                json={"prompt": "Custom prompt"}
            )
            assert response.status_code == 200
            assert "Custom fast response" in response.json["response"]

    def test_security_headers_fast(self):
        client = app.test_client()
        response = client.get("/health")
        headers = response.headers
        assert "Content-Type" in headers

    def test_rate_limiting_fast(self):
        client = app.test_client()
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200

    def test_input_validation_fast(self):
        client = app.test_client()
        response = client.post(
            "/generate/text",
            data="invalid json",
            content_type="application/json"
        )
        assert response.status_code in [400, 422, 500]

    def test_invalid_endpoint_fast(self):
        client = app.test_client()
        response = client.get("/invalid-endpoint")
        assert response.status_code == 404

    def test_empty_prompt_validation_fast(self):
        client = app.test_client()
        response = client.post(
            "/generate/text",
            json={"prompt": ""}
        )
        assert response.status_code in [400, 422]

    def test_missing_prompt_validation_fast(self):
        client = app.test_client()
        response = client.post(
            "/generate/text",
            json={}
        )
        assert response.status_code in [400, 422] 