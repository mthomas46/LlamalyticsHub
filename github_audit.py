import os
from github import Github
from ollama_code_llama import OllamaCodeLlama
from typing import List, Dict, Optional, Tuple
import re
from loguru import logger
from rich.console import Console

console = Console()


def fetch_repo_data(repo_full_name: str, branch: Optional[str], pr_number: Optional[int], token: str) -> Dict:
    """
    Fetch code files, changed files (if PR), code comments, commit messages, and README from a GitHub repo.
    Args:
        repo_full_name (str): e.g. 'user/repo'
        branch (str or None): branch name to analyze (if not PR)
        pr_number (int or None): PR number to analyze (if any)
        token (str): GitHub API token
    Returns:
        dict: {
            'files': List[dict],  # all code files (or changed files for PR)
            'comments': List[dict],
            'commits': List[dict],
            'readme': str,
            'pr_info': dict or None
        }
    """
    g = Github(token)
    repo = g.get_repo(repo_full_name)
    files = []
    comments = []
    commits = []
    readme = ""
    pr_info = None

    try:
        if pr_number:
            # Analyze only changed files in the PR
            pr = repo.get_pull(pr_number)
            pr_info = {
                'title': pr.title,
                'body': pr.body,
                'user': pr.user.login,
                'created_at': pr.created_at.isoformat(),
                'state': pr.state,
                'merged': pr.is_merged(),
                'base_branch': pr.base.ref,
                'head_branch': pr.head.ref,
                'url': pr.html_url
            }
            # Changed files
            for f in pr.get_files():
                file_content = None
                try:
                    file_content = repo.get_contents(f.filename, ref=pr.head.ref).decoded_content.decode('utf-8')
                except Exception:
                    file_content = None
                files.append({
                    'filename': f.filename,
                    'status': f.status,
                    'patch': getattr(f, 'patch', None),
                    'content': file_content
                })
            # PR comments
            for c in pr.get_issue_comments():
                comments.append({
                    'user': c.user.login,
                    'body': c.body,
                    'created_at': c.created_at.isoformat()
                })
            # PR review comments
            for c in pr.get_review_comments():
                comments.append({
                    'user': c.user.login,
                    'body': c.body,
                    'path': c.path,
                    'position': c.position,
                    'created_at': c.created_at.isoformat()
                })
            # PR commits
            for commit in pr.get_commits():
                commits.append({
                    'sha': commit.sha,
                    'message': commit.commit.message,
                    'author': commit.commit.author.name,
                    'date': commit.commit.author.date.isoformat()
                })
            # README (from base branch)
            try:
                readme = repo.get_readme(ref=pr.base.ref).decoded_content.decode('utf-8')
            except Exception:
                readme = ""
        else:
            # Analyze all code files in the branch
            ref = branch or repo.default_branch
            contents = repo.get_contents("", ref=ref)
            stack = contents[:]
            while stack:
                file_content = stack.pop()
                if file_content.type == "dir":
                    stack.extend(repo.get_contents(file_content.path, ref=ref))
                else:
                    # Only include code files (basic filter)
                    if file_content.name.endswith(('.py', '.js', '.ts', '.java', '.go', '.rb', '.cpp', '.c', '.cs', '.php', '.scala', '.rs', '.sh', '.pl', '.swift', '.kt', '.m', '.h', '.hpp', '.html', '.css', '.json', '.yml', '.yaml', '.xml', '.md')):
                        files.append({
                            'filename': file_content.path,
                            'content': file_content.decoded_content.decode('utf-8')
                        })
            # Branch commits
            for commit in repo.get_commits(sha=ref):
                commits.append({
                    'sha': commit.sha,
                    'message': commit.commit.message,
                    'author': commit.commit.author.name,
                    'date': commit.commit.author.date.isoformat()
                })
            # Branch comments (issues, PRs, etc. - not as direct as PR)
            # For simplicity, fetch recent issue comments
            for issue in repo.get_issues(state='all'):
                for c in issue.get_comments():
                    comments.append({
                        'user': c.user.login,
                        'body': c.body,
                        'created_at': c.created_at.isoformat()
                    })
            # README
            try:
                readme = repo.get_readme(ref=ref).decoded_content.decode('utf-8')
            except Exception:
                readme = ""
    except Exception as e:
        logger.exception("Error in fetch_repo_data")
        console.print_exception()

    return {
        'files': files,
        'comments': comments,
        'commits': commits,
        'readme': readme,
        'pr_info': pr_info
    }


def parse_llm_response(llm_response):
    # Heuristic parsing for common sections
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
        m = re.search(pat, llm_response, re.IGNORECASE | re.DOTALL)
        if m:
            sections[key] = m.group(1).strip()
    # Fallback: if summary is empty, use first 300 chars
    if not sections['summary']:
        sections['summary'] = llm_response[:300].strip()
    return sections


