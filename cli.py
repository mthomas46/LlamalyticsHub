"""
cli.py
------
Main entrypoint and interactive command-line interface for the Ollama Code Llama application.
Handles user interaction, menu routing, and orchestration of code analysis, reporting, and server management.
"""
# Standard library imports
import argparse
import os
import sys
import time
import json
import subprocess
import tempfile
import hashlib
import asyncio
import traceback
from typing import Optional

# Third-party imports
from github import Github
from pydantic import BaseModel, Field, ValidationError, field_validator, AnyUrl
from loguru import logger
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary
import requests

# Local imports
from llm.ollama_client import OllamaCodeLlama
from github_client.github_client import async_fetch_repo_data as new_async_fetch_repo_data
from github_client.github_client import fetch_repo_data as new_fetch_repo_data
from config.config_manager import load_config, print_config, collect_config_edit_args, ConfigEditModel
from server.server_manager import start_server, stop_server, show_server_status, write_env_vars_for_server, print_banner
from utils.helpers import (
    safe_name, get_report_filename, get_readme_filename, hash_content, get_cache_path,
    filter_files, display_diff, analyze_files_parallel, get_changed_files, spinner
)
from github_audit import (
    async_fetch_repo_data,
    fetch_repo_data,
    analyze_code_files,
    async_analyze_code_files,
    generate_test_strategy,
    async_generate_test_strategy,
    suggest_readme_improvements,
    async_suggest_readme_improvements,
    generate_markdown_report
)
from reports.report_manager import preview_report

console = Console()

# Global caches for GitHub data
repo_cache = []
branch_cache = {}
pr_cache = {}

