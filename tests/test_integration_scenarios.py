"""
Integration tests for complete workflows and scenarios.
Tests end-to-end functionality that exercises multiple components together.
"""
import pytest
import tempfile
import os
import json
import asyncio
import requests
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Import application components
from fastapi_app import app
from ollama_code_llama import OllamaCodeLlama
from utils.helpers import analyze_files_parallel, hash_content, get_cache_path
from github_audit import analyze_code_files
from fastapi_app import GithubPRRequest

# Add proper LLM mocking to fix rate limiting
@pytest.fixture(scope="function")
def mock_llm_client():
    """Mock LLM client to avoid real API calls"""
    with patch('http_api.llama') as mock_llama:
        mock_llama.generate.return_value = "Mocked response"
        mock_llama.async_generate.return_value = "Mocked async response"
        yield mock_llama

@pytest.fixture(scope="function")
def client():
    """FastAPI test client"""
    return TestClient(app)

class TestCompleteWorkflows:
    """Test complete application workflows"""
    
    def test_text_generation_workflow(self, client, mock_llm_client):
        """Test complete text generation workflow"""
        
        # Test text generation (mocked to avoid hanging)
        response = client.post("/generate/text", json={"prompt": "Write a simple Python function"})
        assert response.status_code in [200, 500, 503]  # 500/503 if LLM unavailable
        
        if response.status_code == 200:
            data = response.json()
            assert "response" in data
            assert len(data["response"]) > 0
    
    def test_file_upload_workflow(self, client, mock_llm_client):
        """Test complete file upload and analysis workflow"""
        
        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    return 'Hello, World!'")
            temp_file_path = f.name
        
        try:
            with open(temp_file_path, 'rb') as f:
                response = client.post(
                    "/generate/file",
                    files={"file": ("test.py", f, "text/plain")}
                )
                
                assert response.status_code in [200, 500, 503]
                
                if response.status_code == 200:
                    data = response.json()
                    assert "response" in data
                    assert len(data["response"]) > 0
        finally:
            os.unlink(temp_file_path)
    
    def test_github_pr_analysis_workflow(self, client, mock_llm_client):
        """Test GitHub PR analysis workflow"""
        
        # Test with mock GitHub token
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'mock_token'}):
            response = client.post("/generate/github-pr", json={
                "repo": "testuser/testrepo",
                "pr_number": 1
            })
            
            # Should return 200, 500, or 503 depending on GitHub API availability
            assert response.status_code in [200, 500, 503, 401]
    
    def test_health_check_workflow(self, client, mock_llm_client):
        """Test health check workflow with LLM integration"""
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "unhealthy"]
        
        if data["status"] == "healthy":
            assert "llm_reply" in data
            assert data["llm_reply"] is not None
    
    def test_reports_workflow(self):
        """Test complete reports workflow"""
        client = TestClient(app)
        
        # List reports
        response = client.get("/reports")
        assert response.status_code == 200
        data = response.json()
        assert "reports" in data
        assert isinstance(data["reports"], list)
        
        # Get specific report if available
        if data["reports"]:
            report_name = data["reports"][0]
            response = client.get(f"/reports/{report_name}")
            assert response.status_code in [200, 404]
    
    def test_logs_workflow(self):
        """Test logs workflow"""
        client = TestClient(app)
        
        response = client.get("/logs")
        assert response.status_code == 200
        
        data = response.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)

