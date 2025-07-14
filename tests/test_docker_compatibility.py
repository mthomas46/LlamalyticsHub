"""
Docker compatibility tests for LlamalyticsHub FastAPI application.
Tests that the application can start and run independently in a containerized environment.
"""
import pytest
import subprocess
import time
import requests
import os
import tempfile
import json
from unittest.mock import patch, Mock
import docker

class TestDockerCompatibility:
    """Test Docker-specific functionality and container startup"""
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and is valid"""
        assert os.path.exists("Dockerfile"), "Dockerfile not found"
        
        # Check Dockerfile content
        with open("Dockerfile", "r") as f:
            content = f.read()
            assert "FROM python" in content, "Dockerfile should use Python base image"
            assert "COPY" in content, "Dockerfile should copy application files"
            assert "EXPOSE" in content, "Dockerfile should expose port"
    
    def test_docker_compose_exists(self):
        """Test that docker-compose files exist"""
        assert os.path.exists("docker-compose.yml"), "docker-compose.yml not found"
        assert os.path.exists("docker-compose.dev.yml"), "docker-compose.dev.yml not found"
    
    def test_requirements_txt_exists(self):
        """Test that requirements.txt exists and is valid"""
        assert os.path.exists("requirements.txt"), "requirements.txt not found"
        
        with open("requirements.txt", "r") as f:
            content = f.read()
            assert "fastapi" in content, "FastAPI should be in requirements"
            assert "uvicorn" in content, "Uvicorn should be in requirements"
    
    def test_env_example_exists(self):
        """Test that environment example file exists"""
        assert os.path.exists("env.example"), "env.example not found"
    
    def test_dockerignore_exists(self):
        """Test that .dockerignore exists"""
        assert os.path.exists(".dockerignore"), ".dockerignore not found"
    
    def test_application_imports(self):
        """Test that all required modules can be imported"""
        try:
            import fastapi_app
            assert hasattr(fastapi_app, 'app'), "FastAPI app should be defined"
        except ImportError as e:
            pytest.fail(f"Failed to import fastapi_app: {e}")
    
    def test_environment_variables_loading(self):
        """Test environment variable loading in container context"""
        # Test with minimal environment
        with patch.dict(os.environ, {
            'OLLAMA_API_KEY': 'test_key',
            'GITHUB_TOKEN': 'test_token'
        }, clear=True):
            import importlib
            import fastapi_app
            importlib.reload(fastapi_app)
            assert fastapi_app.API_KEY == 'test_key'
            assert fastapi_app.GITHUB_TOKEN == 'test_token'
    
    def test_config_file_loading(self):
        """Test configuration file loading"""
        # Create a temporary config file
        config_content = """
llamalyticshub:
  api_key: test_api_key
github:
  token: test_github_token