# Set up Loguru logging
# Remove all previous handlers to avoid logging to stdout/stderr
logger.remove()
logger.add(os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log'), rotation="10 MB", retention="10 days", compression="zip", enqueue=True, backtrace=True, diagnose=True)

# Standardized logging helper
MODULE = "CLI"
def log_info(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.info(f"[CLI] [{function}] [{action}] {context}{details}")
def log_warning(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.warning(f"[CLI] [{function}] [{action}] {context}{details}")
def log_error(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.error(f"[CLI] [{function}] [{action}] {context}{details}")
def log_exception(function, action, details):
    logger.exception(f"[{MODULE}] [{function}] [{action}] {details}")

def print_banner() -> None:
    try:
        banner = Text("Ollama Code Llama CLI", style="bold magenta")
        console.print(Panel(banner, expand=False, border_style="cyan"))
        log_info("print_banner", "display", "Banner printed successfully.", feature="print_banner")
    except Exception as e:
        log_exception("print_banner", "display", f"Failed to print banner: {e}", feature="print_banner")

def print_config():
    try:
        config = load_config()
        table = Table(title="Current config.yaml", show_header=True, header_style="bold blue")
        table.add_column("Section", style="cyan", no_wrap=True)
        table.add_column("Key", style="green")
        table.add_column("Value", style="yellow")
        for section, values in config.items():
            if isinstance(values, dict):
                for k, v in values.items():
                    table.add_row(str(section), str(k), str(v))
            else:
                table.add_row(str(section), "-", str(values))
        console.print(table)
        log_info("print_config", "display", "Config table printed.", feature="print_config")
        if questionary.confirm("Edit config?").ask():
            args = collect_config_edit_args(config)
            if not args:
                log_info("print_config", "edit", "User aborted config edit.", feature="print_config")
                return
            section, key, value = args['section'], args['key'], args['value']
            if section in config and isinstance(config[section], dict):
                config[section][key] = value
            else:
                config[section] = {key: value}
            with open('config.yaml', 'w') as f:
                import yaml
                yaml.safe_dump(config, f)
            console.print("[green]Config updated.[/green]")
            log_info("print_config", "edit", f"Config updated: {section}.{key} = {value}", feature="print_config")
    except Exception as e:
        log_exception("print_config", "display/edit", f"Error: {e}", feature="print_config")
        console.print(f"[red]Error displaying or editing config: {e}[/red]")

def print_logs():
    log_file = os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log')
    console.print(Panel("Recent logs", style="bold blue"))
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()[-50:]
            for line in lines:
                console.print(Text(line.rstrip(), style="dim"))
    except FileNotFoundError:
        console.print("[yellow]No log file found.[/yellow]")

class LogViewModel(BaseModel):
    log_file: str
    lines: int = 50
    filter: str = None
    @field_validator('log_file')
    def valid_log_file(cls, v):
        if '..' in v or '\x00' in v:
            raise ValueError('Invalid log file path')
        return v

class ServerParamsModel(BaseModel):
    host: str
    port: int
    model: str
    @field_validator('host')
    def valid_host(cls, v):
        import re
        if not re.match(r'^[\w.-]+$', v):
            raise ValueError('Invalid host')
        return v
    @field_validator('port')
    def valid_port(cls, v):
        if not (0 < v < 65536):
            raise ValueError('Port must be between 1 and 65535')
        return v
    @field_validator('model')
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError('Model cannot be empty')
        return v

class EndpointTestModel(BaseModel):
    endpoint: str
    method: str
    payload: str = None
    headers: dict = {}
    @field_validator('endpoint')
    def valid_endpoint(cls, v):
        if not v.startswith('/'):
            raise ValueError('Endpoint must start with /')
        return v
    @field_validator('method')
    def valid_method(cls, v):
        if v.upper() not in ['GET', 'POST']:
            raise ValueError('Method must be GET or POST')
        return v

class ExampleRunModel(BaseModel):
    script: str
    args: str = None
    @field_validator('script')
    def valid_script(cls, v):
        if not v.endswith('.py') or '..' in v or '\x00' in v:
            raise ValueError('Script must be a .py file and safe path')
        return v

class APIUploadModel(BaseModel):
    report_file: str
    api_url: AnyUrl
    headers: dict = {}
    content_type: str
    @field_validator('report_file')
    def valid_report_file(cls, v):
        if not v.endswith('.md'):
            raise ValueError('Report file must be a .md file')
        if '..' in v or '\x00' in v:
            raise ValueError('Invalid report file path')
        return v
    @field_validator('content_type')
    def valid_content_type(cls, v):
        if v not in ["JSON (report as string)", "multipart/form-data (file upload)"]:
            raise ValueError('Invalid content type')
        return v

def collect_log_view_args() -> dict:
    """Collect arguments for log viewing."""
    log_file = questionary.text("Log file path:", default="ollama_server.log").ask()
    lines = questionary.text("Number of lines to show:", default="50").ask()
    filter_text = questionary.text("Filter text (optional):").ask()
    return {
        'log_file': log_file,
        'lines': int(lines) if lines.isdigit() else 50,
        'filter': filter_text if filter_text else None
    }

def collect_server_params(params: dict) -> dict:
    """Collect server parameters interactively."""
    host = questionary.text("Host:", default=params.get('host', 'localhost')).ask()
    port = questionary.text("Port:", default=str(params.get('port', 8000))).ask()
    model = questionary.text("Model:", default=params.get('model', 'codellama:7b')).ask()
    return {
        'host': host,
        'port': int(port) if port.isdigit() else 8000,
        'model': model
    }

def set_parameters(params: dict) -> dict:
    """Set server parameters."""
    return collect_server_params(params)

def collect_endpoint_test_args(base_url: str, endpoint_choices: list) -> dict:
    """Collect arguments for endpoint testing."""
    endpoint = questionary.select(
        "Select endpoint to test:",
        choices=endpoint_choices
    ).ask()
    method = questionary.select(
        "HTTP method:",
        choices=["GET", "POST"]
    ).ask()
    payload = None
    if method == "POST":
        payload = questionary.text("JSON payload (optional):").ask()
    headers = {}
    add_headers = questionary.confirm("Add custom headers?").ask()
    if add_headers:
        while True:
            key = questionary.text("Header key (or 'done' to finish):").ask()
            if key.lower() == 'done':
                break
            value = questionary.text(f"Header value for {key}:").ask()
            headers[key] = value
    return {
        'endpoint': endpoint,
        'method': method,
        'payload': payload,
        'headers': headers
    }

def collect_example_run_args() -> dict:
    """Collect arguments for running example scripts."""
    script = questionary.text("Script to run (e.g., example.py):").ask()
    args = questionary.text("Arguments (optional):").ask()
    return {
        'script': script,
        'args': args if args else None
    }

def run_example() -> None:
    """Run an example script."""
    args = collect_example_run_args()
    if not args['script']:
        console.print("[red]No script specified.[/red]")
        return
    try:
        import subprocess
        cmd = [sys.executable, args['script']]
        if args['args']:
            cmd.extend(args['args'].split())
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            console.print(f"[green]Script executed successfully:[/green]\n{result.stdout}")
        else:
            console.print(f"[red]Script failed:[/red]\n{result.stderr}")
    except Exception as e:
        console.print(f"[red]Error running script: {e}[/red]")

def write_env_vars_for_server():
    """Write environment variables for the server."""
    env_vars = {
        'OLLAMA_HOST': 'http://localhost:11434',
        'OLLAMA_MODEL': 'codellama:7b',
        'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN', ''),
        'LOG_LEVEL': 'INFO',
        'MAX_WORKERS': '8',
        'CACHE_DIR': '.cache',
        'REPORTS_DIR': 'reports'
    }
    
    def set_or_update(key, value):
        if key in os.environ:
            env_vars[key] = os.environ[key]
        else:
            env_vars[key] = value
    
    set_or_update('OLLAMA_HOST', 'http://localhost:11434')
    set_or_update('OLLAMA_MODEL', 'codellama:7b')
    set_or_update('GITHUB_TOKEN', '')
    set_or_update('LOG_LEVEL', 'INFO')
    set_or_update('MAX_WORKERS', '8')
    set_or_update('CACHE_DIR', '.cache')
    set_or_update('REPORTS_DIR', 'reports')
    
    with open('.env', 'w') as f:
        for key, value in env_vars.items():
            f.write(f'{key}={value}\n')
    console.print("[green]Environment variables written to .env[/green]")

def start_server():
    """Start the FastAPI server."""
    try:
        write_env_vars_for_server()
        import subprocess
        import sys
        cmd = [sys.executable, '-m', 'uvicorn', 'fastapi_app:app', '--host', '0.0.0.0', '--port', '8000', '--reload']
        console.print("[green]Starting FastAPI server...[/green]")
        console.print(f"[cyan]Command: {' '.join(cmd)}[/cyan]")
        subprocess.run(cmd)
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/red]")

def show_server_status(params):
    """Show server status."""
    try:
        import requests
        response = requests.get('http://localhost:8000/health', timeout=5)
        if response.status_code == 200:
            console.print("[green]Server is running[/green]")
            console.print(f"[cyan]Health check response: {response.json()}[/cyan]")
        else:
            console.print(f"[yellow]Server responded with status {response.status_code}[/yellow]")
    except requests.exceptions.ConnectionError:
        console.print("[red]Server is not running[/red]")
    except Exception as e:
        console.print(f"[red]Error checking server status: {e}[/red]")

def print_help():
    """Print help information."""
    help_text = """
    Ollama Code Llama CLI - Help
    
    Available commands:
    - audit: Analyze GitHub repositories
    - server: Manage FastAPI server
    - reports: View generated reports
    - config: Manage configuration
    - logs: View application logs
    - help: Show this help
    
    Examples:
    - audit: Analyze a GitHub repository
    - server start: Start the FastAPI server
    - server status: Check server status
    - reports list: List generated reports
    - config show: Show current configuration
    - logs view: View recent logs
    """
    console.print(Panel(help_text, title="Help", style="cyan"))

def safe_github_call(callable_func, *args, retries=2, delay=2, **kwargs):
    """Safely call a GitHub API function with retries and error handling."""
    for attempt in range(retries + 1):
        try:
            return callable_func(*args, **kwargs)
        except Exception as github_error:
            if attempt < retries:
                console.print(f"[yellow]GitHub API error: {github_error}. Retrying ({attempt+1}/{retries})...[/yellow]")
                time.sleep(delay)
            else:
                console.print(f"[red]GitHub API error: {github_error}[/red]")
                return None

def safe_llm_call(llm_func, *args, retries=1, delay=2, **kwargs):
    """Safely call an LLM function with retries and error handling."""
    for attempt in range(retries + 1):
        try:
            return llm_func(*args, **kwargs)
        except Exception as llm_error:
            if attempt < retries:
                console.print(f"[yellow]LLM error: {llm_error}. Retrying ({attempt+1}/{retries})...[/yellow]")
                time.sleep(delay)
            else:
                console.print(f"[red]LLM error: {llm_error}[/red]")
                return None

class CLIAuditArgsModel(BaseModel):
    repo: str
    branch: Optional[str] = None
    pr: Optional[int] = None
    token: str
    output_dir: Optional[str] = None
    scope: str = Field(..., pattern='^(all|changed|readme|test)$')
    filter: Optional[str] = Field(None, pattern='^(pattern|manual|none)?$')
    pattern: Optional[str] = None
    editor: Optional[str] = None
    no_preview: bool = False
    save_readme: bool = False
    max_workers: int = 8
    only_changed: bool = False
    profile: bool = False

    @classmethod
    def validate_args(cls, args_dict):
        try:
            return cls(**args_dict)
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.errors()}[/red]")
            sys.exit(1)

def collect_interactive_args() -> dict:
    """Collect and validate CLI arguments interactively using Marshmallow schema."""
    while True:
        repo = questionary.autocomplete(
            "GitHub repo (e.g. user/repo):",
            choices=repo_cache + ['Exit'],
        ).ask()
        if repo == 'Exit': return None
        branch = questionary.autocomplete(
            "Branch (leave blank for default):",
            choices=branch_cache.get(repo, []) + ['Exit'],
            default=branch_cache.get(repo, [None])[0] if branch_cache.get(repo) else None
        ).ask()
        if branch == 'Exit': return None
        pr_number = questionary.autocomplete(
            "PR number (leave blank if not analyzing a PR):",
            choices=pr_cache.get(repo, []) + ['Exit']
        ).ask()
        if pr_number == 'Exit': return None
        pr_number_int = int(pr_number) if pr_number and pr_number.isdigit() else None
        token = questionary.text("GitHub token:").ask()
        output_dir = questionary.text("Output directory for reports and README? (default: reports)").ask()
        scope = questionary.select(
            "What do you want to audit?",
            choices=["all", "changed", "readme", "test", "Exit"]
        ).ask()
        if scope == 'Exit': return None
        filter_mode = questionary.select(
            "Filter files by:",
            choices=["pattern", "manual", "none", "Exit"]
        ).ask()
        if filter_mode == 'Exit': return None
        pattern = questionary.text("Enter glob pattern (e.g. *.py, src/*.js):").ask() if filter_mode == "pattern" else None
        no_preview = questionary.confirm("Skip preview before saving report?").ask()
        save_readme = questionary.confirm("Save the updated README as a separate file?").ask()
        max_workers = questionary.text("Number of parallel workers for LLM analysis (default: 8):", default="8").ask()
        only_changed = questionary.confirm("Analyze only changed files (using git diff?)").ask()
        profile = questionary.confirm("Profile report generation steps?").ask()
        args_dict = {
            'repo': repo,
            'branch': branch,
            'pr': pr_number_int,
            'token': token,
            'output_dir': output_dir,
            'scope': scope,
            'filter': filter_mode,
            'pattern': pattern,
            'no_preview': no_preview,
            'save_readme': save_readme,
            'max_workers': int(max_workers) if max_workers.isdigit() else 8,
            'only_changed': only_changed,
            'profile': profile
        }
        try:
            validated = CLIAuditArgsModel.validate_args(args_dict)
            return validated.model_dump()
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.errors()}[/red]")
            continue

