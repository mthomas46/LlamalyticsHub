"""
utils/helpers.py
----------------
General-purpose utility functions for file naming, hashing, caching, file filtering, 
diff display, parallel LLM analysis, git diff, CLI spinners, and .env file management.
These helpers are used throughout the application for modularity and code reuse.
"""

import os
import hashlib
from github_audit import analyze_code_files
from loguru import logger


def log_info(function, action, details, feature=None, file=None, 
             prompt_hash=None):
    """Log info messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    logger.info(f"[{function}] [{action}] {context}{details}")


def log_warning(function, action, details, feature=None, file=None, 
                prompt_hash=None):
    """Log warning messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    logger.warning(f"[{function}] [{action}] {context}{details}")


def log_error(function, action, details, feature=None, file=None, 
              prompt_hash=None):
    """Log error messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    logger.error(f"[{function}] [{action}] {context}{details}")


def log_exception(function, action, details, feature=None, file=None, 
                  prompt_hash=None):
    """Log exception messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    logger.exception(f"[{function}] [{action}] {context}{details}")


def safe_name(name: str) -> str:
    """
    Convert a string to a safe filename by replacing invalid characters.
    Args:
        name (str): The string to convert.
    Returns:
        str: A safe filename.
    """
    # Replace invalid characters with underscores
    invalid_chars = '<>:"/\\|?*@'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.replace(' ', '_')


def get_report_filename(repository: str, branch: str, 
                       pull_request_number: int = None) -> str:
    """
    Generate a safe filename for a GitHub audit report.
    Args:
        repository (str): Repository name (e.g., 'owner/repo').
        branch (str): Branch name.
        pull_request_number (int, optional): PR number if applicable.
    Returns:
        str: Safe filename for the report.
    """
    safe_repo = safe_name(repository)
    safe_branch = safe_name(branch)
    pr_part = f'_pr{pull_request_number}' if pull_request_number else ''
    return f"github_audit_{safe_repo}_{safe_branch}{pr_part}.md"


def get_readme_filename(repository: str, branch: str) -> str:
    """
    Generate a safe filename for an updated README file.
    Args:
        repository (str): Repository name.
        branch (str): Branch name.
    Returns:
        str: Safe filename for the updated README.
    """
    return f"updated_readme_{safe_name(repository)}_{safe_name(branch)}.md"


