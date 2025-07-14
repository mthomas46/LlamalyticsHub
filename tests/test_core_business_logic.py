"""
High-impact tests for core business logic functions.
Focuses on functions that handle the most critical application functionality.
"""
import pytest
import tempfile
import os
import json
import hashlib
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import httpx
import requests

# Import core business logic modules
from ollama_code_llama import OllamaCodeLlama
from utils.helpers import (
    safe_name, get_report_filename, get_readme_filename, hash_content,
    get_cache_path, filter_files, analyze_files_parallel, get_changed_files,
    update_env_file, display_diff
)
from fastapi_app import (
    validate_file_upload, sanitize_input, rate_limiter,
    TextRequest, GithubPRRequest, HealthResponse
)

class TestOllamaCodeLlama:
    """Test the core LLM client functionality"""
    
    def test_ollama_initialization(self):
        """Test OllamaCodeLlama initialization"""
        llama = OllamaCodeLlama(model="test-model", host="http://test-host:11434")
        assert llama.model == "test-model"
        assert llama.host == "http://test-host:11434"
    
    def test_ollama_default_initialization(self):
        """Test OllamaCodeLlama with default parameters"""
        llama = OllamaCodeLlama()
        assert llama.model == "codellama:7b"
        assert llama.host == "http://localhost:11434"
    
    @patch('requests.post')
    def test_ollama_generate_success(self, mock_post):
        """Test successful LLM generation"""
        # Mock successful response
        mock_response = Mock()
        mock_response.text = '{"response": "Hello", "done": false}\n{"response": " World", "done": true}'
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        llama = OllamaCodeLlama()
        result = llama.generate("Test prompt")
        
        assert result == "Hello World"
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_ollama_generate_with_options(self, mock_post):
        """Test LLM generation with custom options"""
        mock_response = Mock()
        mock_response.text = '{"response": "Test response", "done": true}'
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        llama = OllamaCodeLlama()
        options = {"temperature": 0.7, "top_p": 0.9}
        result = llama.generate("Test prompt", options=options)
        
        assert result == "Test response"
        call_args = mock_post.call_args
        assert call_args[1]['json']['options'] == options
    
    @patch('requests.post')
    def test_ollama_generate_empty_response(self, mock_post):
        """Test LLM generation with empty response"""
        mock_response = Mock()
        mock_response.text = '{"response": "", "done": true}'
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        llama = OllamaCodeLlama()
        result = llama.generate("Test prompt")
        
        assert result == ""
    
    @patch('requests.post')
    def test_ollama_generate_request_error(self, mock_post):
        """Test LLM generation with request error"""
        mock_post.side_effect = requests.RequestException("Connection failed")
        
        llama = OllamaCodeLlama()
        with pytest.raises(RuntimeError, match="Request to LLM failed"):
            llama.generate("Test prompt")
    
    @patch('requests.post')
    def test_ollama_generate_json_error(self, mock_post):
        """Test LLM generation with JSON parsing error"""
        mock_response = Mock()
        mock_response.text = 'invalid json\n{"response": "valid", "done": true}'
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        llama = OllamaCodeLlama()
        result = llama.generate("Test prompt")
        
        # Should handle JSON errors gracefully and return valid parts
        assert result == "valid"
    
    @patch('httpx.AsyncClient')
    async def test_ollama_async_generate_success(self, mock_client):
        """Test async LLM generation"""
        mock_response = Mock()
        mock_response.text = '{"response": "Async response", "done": true}'
        mock_response.raise_for_status.return_value = None
        
        mock_async_client = Mock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.__aexit__.return_value = None
        mock_async_client.post.return_value = mock_response
        mock_client.return_value = mock_async_client
        
        llama = OllamaCodeLlama()
        result = await llama.async_generate("Test prompt")
        
        assert result == "Async response"
    
    @patch('httpx.AsyncClient')
    async def test_ollama_batch_async_generate(self, mock_client):
        """Test batch async LLM generation"""
        mock_response1 = Mock()
        mock_response1.text = '{"response": "Response 1", "done": true}'
        mock_response1.raise_for_status.return_value = None
        
        mock_response2 = Mock()
        mock_response2.text = '{"response": "Response 2", "done": true}'
        mock_response2.raise_for_status.return_value = None
        
        mock_async_client = Mock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.__aexit__.return_value = None
        mock_async_client.post.side_effect = [mock_response1, mock_response2]
        mock_client.return_value = mock_async_client
        
        llama = OllamaCodeLlama()
        prompts = ["Prompt 1", "Prompt 2"]
        results = await llama.batch_async_generate(prompts)
        
        assert results == ["Response 1", "Response 2"]
        assert len(results) == 2