def run_async(coro):
    import asyncio
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        tb = traceback.format_exc()
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            try:
                import nest_asyncio
                nest_asyncio.apply()
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(coro)
            except Exception as inner_e:
                log_exception("run_async", "event_loop_running", f"Error running async code (event loop running): {inner_e}\nTraceback:\n{tb}")
                print("[red]Async error: Cannot run async code from a running event loop. Returning to menu.[/red]")
                return '__ASYNC_ERROR__'
        elif "There is no current event loop" in str(e):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            except Exception as inner_e:
                log_exception("run_async", "no_event_loop", f"Error running async code (no event loop): {inner_e}\nTraceback:\n{tb}")
                print("[red]Async error: No event loop found. Returning to menu.[/red]")
                return '__ASYNC_ERROR__'
        elif "cannot reuse already awaited coroutine" in str(e):
            log_exception("run_async", "coroutine_reuse", f"Coroutine reuse error: {e}\nTraceback:\n{tb}")
            print("[red]Async error: Cannot reuse already awaited coroutine. Returning to menu.[/red]")
            return '__ASYNC_ERROR__'
        else:
            log_exception("run_async", "other", f"Error running async code: {e}\nTraceback:\n{tb}")
            print(f"[red]Error running async code: {e}[/red]")
            return '__ASYNC_ERROR__'

