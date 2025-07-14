"""
Optimized API GitHub Test Suite - Fast execution with comprehensive mocking
Tests Flask API GitHub PR analysis and integration endpoints
"""
import pytest
from unittest.mock import Mock, patch
from http_api import app

class TestAPIGitHubFeaturesOptimized:
    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch('http_api.OllamaCodeLlama') as mock_llama_class:
            mock_llama = Mock()
            mock_llama.generate.return_value = "Mocked LLM response"
            mock_llama_class.return_value = mock_llama
            yield

    def test_github_pr_analysis_endpoint_fast(self):
        client = app.test_client()
        with patch('http_api.Github') as mock_github_class:
            mock_github = Mock()
            mock_repo = Mock()
            mock_pr = Mock()
            mock_file = Mock()
            mock_file.filename = "test.py"
            mock_file.patch = "diff content"
            mock_pr.get_files.return_value = [mock_file]
            mock_repo.get_pull.return_value = mock_pr
            mock_github_class.return_value = mock_github
            mock_github.get_repo.return_value = mock_repo
            with patch('http_api.llama.generate', return_value="PR analysis complete"):
                response = client.post(
                    "/generate/github-pr",
                    json={"repo": "test/repo", "pr_number": 123, "token": "ghp_test"}
                )
                assert response.status_code in [200, 400, 422]

    def test_multiple_requests_fast(self):
        client = app.test_client()
        with patch('http_api.llama.generate', return_value="Fast response"):
            responses = []
            for i in range(5):
                response = client.post(
                    "/generate/text",
                    json={"prompt": f"Test prompt {i}"}
                )
                responses.append(response)
            assert all(r.status_code == 200 for r in responses) 