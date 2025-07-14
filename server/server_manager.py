import os
import sys
import subprocess
import requests
from rich.console import Console
from rich.panel import Panel
import questionary
from utils.helpers import update_env_file
from loguru import logger
import signal
import psutil
import socket

console = Console()

server_process = None

MODULE = "SERVER_MANAGER"
PID_FILE = ".llamalyticshub.pid"

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

def write_pid(pid, port):
    with open(PID_FILE, "w") as f:
        f.write(f"{pid},{port}\n")
    log_info("write_pid", "write", f"Wrote PID {pid} and port {port} to {PID_FILE}", feature="Server", file=PID_FILE)

def read_pid():
    if not os.path.exists(PID_FILE):
        return None, None
    with open(PID_FILE) as f:
        line = f.read().strip()
        if not line:
            return None, None
        parts = line.split(",")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
        return int(parts[0]), None

def remove_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        log_info("remove_pid", "remove", f"Removed PID file {PID_FILE}", feature="Server", file=PID_FILE)

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def is_service_healthy(port):
    try:
        r = requests.get(f"http://localhost:{port}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def start_server():
    """
    Start the API server using Gunicorn or Flask app.run.
    Checks if the server is already running, then starts it in the background.
    Now robustly checks port, PID, and health endpoint before starting.
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
    # Robust checks
    pid, pid_port = read_pid()
    port_in_use = is_port_in_use(port)
    healthy = is_service_healthy(port)
    pid_running = pid and psutil.pid_exists(pid)
    # 1. Port in use?
    if port_in_use:
        if healthy:
            console.print(f"[green]Server is already running and healthy at http://localhost:{port}[/green]")
            log_info("start_server", "already_running_healthy", f"Healthy service on port {port}", feature="Server", file=PID_FILE)
            return
        else:
            console.print(f"[yellow]Port {port} is in use but service is not healthy.")
            log_warning("start_server", "port_in_use_not_healthy", f"Port {port} in use but service not healthy", feature="Server", file=PID_FILE)
            # Check PID file
            if pid:
                if pid_running:
                    console.print(f"[yellow]Process with PID {pid} (from PID file) is running. Not starting a new process.[/yellow]")
                    log_info("start_server", "pid_running", f"Process {pid} running on port {port}", feature="Server", file=PID_FILE)
                    return
                else:
                    console.print(f"[red]PID file exists but process {pid} is not running. Cleaning up PID file.[/red]")
                    log_warning("start_server", "stale_pid_file", f"Stale PID file for {pid}", feature="Server", file=PID_FILE)
                    remove_pid()
            else:
                console.print(f"[red]Port {port} is in use by an unknown process. Please free the port or use a different one.[/red]")
                log_error("start_server", "unknown_process_on_port", f"Port {port} in use, no PID file.", feature="Server", file=PID_FILE)
                return
    else:
        # Port is free
        if pid and pid_running:
            console.print(f"[yellow]PID file exists and process {pid} is running, but port {port} is free. Not starting a new process.[/yellow]")
            log_info("start_server", "pid_running_port_free", f"Process {pid} running, port {port} free", feature="Server", file=PID_FILE)
            return
        elif pid and not pid_running:
            console.print(f"[red]PID file exists but process {pid} is not running. Cleaning up PID file.[/red]")
            log_warning("start_server", "stale_pid_file_port_free", f"Stale PID file for {pid}", feature="Server", file=PID_FILE)
            remove_pid()
        # Final health check
        if healthy:
            console.print(f"[green]Server is already running and healthy at http://localhost:{port}[/green]")
            log_info("start_server", "already_running_healthy_port_free", f"Healthy service on port {port}", feature="Server", file=PID_FILE)
            return
    # If we reach here, it's safe to start the server
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
        write_pid(server_process.pid, port)
        console.print("[green]Server started in the background. You can continue using the CLI.[/green]")
        log_info("start_server", "started", f"Started server with PID {server_process.pid} on port {port}", feature="Server", file=PID_FILE)
    except FileNotFoundError:
        console.print("[red]Gunicorn is not installed. Please run: pip install gunicorn[/red]")
        log_error("start_server", "gunicorn_missing", "Gunicorn is not installed.", feature="Server", file=PID_FILE)
    except KeyboardInterrupt:
        console.print("\n[green]Server stopped. Returning to main menu.[/green]")
        log_info("start_server", "keyboard_interrupt", "Server start interrupted by user.", feature="Server", file=PID_FILE)

def show_server_status(params=None):
    pid, port = read_pid()
    if pid and psutil.pid_exists(pid):
        console.print(f"[green]Server running with PID {pid} on port {port}.[/green]")
        log_info("show_server_status", "running", f"Server running with PID {pid} on port {port}", feature="Server", file=PID_FILE)
    else:
        console.print("[yellow]Server not running (no valid PID found).[/yellow]")
        log_info("show_server_status", "not_running", "Server not running (no valid PID found).", feature="Server", file=PID_FILE)

def stop_server():
    """
    Stop the API server if running.
    Attempts to terminate the process and checks if the /health endpoint is down.
    """
    pid, port = read_pid()
    if pid and psutil.pid_exists(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            remove_pid()
            console.print(f"[green]Server with PID {pid} stopped.[/green]")
            log_info("stop_server", "stopped", f"Stopped server with PID {pid} on port {port}", feature="Server", file=PID_FILE)
        except Exception as error:
            console.print(f"[red]Failed to stop server: {error}[/red]")
            log_error("stop_server", "fail", f"Failed to stop server with PID {pid}: {error}", feature="Server", file=PID_FILE)
    else:
        console.print("[yellow]No running server found (by PID file).[/yellow]")
        log_warning("stop_server", "not_found", "No running server found (by PID file).", feature="Server", file=PID_FILE)
        remove_pid()

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