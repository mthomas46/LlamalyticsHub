import argparse
import requests
import yaml
import logging
import sys
import os
import time
from ollama_code_llama import OllamaCodeLlama
import subprocess
from github import Github
import datetime
import re
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
import tempfile
import hashlib
import json
import fnmatch
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
import difflib
from marshmallow import Schema, fields, ValidationError, validates, validates_schema
from loguru import logger
import signal
from dotenv import load_dotenv
import asyncio

# Rich and Questionary for beautiful CLI
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    import questionary
except ImportError:
    print("Installing required packages: rich, questionary...")
    os.system('pip install rich questionary')
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    import questionary

console = Console()

# Set up Loguru logging
# Remove all previous handlers to avoid logging to stdout/stderr
logger.remove()
logger.add(os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log'), rotation="10 MB", retention="10 days", compression="zip", enqueue=True, backtrace=True, diagnose=True)

# Load config
def load_config() -> dict:
    """Load config.yaml if present."""
    CONFIG_PATH = 'config.yaml'
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}

def print_banner() -> None:
    """Print the CLI banner using rich."""
    banner = Text("Ollama Code Llama CLI", style="bold magenta")
    console.print(Panel(banner, expand=False, border_style="cyan"))

def print_config():
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
    if questionary.confirm("Edit config?").ask():
        args = collect_config_edit_args(config)
        section, key, value = args['section'], args['key'], args['value']
        if section in config and isinstance(config[section], dict):
            config[section][key] = value
        else:
            config[section] = {key: value}
        with open('config.yaml', 'w') as f:
            import yaml
            yaml.safe_dump(config, f)
        console.print("[green]Config updated.[/green]")

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

class ConfigEditSchema(Schema):
    section = fields.Str(required=True)
    key = fields.Str(required=True)
    value = fields.Str(required=True)

    @validates('section')
    def validate_section(self, value):
        if not value.strip():
            raise ValidationError('Section cannot be empty')
    @validates('key')
    def validate_key(self, value):
        if not value.strip():
            raise ValidationError('Key cannot be empty')

class LogViewSchema(Schema):
    log_file = fields.Str(required=True)
    lines = fields.Int(required=False, allow_none=True)
    filter = fields.Str(required=False, allow_none=True)

    @validates('log_file')
    def validate_log_file(self, value):
        if '..' in value or '\x00' in value:
            raise ValidationError('Invalid log file path')

def collect_config_edit_args(config: dict) -> dict:
    """Collect and validate config edit arguments interactively using Marshmallow schema."""
    sections = list(config.keys())
    while True:
        section = questionary.select("Select section:", choices=sections).ask()
        keys = list(config[section].keys()) if isinstance(config[section], dict) else []
        key = questionary.text("Key to edit:").ask() if not keys else questionary.select("Select key:", choices=keys).ask()
        value = questionary.text("New value:").ask()
        args_dict = {'section': section, 'key': key, 'value': value}
        try:
            validated = ConfigEditSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            continue

def collect_log_view_args() -> dict:
    """Collect and validate log view arguments interactively using Marshmallow schema."""
    log_file = os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log')
    while True:
        file_input = questionary.text(f"Log file to view (default: {log_file}):", default=log_file).ask()
        lines = questionary.text("Number of lines to show (default: 50):", default="50").ask()
        filter_str = questionary.text("Filter string (leave blank for none):").ask()
        args_dict = {
            'log_file': file_input,
            'lines': int(lines) if lines.isdigit() else 50,
            'filter': filter_str
        }
        try:
            validated = LogViewSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            continue

class ServerParamsSchema(Schema):
    host = fields.Str(required=True)
    port = fields.Int(required=True)
    model = fields.Str(required=True)

    @validates('host')
    def validate_host(self, value):
        if not re.match(r'^[\w.-]+$', value):
            raise ValidationError('Invalid host')
    @validates('port')
    def validate_port(self, value):
        if not (0 < value < 65536):
            raise ValidationError('Port must be between 1 and 65535')
    @validates('model')
    def validate_model(self, value):
        if not value.strip():
            raise ValidationError('Model cannot be empty')