def analyze_code_files(files: List[Dict], comments: List[Dict], commits: List[Dict], readme: str, llama: OllamaCodeLlama) -> List[Dict]:
    """
    For each file/function, use LLM to summarize and suggest improvements.
    Returns a list of dicts with parsed sections.
    """
    analyses = []
    comments_text = '\n'.join([f"- {c['user']}: {c['body']}" for c in comments])
    commits_text = '\n'.join([f"- {c['author']}: {c['message']}" for c in commits])
    readme_context = readme[:2000] if readme else ""
    for file in files:
        filename = file.get('filename')
        content = file.get('content', '')
        if not content or len(content.strip()) == 0:
            continue
        if len(content) > 100_000 or content.count('\n') > 4000:
            llm_response = "File too large for detailed LLM analysis. Skipping."
            sections = {'summary': llm_response}
        else:
            prompt = f"""
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
            try:
                llm_response = llama.generate(prompt)
            except Exception as e:
                llm_response = f"[LLM error: {e}]"
            sections = parse_llm_response(llm_response)
        analyses.append({
            'filename': filename,
            **sections
        })
    return analyses


def generate_test_strategy(files: List[Dict], llama: OllamaCodeLlama) -> str:
    """
    Use LLM to suggest/refine test cases and generate a test strategy summary.
    Args:
        files (list): List of code file dicts
        llama (OllamaCodeLlama): LLM interface
    Returns:
        str: Test strategy summary
    """
    # Aggregate file names and (if small) content for context
    file_list = '\n'.join([f"- {f['filename']}" for f in files])
    small_files = [f for f in files if f.get('content') and len(f['content']) < 4000]
    small_file_snippets = '\n'.join([
        f"File: {f['filename']}\n---\n{f['content'][:1000]}\n---" for f in small_files[:5]
    ])
    prompt = f"""
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
    try:
        response = llama.generate(prompt)
    except Exception as e:
        response = f"[LLM error: {e}]"
    return response


def suggest_readme_improvements(readme: str, llama: OllamaCodeLlama) -> Tuple[str, str]:
    """
    Use LLM to suggest README improvements and output an updated README.
    Args:
        readme (str): Current README contents
        llama (OllamaCodeLlama): LLM interface
    Returns:
        tuple: (suggestions, updated_readme)
    """
    if not readme or not readme.strip():
        return ("No README found to analyze.", "")
    prompt = f"""
You are an expert technical writer and open source maintainer. Review the following README for clarity, completeness, and best practices. Suggest improvements, missing sections, and ways to make it more useful for users and contributors. Then, provide an updated version of the README with your suggestions applied.

--- BEGIN README ---
{readme[:12000]}
--- END README ---

Please provide:
1. A bullet list of suggested improvements and missing sections.
2. The full updated README with your suggestions applied.
"""
    try:
        response = llama.generate(prompt)
        # Try to split suggestions and updated README
        if '\n2.' in response:
            parts = response.split('\n2.', 1)
            suggestions = parts[0].replace('1.', '').strip()
            updated_readme = parts[1].strip()
        else:
            suggestions = response.strip()
            updated_readme = ""
    except Exception as e:
        suggestions = f"[LLM error: {e}]"
        updated_readme = ""
    return (suggestions, updated_readme)


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
        repo_full_name (str): Repository name
        branch (str or None): Branch name
        pr_number (int or None): PR number
        file_analyses (list): List of file/function analyses
        test_strategy (str): Test strategy summary
        readme_suggestions (str): Suggestions for README
        updated_readme (str): Updated README content
        extra_info (dict or None): Any extra info to include
    Returns:
        str: Markdown report as a string
    """
    lines = []
    lines.append(f"# GitHub Code Audit & Report\n")
    lines.append(f"**Repository:** `{repo_full_name}`  ")
    if branch:
        lines.append(f"**Branch:** `{branch}`  ")
    if pr_number:
        lines.append(f"**Pull Request:** `{pr_number}`  ")
    if extra_info:
        for k, v in extra_info.items():
            lines.append(f"**{k}:** {v}  ")
    lines.append("\n---\n")
    lines.append("## Table of Contents\n")
    lines.append("- [File Analyses](#file-analyses)")
    lines.append("- [Test Strategy](#test-strategy)")
    lines.append("- [README Suggestions](#readme-suggestions)")
    lines.append("- [Updated README](#updated-readme)\n")
    lines.append("---\n")
    # File Analyses
    lines.append("## File Analyses\n")
    for analysis in file_analyses:
        lines.append(f"### `{analysis['filename']}`\n")
        lines.append(f"**Summary:**\n\n{analysis.get('summary', '')}\n")
        if analysis.get('suggestions'):
            lines.append(f"**Suggestions:**\n\n{analysis['suggestions']}\n")
        if analysis.get('code_example'):
            lines.append(f"**Code Example:**\n\n```\n{analysis['code_example']}\n```\n")
        lines.append("---\n")
    # Test Strategy
    lines.append("## Test Strategy\n")
    lines.append(f"{test_strategy}\n")
    lines.append("---\n")
    # README Suggestions
    lines.append("## README Suggestions\n")
    lines.append(f"{readme_suggestions}\n")
    lines.append("---\n")
    # Updated README
    lines.append("## Updated README\n")
    lines.append(f"```markdown\n{updated_readme}\n```")
    lines.append("\n---\n")
    return '\n'.join(lines) 