class TestUtilityFunctions:
    """Test core utility functions"""
    
    def test_safe_name(self):
        """Test safe filename generation"""
        assert safe_name("test/repo") == "test_repo"
        assert safe_name("test repo") == "test_repo"
        assert safe_name("test.repo") == "test.repo"
        assert safe_name("test@repo") == "test@repo"  # @ is not replaced
    
    def test_get_report_filename(self):
        """Test report filename generation"""
        filename = get_report_filename("owner/repo", "main")
        assert "owner_repo" in filename
        assert "main" in filename
        assert filename.endswith(".md")
        
        filename_with_pr = get_report_filename("owner/repo", "main", 123)
        assert "pr123" in filename_with_pr
    
    def test_get_readme_filename(self):
        """Test README filename generation"""
        filename = get_readme_filename("owner/repo", "main")
        assert "updated_readme" in filename
        assert "owner_repo" in filename
        assert "main" in filename
        assert filename.endswith(".md")
    
    def test_hash_content(self):
        """Test content hashing"""
        content = "test content"
        hash1 = hash_content(content)
        hash2 = hash_content(content)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
        
        # Test different content produces different hash
        hash3 = hash_content("different content")
        assert hash1 != hash3
    
    def test_get_cache_path(self):
        """Test cache path generation"""
        cache_path = get_cache_path("owner/repo", "main", 123, "abc123")
        
        assert ".cache" in cache_path
        assert "owner_repo" in cache_path
        assert "main" in cache_path
        assert "pr123" in cache_path
        assert "abc123.json" in cache_path
        
        # Test without PR number
        cache_path_no_pr = get_cache_path("owner/repo", "main", None, "abc123")
        assert "pr" not in cache_path_no_pr
    
    def test_filter_files_pattern(self):
        """Test file filtering with pattern"""
        files = [
            {"filename": "test.py", "content": "code"},
            {"filename": "test.js", "content": "code"},
            {"filename": "README.md", "content": "docs"}
        ]
        
        # Test pattern filtering
        python_files = filter_files(files, "pattern", "*.py")
        assert len(python_files) == 1
        assert python_files[0]["filename"] == "test.py"
        
        # Test manual selection
        selected_files = filter_files(files, "manual", manual_selection=["README.md"])
        assert len(selected_files) == 1
        assert selected_files[0]["filename"] == "README.md"
        
        # Test no filtering
        all_files = filter_files(files, "none")
        assert len(all_files) == 3
    
    def test_update_env_file_new_file(self):
        """Test updating environment file (new file)"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_env_path = f.name
        
        try:
            env_vars = {"TEST_KEY": "test_value", "ANOTHER_KEY": "another_value"}
            update_env_file(env_vars, temp_env_path)
            
            with open(temp_env_path, 'r') as f:
                content = f.read()
                assert "TEST_KEY=test_value" in content
                assert "ANOTHER_KEY=another_value" in content
        finally:
            os.unlink(temp_env_path)
    
    def test_update_env_file_existing_file(self):
        """Test updating existing environment file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_env_path = f.name
            f.write("EXISTING_KEY=old_value\n")
        
        try:
            env_vars = {"EXISTING_KEY": "new_value", "NEW_KEY": "new_value"}
            update_env_file(env_vars, temp_env_path)
            
            with open(temp_env_path, 'r') as f:
                content = f.read()
                assert "EXISTING_KEY=new_value" in content
                assert "NEW_KEY=new_value" in content
        finally:
            os.unlink(temp_env_path)

