"""
Security Configuration Module for LlamalyticsHub
Provides centralized security settings and advanced security features.
"""

import os
import hashlib
import secrets
import re
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import ipaddress
from loguru import logger

@dataclass
class SecurityConfig:
    """Centralized security configuration"""
    
    # Rate limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_BURST_SIZE: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    
    # File upload security
    MAX_FILE_SIZE_BYTES: int = 2 * 1024 * 1024  # 2MB
    ALLOWED_FILE_EXTENSIONS: Set[str] = None
    MAX_FILENAME_LENGTH: int = 255
    BLOCKED_FILENAME_PATTERNS: List[str] = None
    
    # Input validation
    MAX_INPUT_LENGTH: int = 10000
    MAX_PROMPT_LENGTH: int = 5000
    ALLOWED_CHARACTERS: str = None
    
    # Session security
    SESSION_TIMEOUT_SECONDS: int = 3600  # 1 hour
    MAX_SESSIONS_PER_IP: int = 5
    
    # IP filtering
    ALLOWED_IPS: Set[str] = None
    BLOCKED_IPS: Set[str] = None
    ALLOWED_CIDR_RANGES: List[str] = None
    
    # API security
    API_KEY_REQUIRED: bool = True
    API_KEY_LENGTH: int = 32
    API_KEY_ALPHABET: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    
    # Logging security
    LOG_SENSITIVE_DATA: bool = False
    LOG_IP_ADDRESSES: bool = True
    LOG_USER_AGENTS: bool = True
    MAX_LOG_ENTRIES: int = 1000
    
    # Content security
    CONTENT_SECURITY_POLICY: str = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    STRICT_TRANSPORT_SECURITY: str = "max-age=31536000; includeSubDomains; preload"
    
    def __post_init__(self):
        """Initialize default values"""
        if self.ALLOWED_FILE_EXTENSIONS is None:
            self.ALLOWED_FILE_EXTENSIONS = {
                '.txt', '.py', '.js', '.java', '.cpp', '.c', '.h', 
                '.md', '.json', '.xml', '.yaml', '.yml', '.html', '.css'
            }
        
        if self.BLOCKED_FILENAME_PATTERNS is None:
            self.BLOCKED_FILENAME_PATTERNS = [
                r'\.\.',  # Path traversal
                r'[<>:"|?*]',  # Invalid characters
                r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$',  # Reserved names (case insensitive)
                r'\.(exe|bat|cmd|com|pif|scr|vbs|js)$',  # Executable files
            ]
        
        if self.ALLOWED_CHARACTERS is None:
            self.ALLOWED_CHARACTERS = (
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789!@#$%^&*()_+-=[]{}|;':\",./<>? "
            )