def generate_github_report(args=None):
    import time as _time
    global repo_cache
    try:
        config = load_config()
        if args:
            args_dict = vars(args)
            validated_args = CLIAuditArgsModel.validate_args(args_dict)
            args = argparse.Namespace(**validated_args.model_dump())
            output_dir = getattr(args, 'output_dir', None)
        else:
            output_dir = questionary.text("Output directory for reports and README? (default: reports)").ask()
        if not output_dir or not output_dir.strip():
            output_dir = 'reports'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        if args:
            token = args.token or os.environ.get('GITHUB_TOKEN') or config.get('github', {}).get('token')
            max_workers = getattr(args, 'max_workers', 8)
            only_changed = getattr(args, 'only_changed', False)
            do_profile = getattr(args, 'profile', False)
        else:
            token = os.environ.get('GITHUB_TOKEN') or config.get('github', {}).get('token')
            if not token or not token.strip():
                token = questionary.text("GitHub token:").ask()
            max_workers = 8
            only_changed = False
            do_profile = False
        if not token or not token.strip():
            console.print("[red]GitHub token is required. Please provide a valid token.[/red]")
            log_error("generate_github_report", "token", "GitHub token missing.", feature="generate_github_report")
            return
        try:
            g = Github(token)
            if not repo_cache:
                spinner("Fetching your repositories...", duration=2)
                repo_cache = [repo.full_name for repo in g.get_user().get_repos()]
            if args:
                repo = args.repo
            else:
                if repo_cache:
                    repo = questionary.select(
                        "Select a GitHub repo:",
                        choices=repo_cache + ['Exit'],
                    ).ask()
                else:
                    repo = questionary.text("GitHub repo (e.g. user/repo):").ask()
                if repo == 'Exit': return None
            spinner("Fetching repository details...", duration=1)
            repo_obj = safe_github_call(g.get_repo, repo)
            if repo_obj is None:
                console.print(f"[red]Failed to fetch repository '{repo}'. Please check the repo name and your GitHub token.[/red]")
                log_error("generate_github_report", "fetch_repo", f"Failed to fetch repo: {repo}", feature="generate_github_report")
                return
            # Prompt user to choose between branch or PR
            audit_target = questionary.select(
                "Would you like to audit a branch or a pull request?",
                choices=["Branch", "Pull Request (PR)", "Exit"]
            ).ask()
            if audit_target == 'Exit': return None
            branch = None
            pr_number = None
            if audit_target == "Pull Request (PR)":
                # Fetch PRs for autocomplete
                if repo not in pr_cache:
                    spinner("Fetching pull requests for this repo...", duration=2)
                    pr_cache[repo] = [str(pr.number) for pr in repo_obj.get_pulls(state="open")]
                pr_choices = pr_cache.get(repo, [])
                if pr_choices:
                    pr_number = questionary.select(
                        "Select a PR number (leave blank if not analyzing a PR):",
                        choices=pr_choices + ['Exit'],
                    ).ask()
                    if pr_number == 'Exit': return None
                else:
                    pr_number = questionary.text("PR number (leave blank if not analyzing a PR):").ask()
                    if pr_number == 'Exit': return None
            else:
                # Fetch branches for autocomplete
                if repo not in branch_cache:
                    spinner("Fetching branches for this repo...", duration=2)
                    branch_cache[repo] = [b.name for b in repo_obj.get_branches()]
                branch_choices = [repo_obj.default_branch] + [b for b in branch_cache[repo] if b != repo_obj.default_branch]
                branch = questionary.select(
                    "Select a branch (leave blank for default):",
                    choices=branch_choices + ['Exit'],
                    default=repo_obj.default_branch,
                ).ask()
                if branch == 'Exit': return None
            pr_number_int = int(pr_number) if pr_number and str(pr_number).isdigit() else None

            # Enhancement 1: Audit Scope Selection
            if args:
                scope = args.scope
            else:
                scope = questionary.select(
                    "What do you want to audit?",
                    choices=[
                        "All code files",
                        "Only changed files (for PR)",
                        "README only",
                        "Test strategy only",
                        "Exit"
                    ]).ask()
            if scope == 'Exit': return None

            spinner("Fetching repository data (async)...", duration=2)
            llm_client = OllamaCodeLlama()
            t0 = _time.time() if do_profile else None
            repo_data = run_async(new_async_fetch_repo_data(repo, branch, pr_number_int, token))
            t1 = _time.time() if do_profile else None
            files = repo_data['files']
            comments = repo_data['comments']
            commits = repo_data['commits']
            readme = repo_data['readme']
            pr_info = repo_data['pr_info']
            extra_info = pr_info if pr_info else None

            # Only analyze changed files if requested
            if only_changed:
                changed_files = get_changed_files()
                files = [f for f in files if f.get('filename') in changed_files]

            file_analyses = []
            test_strategy = ""
            readme_suggestions = ""
            updated_readme = ""

            # Streaming report output path
            report_filename = get_report_filename(repo, branch, pr_number_int)
            report_path = os.path.join(output_dir, report_filename)
            partial_report_path = report_path + ".partial"
            # Write report header and TOC first
            log_info("generate_github_report", "write_report", f"Writing report header to {partial_report_path}", feature="generate_github_report")
            with open(partial_report_path, 'w', encoding='utf-8') as f:
                f.write(f"# GitHub Code Audit & Report\n")
                f.write(f"**Repository:** `{repo}`  \n")
                if branch:
                    f.write(f"**Branch:** `{branch}`  \n")
                if pr_number_int:
                    f.write(f"**Pull Request:** `{pr_number_int}`  \n")
                if extra_info:
                    for k, v in extra_info.items():
                        f.write(f"**{k}:** {v}  \n")
                f.write("\n---\n")
                f.write("## Table of Contents\n")
                f.write("- [File Analyses](#file-analyses)\n")
                f.write("- [Test Strategy](#test-strategy)\n")
                f.write("- [README Suggestions](#readme-suggestions)\n")
                f.write("- [Updated README](#updated-readme)\n\n")
                f.write("---\n\n")
                f.write("## File Analyses\n\n")
            log_info("generate_github_report", "write_report", f"Finished writing report header to {partial_report_path}", feature="generate_github_report")

            def retry_callback(failed_files):
                if not failed_files:
                    return False
                console.print(f"[red]{len(failed_files)} files failed LLM analysis.[/red]")
                if questionary.confirm(f"Retry failed files? ({len(failed_files)} files)").ask():
                    return True
                return False

            # Run only the selected sections
            if scope == "All code files":
                spinner("Analyzing code files with LLM (async, streaming)...", duration=2)
                t2 = _time.time() if do_profile else None
                def analyze_files(rebuild_cache=False):
                    # Always create a fresh coroutine for each analysis
                    return run_async(async_analyze_code_files(
                        files, comments, commits, readme, llm_client, partial_report_path=partial_report_path, retry_callback=retry_callback, rebuild_cache=rebuild_cache))
                file_analyses = analyze_files()
                if file_analyses == '__ASYNC_ERROR__':
                    console.print("[red]Async error occurred. Returning to menu.[/red]")
                    return
                if file_analyses is None:
                    file_analyses = []
                # Always regenerate and rewrite test strategy and readme suggestions (and updated_readme)
                test_strategy_cache_path = os.path.join(CACHE_DIR, f"test_strategy_{hash_content(str([f['filename'] for f in files]))}.json")
                readme_suggestions_cache_path = os.path.join(CACHE_DIR, f"readme_suggestions_{hash_content(readme)}.json")
                spinner("Generating test strategy (async)...", duration=2)
                test_strategy = run_async(async_generate_test_strategy(files, llm_client))
                with open(test_strategy_cache_path, 'w') as f:
                    f.write(test_strategy)
                log_info("generate_github_report", "cache", f"Regenerated and wrote test strategy to cache: {test_strategy_cache_path}", feature="generate_github_report")
                console.print(Panel(f"[green]Test Strategy generated and cached.[/green]", style="bold green"))
                console.print(Panel(f"[bold blue]Test Strategy Preview:[/bold blue]\n{test_strategy[:500]}...", style="cyan"))
                spinner("Reviewing README (async)...", duration=2)
                readme_suggestions, updated_readme = run_async(async_suggest_readme_improvements(readme, llm_client))
                with open(readme_suggestions_cache_path, 'w') as f:
                    f.write(readme_suggestions)
                updated_readme_cache_path = readme_suggestions_cache_path.replace("readme_suggestions_", "updated_readme_")
                with open(updated_readme_cache_path, 'w') as rf:
                    rf.write(updated_readme)
                log_info("generate_github_report", "cache", f"Regenerated and wrote readme_suggestions to cache: {readme_suggestions_cache_path}", feature="generate_github_report")
                log_info("generate_github_report", "cache", f"Regenerated and wrote updated_readme to cache: {updated_readme_cache_path}", feature="generate_github_report")
                console.print(Panel(f"[green]README Suggestions generated and cached.[/green]", style="bold green"))
                console.print(Panel(f"[bold blue]README Suggestions Preview:[/bold blue]\n{readme_suggestions[:500]}...", style="cyan"))
                console.print(Panel(f"[green]Updated README generated and cached.[/green]", style="bold green"))
                console.print(Panel(f"[bold blue]Updated README Preview:[/bold blue]\n{updated_readme[:500]}...", style="cyan"))
                t4 = _time.time() if do_profile else None
            elif scope == "Only changed files (for PR)":
                if not pr_number_int:
                    console.print("[red]No PR selected. Please select a PR for this option.[/red]")
                    return
                changed_files = [f for f in files if f.get('status') in ('added', 'modified', 'changed')]
                spinner("Analyzing changed files with LLM (async, streaming)...", duration=2)
                t2 = _time.time() if do_profile else None
                file_analyses = run_async(async_analyze_code_files(
                    changed_files, comments, commits, readme, llm_client, partial_report_path=partial_report_path, retry_callback=retry_callback))
                if file_analyses == '__ASYNC_ERROR__':
                    console.print("[red]Async error occurred. Returning to menu.[/red]")
                    return
                if file_analyses is None:
                    file_analyses = []
                test_strategy_cache_path = os.path.join(CACHE_DIR, f"test_strategy_{hash_content(str([f['filename'] for f in changed_files]))}.json")
                readme_suggestions_cache_path = os.path.join(CACHE_DIR, f"readme_suggestions_{hash_content(readme)}.json")
                # Always regenerate and rewrite test strategy and readme suggestions (and updated_readme)
                spinner("Generating test strategy (async)...", duration=2)
                test_strategy = run_async(async_generate_test_strategy(changed_files, llm_client))
                with open(test_strategy_cache_path, 'w') as f:
                    f.write(test_strategy)
                spinner("Reviewing README (async)...", duration=2)
                readme_suggestions, updated_readme = run_async(async_suggest_readme_improvements(readme, llm_client))
                with open(readme_suggestions_cache_path, 'w') as f:
                    f.write(readme_suggestions)
                updated_readme_cache_path = readme_suggestions_cache_path.replace("readme_suggestions_", "updated_readme_")
                with open(updated_readme_cache_path, 'w') as rf:
                    rf.write(updated_readme)
                log_info("generate_github_report", "cache", f"Regenerated and wrote test strategy to cache: {test_strategy_cache_path}", feature="generate_github_report")
                log_info("generate_github_report", "cache", f"Regenerated and wrote readme_suggestions to cache: {readme_suggestions_cache_path}", feature="generate_github_report")
                log_info("generate_github_report", "cache", f"Regenerated and wrote updated_readme to cache: {updated_readme_cache_path}", feature="generate_github_report")
                console.print(Panel(f"[green]Test Strategy generated and cached.[/green]", style="bold green"))
                console.print(Panel(f"[bold blue]Test Strategy Preview:[/bold blue]\n{test_strategy[:500]}...", style="cyan"))
                console.print(Panel(f"[green]README Suggestions generated and cached.[/green]", style="bold green"))
                console.print(Panel(f"[bold blue]README Suggestions Preview:[/bold blue]\n{readme_suggestions[:500]}...", style="cyan"))
                console.print(Panel(f"[green]Updated README generated and cached.[/green]", style="bold green"))
                console.print(Panel(f"[bold blue]Updated README Preview:[/bold blue]\n{updated_readme[:500]}...", style="cyan"))
                t4 = _time.time() if do_profile else None
            elif scope == "README only":
                spinner("Reviewing README (async)...", duration=2)
                readme_suggestions, updated_readme = run_async(async_suggest_readme_improvements(readme, llm_client))
            elif scope == "Test strategy only":
                spinner("Generating test strategy (async)...", duration=2)
                test_strategy = run_async(async_generate_test_strategy(files, llm_client))

            # Append remaining report sections
            log_info("generate_github_report", "write_report", f"Appending Test Strategy, README Suggestions, Updated README to {partial_report_path}", feature="generate_github_report")
            with open(partial_report_path, 'a', encoding='utf-8') as f:
                f.write("## Test Strategy\n\n")
                f.write(f"{test_strategy}\n\n---\n\n")
                f.write("## README Suggestions\n\n")
                f.write(f"{readme_suggestions}\n\n---\n\n")
                f.write("## Updated README\n\n")
                f.write(f"```markdown\n{updated_readme}\n```\n\n---\n\n")
            log_info("generate_github_report", "write_report", f"Moving {partial_report_path} to {report_path}", feature="generate_github_report")

            # Move partial report to final report path
            import shutil
            shutil.move(partial_report_path, report_path)
            console.print(Panel(f"[green]GitHub Code Audit & Report generated![green]\nSaved as: [yellow]{report_path}[/yellow]", style="bold green"))

            if do_profile:
                timings = [
                    ("Fetch repo data", t1-t0 if t0 and t1 else None),
                    ("LLM analysis", t4-t2 if t2 and t4 else None),
                    ("Test strategy/README", t4-t2 if t2 and t4 else None),
                ]
                for label, t in timings:
                    if t is not None:
                        console.print(f"[cyan]{label} took {t:.2f} seconds[/cyan]")

            # --- Modularized file filtering ---
            file_names = [f['filename'] for f in files]
            if scope in ("All code files", "Only changed files (for PR)") and file_names:
                if questionary.confirm("Would you like to filter which files to include in the audit?").ask():
                    if args:
                        filter_mode = args.filter
                    else:
                        filter_mode = questionary.select(
                            "Filter files by:",
                            choices=["Pattern (glob/regex)", "Manual selection", "No filter (include all)", "Exit"]
                        ).ask()
                    if filter_mode == 'Exit': return None
                    if filter_mode == "Pattern (glob/regex)":
                        if args:
                            pattern = args.pattern
                        else:
                            pattern = questionary.text("Enter glob pattern (e.g. *.py, src/*.js):").ask()
                        files = filter_files(files, 'pattern', pattern=pattern)
                    elif filter_mode == "Manual selection":
                        if args:
                            selected_files = args.pattern.split(',')
                        else:
                            selected_files = questionary.checkbox(
                                "Select files to include:",
                                choices=file_names
                            ).ask()
                        files = filter_files(files, 'manual', manual_selection=selected_files)
                    else:
                        files = filter_files(files, 'none')

            # --- Modularized diff display ---
            if pr_number_int:
                for file_info in files:
                    filename = file_info['filename']
                    if file_info.get('status') in ('added', 'modified', 'changed'):
                        try:
                            old_content = repo_obj.get_contents(filename, ref=pr_info['base_branch']).decoded_content.decode('utf-8')
                        except Exception:
                            old_content = ''
                        new_content = file_info.get('content', '')
                        display_diff(old_content, new_content, filename)

            # --- Modularized report preview ---
            if args:
                if args.no_preview:
                    preview_report(report_path)
                else:
                    if questionary.confirm("Open full report in your editor before saving?").ask():
                        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md") as tf:
                            tf.write(report_path)
                            tf.flush()
                            os.system(f"${{EDITOR:-nano}} {tf.name}")
            else:
                if questionary.confirm("Open full report in your editor before saving?").ask():
                    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md") as tf:
                        tf.write(report_path)
                        tf.flush()
                        os.system(f"${{EDITOR:-nano}} {tf.name}")

            # Enhancement 3: Option to Save Only the Updated README
            if updated_readme and updated_readme.strip():
                if args:
                    if args.save_readme:
                        readme_filename = get_readme_filename(repo, branch)
                        readme_path = os.path.join(output_dir, readme_filename)
                        with open(readme_path, "w", encoding="utf-8") as rf:
                            rf.write(updated_readme)
                        console.print(f"[green]Updated README saved as:[/green] [yellow]{readme_path}[/yellow]")
                else:
                    if questionary.confirm("Save the updated README as a separate file?").ask():
                        readme_filename = get_readme_filename(repo, branch)
                        readme_path = os.path.join(output_dir, readme_filename)
                        with open(readme_path, "w", encoding="utf-8") as rf:
                            rf.write(updated_readme)
                        console.print(f"[green]Updated README saved as:[/green] [yellow]{readme_path}[/yellow]")

            # Optionally show a summary in the CLI
            if file_analyses:
                for file_analysis in file_analyses[:2]:
                    panels = []
                    panels.append(Panel(file_analysis.get('summary', ''), title=f"[yellow]{file_analysis['filename']}[/yellow] - Summary", style="cyan"))
                    if file_analysis.get('bugs_issues'):
                        panels.append(Panel(file_analysis['bugs_issues'], title="Bugs/Issues", style="red"))
                    if file_analysis.get('suggestions'):
                        panels.append(Panel(file_analysis['suggestions'], title="Suggestions", style="green"))
                    if file_analysis.get('code_example'):
                        panels.append(Panel(file_analysis['code_example'], title="Code Example", style="magenta"))
                    if file_analysis.get('code_smells'):
                        panels.append(Panel(file_analysis['code_smells'], title="Code Smells/Anti-patterns", style="yellow"))
                    if file_analysis.get('security_performance'):
                        panels.append(Panel(file_analysis['security_performance'], title="Security/Performance", style="blue"))
                    if file_analysis.get('test_coverage'):
                        panels.append(Panel(file_analysis['test_coverage'], title="Test Coverage/Quality", style="cyan"))
                    for p in panels:
                        console.print(p)
            if test_strategy:
                console.print(Panel(f"[bold blue]Test Strategy:[/bold blue]\n{test_strategy[:500]}...", style="cyan"))
            if readme_suggestions:
                console.print(Panel(f"[bold blue]README Suggestions:[/bold blue]\n{readme_suggestions[:500]}...", style="cyan"))

            # Enhancement 4: Re-run Only a Section
            while True:
                rerun_choice = questionary.select(
                    "Would you like to re-run a section?",
                    choices=[
                        "No, return to main menu",
                        "Re-run README analysis",
                        "Re-run test strategy",
                        "Rebuild analysis cache",
                        "Exit"
                    ]).ask()
                if rerun_choice == "Exit": return None
                elif rerun_choice == "No, return to main menu":
                    break
                elif rerun_choice == "Re-run README analysis":
                    spinner("Reviewing README...", duration=2)
                    readme_suggestions, updated_readme = run_async(async_suggest_readme_improvements(readme, llm_client))
                    # Write to cache after re-running
                    with open(readme_suggestions_cache_path, 'w') as f:
                        f.write(readme_suggestions)
                    updated_readme_cache_path = readme_suggestions_cache_path.replace("readme_suggestions_", "updated_readme_")
                    with open(updated_readme_cache_path, 'w') as rf:
                        rf.write(updated_readme)
                    log_info("generate_github_report", "rerun", f"Re-ran README analysis and updated cache: {readme_suggestions_cache_path}, {updated_readme_cache_path}", feature="generate_github_report")
                    console.print(Panel(f"[green]README analysis re-run complete. Suggestions and updated README have been refreshed and cached.[/green]", style="bold green"))
                    console.print(Panel(f"[bold blue]README Suggestions (updated):[/bold blue]\n{readme_suggestions[:500]}...", style="cyan"))
                    if updated_readme and updated_readme.strip():
                        if args:
                            if args.save_readme:
                                readme_filename = get_readme_filename(repo, branch)
                                readme_path = os.path.join(output_dir, readme_filename)
                                with open(readme_path, "w", encoding="utf-8") as rf:
                                    rf.write(updated_readme)
                                console.print(f"[green]Updated README saved as:[/green] [yellow]{readme_path}[/yellow]")
                        else:
                            if questionary.confirm("Save the updated README as a separate file?").ask():
                                readme_filename = get_readme_filename(repo, branch)
                                readme_path = os.path.join(output_dir, readme_filename)
                                with open(readme_path, "w", encoding="utf-8") as rf:
                                    rf.write(updated_readme)
                                console.print(f"[green]Updated README saved as:[/green] [yellow]{readme_path}[/yellow]")
                elif rerun_choice == "Re-run test strategy":
                    spinner("Generating test strategy...", duration=2)
                    test_strategy = run_async(async_generate_test_strategy(files, llm_client))
                    # Write to cache after re-running
                    with open(test_strategy_cache_path, 'w') as f:
                        f.write(test_strategy)
                    log_info("generate_github_report", "rerun", f"Re-ran test strategy and updated cache: {test_strategy_cache_path}", feature="generate_github_report")
                    console.print(Panel(f"[green]Test strategy re-run complete. Test strategy has been refreshed and cached.[/green]", style="bold green"))
                    console.print(Panel(f"[bold blue]Test Strategy (updated):[/bold blue]\n{test_strategy[:500]}...", style="cyan"))
                elif rerun_choice == "Rebuild analysis cache":
                    spinner("Rebuilding analysis cache and re-analyzing files...", duration=2)
                    file_analyses = analyze_files(rebuild_cache=True)
                    if file_analyses == '__ASYNC_ERROR__':
                        console.print("[red]Async error occurred. Returning to menu.[/red]")
                        return
                    if file_analyses is None:
                        file_analyses = []
        except Exception as e:
            log_exception("generate_github_report", "github_api", f"Error: {e}", feature="generate_github_report")
            console.print(f"[red]GitHub API error: {e}[/red]")
            return
    except AssertionError:
        log_error("generate_github_report", "token", "GitHub token cannot be empty.", feature="generate_github_report")
        console.print("[red]GitHub token cannot be empty. Please provide a valid token.[/red]")
    except Exception as e:
        log_exception("generate_github_report", "main", f"Error: {e}", feature="generate_github_report")
        console.print_exception()

