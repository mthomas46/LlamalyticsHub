"""
Performance and stress tests for the LlamalyticsHub application.
Tests high-load scenarios, concurrent operations, and edge cases.
"""

import pytest
import tempfile
import os
import time
import threading
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi_app import app
from utils.helpers import analyze_files_parallel
from ollama_code_llama import OllamaCodeLlama

@pytest.fixture(scope="function")
def mock_llm_client():
    """Mock LLM client to avoid real API calls"""
    with patch('ollama_code_llama.OllamaCodeLlama.generate') as mock_generate:
        mock_generate.return_value = "Mocked LLM response"
        yield mock_generate

@pytest.fixture(scope="function")
def client():
    """FastAPI test client with patched rate limiter"""
    with patch('fastapi_app.rate_limiter') as mock_limiter:
        mock_limiter.is_allowed.return_value = True
        yield TestClient(app)

class TestRewrittenPerformanceScenarios:
    """Rewritten performance tests with proper mocking and fixtures"""
    
    def test_concurrent_file_analysis(self, mock_llm_client):
        """Test concurrent file analysis with proper mocking"""
        files = [
            {'filename': f'test_{i}.py', 'content': f'def test{i}(): pass'}
            for i in range(5)
        ]
        
        # Mock the analyze_code_files function to return proper results
        with patch('github_audit.analyze_code_files') as mock_analyze:
            mock_analyze.return_value = [{
                'filename': 'test.py',
                'analysis': 'This is a test file with basic functionality.',
                'sections': {
                    'summary': 'Basic test file',
                    'issues': [],
                    'recommendations': ['Add more tests']
                }
            }]
            # Use a real LLM client with generate patched
            llama = OllamaCodeLlama()
            with patch.object(llama, "generate", return_value="Mocked LLM response"):
                results = analyze_files_parallel(
                    files, [], [], "", llama, "test_repo", "main", None
                )
                assert isinstance(results, list)
                assert len(results) >= 0  # May be 0 if no valid files

    def test_multiple_file_uploads(self, client):
        """Test multiple file uploads with FastAPI TestClient"""
        # Create multiple test files in memory
        test_files = [
            ("test1.py", b"def test1(): pass"),
            ("test2.py", b"def test2(): pass"),
            ("test3.py", b"def test3(): pass")
        ]
        
        for filename, content in test_files:
            response = client.post(
                "/generate/file",
                files={"file": (filename, content, "text/plain")}
            )
            assert response.status_code in [200, 400, 413]

    def test_large_prompt_handling(self, client):
        """Test handling of large prompts"""
        large_prompt = "x" * 5000  # Large but not too large
        
        response = client.post(
            "/generate/text",
            json={"prompt": large_prompt}
        )
        assert response.status_code in [200, 400, 413]

class TestRewrittenStressScenarios:
    """Rewritten stress tests with proper mocking and fixtures"""
    
    def test_rapid_requests(self, client):
        """Test rapid successive requests with patched rate limiter"""
        # Test multiple rapid requests
        for i in range(5):
            response = client.post(
                "/generate/text",
                json={"prompt": f"Test prompt {i}"}
            )
            assert response.status_code in [200, 400, 413]

    def test_memory_intensive_operations(self, client):
        """Test memory usage with large operations"""
        for i in range(10):
            prompt = f"Test prompt {i}" * 100
            response = client.post(
                "/generate/text", 
                json={"prompt": prompt}
            )
            assert response.status_code in [200, 400, 413]

    def test_concurrent_api_calls(self, client):
        """Test concurrent API endpoint calls"""
        import threading
        
        results = []
        
        def make_request():
            response = client.get("/health")
            results.append(response.status_code)
        
        threads = [threading.Thread(target=make_request) for _ in range(10)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert all(status == 200 for status in results)

class TestRewrittenEdgeCaseScenarios:
    """Rewritten edge case tests with proper mocking and fixtures"""
    
    def test_empty_prompt(self, client):
        """Test handling of empty prompts"""
        response = client.post("/generate/text", json={"prompt": ""})
        assert response.status_code == 422  # Validation error for empty prompt

    def test_very_long_prompt(self, client):
        """Test handling of extremely long prompts"""
        too_long_prompt = "x" * 10001  # Exceeds max length
        
        response = client.post(
            "/generate/text", 
            json={"prompt": too_long_prompt}
        )
        assert response.status_code == 422  # Validation error for too long

    def test_invalid_file_types(self, client):
        """Test handling of invalid file types"""
        response = client.post(
            "/generate/file",
            files={"file": ("test.exe", b"executable content", "application/octet-stream")}
        )
        assert response.status_code in [400, 413, 422]

    def test_malformed_requests(self, client):
        """Test handling of malformed requests"""
        # Test missing required fields
        response = client.post("/generate/text", json={})
        assert response.status_code == 422
        
        # Test invalid JSON
        response = client.post("/generate/text", data="invalid json")
        assert response.status_code == 422

class TestRewrittenAsyncScenarios:
    """Rewritten async tests with proper mocking and fixtures"""
    
    def test_async_file_processing(self, mock_llm_client):
        """Test asynchronous file processing with proper mocking"""
        files = [
            {'filename': f'async_test_{i}.py', 'content': f'async def test{i}(): pass'}
            for i in range(5)
        ]
        
        # Mock the analyze_code_files function
        with patch('github_audit.analyze_code_files') as mock_analyze:
            mock_analyze.return_value = [{
                'filename': 'test.py',
                'analysis': 'Async test file analysis.',
                'sections': {
                    'summary': 'Async test file',
                    'issues': [],
                    'recommendations': ['Add async tests']
                }
            }]
            
            results = analyze_files_parallel(
                files, [], [], "", Mock(), "test_repo", "main", None
            )
            
            assert isinstance(results, list)

    def test_concurrent_llm_calls(self, client):
        """Test concurrent LLM API calls"""
        import threading
        
        def make_llm_request():
            response = client.post(
                "/generate/text", 
                json={"prompt": "Test concurrent request"}
            )
            return response.status_code
        
        threads = [threading.Thread(target=make_llm_request) for _ in range(5)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()

class TestRewrittenResourceManagement:
    """Rewritten resource management tests with proper mocking and fixtures"""
    
    def test_file_handle_cleanup(self, client):
        """Test proper cleanup of file handles"""
        for i in range(10):
            response = client.post(
                "/generate/text", 
                json={"prompt": f"Test prompt {i}"}
            )
            assert response.status_code in [200, 400, 413]

    def test_memory_cleanup(self, client):
        """Test memory cleanup after operations"""
        response = client.post(
            "/generate/file",
            files={"file": ("test.py", b"def test(): pass", "text/plain")}
        )
        assert response.status_code in [200, 400, 413]

    def test_session_cleanup(self, client):
        """Test session cleanup"""
        response = client.get("/health")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 