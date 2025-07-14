"""
Working test suite for LlamalyticsHub application.
Comprehensive tests covering core business logic, integration workflows, error handling, and utility functions.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi_app import app
from ollama_code_llama import OllamaCodeLlama
from utils.helpers import (
    safe_name, get_report_filename, hash_content, filter_files,
    update_env_file
)
from fastapi_app import (
    rate_limiter, TextRequest, GithubPRRequest, HealthResponse,
    validate_file_upload, sanitize_input
)


class TestCoreBusinessLogic:
    """Test core business logic and fundamental functions."""

    def test_ollama_initialization(self):
        """Test OllamaCodeLlama initialization with custom parameters."""
        llama = OllamaCodeLlama(
            model="test-model", 
            host="http://test-host:11434"
        )
        assert llama.model == "test-model"
        assert llama.host == "http://test-host:11434"

    def test_ollama_default_initialization(self):
        """Test OllamaCodeLlama initialization with default parameters."""
        llama = OllamaCodeLlama()
        assert llama.model == "codellama:7b"
        assert llama.host == "http://localhost:11434"

    def test_ollama_generate_success(self):
        """Test successful text generation with OllamaCodeLlama."""
        llama = OllamaCodeLlama()
        
        with patch('ollama_code_llama.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.text = (
                '{"response": "Hello", "done": false}\n'
                '{"response": " World", "done": true}'
            )
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = llama.generate("Test prompt")
            assert "Hello World" in result

    def test_safe_name(self):
        """Test safe_name function for filename sanitization."""
        assert safe_name("test/repo") == "test_repo"
        assert safe_name("test repo") == "test_repo"
        assert safe_name("test.repo") == "test.repo"
        assert safe_name("test@repo") == "test@repo"  # @ is preserved

    def test_get_report_filename(self):
        """Test report filename generation."""
        filename = get_report_filename("test/repo", "main", 123)
        assert "test_repo" in filename
        assert "main" in filename
        assert "123" in filename
        assert filename.endswith(".md")

    def test_hash_content(self):
        """Test content hashing functionality."""
        content = "test content"
        hash_result = hash_content(content)
        assert len(hash_result) == 64  # SHA-256 hex length
        assert hash_result != hash_content("different content")

    def test_filter_files(self):
        """Test file filtering functionality."""
        files = [
            {"filename": "test.py", "content": "def test(): pass"},
            {"filename": "test.js", "content": "function test() {}"},
            {"filename": "test.txt", "content": "plain text"}
        ]
        
        # Test pattern filtering
        filtered = filter_files(files, "pattern", pattern="*.py")
        assert len(filtered) == 1
        assert filtered[0]["filename"] == "test.py"
        
        # Test manual selection
        filtered = filter_files(files, "manual", manual_selection=["test.js"])
        assert len(filtered) == 1
        assert filtered[0]["filename"] == "test.js"

    def test_validate_file_upload_valid(self):
        """Test file upload validation with valid file."""
        from fastapi import UploadFile
        import io
        file_content = b"def test(): pass"
        file = UploadFile(filename="test.py", file=io.BytesIO(file_content))
        file.size = len(file_content)
        is_valid, msg = validate_file_upload(file)
        assert is_valid is True

    def test_sanitize_input_normal(self):
        """Test input sanitization with normal input."""
        result = sanitize_input("normal input")
        assert result == "normal input"

    def test_sanitize_input_null_bytes(self):
        """Test input sanitization with null bytes."""
        result = sanitize_input("input\x00with\x00nulls")
        assert "\x00" not in result

    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        assert hasattr(rate_limiter, 'requests')
        assert hasattr(rate_limiter, 'is_allowed')

    def test_text_request_validation(self):
        """Test TextRequest Pydantic model validation."""
        request = TextRequest(prompt="test prompt")
        assert request.prompt == "test prompt"

    def test_github_pr_request_validation(self):
        """Test GithubPRRequest Pydantic model validation."""
        request = GithubPRRequest(
            owner="test",
            repo="repo", 
            pr=123
        )
        assert request.owner == "test"
        assert request.repo == "repo"
        assert request.pr == 123

    def test_health_response_validation(self):
        """Test HealthResponse Pydantic model validation."""
        response = HealthResponse(
            status="healthy",
            llm_reply="test reply"
        )
        assert response.status == "healthy"
        assert response.llm_reply == "test reply"


class TestIntegrationWorkflows:
    """Test integration workflows and end-to-end scenarios."""

    def test_health_check_workflow(self):
        """Test health check workflow."""
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "llm_reply" in data

    def test_reports_workflow(self):
        """Test reports endpoint workflow."""
        client = TestClient(app)
        response = client.get("/reports")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["reports"], list)

    def test_logs_workflow(self):
        """Test logs endpoint workflow."""
        client = TestClient(app)
        response = client.get("/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data

    def test_text_generation_workflow_mocked(self):
        """Test text generation workflow with mocked LLM."""
        client = TestClient(app)
        
        with patch('ollama_code_llama.OllamaCodeLlama.generate') as mock_generate:
            mock_generate.return_value = "Generated text response"
            
            response = client.post(
                "/generate/text", 
                json={"prompt": "Write a simple Python function"}
            )
            
            assert response.status_code == 200

    def test_file_upload_workflow_mocked(self):
        """Test file upload workflow with mocked processing."""
        client = TestClient(app)
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as f:
            f.write("def test(): pass")
            temp_file = f.name
        
        try:
            with open(temp_file, 'rb') as f:
                with patch('ollama_code_llama.OllamaCodeLlama.generate') as mock_generate:
                    mock_generate.return_value = "File analysis result"
                    
                    response = client.post(
                        "/upload",
                        files={"file": (os.path.basename(temp_file), f, "text/plain")}
                    )
                    
                    assert response.status_code == 200
        finally:
            os.unlink(temp_file)

    def test_file_upload_errors(self):
        """Test file upload error handling."""
        client = TestClient(app)
        
        # Test with non-existent file
        response = client.post(
            "/upload",
            files={"file": ("nonexistent.py", b"", "text/plain")}
        )
        assert response.status_code in [400, 422, 404]


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_requests(self):
        """Test handling of invalid requests."""
        client = TestClient(app)
        
        # Test missing required fields
        response = client.post("/generate/text", json={})
        assert response.status_code == 422
        
        # Test invalid data types
        response = client.post("/generate/text", json={"prompt": 123})
        assert response.status_code == 422

    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        # Clear rate limiter state
        rate_limiter.requests.clear()
        
        # Test rate limiting
        assert rate_limiter.is_allowed("127.0.0.1") is True


class TestUtilityFunctions:
    """Test utility functions and helpers."""

    def test_update_env_file_new_file(self):
        """Test updating environment file (new file creation)."""
        env_vars = {"TEST_KEY": "test_value", "ANOTHER_KEY": "another_value"}
        
        update_env_file(env_vars, "test.env")
        
        try:
            with open("test.env", "r") as f:
                content = f.read()
                assert "TEST_KEY=test_value" in content
                assert "ANOTHER_KEY=another_value" in content
        finally:
            if os.path.exists("test.env"):
                os.unlink("test.env")

    def test_display_functions(self):
        """Test display and formatting functions."""
        # Test that display functions don't raise exceptions
        from utils.helpers import spinner
        spinner("Test message", duration=0.1)


def test_comprehensive_coverage():
    """Test comprehensive coverage of core functionality."""
    # Test that all major components can be imported and instantiated
    from fastapi_app import app
    from ollama_code_llama import OllamaCodeLlama
    from utils.helpers import safe_name, hash_content
    
    # Test basic functionality
    assert safe_name("test/repo") == "test_repo"
    assert len(hash_content("test")) == 64
    
    # Test app instantiation
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 