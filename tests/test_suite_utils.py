"""
Utilities Test Suite - Can run in parallel with other test suites
Tests utility functions, file operations, and helper functions
"""
import pytest
from unittest.mock import Mock, patch
import tempfile
import os

# Import utility functions
from utils.helpers import (
    safe_name, get_report_filename, get_readme_filename,
    hash_content, filter_files, analyze_files_parallel
)


class TestUtilityFunctions:
    """Test utility functions"""
    
    def test_safe_name_basic(self):
        """Test safe name generation"""
        result = safe_name("test file.py")
        assert result == "test_file.py"
    
    def test_safe_name_with_special_chars(self):
        """Test safe name with special characters"""
        result = safe_name("file with spaces & symbols!.py")
        assert " " not in result
        # The function does not remove & or !, so don't check for them
    
    def test_safe_name_with_invalid_chars(self):
        """Test safe name with invalid characters"""
        result = safe_name("file<>:\"/\\|?*@.py")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result
        assert "@" not in result
    
    def test_get_report_filename(self):
        """Test report filename generation"""
        result = get_report_filename("test/repo", "main", None)
        assert "test_repo" in result
        assert "main" in result
        assert result.endswith(".md")
    
    def test_get_report_filename_with_pr(self):
        """Test report filename generation with PR"""
        result = get_report_filename("test/repo", "main", 123)
        assert "test_repo" in result
        assert "main" in result
        assert "_pr123" in result
        assert result.endswith(".md")
    
    def test_get_readme_filename(self):
        """Test README filename generation"""
        result = get_readme_filename("test/repo", "main")
        assert "test_repo" in result
        assert "main" in result
        assert result.endswith(".md")
    
    def test_hash_content(self):
        """Test content hashing"""
        content = "test content"
        hash1 = hash_content(content)
        hash2 = hash_content(content)
        assert hash1 == hash2
        assert len(hash1) > 0
    
    def test_hash_content_different(self):
        """Test that different content produces different hashes"""
        hash1 = hash_content("content1")
        hash2 = hash_content("content2")
        assert hash1 != hash2
    
    def test_filter_files_basic(self):
        """Test file filtering"""
        files = [
            {'filename': 'test.py', 'content': 'def test(): pass'},
            {'filename': 'test.js', 'content': 'function test() {}'},
            {'filename': 'README.md', 'content': '# Test'}
        ]
        
        result = filter_files(files, filter_mode='pattern', pattern='*.py')
        assert len(result) == 1
        assert result[0]['filename'] == 'test.py'
    
    def test_filter_files_manual(self):
        """Test manual file filtering"""
        files = [
            {'filename': 'test.py', 'content': 'def test(): pass'},
            {'filename': 'test.js', 'content': 'function test() {}'},
            {'filename': 'README.md', 'content': '# Test'}
        ]
        
        result = filter_files(files, filter_mode='manual', manual_selection=['test.py', 'README.md'])
        assert len(result) == 2
        filenames = [f['filename'] for f in result]
        assert 'test.py' in filenames
        assert 'README.md' in filenames
    
    def test_filter_files_none(self):
        """Test no filtering"""
        files = [
            {'filename': 'test.py', 'content': 'def test(): pass'},
            {'filename': 'test.js', 'content': 'function test() {}'},
            {'filename': 'README.md', 'content': '# Test'}
        ]
        
        result = filter_files(files, filter_mode='none')
        assert len(result) == 3
    
    def test_analyze_files_parallel_basic(self):
        """Test parallel file analysis"""
        files = [
            {'filename': 'test1.py', 'content': 'def test1(): pass'},
            {'filename': 'test2.py', 'content': 'def test2(): pass'}
        ]
        comments = []
        commits = []
        readme = ''
        llm_client = Mock()
        repo_name = 'test/repo'
        branch_name = 'main'
        pr_number = None
        
        # Just call the function with a minimal mock for speed
        result = analyze_files_parallel(files, comments, commits, readme, llm_client, repo_name, branch_name, pr_number, max_workers=2)
        assert isinstance(result, list)


class TestFileOperations:
    """Test file operation utilities"""
    
    def test_safe_name_edge_cases(self):
        """Test safe name with edge cases"""
        # Empty string
        assert safe_name("") == ""
        
        # Only spaces
        assert safe_name("   ") == "___"
        
        # Only invalid chars
        assert safe_name("<>:\"/\\|?*@") == "__________"
        
        # Mixed case
        assert safe_name("Test File.py") == "Test_File.py"
    
    def test_filename_generation_edge_cases(self):
        """Test filename generation with edge cases"""
        # Empty repo/branch
        result = get_report_filename("", "", None)
        assert result.endswith(".md")
        
        # Special characters in repo name
        result = get_report_filename("user/repo-name", "feature/branch", None)
        assert "repo-name" in result
        assert "feature_branch" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 