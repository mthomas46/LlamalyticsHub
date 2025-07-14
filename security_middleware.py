"""
Advanced Security Middleware for LlamalyticsHub
Provides comprehensive security features including threat detection, IP filtering, and monitoring.
"""

import time
import json
import hashlib
from typing import Dict, List, Optional, Set
from collections import defaultdict, deque
from datetime import datetime, timedelta
import threading
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from security_config import get_security_config, get_security_validator, get_security_monitor
import re

class AdvancedRateLimiter:
    """Advanced rate limiter with burst protection and IP-based limits"""
    
    def __init__(self):
        self.config = get_security_config()
        self.requests = defaultdict(lambda: deque())
        self.lock = threading.Lock()
        self.blocked_ips = set()
        self.blocked_until = {}
    
    def is_allowed(self, client_ip: str) -> tuple[bool, str]:
        """Check if request is allowed with detailed response"""
        now = datetime.now()
        
        with self.lock:
            # Check if IP is blocked
            if client_ip in self.blocked_ips:
                if client_ip in self.blocked_until:
                    if now < self.blocked_until[client_ip]:
                        return False, f"IP blocked until {self.blocked_until[client_ip]}"
                    else:
                        # Unblock IP
                        self.blocked_ips.remove(client_ip)
                        del self.blocked_until[client_ip]
                else:
                    return False, "IP permanently blocked"
            
            # Get request history for this IP
            requests = self.requests[client_ip]
            
            # Remove old requests outside the window
            window_start = now - timedelta(seconds=self.config.RATE_LIMIT_WINDOW_SECONDS)
            while requests and requests[0] < window_start:
                requests.popleft()
            
            # Check burst limit
            if len(requests) >= self.config.RATE_LIMIT_BURST_SIZE:
                # Block IP temporarily
                block_until = now + timedelta(minutes=5)
                self.blocked_ips.add(client_ip)
                self.blocked_until[client_ip] = block_until
                return False, f"Burst limit exceeded, blocked until {block_until}"
            
            # Check rate limit
            if len(requests) >= self.config.RATE_LIMIT_REQUESTS_PER_MINUTE:
                return False, "Rate limit exceeded"
            
            # Add current request
            requests.append(now)
            return True, "OK"
    
    def get_stats(self, client_ip: str) -> Dict:
        """Get rate limiting statistics for an IP"""
        with self.lock:
            requests = self.requests[client_ip]
            now = datetime.now()
            window_start = now - timedelta(seconds=self.config.RATE_LIMIT_WINDOW_SECONDS)
            
            # Count recent requests
            recent_requests = sum(1 for req_time in requests if req_time >= window_start)
            
            return {
                "current_requests": recent_requests,
                "limit": self.config.RATE_LIMIT_REQUESTS_PER_MINUTE,
                "burst_limit": self.config.RATE_LIMIT_BURST_SIZE,
                "is_blocked": client_ip in self.blocked_ips,
                "blocked_until": self.blocked_until.get(client_ip)
            }