def collect_server_params(params: dict) -> dict:
    """Collect and validate server parameters interactively using Marshmallow schema."""
    while True:
        host = questionary.text(f"host [{params['host']}]:", default=str(params['host'])).ask()
        port = questionary.text(f"port [{params['port']}]:", default=str(params['port'])).ask()
        model = questionary.text(f"model [{params['model']}]:", default=str(params['model'])).ask()
        args_dict = {
            'host': host,
            'port': int(port) if port.isdigit() else 0,
            'model': model
        }
        try:
            validated = ServerParamsSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            continue

def set_parameters(params: dict) -> dict:
    """Set and validate run parameters using a modular, schema-based workflow."""
    validated = collect_server_params(params)
    console.print("[green]Parameters updated.[/green]")
    return validated

def spinner(msg, duration=2):
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        task = progress.add_task(msg, total=None)
        time.sleep(duration)
        progress.remove_task(task)

class EndpointTestSchema(Schema):
    endpoint = fields.Str(required=True)
    method = fields.Str(required=True, validate=lambda m: m.upper() in ['GET', 'POST'])
    payload = fields.Str(required=False, allow_none=True)
    headers = fields.Dict(keys=fields.Str(), values=fields.Str(), required=False)

    @validates('endpoint')
    def validate_endpoint(self, value):
        if not value.startswith('/'):
            raise ValidationError('Endpoint must start with /')
    @validates('method')
    def validate_method(self, value):
        if value.upper() not in ['GET', 'POST']:
            raise ValidationError('Method must be GET or POST')

def collect_endpoint_test_args(base_url: str, endpoint_choices: list) -> dict:
    """Collect and validate endpoint test arguments interactively using Marshmallow schema."""
    while True:
        endpoint = questionary.select(
            "Select an endpoint to test:",
            choices=endpoint_choices
        ).ask()
        method = questionary.select(
            "HTTP method:",
            choices=["GET", "POST"]
        ).ask()
        payload = questionary.text("Payload (JSON string, leave blank for none):").ask() if method == "POST" else None
        headers = {}
        if questionary.confirm("Add custom headers?").ask():
            while True:
                key = questionary.text("Header key (leave blank to finish):").ask()
                if not key.strip():
                    break
                value = questionary.text(f"Value for {key}:").ask()
                headers[key] = value
        args_dict = {
            'endpoint': endpoint,
            'method': method,
            'payload': payload,
            'headers': headers
        }
        try:
            validated = EndpointTestSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            continue

def test_endpoints(params: dict) -> None:
    """Test API endpoints using a modular, schema-based workflow."""
    console.print(Panel("Test Endpoints", style="bold blue"))
    base_url = f"http://localhost:{params['port']}"
    endpoint_choices = [
        "/health",
        "/generate/text",
        "/generate/file",
        "/generate/github-pr",
        "Back to main menu"
    ]
    while True:
        args = collect_endpoint_test_args(base_url, endpoint_choices)
        if args['endpoint'] == "Back to main menu":
            break
        try:
            url = f"{base_url}{args['endpoint']}"
            if args['method'] == "GET":
                r = requests.get(url, headers=args['headers'], timeout=10)
            else:
                payload = args['payload']
                json_payload = None
                if payload:
                    json_payload = json.loads(payload)
                r = requests.post(url, json=json_payload, headers=args['headers'], timeout=30)
            console.print(f"[green]{r.status_code}[/green] [yellow]{r.json()}[/yellow]")
        except Exception as e:
            logger.exception(f"Error testing endpoint {args['endpoint']}")
            console.print_exception()

class ExampleRunSchema(Schema):
    script = fields.Str(required=True)
    args = fields.Str(required=False, allow_none=True)

    @validates('script')
    def validate_script(self, value):
        if not value.endswith('.py') or '..' in value or '\x00' in value:
            raise ValidationError('Script must be a .py file and safe path')


def collect_example_run_args() -> dict:
    """Collect and validate example script run arguments using Marshmallow schema."""
    while True:
        script = questionary.text("Script to run (default: example.py):", default="example.py").ask()
        args = questionary.text("Arguments to pass (leave blank for none):").ask()
        args_dict = {'script': script, 'args': args}
        try:
            validated = ExampleRunSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            continue