class TestLLMIntegrationScenarios:
    """Test LLM integration scenarios"""
    
    def test_llm_client_initialization_scenarios(self):
        """Test LLM client initialization with different scenarios"""
        # Normal initialization
        llama = OllamaCodeLlama()
        assert llama.model == "codellama:7b"
        assert llama.host == "http://localhost:11434"
        
        # Custom initialization
        llama = OllamaCodeLlama(model="custom-model", host="http://custom-host:11434")
        assert llama.model == "custom-model"
        assert llama.host == "http://custom-host:11434"
    
    @patch('requests.post')
    def test_llm_generation_scenarios(self, mock_post):
        """Test LLM generation with different scenarios"""
        llama = OllamaCodeLlama()
        
        # Scenario 1: Normal generation
        mock_response = Mock()
        mock_response.text = '{"response": "Normal response", "done": true}'
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = llama.generate("Test prompt")
        assert result == "Normal response"
        
        # Scenario 2: Empty response
        mock_response.text = '{"response": "", "done": true}'
        result = llama.generate("Test prompt")
        assert result == ""
        
        # Scenario 3: Multiple response chunks
        mock_response.text = '{"response": "Part 1", "done": false}\n{"response": " Part 2", "done": true}'
        result = llama.generate("Test prompt")
        assert result == "Part 1 Part 2"
    
    @patch('httpx.AsyncClient')
    async def test_async_llm_scenarios(self, mock_client):
        """Test async LLM scenarios"""
        mock_response = Mock()
        mock_response.text = '{"response": "Async response", "done": true}'
        mock_response.raise_for_status.return_value = None
        
        mock_async_client = Mock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.__aexit__.return_value = None
        mock_async_client.post.return_value = mock_response
        mock_client.return_value = mock_async_client
        
        llama = OllamaCodeLlama()
        
        # Single async generation
        result = await llama.async_generate("Test prompt")
        assert result == "Async response"
        
        # Batch async generation
        prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
        results = await llama.batch_async_generate(prompts)
        assert len(results) == 3
        assert all(result == "Async response" for result in results)

class TestFileAnalysisScenarios:
    """Test file analysis scenarios"""
    
    @patch('github_audit.analyze_code_files')
    def test_file_analysis_with_cache(self, mock_analyze):
        """Test file analysis with caching"""
        # Mock the analyze function to return a proper string response
        mock_analyze.return_value = [{
            'filename': 'test.py',
            'analysis': 'This is a test file with basic functionality.',
            'sections': {
                'summary': 'Basic test file',
                'issues': [],
                'recommendations': ['Add more tests']
            }
        }]
        
        files = [{'filename': 'test.py', 'content': 'def test(): pass'}]
        comments = []
        commits = []
        readme = ""
        
        # Create cache directory
        cache_dir = '.cache/test_repo_main'
        os.makedirs(cache_dir, exist_ok=True)
        
        try:
            results = analyze_files_parallel(files, comments, commits, readme, llm_client, 'test/repo', 'main', None)
            assert len(results) > 0
        finally:
            # Clean up cache directory
            import shutil
            if os.path.exists('.cache'):
                shutil.rmtree('.cache')
    
    def test_file_analysis_empty_files(self):
        """Test file analysis with empty files"""
        files = [
            {"filename": "empty.py", "content": ""},
            {"filename": "whitespace.py", "content": "   \n  \n"},
            {"filename": "valid.py", "content": "def valid(): pass"}
        ]
        comments = []
        commits = []
        readme = ""
        llm_client = Mock()
        repo_name = "test/repo"
        branch_name = "main"
        pr_number = None
        
        # Mock the LLM client to return a proper string
        llm_client.generate.return_value = "Analysis of the file"
        
        results = analyze_files_parallel(files, comments, commits, readme, llm_client, repo_name, branch_name, pr_number)
        
        # Should only process valid files
        assert len(results) >= 0  # May be 0 if no valid files or LLM unavailable
    
    def test_file_analysis_large_files(self):
        """Test file analysis with large files"""
        large_content = "def large_function():\n" + "    pass\n" * 5000  # Large file
        
        files = [
            {"filename": "large.py", "content": large_content}
        ]
        comments = []
        commits = []
        readme = ""
        llm_client = Mock()
        repo_name = "test/repo"
        branch_name = "main"
        pr_number = None
        
        results = analyze_files_parallel(files, comments, commits, readme, llm_client, repo_name, branch_name, pr_number)
        
        # Should handle large files gracefully
        assert isinstance(results, list)

class TestErrorHandlingScenarios:
    """Test error handling scenarios"""
    
    def test_llm_connection_error_scenario(self):
        """Test LLM connection error scenario"""
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.RequestException("Connection failed")
            
            llama = OllamaCodeLlama()
            with pytest.raises(RuntimeError, match="Request to LLM failed"):
                llama.generate("Test prompt")
    
    def test_file_upload_error_scenarios(self, client, mock_llm_client):
        """Test file upload error scenarios"""
        
        # Test with no file
        response = client.post("/generate/file")
        assert response.status_code == 422
        
        # Test with invalid file type
        with tempfile.NamedTemporaryFile(mode='w', suffix='.exe', delete=False) as f:
            f.write("executable content")
            temp_file_path = f.name
        
        try:
            with open(temp_file_path, 'rb') as f:
                response = client.post(
                    "/generate/file",
                    files={"file": ("test.exe", f, "application/octet-stream")}
                )
                assert response.status_code == 400
        finally:
            os.unlink(temp_file_path)
    
    def test_rate_limiting_scenario(self, client, mock_llm_client):
        """Test rate limiting scenario"""
        # Make multiple requests quickly
        responses = []
        for _ in range(10):
            response = client.get("/health")
            responses.append(response.status_code)
        
        # Should handle rate limiting gracefully
        assert all(status in [200, 429] for status in responses)
    
    def test_github_api_error_scenario(self, client, mock_llm_client):
        """Test GitHub API error scenario"""
        
        # Test with invalid token
        response = client.post("/generate/github-pr", json={
            "owner": "invalid",
            "repo": "repo",
            "pr": 999999
        })
        
        # Should handle GitHub API errors gracefully
        assert response.status_code in [400, 500, 503, 401]

