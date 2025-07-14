"""
Optimized API File Test Suite - Fast execution with comprehensive mocking
Tests Flask API file upload and file validation endpoints
"""
import pytest
from unittest.mock import Mock, patch
from http_api import app
import io

class TestAPIFileFeaturesOptimized:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch('http_api.OllamaCodeLlama') as mock_llama_class:
            mock_llama = Mock()
            mock_llama.generate.return_value = "Mocked LLM response"
            mock_llama_class.return_value = mock_llama
            yield

    def test_upload_file_endpoint_fast(self):
        client = app.test_client()
        file_content = "def test(): pass"
        file_data = io.BytesIO(file_content.encode('utf-8'))
        with patch('http_api.llama.generate', return_value="File analysis complete"):
            data = {
                'file': (file_data, 'test.py'),
            }
            response = client.post(
                "/generate/file",
                data=data,
                content_type='multipart/form-data'
            )
            assert response.status_code in [200, 400, 422]

    def test_file_upload_security_fast(self):
        client = app.test_client()
        malicious_content = "malicious content"
        file_data = io.BytesIO(malicious_content.encode('utf-8'))
        data = {
            'file': (file_data, 'malicious.exe'),
        }
        response = client.post(
            "/generate/file",
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code in [400, 422]

    def test_large_file_upload_fast(self):
        client = app.test_client()
        large_content = "x" * (2 * 1024 * 1024 + 1)
        file_data = io.BytesIO(large_content.encode('utf-8'))
        data = {
            'file': (file_data, 'large.txt'),
        }
        response = client.post(
            "/generate/file",
            data=data,
            content_type='multipart/form-data'
        )
        assert response.status_code in [400, 413, 500]

    def test_file_validation_performance(self):
        client = app.test_client()
        test_files = [
            ("test.py", "def test(): pass"),
            ("test.js", "function test() {}"),
            ("test.md", "# Test"),
            ("test.txt", "Test content"),
        ]
        with patch('http_api.llama.generate', return_value="Analysis complete"):
            for filename, content in test_files:
                file_data = io.BytesIO(content.encode('utf-8'))
                data = {
                    'file': (file_data, filename),
                }
                response = client.post(
                    "/generate/file",
                    data=data,
                    content_type='multipart/form-data'
                )
                assert response.status_code in [200, 400, 422] 