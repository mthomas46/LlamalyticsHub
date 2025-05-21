"""
Production-ready Flask API for Code Llama, designed to be run with Gunicorn for multi-threaded/multi-process serving.
Example:
    gunicorn -w 2 --threads 4 -b 0.0.0.0:5000 http_api:app
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env first for environment variables
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, abort, send_from_directory, Response
from ollama_code_llama import OllamaCodeLlama
from github import Github
import difflib
from marshmallow import Schema, fields, ValidationError
import sys
import socket
import multiprocessing
from loguru import logger
from rich.console import Console
import yaml
import glob

# Load config.yaml after .env
CONFIG_PATH = 'config.yaml'
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
else:
    config = {}

# Merge config and environment variables (env vars take priority)
LOG_FILE = os.environ.get('OLLAMA_LOG_FILE') or config.get('OLLAMA_LOG_FILE') or config.get('log_file', 'ollama_server.log')
API_KEY = os.environ.get('OLLAMA_API_KEY') or config.get('OLLAMA_API_KEY') or config.get('llamalyticshub', {}).get('api_key', 'changeme')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or config.get('GITHUB_TOKEN') or config.get('github', {}).get('token')

# Persistent logging
handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=3)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max upload
llama = OllamaCodeLlama()

logger.info(f"GITHUB_TOKEN loaded: {'yes' if GITHUB_TOKEN else 'no'}")

console = Console()

# Add standardized logging helpers
MODULE = "HTTP_API"
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

@app.before_request
def require_api_key():
    # Log each incoming request
    log_info(__name__, "Incoming request", f"{request.method} {request.path} from {request.remote_addr}", feature=__name__, file=request.path)
    # API key is now optional; just log if present or not
    api_key_header = request.headers.get('X-API-KEY')
    if api_key_header:
        log_info(__name__, "API key provided", api_key_header, feature=__name__, file=request.path)
    else:
        log_info(__name__, "No API key provided", None, feature=__name__, file=request.path)

# Marshmallow Schemas
class TextSchema(Schema):
    prompt = fields.Str(required=True)

class GithubPRSchema(Schema):
    repo = fields.Str(required=True)
    pr_number = fields.Int(required=True)
    token = fields.Str(required=True)
    prompt = fields.Str(required=False)

@app.route('/help', methods=['GET'])
def help():
    info = {
        "endpoints": {
            "/generate/text": "POST JSON {prompt}",
            "/generate/file": "POST multipart/form-data file=@...",
            "/generate/github-pr": "POST JSON {repo, pr_number, token, prompt?}",
            "/health": "GET",
            "/help": "GET"
        },
        "auth": "Set X-API-KEY header to your API key."
    }
    return jsonify(info)

@app.route('/generate/text', methods=['POST'])
def generate_text():
    try:
        data = request.get_json()
        validated = TextSchema().load(data)
        prompt = validated['prompt']
        result = llama.generate(prompt)
        return jsonify({'response': result})
    except ValidationError as ve:
        log_warning(__name__, "Validation error in /generate/text", ve.messages, feature=__name__, file=request.path)
        return jsonify({'error': ve.messages}), 400
    except Exception as e:
        log_exception(__name__, "Error in /generate/text", str(e), feature=__name__, file=request.path)
        console.print_exception()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate/file', methods=['POST'])
def generate_file():
    try:
        if 'file' not in request.files:
            log_warning(__name__, "Missing file in /generate/file", None, feature=__name__, file=request.path)
            return jsonify({'error': 'Missing file'}), 400
        file = request.files['file']
        prompt = file.read().decode('utf-8')
        if not prompt.strip():
            log_warning(__name__, "Empty file uploaded to /generate/file", None, feature=__name__, file=request.path)
            return jsonify({'error': 'File is empty'}), 400
        result = llama.generate(prompt)
        return jsonify({'response': result})
    except Exception as e:
        log_exception(__name__, "Error in /generate/file", str(e), feature=__name__, file=request.path)
        console.print_exception()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate/github-pr', methods=['POST'])
def generate_github_pr():
    try:
        data = request.get_json()
        validated = GithubPRSchema().load(data)
        repo_name = validated['repo']
        pr_number = validated['pr_number']
        token = validated.get('token') or GITHUB_TOKEN
        if not token:
            return jsonify({'error': 'GitHub token required'}), 400
        prompt_prefix = validated.get('prompt', 'Review the following GitHub pull request diff for bugs, improvements, and best practices.')
        g = Github(token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files = pr.get_files()
        diff_summary = []
        for file in files:
            filename = file.filename
            patch = file.patch if hasattr(file, 'patch') else ''
            diff_summary.append(f"File: {filename}\n{patch}")
        diff_text = '\n\n'.join(diff_summary)
        prompt = f"{prompt_prefix}\n\n{diff_text}"
        result = llama.generate(prompt)
        return jsonify({'response': result})
    except ValidationError as ve:
        log_warning(__name__, "Validation error in /generate/github-pr", ve.messages, feature=__name__, file=request.path)
        return jsonify({'error': ve.messages}), 400
    except Exception as e:
        log_exception(__name__, "Error in /generate/github-pr", str(e), feature=__name__, file=request.path)
        console.print_exception()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    try:
        reply = llama.generate('ping')
        return jsonify({'status': 'ok', 'llm_reply': reply})
    except Exception as e:
        log_exception(__name__, "Error in /health", str(e), feature=__name__, file=request.path)
        console.print_exception()
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/reports', methods=['GET'])
def list_reports():
    try:
        reports_dir = os.path.join(os.getcwd(), 'reports')
        report_files = [os.path.basename(f) for f in glob.glob(os.path.join(reports_dir, '*.md')) if not f.endswith('.partial')]
        log_info(__name__, "Listing reports", f"Report files: {report_files}", feature=__name__, file=request.path)
        return jsonify({'reports': report_files})
    except Exception as e:
        log_exception(__name__, "Error in /reports", str(e), feature=__name__, file=request.path)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/reports/<report_name>', methods=['GET'])
def get_report(report_name):
    try:
        reports_dir = os.path.join(os.getcwd(), 'reports')
        if not report_name.endswith('.md') or report_name.endswith('.partial'):
            log_warning(__name__, "Attempt to access invalid report", f"Report name: {report_name}", feature=__name__, file=request.path)
            return jsonify({'error': 'Invalid report name'}), 400
        report_path = os.path.join(reports_dir, report_name)
        if not os.path.isfile(report_path):
            log_warning(__name__, "Report not found", f"Report name: {report_name}", feature=__name__, file=request.path)
            return jsonify({'error': 'Report not found'}), 404
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        log_info(__name__, "Served report", f"Report name: {report_name}", feature=__name__, file=report_name)
        return Response(content, mimetype='text/markdown')
    except Exception as e:
        log_exception(__name__, "Error in /reports/<report_name>", str(e), feature=__name__, file=request.path)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        log_file = os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log')
        if not os.path.isfile(log_file):
            log_warning(__name__, "Log file not found", f"Log file: {log_file}", feature=__name__, file=log_file)
            return jsonify({'error': 'Log file not found'}), 404
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        log_info(__name__, "Served server log file", None, feature=__name__, file=log_file)
        return Response(content, mimetype='text/plain')
    except Exception as e:
        log_exception(__name__, "Error in /logs", str(e), feature=__name__, file=request.path)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/endpoints', methods=['GET'])
def list_endpoints():
    """Return a JSON list of all currently served HTTP endpoints and their methods."""
    output = []
    for rule in app.url_map.iter_rules():
        # Exclude static endpoint if not needed
        if rule.endpoint == 'static':
            continue
        methods = sorted(rule.methods - {'HEAD', 'OPTIONS'})
        output.append({
            'endpoint': str(rule.rule),
            'methods': methods,
            'function': rule.endpoint
        })
    return jsonify({'endpoints': output})

def log_startup_context():
    mode = 'production (Gunicorn)' if 'gunicorn' in sys.argv[0] else 'development (Flask app.run)'
    host = os.environ.get('HOST', '0.0.0.0')
    port = os.environ.get('PORT', '5000')
    pid = os.getpid()
    cpu_count = multiprocessing.cpu_count()
    log_info(__name__, "=== Ollama Server Startup ===", None, feature=__name__)
    log_info(__name__, "Mode", mode, feature=__name__)
    log_info(__name__, "Host", host, feature=__name__)
    log_info(__name__, "Port", port, feature=__name__)
    log_info(__name__, "Process ID", pid, feature=__name__)
    log_info(__name__, "CPU count", cpu_count, feature=__name__)
    log_info(__name__, "Log file", LOG_FILE, feature=__name__)
    log_info(__name__, "API key set", 'yes' if API_KEY != 'changeme' else 'no', feature=__name__)
    log_info(__name__, "GitHub token set", 'yes' if GITHUB_TOKEN else 'no', feature=__name__)
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        log_info(__name__, "Hostname", hostname, feature=__name__)
        log_info(__name__, "IP", ip, feature=__name__)
    except Exception as e:
        log_info(__name__, "Could not determine hostname/IP", str(e), feature=__name__)
    log_info(__name__, "Server is starting up...", None, feature=__name__)
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        log_info(__name__, "Endpoint", rule.endpoint, feature=__name__, file=rule.rule)
    log_info(__name__, "Server ready to accept requests.", None, feature=__name__)

# Call this function at startup for both app.run and Gunicorn
log_startup_context()

if __name__ == "__main__":
    log_startup_context()
    import sys
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except Exception:
            pass
    port = int(os.environ.get('PORT', port))
    log_info(__name__, "Startup", f"Running app.run on port {port}", feature=__name__)
    app.run(host="0.0.0.0", port=port, debug=True)

# Note: Do NOT use app.run() here. Use Gunicorn to run this app in production. 