def run_automated_test():
    console.print(Panel("[cyan]Running automated test on public repo: psf/requests[/cyan]", style="bold blue"))
    test_repo = "psf/requests"
    test_branch = "master"
    test_token = os.environ.get("GITHUB_TOKEN", "")
    if not test_token:
        console.print("[yellow]No GITHUB_TOKEN in environment. Test may be rate-limited or fail on private repos.[/yellow]")
    llm_client = OllamaCodeLlama()
    try:
        repo_data = new_fetch_repo_data(test_repo, test_branch, None, test_token)
        files = repo_data['files'][:2]  # Only 2 files for speed
        comments = repo_data['comments']
        commits = repo_data['commits']
        readme = repo_data['readme']
        file_analyses = safe_llm_call(analyze_files_parallel, files, comments, commits, readme, llm_client, test_repo, test_branch, None)
        test_strategy = generate_test_strategy(files, llm_client)
        readme_suggestions, updated_readme = suggest_readme_improvements(readme, llm_client)
        report_md = generate_markdown_report(
            repo_full_name=test_repo,
            branch=test_branch,
            pr_number=None,
            file_analyses=file_analyses,
            test_strategy=test_strategy,
            readme_suggestions=readme_suggestions,
            updated_readme=updated_readme,
            extra_info=None
        )
        # Check for key sections
        passed = True
        for section in ["File Analyses", "Test Strategy", "README Suggestions", "Updated README"]:
            if section not in report_md:
                console.print(f"[red]Missing section: {section}[/red]")
                passed = False
        if passed:
            console.print(Panel("[green]Automated test PASSED! All key sections found in the report.[/green]", style="bold green"))
        else:
            console.print(Panel("[red]Automated test FAILED. Some sections missing.[/red]", style="bold red"))
    except Exception as e:
        console.print(f"[red]Automated test failed: {e}[/red]")