class ThreatDetector:
    """Advanced threat detection and analysis"""
    
    def __init__(self):
        self.config = get_security_config()
        self.monitor = get_security_monitor()
        self.validator = get_security_validator()
        self.threat_history = defaultdict(list)
        self.suspicious_ips = set()
    
    def analyze_request(self, request: Request, client_ip: str) -> Dict:
        """Analyze request for potential threats"""
        threats = {}
        
        # Analyze headers
        headers_threats = self._analyze_headers(request.headers)
        if headers_threats:
            threats['headers'] = headers_threats
        
        # Analyze query parameters
        query_threats = self._analyze_query_params(request.query_params)
        if query_threats:
            threats['query_params'] = query_threats
        
        # Analyze user agent
        user_agent = request.headers.get("User-Agent", "")
        ua_threats = self._analyze_user_agent(user_agent)
        if ua_threats:
            threats['user_agent'] = ua_threats
        
        # Analyze path
        path_threats = self._analyze_path(request.url.path)
        if path_threats:
            threats['path'] = path_threats
        
        # Log threats if detected
        if threats:
            self._log_threats(client_ip, threats, request)
            self._update_suspicious_ips(client_ip)
        
        return threats
    
    def _analyze_headers(self, headers) -> List[str]:
        """Analyze request headers for threats"""
        threats = []
        
        # Check for suspicious headers
        suspicious_headers = {
            'X-Forwarded-For': r'(\d{1,3}\.){3}\d{1,3}',
            'X-Real-IP': r'(\d{1,3}\.){3}\d{1,3}',
            'X-Originating-IP': r'(\d{1,3}\.){3}\d{1,3}',
        }
        
        for header_name, pattern in suspicious_headers.items():
            if header_name in headers:
                value = headers[header_name]
                # Check if it looks like IP spoofing
                if len(value) > 50 or ',' in value:
                    threats.append(f"Suspicious {header_name} header")
        
        return threats
    
    def _analyze_query_params(self, query_params) -> List[str]:
        """Analyze query parameters for threats"""
        threats = []
        
        for param_name, param_value in query_params.items():
            # Check for SQL injection patterns
            sql_patterns = [
                r'(\b(union|select|insert|update|delete|drop|create|alter)\b)',
                r'(\b(or|and)\s+\d+\s*=\s*\d+)',
                r'(\b(union|select).*?\b(from|where)\b)',
            ]
            
            for pattern in sql_patterns:
                if re.search(pattern, param_value, re.IGNORECASE):
                    threats.append(f"SQL injection pattern in {param_name}")
                    break
            
            # Check for XSS patterns
            xss_patterns = [
                r'<script[^>]*>',
                r'javascript:',
                r'on\w+\s*=',
            ]
            
            for pattern in xss_patterns:
                if re.search(pattern, param_value, re.IGNORECASE):
                    threats.append(f"XSS pattern in {param_name}")
                    break
        
        return threats
    
    def _analyze_user_agent(self, user_agent: str) -> List[str]:
        """Analyze user agent for threats"""
        threats = []
        
        # Check for suspicious user agents
        suspicious_ua_patterns = [
            r'(bot|crawler|spider|scraper)',
            r'(sqlmap|nmap|nikto|w3af)',
            r'(curl|wget|python-requests)',
        ]
        
        for pattern in suspicious_ua_patterns:
            if re.search(pattern, user_agent, re.IGNORECASE):
                threats.append(f"Suspicious user agent: {user_agent[:50]}")
                break
        
        return threats
    
    def _analyze_path(self, path: str) -> List[str]:
        """Analyze request path for threats"""
        threats = []
        
        # Check for path traversal
        if '..' in path or '%2e%2e' in path:
            threats.append("Path traversal attempt")
        
        # Check for suspicious file extensions
        suspicious_extensions = ['.php', '.asp', '.jsp', '.exe', '.bat', '.cmd']
        for ext in suspicious_extensions:
            if ext in path.lower():
                threats.append(f"Suspicious file extension: {ext}")
        
        return threats
    
    def _log_threats(self, client_ip: str, threats: Dict, request: Request):
        """Log detected threats"""
        threat_summary = []
        for category, threat_list in threats.items():
            threat_summary.extend(threat_list)
        
        self.monitor.log_security_event(
            "threat_detected",
            f"Threats: {', '.join(threat_summary)}",
            client_ip,
            request.headers.get("User-Agent", "")
        )
    
    def _update_suspicious_ips(self, client_ip: str):
        """Update suspicious IP tracking"""
        self.threat_history[client_ip].append(datetime.now())
        
        # Check if IP should be marked as suspicious
        recent_threats = [
            threat_time for threat_time in self.threat_history[client_ip]
            if datetime.now() - threat_time < timedelta(hours=1)
        ]
        
        if len(recent_threats) >= 3:
            self.suspicious_ips.add(client_ip)
            logger.warning(f"IP {client_ip} marked as suspicious due to multiple threats")