class TestFileAnalysis:
    """Test file analysis and caching functionality"""
    
    def test_analyze_files_parallel_empty_files(self):
        """Test parallel file analysis with empty file list"""
        files = []
        comments = []
        commits = []
        readme = ""
        llm_client = Mock()
        repo_name = "test/repo"
        branch_name = "main"
        pr_number = None
        
        results = analyze_files_parallel(files, comments, commits, readme, llm_client, repo_name, branch_name, pr_number)
        assert results == []
    
    def test_analyze_files_parallel_with_cache(self):
        """Test parallel file analysis with caching"""
        files = [
            {"filename": "test.py", "content": "def test(): pass"}
        ]
        comments = []
        commits = []
        readme = ""
        llm_client = Mock()
        repo_name = "test/repo"
        branch_name = "main"
        pr_number = None
        
        # Create cache directory and file
        cache_path = get_cache_path(repo_name, branch_name, pr_number, hash_content("def test(): pass"))
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        
        cached_result = {"filename": "test.py", "summary": "Cached analysis"}
        with open(cache_path, 'w') as f:
            json.dump(cached_result, f)
        
        try:
            results = analyze_files_parallel(files, comments, commits, readme, llm_client, repo_name, branch_name, pr_number)
            assert len(results) == 1
            assert results[0]["summary"] == "Cached analysis"
        finally:
            # Cleanup
            if os.path.exists(cache_path):
                os.unlink(cache_path)
            cache_dir = os.path.dirname(cache_path)
            if os.path.exists(cache_dir):
                os.rmdir(cache_dir)

class TestSecurityAndValidation:
    """Test security and validation functions"""
    
    def test_validate_file_upload_valid(self):
        """Test file upload validation with valid file"""
        mock_file = Mock()
        mock_file.filename = "test.py"
        mock_file.size = 1024
        
        is_valid, message = validate_file_upload(mock_file)
        assert is_valid == True
        assert message == "OK"
    
    def test_validate_file_upload_invalid_type(self):
        """Test file upload validation with invalid file type"""
        mock_file = Mock()
        mock_file.filename = "test.exe"
        mock_file.size = 1024
        
        is_valid, message = validate_file_upload(mock_file)
        assert is_valid == False
        assert "not allowed" in message
    
    def test_validate_file_upload_too_large(self):
        """Test file upload validation with oversized file"""
        mock_file = Mock()
        mock_file.filename = "test.py"
        mock_file.size = 3 * 1024 * 1024  # 3MB
        
        is_valid, message = validate_file_upload(mock_file)
        assert is_valid == False
        assert "too large" in message
    
    def test_validate_file_upload_path_traversal(self):
        """Test file upload validation with path traversal attempt"""
        mock_file = Mock()
        mock_file.filename = "../../../etc/passwd"
        mock_file.size = 1024
        
        is_valid, message = validate_file_upload(mock_file)
        assert is_valid == False
        assert "Invalid filename" in message or "not allowed" in message
    
    def test_sanitize_input_normal(self):
        """Test input sanitization with normal input"""
        result = sanitize_input("Normal text input")
        assert result == "Normal text input"
    
    def test_sanitize_input_null_bytes(self):
        """Test input sanitization with null bytes"""
        result = sanitize_input("Text\x00with\x00nulls")
        assert "\x00" not in result
    
    def test_sanitize_input_too_long(self):
        """Test input sanitization with oversized input"""
        long_input = "x" * 15000
        result = sanitize_input(long_input)
        assert len(result) <= 10000
    
    def test_sanitize_input_empty(self):
        """Test input sanitization with empty input"""
        result = sanitize_input("")
        assert result == ""
    
    def test_sanitize_input_none(self):
        """Test input sanitization with None input"""
        result = sanitize_input(None)
        assert result == ""

