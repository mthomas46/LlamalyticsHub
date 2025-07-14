"""
Production-ready FastAPI application for LlamalyticsHub.
Features: Async support, automatic API documentation, OpenAPI schema, and enhanced security.
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env first for environment variables

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from contextlib import asynccontextmanager
import yaml
import glob
import re
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
import threading
from loguru import logger
from rich.console import Console
import json

# Import existing modules
from ollama_code_llama import OllamaCodeLlama
from github import Github

# Import security modules
from security_config import get_security_config, get_security_validator, get_security_monitor, get_security_headers
from security_middleware import get_security_middleware

# Load configuration
CONFIG_PATH = 'config.yaml'
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
else:
    config = {}

# Environment variables
LOG_FILE = os.environ.get('OLLAMA_LOG_FILE') or config.get('OLLAMA_LOG_FILE') or config.get('log_file', 'ollama_server.log')
API_KEY = os.environ.get('OLLAMA_API_KEY') or config.get('OLLAMA_API_KEY') or config.get('llamalyticshub', {}).get('api_key', 'changeme')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or config.get('GITHUB_TOKEN') or config.get('github', {}).get('token')

# Initialize security components
SECURITY_CONFIG = get_security_config()
SECURITY_VALIDATOR = get_security_validator()
SECURITY_MONITOR = get_security_monitor()
SECURITY_HEADERS = get_security_headers()
SECURITY_MIDDLEWARE = get_security_middleware()

# Setup logging
handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=3)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    log_info("lifespan", "Application starting", "FastAPI application starting up", feature="startup")
    console.print("[green]FastAPI application starting up...[/green]")
    
    yield
    
    # Shutdown
    log_info("lifespan", "Application shutting down", "FastAPI application shutting down", feature="shutdown")
    console.print("[yellow]FastAPI application shutting down...[/yellow]")

# Initialize FastAPI app
app = FastAPI(
    title="LlamalyticsHub API",
    description="FastAPI-based LLM code analysis and GitHub audit service",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Security middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure appropriately for production
)

# Initialize services
llama = OllamaCodeLlama()
security = HTTPBearer(auto_error=False)
console = Console()

# Logging helpers
MODULE = "FASTAPI_APP"
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
    def __init__(self, requests_per_minute=60, test_mode=False):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
        self.lock = threading.Lock()
        self.test_mode = test_mode or os.getenv('TESTING', 'false').lower() == 'true'  # Allow bypassing rate limits in tests
    
    def is_allowed(self, client_ip: str) -> bool:
        # In test mode, always allow requests
        if self.test_mode:
            return True
            
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

# Initialize rate limiter with test mode if in testing environment
rate_limiter = RateLimiter(
    requests_per_minute=1000 if os.getenv('TESTING', 'false').lower() == 'true' else 60,
    test_mode=os.getenv('TESTING', 'false').lower() == 'true'
)

# Pydantic models for request/response validation
class TextRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000, description="Text prompt for LLM generation")
    
    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v):
        if not v.strip():
            raise ValueError('Prompt cannot be empty')
        return v.strip()

class GithubPRRequest(BaseModel):
    owner: str = Field(..., description="GitHub repository owner")
    repo: str = Field(..., description="GitHub repository name")
    pr: int = Field(..., ge=1, le=999999, description="Pull request number")
    token: Optional[str] = Field(None, description="GitHub token (optional if set in env)")
    prompt: Optional[str] = Field(None, max_length=10000, description="Custom prompt for PR analysis")
    
    @field_validator('owner')
    @classmethod
    def validate_owner(cls, v):
        if not v.strip():
            raise ValueError('Owner cannot be empty')
        return v.strip()
    
    @field_validator('repo')
    @classmethod
    def validate_repo(cls, v):
        if not v.strip():
            raise ValueError('Repository name cannot be empty')
        return v.strip()

class HealthResponse(BaseModel):
    status: str
    llm_reply: Optional[str] = None
    error: Optional[str] = None

class GenerateResponse(BaseModel):
    response: str

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None

class ReportsResponse(BaseModel):
    reports: List[str]

# Security functions
def validate_file_upload(file: UploadFile) -> tuple[bool, str]:
    """Validate uploaded file for security using advanced validation"""
    if not file:
        return False, "No file provided"
    
    # Use advanced security validator
    is_valid, message = SECURITY_VALIDATOR.validate_filename(file.filename or "")
    if not is_valid:
        return False, message
    
    # Check file size using security config
    if file.size and file.size > SECURITY_CONFIG.MAX_FILE_SIZE_BYTES:
        return False, f"File too large (max {SECURITY_CONFIG.MAX_FILE_SIZE_BYTES} bytes)"
    
    return True, "OK"

def sanitize_input(text: str) -> str:
    """Sanitize user input using advanced security validator"""
    return SECURITY_VALIDATOR.sanitize_input(text, SECURITY_CONFIG.MAX_INPUT_LENGTH)

def validate_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
    """Validate API key for protected endpoints"""
    if not SECURITY_CONFIG.API_KEY_REQUIRED or API_KEY == "changeme":
        return True  # No API key required
    
    if not credentials:
        return False
    
    return credentials.credentials == API_KEY

async def get_client_ip(request: Request) -> str:
    """Get client IP address with advanced proxy support"""
    return await SECURITY_MIDDLEWARE._get_client_ip(request)

async def check_rate_limit(request: Request):
    """Check rate limiting using advanced rate limiter"""
    client_ip = await get_client_ip(request)
    is_allowed, reason = SECURITY_MIDDLEWARE.rate_limiter.is_allowed(client_ip)
    
    if not is_allowed:
        SECURITY_MONITOR.log_security_event("rate_limit_exceeded", reason, client_ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    return client_ip

async def log_request(request: Request, client_ip: str):
    """Log incoming requests with advanced security monitoring"""
    # Analyze request for threats
    threats = SECURITY_MIDDLEWARE.threat_detector.analyze_request(request, client_ip)
    
    if threats:
        SECURITY_MONITOR.log_security_event(
            "threats_detected", 
            f"Threats: {threats}", 
            client_ip,
            request.headers.get("User-Agent", "")
        )
    
    log_info("log_request", "Incoming request", 
             f"{request.method} {request.url.path} from {client_ip}", 
             feature="request_logging", file=request.url.path)

async def get_llama() -> OllamaCodeLlama:
    """Get LLM client instance"""
    return llama

async def get_github_token() -> Optional[str]:
    """Get GitHub token from environment or config"""
    return GITHUB_TOKEN

# Enhanced security middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Enhanced request logging middleware with advanced security monitoring"""
    start_time = datetime.now()
    client_ip = await get_client_ip(request)
    
    # Log request
    await log_request(request, client_ip)
    
    # Security checks using advanced middleware
    user_agent = request.headers.get("User-Agent", "")
    if "bot" in user_agent.lower() or "crawler" in user_agent.lower():
        log_warning("middleware", "Bot detected", f"Bot user agent: {user_agent}", feature="security")
    
    # Process request with advanced security
    try:
        response = await call_next(request)
        process_time = datetime.now() - start_time
        
        # Add comprehensive security headers
        response = SECURITY_MIDDLEWARE._add_security_headers(response)
        
        # Log response with security context
        log_info("middleware", "Response", 
                f"{response.status_code} in {process_time.total_seconds():.3f}s", 
                feature="request_logging", file=request.url.path)
        
        return response
    except Exception as e:
        log_exception("middleware", "Request failed", str(e), feature="error_handling", file=request.url.path)
        raise