def hash_content(content: str) -> str:
    """
    Compute a SHA-256 hash of the given content string.
    Args:
        content (str): The content to hash.
    Returns:
        str: The SHA-256 hash as a hex string.
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def get_cache_path(repository: str, branch: str, pull_request_number: int, 
                   filename_hash: str) -> str:
    """
    Generate a filesystem path for caching LLM analysis results for a specific file.
    Args:
        repository (str): Repository name.
        branch (str): Branch name.
        pull_request_number (int): PR number if applicable.
        filename_hash (str): Hash of the file content.
    Returns:
        str: Path to the cache file.
    """
    safe_repo = repository.replace('/', '_')
    safe_branch = (branch or 'default').replace('/', '_')
    pr_part = f'_pr{pull_request_number}' if pull_request_number else ''
    cache_dir = os.path.join('.cache', f'{safe_repo}_{safe_branch}{pr_part}')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'{filename_hash}.json')


def filter_files(files, filter_mode, pattern=None, manual_selection=None):
    """
    Filter files based on pattern or manual selection.
    Args:
        files (list): List of file dicts.
        filter_mode (str): 'pattern', 'manual', or 'none'.
        pattern (str, optional): Glob pattern.
        manual_selection (list, optional): List of selected filenames.
    Returns:
        list: Filtered list of file dicts.
    """
    import fnmatch
    if filter_mode == 'pattern' and pattern:
        return [f for f in files if fnmatch.fnmatch(f['filename'], pattern)]
    elif filter_mode == 'manual' and manual_selection:
        return [f for f in files if f['filename'] in manual_selection]
    return files


def display_diff(old_content, new_content, filename):
    """
    Display a colorized diff for a file using rich and difflib.
    Args:
        old_content (str): The old file content.
        new_content (str): The new file content.
        filename (str): The filename for labeling the diff.
    """
    import difflib
    from rich.syntax import Syntax
    from rich.panel import Panel
    from rich.console import Console
    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(),
        new_content.splitlines(),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=''
    ))
    if not diff_lines:
        return
    diff_text = '\n'.join(diff_lines)
    syntax = Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=False)
    console = Console()
    console.print(
        Panel(syntax, title=f"[bold magenta]Diff for {filename}", style="magenta")
    )


def analyze_files_parallel(files, comments, commits, readme, llm_client, 
                          repo_name, branch_name, pr_number, max_workers=8):
    """
    Analyze files in parallel using the LLM client, with caching.
    Args:
        files: List of file dicts.
        comments: List of comments.
        commits: List of commits.
        readme: README content.
        llm_client: LLM client instance.
        repo_name: Repository name.
        branch_name: Branch name.
        pr_number: PR number.
        max_workers: Number of parallel workers.
    Returns:
        List of analysis results.
    """
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from rich.progress import Progress
    results = []
    uncached = []
    cache_map = {}
    for file_obj in files:
        content = file_obj.get('content', '')
        if not content:
            continue
        file_hash = hash_content(content)
        cache_path = get_cache_path(repo_name, branch_name, pr_number, file_hash)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as cache_file:
                    cached_result = json.load(cache_file)
                    results.append(cached_result)
                    cache_map[file_obj['filename']] = True
            except Exception:
                uncached.append(file_obj)
        else:
            uncached.append(file_obj)
    if uncached:
        with Progress() as progress:
            task = progress.add_task("Analyzing files with LLM...", total=len(uncached))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(analyze_code_files, [f], comments, commits, 
                                   readme, llm_client): f for f in uncached
                }
                for future in as_completed(futures):
                    file_result = future.result()
                    if file_result:
                        results.extend(file_result)
                        f = futures[future]
                        content = f.get('content', '')
                        file_hash = hash_content(content)
                        cache_path = get_cache_path(repo_name, branch_name, 
                                                   pr_number, file_hash)
                        try:
                            with open(cache_path, 'w', encoding='utf-8') as cf:
                                json.dump(file_result[0], cf)
                        except Exception:
                            pass
                    progress.update(task, advance=1)
    return results


def get_changed_files():
    """
    Return a set of changed files using git diff if available.
    Returns:
        set: Set of changed filenames.
    """
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD'], 
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return set(result.stdout.splitlines())
    except Exception:
        pass
    return set()


def spinner(message: str, duration: int = 2):
    """
    Display a spinner/progress indicator for a given duration.
    Args:
        message (str): The message to display.
        duration (int): Duration in seconds.
    """
    import time
    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(
        SpinnerColumn(), 
        TextColumn("[progress.description]{task.description}"), 
        transient=True
    ) as progress:
        task = progress.add_task(message, total=None)
        time.sleep(duration)
        progress.remove_task(task)


def update_env_file(env_vars: dict, env_path: str = '.env') -> None:
    """
    Update or append key-value pairs in a .env file.
    Args:
        env_vars (dict): Dictionary of environment variables to set.
        env_path (str): Path to the .env file (default: '.env').
    """
    if not os.path.exists(env_path):
        with open(env_path, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')
        return
    with open(env_path, 'r+') as f:
        lines = f.readlines()
        # Parse existing environment variables
        existing_vars = {
            line.split('=')[0]: line.split('=')[1].strip() 
            for line in lines if '=' in line
        }
        for key, value in env_vars.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f'{key}='):
                    lines[i] = f'{key}={value}\n'
                    found = True
                    break
            if not found:
                lines.append(f'{key}={value}\n')
        f.seek(0)
        f.truncate()
        f.writelines(lines) 