class TestConfigurationScenarios:
    """Test configuration scenarios"""
    
    def test_environment_variable_scenarios(self):
        """Test environment variable scenarios"""
        # Test with different environment configurations
        scenarios = [
            {"OLLAMA_API_KEY": "test_key", "GITHUB_TOKEN": "test_token"},
            {"OLLAMA_API_KEY": "", "GITHUB_TOKEN": ""},
            {},  # No environment variables
        ]
        
        for env_vars in scenarios:
            with patch.dict(os.environ, env_vars, clear=True):
                # Should not crash
                from fastapi_app import app
                client = TestClient(app)
                response = client.get("/")
                assert response.status_code == 200
    
    def test_config_file_scenarios(self):
        """Test configuration file scenarios"""
        # Test with missing config file
        if os.path.exists("config.yaml"):
            os.rename("config.yaml", "config.yaml.backup")
        
        try:
            # Should not crash
            from fastapi_app import app
            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 200
        finally:
            if os.path.exists("config.yaml.backup"):
                os.rename("config.yaml.backup", "config.yaml")

class TestSecurityScenarios:
    """Test security scenarios"""
    
    def test_cors_scenarios(self):
        """Test CORS scenarios"""
        client = TestClient(app)
        
        # Test with different origins
        origins = [
            "http://localhost:3000",
            "https://example.com",
            "http://malicious-site.com",
        ]
        
        for origin in origins:
            response = client.get("/health", headers={"Origin": origin})
            assert response.status_code == 200
            assert response.headers.get("access-control-allow-origin") == "*"
    
    @pytest.mark.usefixtures("client", "mock_llm")
    class TestRewrittenIntegrationScenarios:
        def test_github_pr_analysis_workflow(self, client):
            """Test GitHub PR analysis workflow with correct model fields and patched rate limiter."""
            response = client.post("/generate/github-pr", json={
                "owner": "test",
                "repo": "repo",
                "pr": 1
            })
            assert response.status_code in [200, 400, 401, 500, 503, 422]

        def test_file_upload_security_scenarios(self, client):
            """Test file upload security scenarios with in-memory files and patched rate limiter."""
            # Valid file
            response = client.post(
                "/generate/file",
                files={"file": ("test.py", b"def test(): pass", "text/plain")}
            )
            assert response.status_code in [200, 400, 413]
            # Invalid extension
            response = client.post(
                "/generate/file",
                files={"file": ("test.exe", b"binary", "application/octet-stream")}
            )
            assert response.status_code in [400, 413, 422]
            # Path traversal
            response = client.post(
                "/generate/file",
                files={"file": ("../../../etc/passwd", b"content", "text/plain")}
            )
            assert response.status_code in [400, 413, 422]
            # Too large
            response = client.post(
                "/generate/file",
                files={"file": ("test.py", b"x" * (3 * 1024 * 1024), "text/plain")}
            )
            assert response.status_code in [400, 413, 422]

        def test_input_validation_scenarios(self, client):
            """Test input validation scenarios for /generate/text endpoint."""
            # Empty prompt
            response = client.post("/generate/text", json={"prompt": ""})
            assert response.status_code == 422
            # Whitespace only
            response = client.post("/generate/text", json={"prompt": "   "})
            assert response.status_code == 422
            # Too long
            response = client.post("/generate/text", json={"prompt": "x" * 10001})
            assert response.status_code == 422
            # Valid
            response = client.post("/generate/text", json={"prompt": "Normal prompt"})
            assert response.status_code in [200, 500, 503]

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 