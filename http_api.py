"""
Production-ready Flask API for Code Llama, designed to be run with Gunicorn for multi-threaded/multi-process serving.
Example:
    gunicorn -w 2 --threads 4 -b 0.0.0.0:5000 http_api:app
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, abort
from ollama_code_llama import OllamaCodeLlama
from github import Github
import difflib
from marshmallow import Schema, fields, ValidationError
import sys
import socket
import multiprocessing
from loguru import logger
from rich.console import Console
from dotenv import load_dotenv
import yaml

# Persistent logging
LOG_FILE = os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log')
handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=3)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max upload
llama = OllamaCodeLlama()

API_KEY = os.environ.get('OLLAMA_API_KEY', 'changeme')

# Load config.yaml for fallback
CONFIG_PATH = 'config.yaml'
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
else:
    config = {}

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or config.get('github', {}).get('token')
logger.info(f"GITHUB_TOKEN loaded: {'yes' if GITHUB_TOKEN else 'no'}")

console = Console()

@app.before_request
def require_api_key():
    # Log each incoming request
    logger.info(f"Incoming request: {request.method} {request.path} from {request.remote_addr}")
    if request.endpoint not in ('health', 'help'):
        if request.headers.get('X-API-KEY') != API_KEY:
            abort(401)

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
        logger.warning(f"Validation error in /generate/text: {ve.messages}")
        return jsonify({'error': ve.messages}), 400
    except Exception as e:
        logger.exception("Error in /generate/text")
        console.print_exception()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate/file', methods=['POST'])
def generate_file():
    try:
        if 'file' not in request.files:
            logger.warning('Missing file in /generate/file')
            return jsonify({'error': 'Missing file'}), 400
        file = request.files['file']
        prompt = file.read().decode('utf-8')
        if not prompt.strip():
            logger.warning('Empty file uploaded to /generate/file')
            return jsonify({'error': 'File is empty'}), 400
        result = llama.generate(prompt)
        return jsonify({'response': result})
    except Exception as e:
        logger.exception("Error in /generate/file")
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
        logger.warning(f"Validation error in /generate/github-pr: {ve.messages}")
        return jsonify({'error': ve.messages}), 400
    except Exception as e:
        logger.exception("Error in /generate/github-pr")
        console.print_exception()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health():
    try:
        reply = llama.generate('ping')
        return jsonify({'status': 'ok', 'llm_reply': reply})
    except Exception as e:
        logger.exception("Error in /health")
        console.print_exception()
        return jsonify({'status': 'error', 'error': str(e)}), 500

def log_startup_context():
    mode = 'production (Gunicorn)' if 'gunicorn' in sys.argv[0] else 'development (Flask app.run)'
    host = os.environ.get('HOST', '0.0.0.0')
    port = os.environ.get('PORT', '5000')
    pid = os.getpid()
    cpu_count = multiprocessing.cpu_count()
    logger.info(f"=== Ollama Server Startup ===")
    logger.info(f"Mode: {mode}")
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Process ID: {pid}")
    logger.info(f"CPU count: {cpu_count}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"API key set: {'yes' if API_KEY != 'changeme' else 'no'}")
    logger.info(f"GitHub token set: {'yes' if GITHUB_TOKEN else 'no'}")
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        logger.info(f"Hostname: {hostname} | IP: {ip}")
    except Exception as e:
        logger.info(f"Could not determine hostname/IP: {e}")
    logger.info("Server is starting up...")
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        logger.info(f"Endpoint: {rule.endpoint} | Methods: {methods} | Path: {rule}")
    logger.info("Server ready to accept requests.")

# Call this function at startup for both app.run and Gunicorn
log_startup_context()

if __name__ == "__main__":
    log_startup_context()
    app.run(host="0.0.0.0", port=5000, debug=True)

# Note: Do NOT use app.run() here. Use Gunicorn to run this app in production. 