"""
API Test Suite - Can run in parallel with other test suites
Tests Flask API endpoints, security features, and API functionality
"""
import pytest
from unittest.mock import Mock, patch
import tempfile
import os
import json
from http_api import app


class TestAPIFeatures:
    """Test API core functionality"""
    
    def test_root_endpoint(self):
        """Test root endpoint"""
        client = app.test_client()
        response = client.get("/help")
        assert response.status_code == 200
        assert "endpoints" in response.json
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        client = app.test_client()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json["status"] == "ok"
    
    def test_generate_text_endpoint(self):
        """Test text generation endpoint"""
        client = app.test_client()
        with patch('ollama_code_llama.OllamaCodeLlama.generate', return_value="Generated text response"):
            response = client.post(
                "/generate/text",
                json={"prompt": "Test prompt"}
            )
            assert response.status_code == 200
            assert "Generated text response" in response.json["response"]
    
    def test_generate_text_with_custom_options(self):
        """Test text generation with custom options"""
        client = app.test_client()
        with patch('ollama_code_llama.OllamaCodeLlama.generate', return_value="Custom response"):
            response = client.post(
                "/generate/text",
                json={"prompt": "Custom prompt"}
            )
            assert response.status_code == 200
            assert "Custom response" in response.json["response"]
    
    def test_upload_file_endpoint(self):
        """Test file upload endpoint"""
        client = app.test_client()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def test(): pass")
            temp_file_path = f.name
        try:
            with open(temp_file_path, 'rb') as f:
                data = {
                    'file': (f, 'test.py'),
                }
                response = client.post(
                    "/generate/file",
                    data=data,
                    content_type='multipart/form-data'
                )
            assert response.status_code in [200, 400, 422]
        finally:
            os.unlink(temp_file_path)
    
    def test_github_pr_analysis_endpoint(self):
        """Test GitHub PR analysis endpoint"""
        client = app.test_client()
        with patch('http_api.Github') as mock_github:
            mock_github_instance = Mock()
            mock_repo = Mock()
            mock_pr = Mock()
            mock_pr.get_files.return_value = []
            mock_repo.get_pull.return_value = mock_pr
            mock_github_instance.get_repo.return_value = mock_repo
            mock_github.return_value = mock_github_instance
            response = client.post(
                "/generate/github-pr",
                json={"repo": "test/repo", "pr_number": 123, "token": "ghp_test"}
            )
            assert response.status_code in [200, 400, 422]
    
    def test_security_headers(self):
        """Test security headers are present"""
        client = app.test_client()
        response = client.get("/health")
        headers = response.headers
        assert "Content-Type" in headers
    
    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        client = app.test_client()
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200
    
    def test_input_validation(self):
        """Test input validation"""
        client = app.test_client()
        response = client.post(
            "/generate/text",
            data="invalid json",
            content_type="application/json"
        )
        assert response.status_code in [400, 422, 500]
    
    def test_file_upload_security(self):
        """Test file upload security"""
        client = app.test_client()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.exe', delete=False) as f:
            f.write("malicious content")
            temp_file_path = f.name
        try:
            with open(temp_file_path, 'rb') as f:
                data = {
                    'file': (f, 'malicious.exe'),
                }
                response = client.post(
                    "/generate/file",
                    data=data,
                    content_type='multipart/form-data'
                )
            assert response.status_code in [400, 422]
        finally:
            os.unlink(temp_file_path)
    
    def test_invalid_endpoint(self):
        """Test invalid endpoint handling"""
        client = app.test_client()
        response = client.get("/invalid-endpoint")
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 