def run_example() -> None:
    """Run an example script using modular, schema-based workflow."""
    print_banner()
    example_args = collect_example_run_args()
    script = example_args['script']
    script_args = example_args['args']
    spinner(f"Running {script}...")
    try:
        cmd = [sys.executable, script]
        if script_args:
            cmd += script_args.split()
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            logger.info(f"Output from {script}:\n{result.stdout}")
        if result.stderr:
            logger.error(f"Error from {script}:\n{result.stderr}")
        if not result.stdout and not result.stderr:
            logger.warning(f"No output from {script}")
    except Exception as e:
        logger.exception(f"Error running {script}")
        console.print_exception()

server_process = None

def write_env_vars_for_server():
    config = load_config()
    github_token = os.environ.get('GITHUB_TOKEN') or config.get('github', {}).get('token', '')
    api_key = os.environ.get('OLLAMA_API_KEY') or config.get('api', {}).get('key', '')
    log_file = os.environ.get('OLLAMA_LOG_FILE') or config.get('logging', {}).get('log_file', 'ollama_server.log')
    with open('.env', 'a+') as f:
        f.seek(0)
        lines = f.readlines()
        env_dict = {line.split('=')[0]: line.split('=')[1].strip() for line in lines if '=' in line}
        def set_or_update(key, value):
            if key in env_dict:
                for i, line in enumerate(lines):
                    if line.startswith(f'{key}='):
                        lines[i] = f'{key}={value}\n'
                        break
            else:
                lines.append(f'{key}={value}\n')
        set_or_update('GITHUB_TOKEN', github_token)
        set_or_update('OLLAMA_API_KEY', api_key)
        set_or_update('OLLAMA_LOG_FILE', log_file)
        f.seek(0)
        f.truncate()
        f.writelines(lines)

