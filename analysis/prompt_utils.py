"""
analysis/prompt_utils.py
-----------------------
Utilities for constructing LLM prompts and parsing LLM responses for code analysis, test strategy, and README improvement.
"""
from typing import Dict, List
import re

def parse_llm_response(llm_response: str) -> Dict[str, str]:
    """
    Heuristically parse the LLM response into common report sections.
    Args:
        llm_response (str): The raw response from the LLM.
    Returns:
        dict: Parsed sections (summary, bugs_issues, suggestions, etc.).
    """
    sections = {
        'summary': '',
        'bugs_issues': '',
        'suggestions': '',
        'code_example': '',
        'code_smells': '',
        'security_performance': '',
        'test_coverage': ''
    }
    # Patterns for section headers
    patterns = {
        'summary': r'(?:summary of what this file does|summary):?\s*(.*?)(?=\n- |\n\*|\n[A-Z][a-z]+:|\n$)',
        'bugs_issues': r'(?:bugs or issues found|bugs/issues|issues):?\s*(.*?)(?=\n- |\n\*|\n[A-Z][a-z]+:|\n$)',
        'suggestions': r'(?:suggestions for improvement|suggestions):?\s*(.*?)(?=\n- |\n\*|\n[A-Z][a-z]+:|\n$)',
        'code_example': r'(?:code example|example):?\s*```[\w+]*\n?(.*?)```',
        'code_smells': r'(?:code smells|anti-patterns):?\s*(.*?)(?=\n- |\n\*|\n[A-Z][a-z]+:|\n$)',
        'security_performance': r'(?:security or performance concerns|security/performance):?\s*(.*?)(?=\n- |\n\*|\n[A-Z][a-z]+:|\n$)',
        'test_coverage': r'(?:test coverage and quality|test coverage):?\s*(.*?)(?=\n- |\n\*|\n[A-Z][a-z]+:|\n$)'
    }
    for key, pat in patterns.items():
        match = re.search(pat, llm_response, re.IGNORECASE | re.DOTALL)
        if match:
            sections[key] = match.group(1).strip()
    # Fallback: if summary is empty, use first 300 chars
    if not sections['summary']:
        sections['summary'] = llm_response[:300].strip()
    return sections

def construct_file_analysis_prompt(filename: str, content: str, readme_context: str, commits_text: str, comments_text: str) -> str:
    """
    Construct a prompt for LLM file analysis.
    Args:
        filename (str): The filename being analyzed.
        content (str): The file content.
        readme_context (str): Excerpt from the README.
        commits_text (str): Recent commit messages.
        comments_text (str): Recent code review comments.
    Returns:
        str: The constructed prompt.
    """
    return f"""
You are an expert code reviewer. Analyze the following file for bugs, code quality, maintainability, and best practices. Use the README, recent commit messages, and code review comments as context. For small files, include a code example for any suggested improvement.

File: {filename}

README (excerpt):
{readme_context}

Recent commit messages:
{commits_text[:1000]}

Recent code review comments:
{comments_text[:1000]}

--- BEGIN FILE CONTENT ---
{content[:8000]}
--- END FILE CONTENT ---

Please provide:
- A concise summary of what this file does
- Any bugs or issues found
- Suggestions for improvement (with code examples if file is small)
- Notable code smells or anti-patterns
- Security or performance concerns
- If the file is a test, comment on test coverage and quality
"""

def construct_test_strategy_prompt(file_list: str, small_file_snippets: str) -> str:
    """
    Construct a prompt for LLM test strategy analysis.
    Args:
        file_list (str): List of files in the codebase.
        small_file_snippets (str): Snippets from small files.
    Returns:
        str: The constructed prompt.
    """
    return f"""
You are an expert software test strategist. Given the following codebase, generate a high-level test strategy, suggest missing or refinable test cases, and comment on the overall testability of the codebase. If possible, provide example test cases for critical or under-tested areas.

Codebase file list:
{file_list}

Sample file contents:
{small_file_snippets}

Please provide:
- A summary of the recommended test strategy
- Suggestions for missing or weak test cases
- Example test cases (if possible)
- Any notes on test coverage, structure, or improvements
"""

def construct_readme_improvement_prompt(readme: str) -> str:
    """
    Construct a prompt for LLM README improvement analysis.
    Args:
        readme (str): The README content.
    Returns:
        str: The constructed prompt.
    """
    return f"""
You are an expert technical writer and open source maintainer. Review the following README for clarity, completeness, and best practices. Suggest improvements, missing sections, and ways to make it more useful for users and contributors. Then, provide an updated version of the README with your suggestions applied.

--- BEGIN README ---
{readme[:12000]}
--- END README ---

Please provide:
1. A bullet list of suggested improvements and missing sections.
2. The full updated README with your suggestions applied.
"""

# Add more prompt construction utilities here as needed. 