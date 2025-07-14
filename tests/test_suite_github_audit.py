"""
GitHub Audit Test Suite - Can run in parallel with other test suites
Tests GitHub audit workflows, LLM analysis, and report generation
"""
import pytest
from unittest.mock import Mock, patch
import tempfile
import os

# Import GitHub audit functions
from github_audit import (
    analyze_code_files, generate_test_strategy, suggest_readme_improvements,
    generate_markdown_report
)


class TestGitHubAuditWorkflows:
    """Test GitHub audit workflows"""
    
    def test_analyze_code_files_basic(self):
        """Test basic code file analysis"""
        files = [{'filename': 'test.py', 'content': 'def test(): pass'}]
        llama = Mock()
        llama.generate.return_value = "This is a test function"
        
        result = analyze_code_files(files, [], [], "", llama)
        
        assert len(result) > 0
        assert 'test.py' in [r.get('filename', '') for r in result]
    
    def test_analyze_code_files_empty_content(self):
        """Test code analysis with empty content"""
        files = [{'filename': 'test.py', 'content': ''}]
        llama = Mock()
        
        result = analyze_code_files(files, [], [], "", llama)
        
        assert len(result) == 0  # Empty files should be skipped
    
    def test_analyze_code_files_large_file(self):
        """Test code analysis with large file"""
        # Create a large file content
        large_content = "def test():\n" + "    pass\n" * 5000  # Over 4000 lines
        files = [{'filename': 'large_test.py', 'content': large_content}]
        llama = Mock()
        
        result = analyze_code_files(files, [], [], "", llama)
        
        assert len(result) > 0
        # Should handle large files gracefully
        assert 'large_test.py' in [r.get('filename', '') for r in result]
    
    def test_analyze_code_files_llm_error(self):
        """Test code analysis with LLM error"""
        files = [{'filename': 'test.py', 'content': 'def test(): pass'}]
        llama = Mock()
        llama.generate.side_effect = Exception("LLM Error")
        
        result = analyze_code_files(files, [], [], "", llama)
        
        # Should handle errors gracefully
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_generate_test_strategy(self):
        """Test test strategy generation"""
        files = [{'filename': 'test.py', 'content': 'def test(): pass'}]
        
        with patch('github_audit.OllamaCodeLlama') as mock_llama:
            mock_llama_instance = Mock()
            mock_llama_instance.generate.return_value = "Test Strategy:\n1. Unit tests"
            mock_llama.return_value = mock_llama_instance
            
            result = generate_test_strategy(files, mock_llama_instance)
            
            assert "Test Strategy" in result or "Unit tests" in result
    
    def test_generate_test_strategy_empty_files(self):
        """Test test strategy generation with empty files"""
        files = []
        
        with patch('github_audit.OllamaCodeLlama') as mock_llama:
            mock_llama_instance = Mock()
            mock_llama_instance.generate.return_value = "No files to analyze"
            mock_llama.return_value = mock_llama_instance
            
            result = generate_test_strategy(files, mock_llama_instance)
            
            assert isinstance(result, str)
    
    def test_suggest_readme_improvements(self):
        """Test README improvement suggestions"""
        readme = "# Test Project\n\nA simple test project."
        
        with patch('github_audit.OllamaCodeLlama') as mock_llama:
            mock_llama_instance = Mock()
            mock_llama_instance.generate.return_value = "Suggestions:\n1. Add installation\n\nUpdated README:\n# Test Project\n\n## Installation"
            mock_llama.return_value = mock_llama_instance
            
            suggestions, updated_readme = suggest_readme_improvements(readme, mock_llama_instance)
            
            assert suggestions is not None
            assert updated_readme is not None
    
    def test_suggest_readme_improvements_empty_readme(self):
        """Test README improvements with empty README"""
        readme = ""
        
        with patch('github_audit.OllamaCodeLlama') as mock_llama:
            mock_llama_instance = Mock()
            mock_llama_instance.generate.return_value = "Suggestions:\n1. Add content\n\nUpdated README:\n# New Project"
            mock_llama.return_value = mock_llama_instance
            
            suggestions, updated_readme = suggest_readme_improvements(readme, mock_llama_instance)
            
            assert suggestions is not None
            assert updated_readme is not None