ollama:
  log_file: test.log
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            temp_config_path = f.name
        
        try:
            with patch('fastapi_app.CONFIG_PATH', temp_config_path):
                import importlib
                import fastapi_app
                importlib.reload(fastapi_app)
                # Should load config without errors
                assert True
        finally:
            os.unlink(temp_config_path)
    
    def test_logging_setup(self):
        """Test logging configuration"""
        import logging
        from fastapi_app import app
        
        # Test that logging is properly configured
        logger = logging.getLogger()
        assert len(logger.handlers) > 0, "Logging handlers should be configured"
    
    def test_fastapi_app_creation(self):
        """Test FastAPI app creation and configuration"""
        from fastapi_app import app
        
        assert app.title == "LlamalyticsHub API"
        assert app.version == "2.0.0"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
    
    def test_middleware_configuration(self):
        """Test middleware configuration"""
        from fastapi_app import app
        
        # Check that CORS middleware is configured
        found = any(
            getattr(m.cls, '__name__', '') == 'CORSMiddleware'
            for m in app.user_middleware
        )
        assert found, "CORS middleware not found in app.user_middleware"
    
    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        from fastapi_app import rate_limiter
        
        # Test rate limiter initialization
        assert hasattr(rate_limiter, 'requests_per_minute')
        assert hasattr(rate_limiter, 'is_allowed')
        
        # Test rate limiter functionality
        assert rate_limiter.is_allowed("127.0.0.1") == True
    
    def test_pydantic_models(self):
        """Test Pydantic model validation"""
        from fastapi_app import TextRequest, GithubPRRequest, HealthResponse
        
        # Test TextRequest
        valid_text_request = TextRequest(prompt="Test prompt")
        assert valid_text_request.prompt == "Test prompt"
        
        # Test GithubPRRequest
        valid_pr_request = GithubPRRequest(owner="test", repo="repo", pr=1)
        assert valid_pr_request.owner == "test"
        assert valid_pr_request.repo == "repo"
        assert valid_pr_request.pr == 1
        
        # Test HealthResponse
        valid_health_response = HealthResponse(status="healthy")
        assert valid_health_response.status == "healthy"
    
    def test_file_validation(self):
        """Test file upload validation"""
        from fastapi_app import validate_file_upload
        from fastapi import UploadFile
        
        # Test valid file
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "test.py"
        mock_file.size = 1024
        
        is_valid, message = validate_file_upload(mock_file)
        assert is_valid == True
        assert message == "OK"
        
        # Test invalid file type
        mock_file.filename = "test.exe"
        is_valid, message = validate_file_upload(mock_file)
        assert is_valid == False
        assert "not allowed" in message
    
    def test_input_sanitization(self):
        """Test input sanitization"""
        from fastapi_app import sanitize_input
        
        # Test normal input
        result = sanitize_input("Normal text")
        assert result == "Normal text"
        
        # Test input with null bytes
        result = sanitize_input("Text\x00with\x00nulls")
        assert "\x00" not in result
        
        # Test very long input
        long_input = "x" * 15000
        result = sanitize_input(long_input)
        assert len(result) <= 10000
    
    def test_docker_build_simulation(self):
        """Simulate Docker build process"""
        # Check that all required files exist
        required_files = [
            "Dockerfile",
            "docker-compose.yml",
            "requirements.txt",
            "fastapi_app.py",
            "ollama_code_llama.py",
            "github_client/github_client.py",
            "config/config_manager.py"
        ]
        
        for file_path in required_files:
            assert os.path.exists(file_path), f"Required file {file_path} not found"
    
    def test_container_environment_variables(self):
        """Test container environment variable handling"""
        # Test with container-like environment
        container_env = {
            'OLLAMA_API_KEY': 'container_key',
            'GITHUB_TOKEN': 'container_token',
            'OLLAMA_LOG_FILE': 'container.log',
            'PORT': '8000'
        }
        
        with patch.dict(os.environ, container_env, clear=True):
            # Reload the module to test environment variable loading
            import importlib
            import fastapi_app
            importlib.reload(fastapi_app)
            
            # Check that environment variables are loaded
            assert fastapi_app.API_KEY == 'container_key'
            assert fastapi_app.GITHUB_TOKEN == 'container_token'
            assert fastapi_app.LOG_FILE == 'container.log'
    
    def test_health_check_endpoint(self):
        """Test health check endpoint functionality"""
        from fastapi_app import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "unhealthy"]
    
    def test_api_documentation_endpoints(self):
        """Test API documentation endpoints"""
        from fastapi_app import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        
        # Test docs endpoint
        response = client.get("/docs")
        assert response.status_code == 200
        
        # Test OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
    
    def test_error_handling(self):
        """Test error handling in container context"""
        from fastapi_app import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        
        # Test 404 handling
        response = client.get("/nonexistent")
        assert response.status_code == 404
        
        # Test 422 validation error
        response = client.post("/generate/text", json={})
        assert response.status_code == 422
    
    def test_cors_headers(self):
        """Test CORS headers in container context"""
        from fastapi_app import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/health", headers={"Origin": "http://example.com"})
        
        # Check CORS headers
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "*"
        assert "access-control-allow-credentials" in response.headers

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 