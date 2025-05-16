import os
import sys
import subprocess
import requests
from rich.console import Console
from rich.panel import Panel
import questionary
from utils.helpers import update_env_file
from loguru import logger

console = Console()

server_process = None

MODULE = "SERVER_MANAGER"
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

def write_env_vars_for_server():
    """
    Write environment variables for the server from config and environment.
    Updates or appends GITHUB_TOKEN, OLLAMA_API_KEY, and OLLAMA_LOG_FILE in the .env file.
    """
    import yaml
    config_path = 'config.yaml'
    config = {}
    if os.path.exists(config_path):
        with open(config_path) as file:
            config = yaml.safe_load(file)
    github_token = os.environ.get('GITHUB_TOKEN') or config.get('github', {}).get('token', '')
    api_key = os.environ.get('OLLAMA_API_KEY') or config.get('api', {}).get('key', '')
    log_file = os.environ.get('OLLAMA_LOG_FILE') or config.get('logging', {}).get('log_file', 'ollama_server.log')
    update_env_file({
        'GITHUB_TOKEN': github_token,
        'OLLAMA_API_KEY': api_key,
        'OLLAMA_LOG_FILE': log_file
    })

def start_server():
    """
    Start the API server using Gunicorn or Flask app.run.
    Checks if the server is already running, then starts it in the background.
    """
    global server_process
    print_banner()
    write_env_vars_for_server()
    config_path = 'config.yaml'
    config = {}
    if os.path.exists(config_path):
        import yaml
        with open(config_path) as file:
            config = yaml.safe_load(file)
    # Prompt user for port
    default_port = config.get('server', {}).get('port', 5000)
    port = questionary.text(
        "Enter port to start server on (1024-65535):",
        default=str(default_port)
    ).ask()
    try:
        port = int(port)
        if not (1024 <= port <= 65535):
            raise ValueError
    except Exception:
        console.print("[red]Invalid port. Using default 5000.[/red]")
        port = 5000
    base_url = f"http://localhost:{port}"
    try:
        response = requests.get(f"{base_url}/health", timeout=2)
        if response.status_code == 200:
            console.print(f"[green]Server is already running at {base_url}[/green]")
            return
    except Exception:
        pass
    mode = questionary.select(
        "Choose server mode:",
        choices=[
            "Production (Gunicorn)",
            "Development (Flask app.run)"
        ]).ask()
    try:
        if mode == "Production (Gunicorn)":
            console.print(f"[cyan]Starting server with Gunicorn in the background on port {port}...[/cyan]")
            server_process = subprocess.Popen([
                "gunicorn", "-w", "2", "--threads", "4", "-b", f"0.0.0.0:{port}", "http_api:app"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            console.print(f"[cyan]Starting development server with Flask (app.run) in the background on port {port}...[/cyan]")
            server_process = subprocess.Popen([sys.executable, "http_api.py", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print("[green]Server started in the background. You can continue using the CLI.[/green]")
    except FileNotFoundError:
        console.print("[red]Gunicorn is not installed. Please run: pip install gunicorn[/red]")
    except KeyboardInterrupt:
        console.print("\n[green]Server stopped. Returning to main menu.[/green]")

def show_server_status(params):
    """
    Check and display the status of the API server.
    Tries up to 5 times to connect to the /health endpoint.
    Args:
        params (dict): Dictionary containing the 'port' key.
    """
    import time
    base_url = f"http://localhost:{params['port']}"
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                console.print(f"[green]Server is running at {base_url}[/green]")
                return
        except Exception as error:
            if attempt == 1:
                console.print(f"[yellow]Waiting for server to start...[/yellow]")
            time.sleep(1)
    console.print(f"[red]Server is NOT running at {base_url} after {max_retries} attempts.[/red]")

def stop_server():
    """
    Stop the API server if running.
    Attempts to terminate the process and checks if the /health endpoint is down.
    """
    global server_process
    config_path = 'config.yaml'
    config = {}
    if os.path.exists(config_path):
        import yaml
        with open(config_path) as file:
            config = yaml.safe_load(file)
    port = config.get('server', {}).get('port', 5000)
    base_url = f"http://localhost:{port}"
    is_running = False
    try:
        response = requests.get(f"{base_url}/health", timeout=2)
        if response.status_code == 200:
            is_running = True
    except Exception:
        pass
    if not is_running:
        console.print(f"[yellow]No server process is currently running at {base_url}.[/yellow]")
        server_process = None
        return
    if server_process and server_process.poll() is None:
        try:
            server_process.terminate()
            server_process.wait(timeout=5)
            try:
                response = requests.get(f"{base_url}/health", timeout=2)
                if response.status_code != 200:
                    console.print("[green]Server stopped successfully.[/green]")
                else:
                    console.print("[red]Server process terminated, but /health endpoint still responds. Manual check recommended.[/red]")
            except Exception:
                console.print("[green]Server stopped successfully.[/green]")
        except Exception as error:
            console.print(f"[red]Failed to stop server: {error}[/red]")
    else:
        try:
            response = requests.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                console.print(f"[yellow]Server is running at {base_url}, but not managed by this CLI process. Please stop it manually.[/yellow]")
            else:
                console.print("[yellow]No server process is currently running.[/yellow]")
        except Exception:
            console.print("[yellow]No server process is currently running.[/yellow]")
    server_process = None

def print_banner():
    """
    Print the CLI banner using rich.
    """
    from rich.text import Text
    banner = Text("Ollama Code Llama CLI", style="bold magenta")
    console.print(Panel(banner, expand=False, border_style="cyan"))

def check_server_health(port=None):
    """
    Check the /health endpoint of the API server and log the result.
    Args:
        port (int, optional): Port to check. If None, use config or default 5000.
    Returns:
        dict: {'status': 'up'/'down', 'llm_reply': ...} or error info.
    """
    import requests
    import yaml
    config_path = 'config.yaml'
    config = {}
    if os.path.exists(config_path):
        with open(config_path) as file:
            config = yaml.safe_load(file)
    if port is None:
        port = config.get('server', {}).get('port', 5000)
    base_url = f"http://localhost:{port}"
    try:
        response = requests.get(f"{base_url}/health", timeout=3)
        if response.status_code == 200:
            data = response.json()
            log_info("check_server_health", "success", f"Server is UP at {base_url}/health. LLM reply: {data.get('llm_reply')}", feature="Server", file="http_api.py")
            return {"status": "up", "llm_reply": data.get('llm_reply')}
        else:
            log_error("check_server_health", "fail", f"Server responded with status {response.status_code} at {base_url}/health", feature="Server", file="http_api.py")
            return {"status": "down", "error": f"HTTP {response.status_code}"}
    except Exception as e:
        log_error("check_server_health", "fail", f"Could not reach server at {base_url}/health: {e}", feature="Server", file="http_api.py")
        return {"status": "down", "error": str(e)} 