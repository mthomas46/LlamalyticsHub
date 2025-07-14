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
import re
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
import threading

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

# Rate limiting
class RateLimiter:
    def __init__(self, requests_per_minute=60):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
        self.lock = threading.Lock()
    
    def is_allowed(self, client_ip):
        now = datetime.now()
        with self.lock:
            # Clean old requests
            self.requests[client_ip] = [req_time for req_time in self.requests[client_ip] 
                                      if now - req_time < timedelta(minutes=1)]
            
            # Check if under limit
            if len(self.requests[client_ip]) >= self.requests_per_minute:
                return False
            
            # Add current request
            self.requests[client_ip].append(now)
            return True

rate_limiter = RateLimiter()

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        if not rate_limiter.is_allowed(client_ip):
            log_warning(__name__, "Rate limit exceeded", f"IP: {client_ip}", feature=__name__, file=request.path)
            return jsonify({'error': 'Rate limit exceeded'}), 429
        return f(*args, **kwargs)
    return decorated_function

def validate_file_upload(file):
    """Validate uploaded file for security"""
    if not file:
        return False, "No file provided"
    
    # Check file size
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if size > 2 * 1024 * 1024:  # 2MB limit
        return False, "File too large"
    
    # Check file extension
    filename = file.filename
    if not filename:
        return False, "No filename provided"
    
    # Allow only text files
    allowed_extensions = {'.txt', '.py', '.js', '.java', '.cpp', '.c', '.h', '.md', '.json', '.xml', '.yaml', '.yml'}
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in allowed_extensions:
        return False, f"File type {file_ext} not allowed"
    
    # Check for path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return False, "Invalid filename"
    
    return True, "OK"

def sanitize_input(text):
    """Basic input sanitization"""
    if not text:
        return ""
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Limit length
    if len(text) > 10000:  # 10KB limit
        text = text[:10000]
    
    return text

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
    prompt = fields.Str(required=True, validate=lambda x: len(x) <= 10000)

class GithubPRSchema(Schema):
    repo = fields.Str(required=True, validate=lambda x: re.match(r'^[\w.-]+/[\w.-]+$', x))
    pr_number = fields.Int(required=True, validate=lambda x: 1 <= x <= 999999)
    token = fields.Str(required=True)
    prompt = fields.Str(required=False, validate=lambda x: len(x) <= 10000 if x else True)

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
@rate_limit
def generate_text():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400
        
        validated = TextSchema().load(data)
        prompt = sanitize_input(validated['prompt'])
        
        if not prompt.strip():
            return jsonify({'error': 'Empty prompt'}), 400
        
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
@rate_limit
def generate_file():
    try:
        if 'file' not in request.files:
            log_warning(__name__, "Missing file in /generate/file", None, feature=__name__, file=request.path)
            return jsonify({'error': 'Missing file'}), 400
        
        file = request.files['file']
        is_valid, message = validate_file_upload(file)
        
        if not is_valid:
            log_warning(__name__, "File validation failed", message, feature=__name__, file=request.path)
            return jsonify({'error': message}), 400
        
        try:
            prompt = file.read().decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({'error': 'File must be UTF-8 encoded text'}), 400
        
        prompt = sanitize_input(prompt)
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
@rate_limit
def generate_github_pr():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400
        
        validated = GithubPRSchema().load(data)
        repo_name = validated['repo']
        pr_number = validated['pr_number']
        token = validated.get('token') or GITHUB_TOKEN
        
        if not token:
            return jsonify({'error': 'GitHub token required'}), 400
        
        prompt_prefix = sanitize_input(validated.get('prompt', 'Review the following GitHub pull request diff for bugs, improvements, and best practices.'))
        
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
        
        # Security: prevent path traversal
        if '..' in report_name or '/' in report_name or '\\' in report_name:
            return jsonify({'error': 'Invalid report name'}), 400
        
        report_path = os.path.join(reports_dir, report_name)
        if not os.path.isfile(report_path):
            log_warning(__name__, "Report not found", f"Report name: {report_name}", feature=__name__, file=request.path)
            return jsonify({'error': 'Report not found'}), 404
        
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        log_info(__name__, "Served report", f"Report: {report_name}", feature=__name__, file=report_name)
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
        
        # Security: prevent path traversal
        if '..' in log_file or log_file.startswith('/'):
            return jsonify({'error': 'Invalid log file path'}), 400
        
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        log_info(__name__, "Served server log file", None, feature=__name__, file=log_file)
        return Response(content, mimetype='text/plain')
    except Exception as e:
        log_exception(__name__, "Error in /logs", str(e), feature=__name__, file=request.path)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/endpoints', methods=['GET'])
def list_endpoints():
    """List all available endpoints and their methods."""
    try:
        endpoints = []
        for rule in app.url_map.iter_rules():
            endpoints.append({
                'endpoint': rule.rule,
                'methods': list(rule.methods - {'HEAD', 'OPTIONS'}),
                'function': rule.endpoint
            })
        log_info(__name__, "Listed endpoints", f"Found {len(endpoints)} endpoints", feature=__name__, file=request.path)
        return jsonify({'endpoints': endpoints})
    except Exception as e:
        log_exception(__name__, "Error in /endpoints", str(e), feature=__name__, file=request.path)
        return jsonify({'error': 'Internal server error'}), 500

def log_startup_context():
    """Log startup context for debugging."""
    try:
        log_info(__name__, "Startup", f"App started with config: {config}", feature=__name__, file=__file__)
        log_info(__name__, "Startup", f"Environment: FLASK_ENV={os.environ.get('FLASK_ENV', 'development')}", feature=__name__, file=__file__)
        log_info(__name__, "Startup", f"Log file: {LOG_FILE}", feature=__name__, file=__file__)
    except Exception as e:
        log_exception(__name__, "Startup", f"Error logging startup context: {e}", feature=__name__, file=__file__)

if __name__ == '__main__':
    log_startup_context()
    app.run(host='0.0.0.0', port=5000, debug=False) 