"""
Test summary report for high-impact test coverage.
This module provides comprehensive test coverage verification.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from fastapi_app import app
from utils.helpers import (
    safe_name, get_report_filename, get_readme_filename, get_cache_path,
    filter_files, update_env_file, display_diff, spinner
)
from fastapi_app import (
    rate_limiter, TextRequest, GithubPRRequest, HealthResponse
)


@pytest.fixture(scope="function")
def client():
    """FastAPI test client with patched rate limiter"""
    with patch('fastapi_app.rate_limiter') as mock_limiter:
        mock_limiter.is_allowed.return_value = True
        yield TestClient(app)

class TestRewrittenSummaryReport:
    """Rewritten summary report tests with proper mocking and fixtures"""
    
    def test_error_handling_coverage(self, client):
        """Test error handling coverage with proper API testing"""
        # Test invalid request
        response = client.post("/generate/text", json={"prompt": ""})
        assert response.status_code == 422  # Validation error for empty prompt

    def test_model_validation_coverage(self, client):
        """Test model validation coverage"""
        from fastapi_app import GithubPRRequest
        
        # Test valid model creation
        request = GithubPRRequest(owner="test", repo="repo", pr=1)
        assert request.owner == "test"
        assert request.repo == "repo"
        assert request.pr == 1
        
        # Test invalid model creation
        with pytest.raises(ValueError):
            GithubPRRequest(owner="", repo="repo", pr=1) 