# API endpoints
@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "LlamalyticsHub API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health", response_model=HealthResponse)
async def health(llama_client: OllamaCodeLlama = Depends(get_llama)):
    """Health check endpoint with LLM connectivity test"""
    try:
        # Test LLM connectivity
        test_response = llama_client.generate("Hello")
        return HealthResponse(
            status="healthy",
            llm_reply=test_response[:100] + "..." if len(test_response) > 100 else test_response
        )
    except Exception as e:
        log_error("health", "Health check failed", str(e), feature="health")
        return HealthResponse(
            status="unhealthy",
            error=str(e)
        )

@app.post("/generate/text", 
          response_model=GenerateResponse,
          responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def generate_text(
    request: TextRequest,
    client_ip: str = Depends(check_rate_limit),
    llama_client: OllamaCodeLlama = Depends(get_llama)
):
    """Generate text using LLM with input validation and sanitization"""
    try:
        # Sanitize input
        sanitized_prompt = sanitize_input(request.prompt)
        if not sanitized_prompt:
            raise HTTPException(status_code=400, detail="Invalid prompt")
        
        # Generate response
        response = llama_client.generate(sanitized_prompt)
        
        log_info("generate_text", "Success", f"Generated response for {client_ip}", feature="text_generation")
        return GenerateResponse(response=response)
        
    except Exception as e:
        log_error("generate_text", "Generation failed", str(e), feature="text_generation")
        raise HTTPException(status_code=500, detail="Text generation failed")

@app.post("/upload",
          response_model=GenerateResponse,
          responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def upload_file(
    file: UploadFile = File(...),
    client_ip: str = Depends(check_rate_limit),
    llama_client: OllamaCodeLlama = Depends(get_llama)
):
    """Upload and analyze file with comprehensive security validation"""
    try:
        # Validate file
        is_valid, message = validate_file_upload(file)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
        
        # Read file content
        content = await file.read()
        if len(content) > 2 * 1024 * 1024:  # 2MB limit
            raise HTTPException(status_code=400, detail="File too large")
        
        # Decode content
        try:
            text_content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid file encoding")
        
        # Sanitize content
        sanitized_content = sanitize_input(text_content)
        if not sanitized_content:
            raise HTTPException(status_code=400, detail="File content is empty after sanitization")
        
        # Generate analysis
        prompt = f"Analyze this code file ({file.filename}):\n\n{sanitized_content}"
        response = llama_client.generate(prompt)
        
        log_info("upload_file", "Success", f"Analyzed file {file.filename} for {client_ip}", feature="file_upload")
        return GenerateResponse(response=response)
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("upload_file", "File analysis failed", str(e), feature="file_upload")
        raise HTTPException(status_code=500, detail="File analysis failed")

@app.post("/generate/file",
          response_model=GenerateResponse,
          responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def generate_file(
    file: UploadFile = File(...),
    client_ip: str = Depends(check_rate_limit),
    llama_client: OllamaCodeLlama = Depends(get_llama)
):
    """Legacy file generation endpoint - redirects to upload"""
    return await upload_file(file, client_ip, llama_client)

@app.post("/generate/github-pr",
          response_model=GenerateResponse,
          responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def generate_github_pr(
    request: GithubPRRequest,
    client_ip: str = Depends(check_rate_limit),
    llama_client: OllamaCodeLlama = Depends(get_llama),
    github_token: Optional[str] = Depends(get_github_token)
):
    """Analyze GitHub pull request with comprehensive security validation"""
    try:
        # Validate GitHub token
        if not github_token:
            raise HTTPException(status_code=400, detail="GitHub token required")
        
        # Sanitize inputs
        sanitized_owner = sanitize_input(request.owner)
        sanitized_repo = sanitize_input(request.repo)
        sanitized_prompt = sanitize_input(request.prompt) if request.prompt else ""
        
        # Construct full repo name
        full_repo_name = f"{sanitized_owner}/{sanitized_repo}"
        
        # Validate repository format
        if not re.match(r'^[\w.-]+/[\w.-]+$', full_repo_name):
            raise HTTPException(status_code=400, detail="Invalid repository format")
        
        # Initialize GitHub client
        try:
            g = Github(github_token)
            repo = g.get_repo(full_repo_name)
        except Exception as e:
            log_error("generate_github_pr", "GitHub API error", str(e), feature="github_pr")
            raise HTTPException(status_code=400, detail="Failed to access GitHub repository")
        
        # Get PR information
        try:
            pr = repo.get_pull(request.pr)
        except Exception as e:
            log_error("generate_github_pr", "PR not found", str(e), feature="github_pr")
            raise HTTPException(status_code=404, detail="Pull request not found")
        
        # Build analysis prompt
        pr_info = f"PR #{request.pr}: {pr.title}\n\n{pr.body or 'No description'}"
        if sanitized_prompt:
            analysis_prompt = f"{sanitized_prompt}\n\n{pr_info}"
        else:
            analysis_prompt = f"Analyze this GitHub pull request:\n\n{pr_info}"
        
        # Generate analysis
        response = llama_client.generate(analysis_prompt)
        
        log_info("generate_github_pr", "Success", f"Analyzed PR {request.pr} for {client_ip}", feature="github_pr")
        return GenerateResponse(response=response)
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("generate_github_pr", "PR analysis failed", str(e), feature="github_pr")
        raise HTTPException(status_code=500, detail="GitHub PR analysis failed")

@app.get("/reports", response_model=ReportsResponse)
async def list_reports():
    """List available reports with security validation"""
    try:
        # Secure directory traversal prevention
        reports_dir = "reports"
        if not os.path.exists(reports_dir):
            return ReportsResponse(reports=[])
        
        # Get only .md files from reports directory
        pattern = os.path.join(reports_dir, "*.md")
        reports = []
        
        for file_path in glob.glob(pattern):
            # Validate file path
            if os.path.isfile(file_path) and file_path.startswith(reports_dir):
                filename = os.path.basename(file_path)
                # Additional security check
                if not any(char in filename for char in ['..', '/', '\\']):
                    reports.append(filename)
        
        log_info("list_reports", "Success", f"Found {len(reports)} reports", feature="reports")
        return ReportsResponse(reports=reports)
        
    except Exception as e:
        log_error("list_reports", "Failed to list reports", str(e), feature="reports")
        raise HTTPException(status_code=500, detail="Failed to list reports")

@app.get("/reports/{report_name}")
async def get_report(report_name: str):
    """Get specific report with comprehensive security validation"""
    try:
        # Validate report name
        if not report_name or not report_name.endswith('.md'):
            raise HTTPException(status_code=400, detail="Invalid report name")
        
        # Prevent path traversal
        if '..' in report_name or '/' in report_name or '\\' in report_name:
            raise HTTPException(status_code=400, detail="Invalid report name")
        
        # Sanitize filename
        safe_report_name = sanitize_input(report_name)
        if not safe_report_name:
            raise HTTPException(status_code=400, detail="Invalid report name")
        
        # Construct file path
        report_path = os.path.join("reports", safe_report_name)
        
        # Security check: ensure path is within reports directory
        if not os.path.abspath(report_path).startswith(os.path.abspath("reports")):
            raise HTTPException(status_code=400, detail="Invalid report path")
        
        # Check if file exists
        if not os.path.exists(report_path):
            raise HTTPException(status_code=404, detail="Report not found")
        
        # Read and return report
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            log_info("get_report", "Success", f"Retrieved report {report_name}", feature="reports")
            return PlainTextResponse(content=content, media_type="text/markdown")
            
        except UnicodeDecodeError:
            raise HTTPException(status_code=500, detail="Report encoding error")
        except Exception as e:
            log_error("get_report", "Failed to read report", str(e), feature="reports")
            raise HTTPException(status_code=500, detail="Failed to read report")
            
    except HTTPException:
        raise
    except Exception as e:
        log_error("get_report", "Unexpected error", str(e), feature="reports")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/logs")
async def get_logs():
    """Get application logs with security filtering"""
    try:
        # Security: limit log access
        if not os.path.exists(LOG_FILE):
            return {"logs": [], "message": "No log file found"}
        
        # Read last 100 lines for security
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # Get last 100 lines
                recent_lines = lines[-100:] if len(lines) > 100 else lines
                
                # Filter sensitive information
                filtered_lines = []
                for line in recent_lines:
                    # Remove sensitive data
                    filtered_line = re.sub(r'token=[^&\s]+', 'token=***', line)
                    filtered_line = re.sub(r'password=[^&\s]+', 'password=***', filtered_line)
                    filtered_line = re.sub(r'api_key=[^&\s]+', 'api_key=***', filtered_line)
                    filtered_lines.append(filtered_line)
                
                log_info("get_logs", "Success", f"Retrieved {len(filtered_lines)} log lines", feature="logs")
                return {"logs": filtered_lines}
                
        except UnicodeDecodeError:
            raise HTTPException(status_code=500, detail="Log file encoding error")
        except Exception as e:
            log_error("get_logs", "Failed to read logs", str(e), feature="logs")
            raise HTTPException(status_code=500, detail="Failed to read logs")
            
    except HTTPException:
        raise
    except Exception as e:
        log_error("get_logs", "Unexpected error", str(e), feature="logs")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/endpoints", response_model=Dict[str, List[Dict[str, Any]]])
async def list_endpoints():
    """List available API endpoints with security information"""
    try:
        endpoints = []
        
        # Get all routes
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                endpoint_info = {
                    "path": route.path,
                    "methods": list(route.methods),
                    "name": getattr(route, 'name', 'Unknown'),
                    "requires_auth": "Authorization" in str(route.dependencies) if hasattr(route, 'dependencies') else False
                }
                endpoints.append(endpoint_info)
        
        log_info("list_endpoints", "Success", f"Listed {len(endpoints)} endpoints", feature="endpoints")
        return {"endpoints": endpoints}
        
    except Exception as e:
        log_error("list_endpoints", "Failed to list endpoints", str(e), feature="endpoints")
        raise HTTPException(status_code=500, detail="Failed to list endpoints")

@app.get("/security/status")
async def get_security_status():
    """Get comprehensive security status and statistics"""
    try:
        # Get rate limiting statistics
        rate_limit_stats = {}
        for ip in list(SECURITY_MIDDLEWARE.rate_limiter.requests.keys())[:10]:  # Top 10 IPs
            rate_limit_stats[ip] = SECURITY_MIDDLEWARE.rate_limiter.get_stats(ip)
        
        # Get threat statistics
        threat_stats = {
            "suspicious_ips": len(SECURITY_MIDDLEWARE.threat_detector.suspicious_ips),
            "blocked_ips": len(SECURITY_MIDDLEWARE.rate_limiter.blocked_ips),
            "total_threats": sum(len(threats) for threats in SECURITY_MIDDLEWARE.threat_detector.threat_history.values())
        }
        
        # Get security configuration
        config_summary = {
            "rate_limit_per_minute": SECURITY_CONFIG.RATE_LIMIT_REQUESTS_PER_MINUTE,
            "max_file_size": SECURITY_CONFIG.MAX_FILE_SIZE_BYTES,
            "allowed_extensions": list(SECURITY_CONFIG.ALLOWED_FILE_EXTENSIONS),
            "api_key_required": SECURITY_CONFIG.API_KEY_REQUIRED
        }
        
        return {
            "status": "secure",
            "rate_limiting": rate_limit_stats,
            "threat_detection": threat_stats,
            "configuration": config_summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        log_error("get_security_status", "Failed to get security status", str(e), feature="security")
        raise HTTPException(status_code=500, detail="Failed to get security status")

@app.get("/security/threats")
async def get_recent_threats():
    """Get recent security threats and suspicious activity"""
    try:
        # Get recent threats from threat detector
        recent_threats = []
        for ip, threat_times in SECURITY_MIDDLEWARE.threat_detector.threat_history.items():
            recent_threats.append({
                "ip": ip,
                "threat_count": len(threat_times),
                "last_threat": max(threat_times).isoformat() if threat_times else None,
                "is_suspicious": ip in SECURITY_MIDDLEWARE.threat_detector.suspicious_ips
            })
        
        # Sort by threat count
        recent_threats.sort(key=lambda x: x["threat_count"], reverse=True)
        
        return {
            "recent_threats": recent_threats[:20],  # Top 20
            "suspicious_ips": list(SECURITY_MIDDLEWARE.threat_detector.suspicious_ips),
            "blocked_ips": list(SECURITY_MIDDLEWARE.rate_limiter.blocked_ips),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        log_error("get_recent_threats", "Failed to get recent threats", str(e), feature="security")
        raise HTTPException(status_code=500, detail="Failed to get recent threats")

@app.post("/security/block-ip/{ip_address}")
async def block_ip_address(ip_address: str):
    """Block an IP address (admin function)"""
    try:
        # Validate IP address
        if not SECURITY_VALIDATOR.validate_ip_address(ip_address):
            raise HTTPException(status_code=400, detail="Invalid IP address")
        
        # Add to blocked IPs
        SECURITY_MIDDLEWARE.rate_limiter.blocked_ips.add(ip_address)
        
        SECURITY_MONITOR.log_security_event(
            "ip_blocked", 
            f"IP {ip_address} manually blocked", 
            ip_address
        )
        
        return {"message": f"IP {ip_address} blocked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("block_ip_address", "Failed to block IP", str(e), feature="security")
        raise HTTPException(status_code=500, detail="Failed to block IP")

@app.post("/security/unblock-ip/{ip_address}")
async def unblock_ip_address(ip_address: str):
    """Unblock an IP address (admin function)"""
    try:
        # Validate IP address
        if not SECURITY_VALIDATOR.validate_ip_address(ip_address):
            raise HTTPException(status_code=400, detail="Invalid IP address")
        
        # Remove from blocked IPs
        if ip_address in SECURITY_MIDDLEWARE.rate_limiter.blocked_ips:
            SECURITY_MIDDLEWARE.rate_limiter.blocked_ips.remove(ip_address)
        
        # Remove from blocked_until
        if ip_address in SECURITY_MIDDLEWARE.rate_limiter.blocked_until:
            del SECURITY_MIDDLEWARE.rate_limiter.blocked_until[ip_address]
        
        SECURITY_MONITOR.log_security_event(
            "ip_unblocked", 
            f"IP {ip_address} manually unblocked", 
            ip_address
        )
        
        return {"message": f"IP {ip_address} unblocked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        log_error("unblock_ip_address", "Failed to unblock IP", str(e), feature="security")
        raise HTTPException(status_code=500, detail="Failed to unblock IP")

@app.get("/security/validate-input")
async def validate_security_input(text: str):
    """Validate and sanitize input for security testing"""
    try:
        # Sanitize input
        sanitized = sanitize_input(text)
        
        # Detect threats
        threats = SECURITY_MONITOR.detect_threats(text)
        
        return {
            "original": text,
            "sanitized": sanitized,
            "threats_detected": threats,
            "is_safe": len(threats) == 0
        }
        
    except Exception as e:
        log_error("validate_security_input", "Failed to validate input", str(e), feature="security")
        raise HTTPException(status_code=500, detail="Failed to validate input")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with logging"""
    log_warning("exception_handler", f"HTTP {exc.status_code}", exc.detail, feature="error_handling")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with security considerations"""
    log_exception("exception_handler", "Unexpected error", str(exc), feature="error_handling")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    return response

# Application startup and shutdown are now handled by the lifespan manager

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000) 