def collect_api_upload_args(output_dir: str) -> dict:
    """Collect and validate API upload arguments interactively using Marshmallow schema."""
    files = [f for f in os.listdir(output_dir) if f.endswith('.md')]
    if not files:
        console.print(f"[red]No .md report files found in {output_dir}.[/red]")
        return None
    while True:
        report_file = questionary.select("Select report to upload:", choices=files + ['Exit']).ask()
        if report_file == 'Exit': return None
        api_url = questionary.text("API endpoint URL:").ask()
        headers = {}
        if questionary.confirm("Add custom headers (e.g., API key)?").ask():
            while True:
                key = questionary.text("Header key (leave blank to finish):").ask()
                if not key.strip():
                    break
                value = questionary.text(f"Value for {key}:").ask()
                headers[key] = value
        content_type = questionary.select(
            "Send as:",
            choices=["JSON (report as string)", "multipart/form-data (file upload)", "Exit"]
        ).ask()
        if content_type == 'Exit': return None
        args_dict = {
            'report_file': report_file,
            'api_url': api_url,
            'headers': headers,
            'content_type': content_type
        }
        try:
            validated = APIUploadModel(**args_dict)
            return validated.model_dump()
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.errors()}[/red]")
            continue

def upload_report_to_api():
    console.print(Panel("[cyan]Upload a report to a remote API endpoint[/cyan]", style="bold blue"))
    output_dir = questionary.text("Directory containing report? (default: reports)").ask()
    if not output_dir or not output_dir.strip():
        output_dir = 'reports'
    args = collect_api_upload_args(output_dir)
    if not args:
        return
    report_path = os.path.join(output_dir, args['report_file'])
    with open(report_path, 'r', encoding='utf-8') as f:
        report_content = f.read()
    try:
        spinner("Uploading report to API...", duration=2)
        if args['content_type'].startswith("JSON"):
            data = {"report": report_content, "filename": args['report_file']}
            resp = requests.post(args['api_url'], json=data, headers=args['headers'], timeout=30)
        else:
            files = {"file": (args['report_file'], report_content)}
            resp = requests.post(args['api_url'], files=files, headers=args['headers'], timeout=30)
        console.print(Panel(f"[green]API response:[/green]\n{resp.status_code} {resp.text}", style="bold green"))
    except Exception as e:
        console.print(f"[red]Failed to upload report: {e}[/red]")