class TestRateLimiting:
    """Test rate limiting functionality"""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization"""
        assert hasattr(rate_limiter, 'requests_per_minute')
        assert hasattr(rate_limiter, 'is_allowed')
        assert rate_limiter.requests_per_minute == 60
    
    def test_rate_limiter_allows_requests(self):
        """Test rate limiter allows requests within limit"""
        # Clear any existing requests
        rate_limiter.requests.clear()
        
        # Should allow requests within limit
        for i in range(10):
            assert rate_limiter.is_allowed("127.0.0.1") == True
    
    def test_rate_limiter_blocks_excessive_requests(self):
        """Test rate limiter blocks excessive requests"""
        # Clear any existing requests
        rate_limiter.requests.clear()
        
        # Make many requests quickly
        for i in range(70):  # More than the 60 per minute limit
            rate_limiter.is_allowed("127.0.0.1")
        
        # Next request should be blocked
        assert rate_limiter.is_allowed("127.0.0.1") == False

class TestPydanticModels:
    """Test Pydantic model validation"""
    
    def test_text_request_validation(self):
        """Test TextRequest model validation"""
        # Valid request
        request = TextRequest(prompt="Valid prompt")
        assert request.prompt == "Valid prompt"
        
        # Invalid requests
        with pytest.raises(ValueError):
            TextRequest(prompt="")
        
        with pytest.raises(ValueError):
            TextRequest(prompt="   ")
    
    def test_github_pr_request_validation(self):
        """Test GithubPRRequest Pydantic model validation"""
        from fastapi_app import GithubPRRequest
        
        # Test valid request
        request = GithubPRRequest(owner="test", repo="repo", pr=123)
        assert request.owner == "test"
        assert request.repo == "repo"
        assert request.pr == 123
        
        # Test invalid request (missing required fields)
        with pytest.raises(ValueError):
            GithubPRRequest(repo="test/repo", pr_number=123)
    
    def test_health_response_validation(self):
        """Test HealthResponse model validation"""
        # Valid responses
        response1 = HealthResponse(status="healthy")
        assert response1.status == "healthy"
        
        response2 = HealthResponse(status="unhealthy", error="Connection failed")
        assert response2.status == "unhealthy"
        assert response2.error == "Connection failed"

class TestGitIntegration:
    """Test Git integration functionality"""
    
    @patch('subprocess.run')
    def test_get_changed_files_success(self, mock_run):
        """Test getting changed files with successful git command"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.py\nfile2.py\nREADME.md"
        mock_run.return_value = mock_result
        
        changed_files = get_changed_files()
        assert "file1.py" in changed_files
        assert "file2.py" in changed_files
        assert "README.md" in changed_files
    
    @patch('subprocess.run')
    def test_get_changed_files_failure(self, mock_run):
        """Test getting changed files with failed git command"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        
        changed_files = get_changed_files()
        assert changed_files == set()
    
    @patch('subprocess.run')
    def test_get_changed_files_exception(self, mock_run):
        """Test getting changed files with exception"""
        mock_run.side_effect = Exception("Git not found")
        
        changed_files = get_changed_files()
        assert changed_files == set()

class TestDisplayFunctions:
    """Test display and UI functions"""
    
    def test_display_diff_no_changes(self):
        """Test display_diff with no changes"""
        old_content = "line1\nline2"
        new_content = "line1\nline2"
        
        # Should not raise any exceptions
        display_diff(old_content, new_content, "test.txt")
    
    def test_display_diff_with_changes(self):
        """Test display_diff with changes"""
        old_content = "line1\nline2"
        new_content = "line1\nline2\nline3"
        
        # Should not raise any exceptions
        display_diff(old_content, new_content, "test.txt")
    
    def test_spinner_function(self):
        """Test spinner function"""
        # Should not raise any exceptions
        from utils.helpers import spinner
        spinner("Test message", duration=0.1)

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 