def start_server():
    global server_process
    print_banner()
    write_env_vars_for_server()
    # Check if server is already running
    import requests
    config = load_config()
    port = config.get('server', {}).get('port', 5000)
    base_url = f"http://localhost:{port}"
    try:
        r = requests.get(f"{base_url}/health", timeout=2)
        if r.status_code == 200:
            console.print(f"[green]Server is already running at {base_url}[/green]")
            return
    except Exception:
        pass  # Not running, proceed to start
    mode = questionary.select(
        "Choose server mode:",
        choices=[
            "Production (Gunicorn)",
            "Development (Flask app.run)"
        ]).ask()
    try:
        if mode == "Production (Gunicorn)":
            console.print("[cyan]Starting server with Gunicorn in the background...[/cyan]")
            server_process = subprocess.Popen([
                "gunicorn", "-w", "2", "--threads", "4", "-b", "0.0.0.0:5000", "http_api:app"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            console.print("[cyan]Starting development server with Flask (app.run) in the background...[/cyan]")
            server_process = subprocess.Popen([sys.executable, "http_api.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print("[green]Server started in the background. You can continue using the CLI.[/green]")
    except FileNotFoundError:
        console.print("[red]Gunicorn is not installed. Please run: pip install gunicorn[/red]")
    except KeyboardInterrupt:
        console.print("\n[green]Server stopped. Returning to main menu.[/green]")

def show_server_status(params):
    import time
    base_url = f"http://localhost:{params['port']}"
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200:
                console.print(f"[green]Server is running at {base_url}[/green]")
                return
        except Exception as e:
            if attempt == 1:
                console.print(f"[yellow]Waiting for server to start...[/yellow]")
            time.sleep(1)
    console.print(f"[red]Server is NOT running at {base_url} after {max_retries} attempts.[/red]")

def print_help():
    console.print(Panel("""
[bold cyan]Ollama Code Llama CLI Help[/bold cyan]

- [bold]Start server[/bold]: Launches the API server using Gunicorn with recommended settings.
- [bold]Set run parameters[/bold]: Change host, model, or port for your session.
- [bold]Test endpoints[/bold]: Interactively test all API endpoints.
- [bold]Run example.py[/bold]: Run the included example script.
- [bold]View config.yaml[/bold]: Show the current configuration file.
- [bold]View recent logs[/bold]: Show recent logs from this session.
- [bold]Help[/bold]: Show this help message.
- [bold]Exit[/bold]: Quit the CLI.

[bold]Shortcuts:[/bold]
- You can also run the server with [green]./run_server.sh[/green] or [green]make run-server[/green] if you prefer.
""", style="bold blue"))

repo_cache = []
branch_cache = {}
pr_cache = {}

CACHE_DIR = '.cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def safe_name(name: str) -> str:
    """Return a filesystem-safe version of a name (e.g., repo, branch)."""
    return name.replace('/', '_').replace(' ', '_')

def get_report_filename(repo: str, branch: str, pr_number: int = None) -> str:
    """Generate a safe filename for a report."""
    safe_repo = safe_name(repo)
    safe_branch = safe_name(branch) if branch else 'default'
    fname = f"github_audit_{safe_repo}_{safe_branch}"
    if pr_number:
        fname += f"_pr{pr_number}"
    return fname + ".md"

def get_readme_filename(repo: str, branch: str) -> str:
    """Generate a safe filename for an updated README."""
    return f"updated_readme_{safe_name(repo)}_{safe_name(branch)}.md"

def hash_content(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def get_cache_path(repo, branch, pr_number, filename_hash):
    """
    Returns a filesystem path for caching LLM analysis results.
    """
    safe_repo = repo.replace('/', '_')
    safe_branch = (branch or 'default').replace('/', '_')
    pr_part = f'_pr{pr_number}' if pr_number else ''
    cache_dir = os.path.join('.cache', f'{safe_repo}_{safe_branch}{pr_part}')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'{filename_hash}.json')

def analyze_files_parallel(files, comments, commits, readme, llama, repo, branch, pr_number, max_workers=8):
    results = []
    uncached = []
    cache_map = {}
    # Check cache for each file
    for f in files:
        content = f.get('content', '')
        if not content:
            continue
        file_hash = hash_content(content)
        cache_path = get_cache_path(repo, branch, pr_number, file_hash)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as cf:
                    cached_result = json.load(cf)
                    results.append(cached_result)
                    cache_map[f['filename']] = True
            except Exception:
                uncached.append(f)
        else:
            uncached.append(f)
    # Analyze uncached files in parallel
    if uncached:
        from rich.progress import Progress
        with Progress() as progress:
            task = progress.add_task("Analyzing files with LLM...", total=len(uncached))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(analyze_code_files, [f], comments, commits, readme, llama): f for f in uncached
                }
                for future in as_completed(futures):
                    file_result = future.result()
                    if file_result:
                        results.extend(file_result)
                        # Save to cache
                        f = futures[future]
                        content = f.get('content', '')
                        file_hash = hash_content(content)
                        cache_path = get_cache_path(repo, branch, pr_number, file_hash)
                        try:
                            with open(cache_path, 'w', encoding='utf-8') as cf:
                                json.dump(file_result[0], cf)
                        except Exception:
                            pass
                    progress.update(task, advance=1)
    return results

def show_colored_diff(old_content: str, new_content: str, filename: str) -> None:
    """Display a colorized diff for a file using rich and difflib."""
    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(),
        new_content.splitlines(),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=''  # No extra newlines
    ))
    if not diff_lines:
        return
    diff_text = '\n'.join(diff_lines)
    syntax = Syntax(diff_text, "diff", theme="ansi_dark", line_numbers=False)
    console.print(Panel(syntax, title=f"[bold magenta]Diff for {filename}", style="magenta"))

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

class CLIAuditArgsSchema(Schema):
    repo = fields.Str(required=True)
    branch = fields.Str(required=False, allow_none=True)
    pr = fields.Int(required=False, allow_none=True)
    token = fields.Str(required=True)
    output_dir = fields.Str(required=False, allow_none=True)
    scope = fields.Str(required=True, validate=lambda s: s in ['all', 'changed', 'readme', 'test'])
    filter = fields.Str(required=False, allow_none=True, validate=lambda s: s in ['pattern', 'manual', 'none'])
    pattern = fields.Str(required=False, allow_none=True)
    editor = fields.Str(required=False, allow_none=True)
    no_preview = fields.Bool(required=False)
    save_readme = fields.Bool(required=False)
    max_workers = fields.Int(required=False, default=8)
    only_changed = fields.Bool(required=False)
    profile = fields.Bool(required=False)

    @validates('repo')
    def validate_repo(self, value):
        if not re.match(r'^[\w.-]+/[\w.-]+$', value):
            raise ValidationError('Invalid repo format (should be user/repo)')
    @validates('branch')
    def check_branch(self, value):
        if value and not re.match(r'^[\w./-]+$', value):
            raise ValidationError('Invalid branch name')
    @validates('output_dir')
    def validate_output_dir(self, value):
        if value and ('..' in value or '\x00' in value):
            raise ValidationError('Invalid output directory')
    @validates('pattern')
    def validate_pattern(self, value):
        if value and ('..' in value or '\x00' in value):
            raise ValidationError('Invalid pattern')
    @validates_schema
    def validate_scope_schema(self, data, **kwargs):
        if data.get('scope') == 'changed' and not data.get('pr'):
            raise ValidationError('PR number is required for "changed" scope')

def collect_interactive_args() -> dict:
    """Collect and validate CLI arguments interactively using Marshmallow schema."""
    while True:
        repo = questionary.autocomplete(
            "GitHub repo (e.g. user/repo):",
            choices=repo_cache,
        ).ask()
        branch = questionary.autocomplete(
            "Branch (leave blank for default):",
            choices=branch_cache.get(repo, []),
            default=branch_cache.get(repo, [None])[0] if branch_cache.get(repo) else None
        ).ask()
        pr_number = questionary.autocomplete(
            "PR number (leave blank if not analyzing a PR):",
            choices=pr_cache.get(repo, [])
        ).ask()
        pr_number_int = int(pr_number) if pr_number and pr_number.isdigit() else None
        token = questionary.text("GitHub token:").ask()
        output_dir = questionary.text("Output directory for reports and README? (default: reports)").ask()
        scope = questionary.select(
            "What do you want to audit?",
            choices=["all", "changed", "readme", "test"]
        ).ask()
        filter_mode = questionary.select(
            "Filter files by:",
            choices=["pattern", "manual", "none"]
        ).ask()
        pattern = questionary.text("Enter glob pattern (e.g. *.py, src/*.js):").ask() if filter_mode == "pattern" else None
        no_preview = questionary.confirm("Skip preview before saving report?").ask()
        save_readme = questionary.confirm("Save the updated README as a separate file?").ask()
        max_workers = questionary.text("Number of parallel workers for LLM analysis (default: 8):", default="8").ask()
        only_changed = questionary.confirm("Analyze only changed files (using git diff)?").ask()
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
            validated = CLIAuditArgsSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            continue

def get_changed_files():
    """Return a set of changed files using git diff if available."""
    try:
        import subprocess
        result = subprocess.run(['git', 'diff', '--name-only', 'HEAD'], capture_output=True, text=True)
        if result.returncode == 0:
            return set(result.stdout.splitlines())
    except Exception:
        pass
    return set()

def generate_github_report(args=None):
    import time as _time
    global repo_cache, branch_cache, pr_cache
    # Validate args (batch mode) or collect interactively
    config = load_config()
    if args:
        try:
            args_dict = vars(args)
            validated_args = CLIAuditArgsSchema().load(args_dict)
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
            sys.exit(1)
        args = argparse.Namespace(**validated_args)
    else:
        output_dir = questionary.text("Output directory for reports and README? (default: reports)").ask()
    if not output_dir or not output_dir.strip():
        output_dir = 'reports'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    # Use env var first, then config, then prompt
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
        return
    try:
        g = Github(token)
        # Fetch user repos for autocomplete
        if not repo_cache:
            spinner("Fetching your repositories...", duration=2)
            repo_cache = [repo.full_name for repo in g.get_user().get_repos()]
        if args:
            repo = args.repo
        else:
            if repo_cache:
                repo = questionary.select(
                    "Select a GitHub repo:",
                    choices=repo_cache,
                ).ask()
            else:
                repo = questionary.text("GitHub repo (e.g. user/repo):").ask()
        if not repo or not repo.strip():
            console.print("[red]Repository is required.[/red]")
            return
        spinner("Fetching repository details...", duration=1)
        repo_obj = safe_github_call(g.get_repo, repo)
        if repo_obj is None:
            console.print(f"[red]Failed to fetch repository '{repo}'. Please check the repo name and your GitHub token.[/red]")
            return
        # Prompt user to choose between branch or PR
        audit_target = questionary.select(
            "Would you like to audit a branch or a pull request?",
            choices=["Branch", "Pull Request (PR)"]
        ).ask()
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
                    choices=pr_choices,
                ).ask()
            else:
                pr_number = questionary.text("PR number (leave blank if not analyzing a PR):").ask()
        else:
            # Fetch branches for autocomplete
            if repo not in branch_cache:
                spinner("Fetching branches for this repo...", duration=2)
                branch_cache[repo] = [b.name for b in repo_obj.get_branches()]
            branch_choices = [repo_obj.default_branch] + [b for b in branch_cache[repo] if b != repo_obj.default_branch]
            branch = questionary.select(
                "Select a branch (leave blank for default):",
                choices=branch_choices,
                default=repo_obj.default_branch,
            ).ask()
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
                    "Test strategy only"
                ]).ask()

        spinner("Fetching repository data (async)...", duration=2)
        llama = OllamaCodeLlama()
        t0 = _time.time() if do_profile else None
        repo_data = asyncio.run(async_fetch_repo_data(repo, branch, pr_number_int, token))
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
            file_analyses = asyncio.run(async_analyze_code_files(
                files, comments, commits, readme, llama, partial_report_path=partial_report_path, retry_callback=retry_callback))
            if file_analyses is None:
                file_analyses = []
            t3 = _time.time() if do_profile else None
            # Cache test strategy and README suggestions based on file list and readme
            test_strategy_cache_path = os.path.join(CACHE_DIR, f"test_strategy_{hash_content(str([f['filename'] for f in files]))}.json")
            readme_suggestions_cache_path = os.path.join(CACHE_DIR, f"readme_suggestions_{hash_content(readme)}.json")
            if os.path.exists(test_strategy_cache_path):
                with open(test_strategy_cache_path, 'r') as f:
                    test_strategy = f.read()
            else:
                spinner("Generating test strategy (async)...", duration=2)
                test_strategy = asyncio.run(async_generate_test_strategy(files, llama))
                with open(test_strategy_cache_path, 'w') as f:
                    f.write(test_strategy)
            if os.path.exists(readme_suggestions_cache_path):
                with open(readme_suggestions_cache_path, 'r') as f:
                    readme_suggestions = f.read()
                    updated_readme = ""
            else:
                spinner("Reviewing README (async)...", duration=2)
                readme_suggestions, updated_readme = asyncio.run(async_suggest_readme_improvements(readme, llama))
                with open(readme_suggestions_cache_path, 'w') as f:
                    f.write(readme_suggestions)
            t4 = _time.time() if do_profile else None
        elif scope == "Only changed files (for PR)":
            if not pr_number_int:
                console.print("[red]No PR selected. Please select a PR for this option.[/red]")
                return
            changed_files = [f for f in files if f.get('status') in ('added', 'modified', 'changed')]
            spinner("Analyzing changed files with LLM (async, streaming)...", duration=2)
            t2 = _time.time() if do_profile else None
            file_analyses = asyncio.run(async_analyze_code_files(
                changed_files, comments, commits, readme, llama, partial_report_path=partial_report_path, retry_callback=retry_callback))
            if file_analyses is None:
                file_analyses = []
            t3 = _time.time() if do_profile else None
            test_strategy_cache_path = os.path.join(CACHE_DIR, f"test_strategy_{hash_content(str([f['filename'] for f in changed_files]))}.json")
            readme_suggestions_cache_path = os.path.join(CACHE_DIR, f"readme_suggestions_{hash_content(readme)}.json")
            if os.path.exists(test_strategy_cache_path):
                with open(test_strategy_cache_path, 'r') as f:
                    test_strategy = f.read()
            else:
                spinner("Generating test strategy (async)...", duration=2)
                test_strategy = asyncio.run(async_generate_test_strategy(changed_files, llama))
                with open(test_strategy_cache_path, 'w') as f:
                    f.write(test_strategy)
            if os.path.exists(readme_suggestions_cache_path):
                with open(readme_suggestions_cache_path, 'r') as f:
                    readme_suggestions = f.read()
                    updated_readme = ""
            else:
                spinner("Reviewing README (async)...", duration=2)
                readme_suggestions, updated_readme = asyncio.run(async_suggest_readme_improvements(readme, llama))
                with open(readme_suggestions_cache_path, 'w') as f:
                    f.write(readme_suggestions)
            t4 = _time.time() if do_profile else None
        elif scope == "README only":
            spinner("Reviewing README (async)...", duration=2)
            readme_suggestions, updated_readme = asyncio.run(async_suggest_readme_improvements(readme, llama))
        elif scope == "Test strategy only":
            spinner("Generating test strategy (async)...", duration=2)
            test_strategy = asyncio.run(async_generate_test_strategy(files, llama))

        # Append remaining report sections
        with open(partial_report_path, 'a', encoding='utf-8') as f:
            f.write("## Test Strategy\n\n")
            f.write(f"{test_strategy}\n\n---\n\n")
            f.write("## README Suggestions\n\n")
            f.write(f"{readme_suggestions}\n\n---\n\n")
            f.write("## Updated README\n\n")
            f.write(f"```markdown\n{updated_readme}\n```\n\n---\n\n")

        # Move partial report to final report path
        import shutil
        shutil.move(partial_report_path, report_path)
        console.print(Panel(f"[green]GitHub Code Audit & Report generated![/green]\nSaved as: [yellow]{report_path}[/yellow]", style="bold green"))

        if do_profile:
            timings = [
                ("Fetch repo data", t1-t0 if t0 and t1 else None),
                ("LLM analysis", t3-t2 if t2 and t3 else None),
                ("Test strategy/README", t4-t3 if t3 and t4 else None),
            ]
            for label, t in timings:
                if t is not None:
                    console.print(f"[cyan]{label} took {t:.2f} seconds[/cyan]")

        # TODO: Refactor for async/await and batch LLM calls if backend supports it

        # Enhancement 4: Advanced Filtering and Inclusion
        file_names = [f['filename'] for f in files]
        if scope in ("All code files", "Only changed files (for PR)") and file_names:
            if questionary.confirm("Would you like to filter which files to include in the audit?").ask():
                if args:
                    filter_mode = args.filter
                else:
                    filter_mode = questionary.select(
                        "Filter files by:",
                        choices=["Pattern (glob/regex)", "Manual selection", "No filter (include all)"]
                    ).ask()
                if filter_mode == "Pattern (glob/regex)":
                    if args:
                        pattern = args.pattern
                    else:
                        pattern = questionary.text("Enter glob pattern (e.g. *.py, src/*.js):").ask()
                    selected_files = [fn for fn in file_names if fnmatch.fnmatch(fn, pattern)]
                elif filter_mode == "Manual selection":
                    if args:
                        selected_files = args.pattern.split(',')
                    else:
                        selected_files = questionary.checkbox(
                            "Select files to include:",
                            choices=file_names
                        ).ask()
                else:
                    selected_files = file_names
                files = [f for f in files if f['filename'] in selected_files]

        # If pr_number is set, for each changed file, fetch old and new content and show diff
        if pr_number_int:
            for file_info in files:
                filename = file_info['filename']
                if file_info.get('status') in ('added', 'modified', 'changed'):
                    try:
                        # Get old content from base branch
                        old_content = repo_obj.get_contents(filename, ref=pr_info['base_branch']).decoded_content.decode('utf-8')
                    except Exception:
                        old_content = ''
                    new_content = file_info.get('content', '')
                    show_colored_diff(old_content, new_content, filename)

        # Enhancement 2: Preview and Edit Report Before Saving
        preview_lines = report_path.splitlines()[:40]
        console.print(Panel("\n".join(preview_lines), title="Report Preview", style="cyan"))
        if args:
            if args.no_preview:
                preview_lines = report_path.splitlines()[:40]
                console.print(Panel("\n".join(preview_lines), title="Report Preview", style="cyan"))
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
            for fa in file_analyses[:2]:
                panels = []
                panels.append(Panel(fa.get('summary', ''), title=f"[yellow]{fa['filename']}[/yellow] - Summary", style="cyan"))
                if fa.get('bugs_issues'):
                    panels.append(Panel(fa['bugs_issues'], title="Bugs/Issues", style="red"))
                if fa.get('suggestions'):
                    panels.append(Panel(fa['suggestions'], title="Suggestions", style="green"))
                if fa.get('code_example'):
                    panels.append(Panel(fa['code_example'], title="Code Example", style="magenta"))
                if fa.get('code_smells'):
                    panels.append(Panel(fa['code_smells'], title="Code Smells/Anti-patterns", style="yellow"))
                if fa.get('security_performance'):
                    panels.append(Panel(fa['security_performance'], title="Security/Performance", style="blue"))
                if fa.get('test_coverage'):
                    panels.append(Panel(fa['test_coverage'], title="Test Coverage/Quality", style="cyan"))
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
                    "Re-run test strategy"
                ]).ask()
            if rerun_choice == "No, return to main menu":
                break
            elif rerun_choice == "Re-run README analysis":
                spinner("Reviewing README...", duration=2)
                readme_suggestions, updated_readme = suggest_readme_improvements(readme, llama)
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
                test_strategy = generate_test_strategy(files, llama)
                console.print(Panel(f"[bold blue]Test Strategy (updated):[/bold blue]\n{test_strategy[:500]}...", style="cyan"))
    except AssertionError:
        console.print("[red]GitHub token cannot be empty. Please provide a valid token.[/red]")
    except Exception as e:
        logger.exception("Error generating GitHub report")
        console.print_exception()