class SecurityValidator:
    """Advanced security validation and sanitization"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for validation"""
        self.blocked_filename_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.config.BLOCKED_FILENAME_PATTERNS
        ]
    
    def validate_ip_address(self, ip: str) -> bool:
        """Validate and check IP address against allow/block lists"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            
            # Check blocked IPs
            if self.config.BLOCKED_IPS and ip in self.config.BLOCKED_IPS:
                return False
            
            # Check allowed IPs (if specified)
            if self.config.ALLOWED_IPS:
                return ip in self.config.ALLOWED_IPS
            
            # Check CIDR ranges
            if self.config.ALLOWED_CIDR_RANGES:
                for cidr in self.config.ALLOWED_CIDR_RANGES:
                    if ip_obj in ipaddress.ip_network(cidr):
                        return True
                return False
            
            return True
            
        except ValueError:
            return False
    
    def validate_filename(self, filename: str) -> tuple[bool, str]:
        """Validate filename for security"""
        if not filename:
            return False, "No filename provided"
        
        if len(filename) > self.config.MAX_FILENAME_LENGTH:
            return False, f"Filename too long (max {self.config.MAX_FILENAME_LENGTH})"
        
        # Check for blocked patterns
        for pattern in self.blocked_filename_patterns:
            if pattern.search(filename):
                return False, f"File type not allowed"
        
        # Check file extension
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in self.config.ALLOWED_FILE_EXTENSIONS:
            return False, f"File type {file_ext} not allowed"
        
        return True, "OK"
    
    def sanitize_input(self, text: str, max_length: Optional[int] = None) -> str:
        """Advanced input sanitization"""
        if not text:
            return ""
        
        # Remove null bytes and control characters
        text = text.replace('\x00', '')
        text = ''.join(char for char in text if char.isprintable() or char in '\n\t')
        
        # Apply length limit
        max_len = max_length or self.config.MAX_INPUT_LENGTH
        if len(text) > max_len:
            text = text[:max_len]
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<script>', 'javascript:', 'data:', 'vbscript:']
        for char in dangerous_chars:
            text = text.replace(char, '')
        
        return text.strip()
    
    def validate_content(self, content: bytes) -> tuple[bool, str]:
        """Validate file content for security"""
        if len(content) > self.config.MAX_FILE_SIZE_BYTES:
            return False, f"File too large (max {self.config.MAX_FILE_SIZE_BYTES} bytes)"
        
        # Check for executable content
        executable_signatures = [
            b'MZ',  # Windows executable
            b'\x7fELF',  # Linux executable
            b'\xfe\xed\xfa',  # Mach-O executable
        ]
        
        for sig in executable_signatures:
            if content.startswith(sig):
                return False, "File appears to be executable"
        
        # Check for null bytes (potential binary content)
        if b'\x00' in content:
            return False, "File contains null bytes"
        
        return True, "OK"
    
    def generate_secure_token(self) -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(self.config.API_KEY_LENGTH)
    
    def hash_sensitive_data(self, data: str) -> str:
        """Hash sensitive data for logging"""
        return hashlib.sha256(data.encode()).hexdigest()[:16]

class SecurityMonitor:
    """Advanced security monitoring and threat detection"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.threat_patterns = {
            'sql_injection': [
                r'(\b(union|select|insert|update|delete|drop|create|alter)\b)',
                r'(\b(or|and)\s+\d+\s*=\s*\d+)',
                r'(\b(union|select).*?\b(from|where)\b)',
            ],
            'xss_attack': [
                r'<script[^>]*>.*?</script>',
                r'javascript:',
                r'on\w+\s*=',
                r'<iframe[^>]*>',
            ],
            'path_traversal': [
                r'\.\./',
                r'\.\.\\',
                r'%2e%2e%2f',
                r'%2e%2e%5c',
            ],
            'command_injection': [
                r'(\b(cat|ls|pwd|whoami|id|uname)\b)',
                r'(\b(rm|del|format|fdisk)\b)',
                r'(\b(netcat|nc|telnet|ssh|ftp)\b)',
            ]
        }
        self._compile_threat_patterns()
    
    def _compile_threat_patterns(self):
        """Compile threat detection patterns"""
        self.compiled_patterns = {}
        for threat_type, patterns in self.threat_patterns.items():
            self.compiled_patterns[threat_type] = [
                re.compile(pattern, re.IGNORECASE) 
                for pattern in patterns
            ]
    
    def detect_threats(self, input_data: str) -> Dict[str, List[str]]:
        """Detect potential security threats in input data"""
        threats = {}
        
        for threat_type, patterns in self.compiled_patterns.items():
            detected = []
            for pattern in patterns:
                matches = pattern.findall(input_data)
                if matches:
                    detected.extend(matches)
            
            if detected:
                threats[threat_type] = detected
        
        return threats
    
    def log_security_event(self, event_type: str, details: str, ip: str = None, user_agent: str = None):
        """Log security events with appropriate detail level"""
        context = []
        
        if ip and self.config.LOG_IP_ADDRESSES:
            context.append(f"IP: {ip}")
        
        if user_agent and self.config.LOG_USER_AGENTS:
            context.append(f"UA: {user_agent[:100]}")
        
        context_str = " | ".join(context) if context else ""
        
        if event_type in ['threat_detected', 'rate_limit_exceeded', 'authentication_failed']:
            logger.warning(f"SECURITY_EVENT: {event_type} | {details} | {context_str}")
        else:
            logger.info(f"SECURITY_EVENT: {event_type} | {details} | {context_str}")

class SecurityHeaders:
    """Advanced security headers management"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
    
    def get_security_headers(self) -> Dict[str, str]:
        """Get comprehensive security headers"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": self.config.STRICT_TRANSPORT_SECURITY,
            "Content-Security-Policy": self.config.CONTENT_SECURITY_POLICY,
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "X-Permitted-Cross-Domain-Policies": "none",
            "Cross-Origin-Embedder-Policy": "require-corp",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin",
        }

# Global security configuration
SECURITY_CONFIG = SecurityConfig()

# Initialize security components
SECURITY_VALIDATOR = SecurityValidator(SECURITY_CONFIG)
SECURITY_MONITOR = SecurityMonitor(SECURITY_CONFIG)
SECURITY_HEADERS = SecurityHeaders(SECURITY_CONFIG)

def get_security_config() -> SecurityConfig:
    """Get the global security configuration"""
    return SECURITY_CONFIG

def get_security_validator() -> SecurityValidator:
    """Get the global security validator"""
    return SECURITY_VALIDATOR

def get_security_monitor() -> SecurityMonitor:
    """Get the global security monitor"""
    return SECURITY_MONITOR

def get_security_headers() -> SecurityHeaders:
    """Get the global security headers manager"""
    return SECURITY_HEADERS 