class SecurityMiddleware:
    """Comprehensive security middleware"""
    
    def __init__(self):
        self.config = get_security_config()
        self.validator = get_security_validator()
        self.monitor = get_security_monitor()
        self.rate_limiter = AdvancedRateLimiter()
        self.threat_detector = ThreatDetector()
        self.request_stats = defaultdict(lambda: {
            'count': 0,
            'last_request': None,
            'errors': 0,
            'threats': 0
        })
    
    async def process_request(self, request: Request, call_next):
        """Process request with comprehensive security checks"""
        start_time = time.time()
        client_ip = await self._get_client_ip(request)
        
        # Update request statistics
        self._update_request_stats(client_ip)
        
        # Validate IP address
        if not self.validator.validate_ip_address(client_ip):
            self.monitor.log_security_event("invalid_ip", f"Invalid IP: {client_ip}", client_ip)
            return JSONResponse(
                status_code=403,
                content={"error": "Access denied"}
            )
        
        # Check rate limiting
        is_allowed, reason = self.rate_limiter.is_allowed(client_ip)
        if not is_allowed:
            self.monitor.log_security_event("rate_limit_exceeded", reason, client_ip)
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "retry_after": 60}
            )
        
        # Detect threats
        threats = self.threat_detector.analyze_request(request, client_ip)
        if threats:
            # For severe threats, block the request
            if self._is_severe_threat(threats):
                self.monitor.log_security_event("severe_threat_blocked", str(threats), client_ip)
                return JSONResponse(
                    status_code=403,
                    content={"error": "Request blocked due to security concerns"}
                )
        
        # Process request
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Add security headers
            response = self._add_security_headers(response)
            
            # Log successful request
            self._log_request_success(request, client_ip, process_time, threats)
            
            return response
            
        except Exception as e:
            # Log error
            self._log_request_error(request, client_ip, str(e))
            raise
    
    async def _get_client_ip(self, request: Request) -> str:
        """Get client IP with proxy support"""
        # Check for forwarded headers
        forwarded_headers = [
            "X-Forwarded-For",
            "X-Real-IP", 
            "X-Originating-IP",
            "CF-Connecting-IP",  # Cloudflare
            "True-Client-IP",    # Akamai
        ]
        
        for header in forwarded_headers:
            if header in request.headers:
                ip = request.headers[header].split(',')[0].strip()
                if self.validator.validate_ip_address(ip):
                    return ip
        
        # Fallback to direct IP
        return request.client.host if request.client else "unknown"
    
    def _update_request_stats(self, client_ip: str):
        """Update request statistics"""
        stats = self.request_stats[client_ip]
        stats['count'] += 1
        stats['last_request'] = datetime.now()
    
    def _is_severe_threat(self, threats: Dict) -> bool:
        """Check if threats are severe enough to block"""
        severe_patterns = [
            'sql_injection',
            'command_injection',
            'path_traversal'
        ]
        
        for category, threat_list in threats.items():
            for threat in threat_list:
                for pattern in severe_patterns:
                    if pattern in threat.lower():
                        return True
        
        return False
    
    def _add_security_headers(self, response: Response) -> Response:
        """Add comprehensive security headers"""
        security_headers = {
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
        
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response
    
    def _log_request_success(self, request: Request, client_ip: str, process_time: float, threats: Dict):
        """Log successful request with security context"""
        context = {
            "ip": client_ip,
            "method": request.method,
            "path": request.url.path,
            "process_time": f"{process_time:.3f}s",
            "threats": len(threats) if threats else 0
        }
        
        self.monitor.log_security_event(
            "request_success",
            f"{request.method} {request.url.path}",
            client_ip,
            request.headers.get("User-Agent", "")
        )
    
    def _log_request_error(self, request: Request, client_ip: str, error: str):
        """Log request error"""
        self.monitor.log_security_event(
            "request_error",
            f"Error: {error}",
            client_ip,
            request.headers.get("User-Agent", "")
        )
        
        # Update error statistics
        self.request_stats[client_ip]['errors'] += 1

# Global security middleware instance
security_middleware = SecurityMiddleware()

def get_security_middleware() -> SecurityMiddleware:
    """Get the global security middleware instance"""
    return security_middleware 