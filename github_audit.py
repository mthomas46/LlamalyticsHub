"""
github_audit.py
--------------
High-level orchestration and wrappers for GitHub repo analysis, LLM-based code review, test strategy, and README improvement.
Delegates core logic to modular helpers and prompt utilities.
"""
from github import Github
from llm.ollama_client import OllamaCodeLlama
from typing import List, Dict, Optional, Tuple
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from github_client.github_client import async_fetch_repo_data as new_async_fetch_repo_data
from github_client.github_client import fetch_repo_data as new_fetch_repo_data
from reports.report_manager import generate_markdown_report
from analysis.prompt_utils import (
    parse_llm_response,
    construct_file_analysis_prompt,
    construct_test_strategy_prompt,
    construct_readme_improvement_prompt
)
import asyncio
import os
import json
from rich.table import Table

console = Console()

MODULE = "GITHUB_AUDIT"
def log_info(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.info(f"[GITHUB_AUDIT] [{function}] [{action}] {context}{details}")
def log_warning(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.warning(f"[GITHUB_AUDIT] [{function}] [{action}] {context}{details}")
def log_error(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.error(f"[GITHUB_AUDIT] [{function}] [{action}] {context}{details}")
def log_exception(function, action, details):
    logger.exception(f"[{MODULE}] [{function}] [{action}] {details}")


async def async_fetch_repo_data(repo_full_name: str, branch: Optional[str], pr_number: Optional[int], token: str) -> Dict:
    """
    Wrapper for the new modular async_fetch_repo_data in github_client/github_client.py
    """
    return await new_async_fetch_repo_data(repo_full_name, branch, pr_number, token)


def fetch_repo_data(repo_full_name: str, branch: Optional[str], pr_number: Optional[int], token: str) -> Dict:
    """
    Wrapper for the new modular fetch_repo_data in github_client/github_client.py
    """
    return new_fetch_repo_data(repo_full_name, branch, pr_number, token)


def analyze_code_files(
    files: List[Dict],
    comments: List[Dict],
    commits: List[Dict],
    readme: str,
    llama: OllamaCodeLlama
) -> List[Dict]:
    """
    For each file/function, use LLM to summarize and suggest improvements.
    Returns a list of dicts with parsed sections.
    Args:
        files (List[Dict]): List of code files.
        comments (List[Dict]): List of code review comments.
        commits (List[Dict]): List of commit messages.
        readme (str): README content.
        llama (OllamaCodeLlama): LLM client instance.
    Returns:
        List[Dict]: List of analysis results for each file.
    """
    analyses = []
    comments_text = '\n'.join([f"- {comment['user']}: {comment['body']}" for comment in comments])
    commits_text = '\n'.join([f"- {commit['author']}: {commit['message']}" for commit in commits])
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
            prompt = construct_file_analysis_prompt(
                filename,
                content,
                readme_context,
                comments_text,
                commits_text
            )
            try:
                llm_response = llama.generate(prompt)
            except Exception as error:
                llm_response = f"[LLM error: {error}]"
            sections = parse_llm_response(llm_response)
        analyses.append({
            'filename': filename,
            **sections
        })
    return analyses


async def async_analyze_code_files(
    files: List[Dict],
    comments: List[Dict],
    commits: List[Dict],
    readme: str,
    llama: OllamaCodeLlama,
    partial_report_path: str = None,
    retry_callback=None,
    rebuild_cache: bool = False
) -> List[Dict]:
    """
    Async version: For each file/function, use LLM to summarize and suggest improvements (batch).
    Streams each result to disk as soon as it's ready (if partial_report_path is given).
    Tracks failed files and supports interactive retry via retry_callback.
    Uses cached results unless rebuild_cache is True.
    Returns a list of dicts with parsed sections and prints a summary table of statuses.
    Args:
        files (List[Dict]): List of code files.
        comments (List[Dict]): List of code review comments.
        commits (List[Dict]): List of commit messages.
        readme (str): README content.
        llama (OllamaCodeLlama): LLM client instance.
        partial_report_path (str, optional): Path to stream partial results.
        retry_callback (callable, optional): Callback for retrying failed files.
        rebuild_cache (bool): If True, ignore cache and re-analyze all files.
    Returns:
        List[Dict]: List of analysis results for each file.
    """
    from utils.helpers import hash_content, get_cache_path
    analyses = []
    failed_files = []
    file_status = {}
    comments_text = '\n'.join([f"- {comment['user']}: {comment['body']}" for comment in comments])
    commits_text = '\n'.join([f"- {commit['author']}: {commit['message']}" for commit in commits])
    readme_context = readme[:2000] if readme else ""
    prompts = []
    file_objs = []
    cached_results = {}
    uncached_files = []
    # Check cache for each file
    for file in files:
        filename = file.get('filename')
        content = file.get('content', '')
        if not content or len(content.strip()) == 0:
            file_status[filename] = 'Skipped (empty)'
            continue
        if len(content) > 100_000 or content.count('\n') > 4000:
            analyses.append({'filename': filename, 'summary': 'File too large for detailed LLM analysis. Skipping.'})
            file_status[filename] = 'Skipped (too large)'
            continue
        file_hash = hash_content(content)
        cache_path = get_cache_path('repo', 'branch', None, file_hash)  # You may want to pass real repo/branch/pr
        if not rebuild_cache and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as cache_file:
                    cached_result = json.load(cache_file)
                    analyses.append(cached_result)
                    cached_results[filename] = cached_result
                    file_status[filename] = 'Cached'
                    # Write cached result to partial report if requested
                    if partial_report_path:
                        log_info("async_analyze_code_files", "write_file_section_cached", f"Writing cached analysis for {filename} to {partial_report_path}", feature=MODULE, file=filename)
                        try:
                            with open(partial_report_path, 'a', encoding='utf-8') as f:
                                f.write(f"### `{cached_result['filename']}`\n\n**Summary:**\n\n{cached_result.get('summary', '')}\n\n")
                                if cached_result.get('suggestions'):
                                    f.write(f"**Suggestions:**\n\n{cached_result['suggestions']}\n\n")
                                if cached_result.get('code_example'):
                                    f.write(f"**Code Example:**\n\n```\n{cached_result['code_example']}\n```\n\n")
                                f.write("---\n\n")
                            log_info("async_analyze_code_files", "write_file_section_cached", f"Finished writing cached analysis for {filename} to {partial_report_path}", feature=MODULE, file=filename)
                        except Exception as write_err:
                            log_error("async_analyze_code_files", "write_file_section_cached", f"Error writing cached analysis for {filename} to {partial_report_path}: {write_err}", feature=MODULE, file=filename)
            except Exception:
                uncached_files.append(file)
                file_status[filename] = 'Analyzing'
        else:
            uncached_files.append(file)
            file_status[filename] = 'Analyzing'
    # Prepare prompts for uncached files
    for file in uncached_files:
        filename = file.get('filename')
        content = file.get('content', '')
        prompt = construct_file_analysis_prompt(
            filename,
            content,
            readme_context,
            comments_text,
            commits_text
        )
        prompts.append(prompt)
        file_objs.append(file)
    results = [None] * len(prompts)
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True
        ) as progress:
            overall_task = progress.add_task(
                f"Analyzing {len(prompts)} files with LLM...", total=len(prompts)
            )
            file_tasks = []
            for idx, file in enumerate(file_objs):
                filename = file.get('filename', f"File {idx+1}")
                file_task = progress.add_task(
                    f"[cyan]Analyzing:[/cyan] {filename} ({idx+1}/{len(prompts)})", total=1
                )
                file_tasks.append(file_task)
            batch_size = 8  # Tune as needed
            for i in range(0, len(prompts), batch_size):
                batch_prompts = prompts[i:i+batch_size]
                batch_files = file_objs[i:i+batch_size]
                try:
                    batch_results = await llama.batch_async_generate(batch_prompts)
                except KeyboardInterrupt:
                    progress.console.print("\n[red]Aborted by user. Returning to next prompt.[/red]")
                    return '__ABORTED__'
                for j, (file, llm_response) in enumerate(zip(batch_files, batch_results)):
                    idx = i + j
                    filename = file.get('filename', f"File {idx+1}")
                    file_task = file_tasks[idx]
                    try:
                        if not llm_response or 'LLM error' in llm_response:
                            failed_files.append(file)
                            results[idx] = None
                            file_status[filename] = 'Failed'
                        else:
                            sections = parse_llm_response(llm_response)
                            result = {'filename': filename, **sections}
                            results[idx] = result
                            analyses.append(result)
                            file_status[filename] = 'Done'
                            # Stream to disk if requested
                            if partial_report_path:
                                log_info("async_analyze_code_files", "write_file_section", f"Writing analysis for {filename} to {partial_report_path}", feature=MODULE, file=filename)
                                try:
                                    with open(partial_report_path, 'a', encoding='utf-8') as f:
                                        f.write(f"### `{result['filename']}`\n\n**Summary:**\n\n{result.get('summary', '')}\n\n")
                                        if result.get('suggestions'):
                                            f.write(f"**Suggestions:**\n\n{result['suggestions']}\n\n")
                                        if result.get('code_example'):
                                            f.write(f"**Code Example:**\n\n```\n{result['code_example']}\n```\n\n")
                                        f.write("---\n\n")
                                    log_info("async_analyze_code_files", "write_file_section", f"Finished writing analysis for {filename} to {partial_report_path}", feature=MODULE, file=filename)
                                except Exception as write_err:
                                    log_error("async_analyze_code_files", "write_file_section", f"Error writing analysis for {filename} to {partial_report_path}: {write_err}", feature=MODULE, file=filename)
                            # Save to cache
                            file_hash = hash_content(file.get('content', ''))
                            cache_path = get_cache_path('repo', 'branch', None, file_hash)  # Use real repo/branch/pr if available
                            try:
                                with open(cache_path, 'w', encoding='utf-8') as cf:
                                    json.dump(result, cf)
                            except Exception:
                                pass
                    except KeyboardInterrupt:
                        progress.console.print("\n[red]Aborted by user. Returning to next prompt.[/red]")
                        return '__ABORTED__'
                    progress.update(file_task, advance=1)
                    progress.update(overall_task, advance=1)
            for file_task in file_tasks:
                progress.remove_task(file_task)
    except KeyboardInterrupt:
        console.print("\n[red]Aborted by user. Returning to next prompt.[/red]")
        return '__ABORTED__'
    # Interactive retry for failed files
    if failed_files and retry_callback:
        retry = retry_callback(failed_files)
        if retry:
            retry_analyses = await async_analyze_code_files(
                failed_files, comments, commits, readme, llama, partial_report_path, retry_callback=None, rebuild_cache=rebuild_cache)
            analyses.extend(retry_analyses)
    # Print summary table
    table = Table(title="File Analysis Status", show_header=True, header_style="bold blue")
    table.add_column("Filename", style="cyan")
    table.add_column("Status", style="green")
    for file in files:
        filename = file.get('filename')
        status = file_status.get(filename, 'Unknown')
        table.add_row(filename, status)
    console.print(table)
    return [r for r in analyses if r]


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
    prompt = construct_test_strategy_prompt(
        file_list,
        small_file_snippets
    )
    try:
        response = llama.generate(prompt)
    except Exception as e:
        response = f"[LLM error: {e}]"
    return response


async def async_generate_test_strategy(files: List[Dict], llama: OllamaCodeLlama) -> str:
    file_list = '\n'.join([f"- {f['filename']}" for f in files])
    small_files = [f for f in files if f.get('content') and len(f['content']) < 4000]
    small_file_snippets = '\n'.join([
        f"File: {f['filename']}\n---\n{f['content'][:1000]}\n---" for f in small_files[:5]
    ])
    prompt = construct_test_strategy_prompt(
        file_list,
        small_file_snippets
    )
    try:
        response = await llama.async_generate(prompt)
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
    prompt = construct_readme_improvement_prompt(
        readme
    )
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


async def async_suggest_readme_improvements(readme: str, llama: OllamaCodeLlama) -> Tuple[str, str]:
    if not readme or not readme.strip():
        return ("No README found to analyze.", "")
    prompt = construct_readme_improvement_prompt(
        readme
    )
    try:
        response = await llama.async_generate(prompt)
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