class TestReportGeneration:
    """Test report generation functionality"""
    
    def test_generate_markdown_report(self):
        """Test markdown report generation"""
        file_analyses = [
            {'filename': 'test.py', 'summary': 'Test function', 'suggestions': 'Add docstring'}
        ]
        test_strategy = "Test Strategy:\n1. Unit tests"
        readme_suggestions = "Suggestions:\n1. Add installation"
        updated_readme = "# Test Project\n\n## Installation"
        
        result = generate_markdown_report(
            "test/repo", "main", None,
            file_analyses, test_strategy, readme_suggestions, updated_readme
        )
        
        assert "GitHub Code Audit & Report" in result
        assert "test.py" in result
        assert "Test Strategy" in result
    
    def test_generate_markdown_report_with_pr(self):
        """Test markdown report generation with PR"""
        file_analyses = [
            {'filename': 'test.py', 'summary': 'Test function', 'suggestions': 'Add docstring'}
        ]
        test_strategy = "Test Strategy:\n1. Unit tests"
        readme_suggestions = "Suggestions:\n1. Add installation"
        updated_readme = "# Test Project\n\n## Installation"
        
        result = generate_markdown_report(
            "test/repo", "main", 123,
            file_analyses, test_strategy, readme_suggestions, updated_readme
        )
        
        assert "GitHub Code Audit & Report" in result
        assert "**Pull Request:** `123`" in result
    
    def test_generate_markdown_report_with_extra_info(self):
        """Test markdown report generation with extra info"""
        file_analyses = [
            {'filename': 'test.py', 'summary': 'Test function', 'suggestions': 'Add docstring'}
        ]
        test_strategy = "Test Strategy:\n1. Unit tests"
        readme_suggestions = "Suggestions:\n1. Add installation"
        updated_readme = "# Test Project\n\n## Installation"
        extra_info = {"Author": "test@example.com", "Created": "2024-01-01"}
        
        result = generate_markdown_report(
            "test/repo", "main", None,
            file_analyses, test_strategy, readme_suggestions, updated_readme,
            extra_info
        )
        
        assert "GitHub Code Audit & Report" in result
        assert "**Author:** test@example.com" in result
        assert "**Created:** 2024-01-01" in result
    
    def test_generate_markdown_report_empty_analyses(self):
        """Test markdown report generation with empty analyses"""
        file_analyses = []
        test_strategy = "Test Strategy:\n1. Unit tests"
        readme_suggestions = "Suggestions:\n1. Add installation"
        updated_readme = "# Test Project\n\n## Installation"
        
        result = generate_markdown_report(
            "test/repo", "main", None,
            file_analyses, test_strategy, readme_suggestions, updated_readme
        )
        
        assert "GitHub Code Audit & Report" in result
        assert "File Analyses" in result


class TestErrorHandling:
    """Test error handling in GitHub audit workflows"""
    
    def test_analyze_code_files_with_llm_error(self):
        """Test code analysis with LLM error"""
        files = [{'filename': 'test.py', 'content': 'def test(): pass'}]
        llama = Mock()
        llama.generate.side_effect = Exception("LLM Error")
        
        result = analyze_code_files(files, [], [], "", llama)
        
        # Should handle errors gracefully
        assert isinstance(result, list)
        assert len(result) > 0
    
    def test_generate_test_strategy_with_llm_error(self):
        """Test test strategy generation with LLM error"""
        files = [{'filename': 'test.py', 'content': 'def test(): pass'}]
        
        with patch('github_audit.OllamaCodeLlama') as mock_llama:
            mock_llama_instance = Mock()
            mock_llama_instance.generate.side_effect = Exception("LLM Error")
            mock_llama.return_value = mock_llama_instance
            
            result = generate_test_strategy(files, mock_llama_instance)
            
            # Should handle errors gracefully
            assert isinstance(result, str)
    
    def test_suggest_readme_improvements_with_llm_error(self):
        """Test README improvements with LLM error"""
        readme = "# Test Project\n\nA simple test project."
        
        with patch('github_audit.OllamaCodeLlama') as mock_llama:
            mock_llama_instance = Mock()
            mock_llama_instance.generate.side_effect = Exception("LLM Error")
            mock_llama.return_value = mock_llama_instance
            
            suggestions, updated_readme = suggest_readme_improvements(readme, mock_llama_instance)
            
            # Should handle errors gracefully
            assert suggestions is not None
            assert updated_readme is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"]) 