def run_automated_test():
    console.print(Panel("[cyan]Running automated test on public repo: psf/requests[/cyan]", style="bold blue"))
    test_repo = "psf/requests"
    test_branch = "master"
    test_token = os.environ.get("GITHUB_TOKEN", "")
    if not test_token:
        console.print("[yellow]No GITHUB_TOKEN in environment. Test may be rate-limited or fail on private repos.[/yellow]")
    llama = OllamaCodeLlama()
    try:
        repo_data = fetch_repo_data(test_repo, test_branch, None, test_token)
        files = repo_data['files'][:2]  # Only 2 files for speed
        comments = repo_data['comments']
        commits = repo_data['commits']
        readme = repo_data['readme']
        file_analyses = safe_llm_call(analyze_files_parallel, files, comments, commits, readme, llama, test_repo, test_branch, None)
        test_strategy = generate_test_strategy(files, llama)
        readme_suggestions, updated_readme = suggest_readme_improvements(readme, llama)
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

class APIUploadSchema(Schema):
    report_file = fields.Str(required=True)
    api_url = fields.Url(required=True, error_messages={"invalid": "Invalid API endpoint URL"})
    headers = fields.Dict(keys=fields.Str(), values=fields.Str(), required=False)
    content_type = fields.Str(required=True, validate=lambda s: s in ["JSON (report as string)", "multipart/form-data (file upload)"])

    @validates('report_file')
    def validate_report_file(self, value):
        if not value.endswith('.md'):
            raise ValidationError('Report file must be a .md file')
        if '..' in value or '\x00' in value:
            raise ValidationError('Invalid report file path')

# Modularize API upload input collection

def collect_api_upload_args(output_dir: str) -> dict:
    """Collect and validate API upload arguments interactively using Marshmallow schema."""
    files = [f for f in os.listdir(output_dir) if f.endswith('.md')]
    if not files:
        console.print(f"[red]No .md report files found in {output_dir}.[/red]")
        return None
    while True:
        report_file = questionary.select("Select report to upload:", choices=files).ask()
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
            choices=["JSON (report as string)", "multipart/form-data (file upload)"]
        ).ask()
        args_dict = {
            'report_file': report_file,
            'api_url': api_url,
            'headers': headers,
            'content_type': content_type
        }
        try:
            validated = APIUploadSchema().load(args_dict)
            return validated
        except ValidationError as ve:
            console.print(f"[red]Input error: {ve.messages}[/red]")
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
            console.print("[green]Goodbye![/green]")
            break

def server_menu(params):
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
        console.print("\n[green]Exiting gracefully. Goodbye![/green]")
        sys.exit(0) 