def test_github_connect():
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        console.print(Panel('[red]GITHUB_TOKEN not set in environment.[/red]', style='red'))
        return False
    try:
        g = Github(token)
        user = g.get_user()
        console.print(Panel(f'[green]GitHub connection successful![/green]\nAuthenticated as: [bold]{user.login}[/bold]', style='green'))
        return True
    except Exception as e:
        console.print(Panel(f'[red]GitHub connection failed: {e}[/red]', style='red'))
        return False

def parse_cli_args() -> argparse.Namespace:
    """Parse command-line arguments for batch/non-interactive mode."""
    parser = argparse.ArgumentParser(description="Ollama Code Llama GitHub Audit CLI")
    parser.add_argument('--repo', type=str, help='GitHub repo (user/repo)')
    parser.add_argument('--branch', type=str, help='Branch name')
    parser.add_argument('--pr', type=int, help='PR number')
    parser.add_argument('--token', type=str, help='GitHub token')
    parser.add_argument('--output-dir', type=str, default='reports', help='Output directory')
    parser.add_argument('--scope', type=str, choices=[
        'all', 'changed', 'readme', 'test'
    ], help='Audit scope: all, changed, readme, test')
    parser.add_argument('--filter', type=str, choices=['pattern', 'manual', 'none'], help='File filter mode')
    parser.add_argument('--pattern', type=str, help='Glob pattern for file filtering')
    parser.add_argument('--editor', type=str, help='Editor for preview (default: $EDITOR or nano)')
    parser.add_argument('--no-preview', action='store_true', help='Skip preview before saving report')
    parser.add_argument('--save-readme', action='store_true', help='Save updated README as a separate file')
    parser.add_argument('--max-workers', type=int, default=8, help='Number of parallel workers for LLM analysis')
    parser.add_argument('--only-changed', action='store_true', help='Analyze only changed files (using git diff)')
    parser.add_argument('--profile', action='store_true', help='Profile report generation steps')
    return parser.parse_args()

