"""
reports/report_manager.py
------------------------
Helpers for generating, previewing, and managing Markdown reports for code audits and LLM analysis results.
"""
from typing import List, Dict, Optional
from loguru import logger

MODULE = "REPORT_MANAGER"
def log_info(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.info(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_warning(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.warning(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_error(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.error(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_exception(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.exception(f"[{MODULE}] [{function}] [{action}] {context}{details}")

def generate_markdown_report(
    repo_full_name: str,
    branch: Optional[str],
    pr_number: Optional[int],
    file_analyses: List[Dict],
    test_strategy: str,
    readme_suggestions: str,
    updated_readme: str,
    extra_info: Optional[Dict] = None
) -> str:
    """
    Aggregate all results into a Markdown report.
    Args:
        repo_full_name (str): Repository name.
        branch (str or None): Branch name.
        pr_number (int or None): PR number.
        file_analyses (list): List of file/function analyses.
        test_strategy (str): Test strategy summary.
        readme_suggestions (str): Suggestions for README.
        updated_readme (str): Updated README content.
        extra_info (dict or None): Any extra info to include.
    Returns:
        str: Markdown report as a string.
    """
    lines = []
    # Report header
    lines.append(f"# GitHub Code Audit & Report\n")
    lines.append(f"**Repository:** `{repo_full_name}`  ")
    if branch:
        lines.append(f"**Branch:** `{branch}`  ")
    if pr_number:
        lines.append(f"**Pull Request:** `{pr_number}`  ")
    if extra_info:
        for key, value in extra_info.items():
            lines.append(f"**{key}:** {value}  ")
    lines.append("\n---\n")
    # Table of Contents
    lines.append("## Table of Contents\n")
    lines.append("- [File Analyses](#file-analyses)")
    lines.append("- [Test Strategy](#test-strategy)")
    lines.append("- [README Suggestions](#readme-suggestions)")
    lines.append("- [Updated README](#updated-readme)\n")
    lines.append("---\n")
    # File Analyses section
    lines.append("## File Analyses\n")
    for analysis in file_analyses:
        lines.append(f"### `{analysis['filename']}`\n")
        lines.append(f"**Summary:**\n\n{analysis.get('summary', '')}\n")
        if analysis.get('suggestions'):
            lines.append(f"**Suggestions:**\n\n{analysis['suggestions']}\n")
        if analysis.get('code_example'):
            lines.append(f"**Code Example:**\n\n```\n{analysis['code_example']}\n```\n")
        lines.append("---\n")
    # Test Strategy section
    lines.append("## Test Strategy\n")
    lines.append(f"{test_strategy}\n")
    lines.append("---\n")
    # README Suggestions section
    lines.append("## README Suggestions\n")
    lines.append(f"{readme_suggestions}\n")
    lines.append("---\n")
    # Updated README section
    lines.append("## Updated README\n")
    lines.append(f"```markdown\n{updated_readme}\n```")
    lines.append("\n---\n")
    return '\n'.join(lines)

def preview_report(report_path, lines=40):
    """
    Preview the first N lines of a report file in the CLI.
    Args:
        report_path (str): Path to the report file.
        lines (int): Number of lines to preview.
    """
    from rich.panel import Panel
    from rich.console import Console
    console = Console()
    with open(report_path, 'r', encoding='utf-8') as f:
        preview_lines = f.readlines()[:lines]
    console.print(Panel("".join(preview_lines), title="Report Preview", style="cyan")) 