def main_menu(params):
    """
    Display the main menu and route user to the selected section.
    Args:
        params (dict): Dictionary of server/config parameters.
    """
    while True:
        print_banner()
        choice = questionary.select(
            "Main Menu:",
            choices=[
                "🖥️  Server",
                "📄  Reports & Audits",
                "⚙️  Configuration",
                "📝  Logs & Help",
                "🚪  Exit"
            ]).ask()
        if choice.startswith("🖥️"):
            server_menu(params)
        elif choice.startswith("📄"):
            reports_menu(params)
        elif choice.startswith("⚙️"):
            config_menu()
        elif choice.startswith("📝"):
            logs_help_menu()
        elif choice.startswith("🚪"):
            console.print("[green]Goodbye![green]")
            break

def server_menu(params):
    """
    Display the server management menu and handle user actions.
    Args:
        params (dict): Dictionary of server/config parameters.
    """
    while True:
        console.print(Panel("[bold cyan]Server Menu[/bold cyan]", style="cyan"))
        choice = questionary.select(
            "Server Menu:",
            choices=[
                "🔎 Show server status",
                "🚀 Start server",
                "🛑 Stop server",
                "⚙️ Set run parameters",
                "🔙 Back"
            ]).ask()
        if choice.startswith("🔎"):
            show_server_status(params)
            input("Press Enter to return...")
        elif choice.startswith("🚀"):
            start_server()
        elif choice.startswith("🛑"):
            stop_server()
            input("Press Enter to return...")
        elif choice.startswith("⚙️"):
            params = set_parameters(params)
        elif choice.startswith("🔙"):
            break

def reports_menu(params):
    """
    Display the reports and audits menu and handle user actions.
    Args:
        params (dict): Dictionary of server/config parameters.
    """
    while True:
        console.print(Panel("[bold magenta]Reports & Audits[/bold magenta]", style="magenta"))
        choice = questionary.select(
            "Reports & Audits:",
            choices=[
                "📝 Generate GitHub Report",
                "🤖 Run automated test",
                "☁️ Upload report to API",
                "🔗 Test GitHub Connection",
                "🔙 Back"
            ]).ask()
        if choice.startswith("📝"):
            generate_github_report()
            input("Press Enter to return...")
        elif choice.startswith("🤖"):
            run_automated_test()
            input("Press Enter to return...")
        elif choice.startswith("☁️"):
            upload_report_to_api()
            input("Press Enter to return...")
        elif choice.startswith("🔗"):
            test_github_connect()
            input("Press Enter to return...")
        elif choice.startswith("🔙"):
            break

def config_menu():
    """
    Display the configuration menu and handle user actions.
    """
    while True:
        console.print(Panel("[bold yellow]Configuration[/bold yellow]", style="yellow"))
        choice = questionary.select(
            "Configuration:",
            choices=[
                "📄 View config.yaml",
                "✏️ Edit config.yaml",
                "🔙 Back"
            ]).ask()
        if choice.startswith("📄"):
            print_config()
            input("Press Enter to return...")
        elif choice.startswith("✏️"):
            print_config()  # Edit is handled in print_config
            input("Press Enter to return...")
        elif choice.startswith("🔙"):
            break

def logs_help_menu():
    """
    Display the logs and help menu and handle user actions.
    """
    while True:
        console.print(Panel("[bold blue]Logs & Help[/bold blue]", style="blue"))
        choice = questionary.select(
            "Logs & Help:",
            choices=[
                "📜 View recent logs",
                "❓ Help",
                "🔙 Back"
            ]).ask()
        if choice.startswith("📜"):
            print_logs()
            input("Press Enter to return...")
        elif choice.startswith("❓"):
            print_help()
            input("Press Enter to return...")
        elif choice.startswith("🔙"):
            break

def stop_server():
    global server_process
    import requests
    config = load_config()
    port = config.get('server', {}).get('port', 5000)
    base_url = f"http://localhost:{port}"
    # Check if server is running before attempting to stop
    is_running = False
    try:
        r = requests.get(f"{base_url}/health", timeout=2)
        if r.status_code == 200:
            is_running = True
    except Exception:
        pass
    if not is_running:
        console.print("[yellow]No server process is currently running at {base_url}.[/yellow]")
        server_process = None
        return
    # Attempt to stop the server process
    if server_process and server_process.poll() is None:
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
            # Check if server is stopped
            try:
                r = requests.get(f"{base_url}/health", timeout=2)
                if r.status_code != 200:
                    console.print("[green]Server stopped successfully.[/green]")
                else:
                    console.print("[red]Server process terminated, but /health endpoint still responds. Manual check recommended.[/red]")
            except Exception:
                console.print("[green]Server stopped successfully.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to stop server: {e}[/red]")
    else:
        # Try to check if something else is running on the port
        try:
            r = requests.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200:
                console.print(f"[yellow]Server is running at {base_url}, but not managed by this CLI process. Please stop it manually.[/yellow]")
            else:
                console.print("[yellow]No server process is currently running.[/yellow]")
        except Exception:
            console.print("[yellow]No server process is currently running.[/yellow]")
    server_process = None

def main():
    """
    Main entrypoint for the CLI application.
    Parses arguments, loads config, and launches the main menu.
    """
    args = parse_cli_args()
    required_args = ['repo', 'token', 'scope']
    if all(getattr(args, arg, None) for arg in required_args):
        generate_github_report(args=args)
        return
    config = load_config()
    params = {
        'host': config.get('ollama', {}).get('host', 'http://localhost:11434'),
        'model': config.get('ollama', {}).get('model', 'codellama:7b'),
        'port': config.get('server', {}).get('port', 5000),
    }
    # Debug print for GITHUB_TOKEN source
    github_token_env = os.environ.get('GITHUB_TOKEN')
    github_token_config = config.get('github', {}).get('token')
    if github_token_env:
        print(f"[DEBUG] GITHUB_TOKEN loaded from environment or .env: {github_token_env[:8]}... (hidden)")
    elif github_token_config:
        print(f"[DEBUG] GITHUB_TOKEN loaded from config.yaml: {github_token_config[:8]}... (hidden)")
    else:
        print("[DEBUG] GITHUB_TOKEN not set in environment, .env, or config.yaml")
    main_menu(params)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[green]Exiting gracefully. Goodbye![green]")
        sys.exit(0) 