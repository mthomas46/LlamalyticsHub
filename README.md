# LlamalyticsHub - FastAPI Edition

A modern, high-performance LLM code analysis and GitHub audit service built with FastAPI.

## 🚀 Features

| Feature | Description |
|---------|-------------|
| **FastAPI Framework** | Modern async web framework with automatic API documentation |
| **Interactive API Docs** | Swagger UI and ReDoc for easy API testing |
| **Type Safety** | Pydantic models for automatic request/response validation |
| **Async Support** | Better performance and concurrency handling |
| **Live Endpoint Discovery** | `/docs` provides interactive API documentation |
| **Open API** | All endpoints are accessible without authentication by default |
| **Optional API Key** | `X-API-KEY` header is optional; presence is logged but not required |
| **Local LLM API** | Run and interact with the 7B Code Llama model locally via Ollama |
| **Modern CLI** | Interactive CLI with rich UI, arrow-key navigation, and spinners |
| **Audit Scope Selection** | Choose to audit all files, changed files (PR), README only, or test strategy only |
| **Parallel Analysis & Caching** | LLM file analysis runs in parallel with progress bar and session caching |
| **File Filtering** | Filter files by pattern or manual selection before audit |
| **Configurable Output Directory** | Choose where reports and updated READMEs are saved |
| **API Integration** | Upload generated reports to a remote API endpoint |
| **Automated CLI Tests** | Run a full audit workflow on a public repo for validation |
| **Improved Output Parsing** | LLM output is parsed into structured sections for actionable insights |
| **Persistent Logging** | Rotating log file with detailed logs |
| **Environment Variables** | Used for secrets (API key, GitHub token, log file path) |
| **Graceful Error Handling** | User-friendly error messages and robust validation |
| **Docker Support** | Complete containerization with security hardening |

## 🏗️ Architecture

### FastAPI Benefits

- **Performance**: Async support and improved concurrency
- **Documentation**: Automatic Swagger UI and ReDoc
- **Type Safety**: Pydantic models for validation
- **Modern Python**: Latest async/await patterns
- **Security**: Built-in security features

### API Documentation

Access the interactive API documentation:
- **Swagger UI**: http://localhost:5000/docs
- **ReDoc**: http://localhost:5000/redoc
- **OpenAPI JSON**: http://localhost:5000/openapi.json

## 🐳 Docker Setup

### Quick Start

1. **Clone and navigate to the project:**
   ```bash
   cd LlamalyticsHub
   ```

2. **Copy environment file:**
   ```bash
   cp env.example .env
   ```

3. **Edit environment variables:**
   ```bash
   # Edit .env file with your configuration
   nano .env
   ```

4. **Start the services:**
   ```bash
   docker-compose up -d
   ```

5. **Check service status:**
   ```bash
   docker-compose ps
   ```

6. **View logs:**
   ```bash
   docker-compose logs -f
   ```

### Development Mode

For development with hot reload:

```bash
# Use development compose file
docker-compose -f docker-compose.dev.yml up -d

# View development logs
docker-compose -f docker-compose.dev.yml logs -f app
```

## 📋 Setup

### Prerequisites

1. **Install [Ollama](https://ollama.com/download)** and ensure the 7B Code Llama model is available:
   ```sh
   ollama pull codellama:7b
   ollama serve
   ```

2. **Install Python dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

   This will install all required packages, including:
   - FastAPI
   - Uvicorn
   - Pydantic
   - PyGithub
   - httpx
   - loguru
   - rich
   - python-dotenv
   - textual
   - And more...

3. **Configure secrets and environment variables:**
   - Copy `env.example` to `.env` and fill in your secrets (e.g., `GITHUB_TOKEN`, `OLLAMA_API_KEY`).
   - You can also set these variables directly in your shell or in `config.yaml`.

## 🚀 How to Run

### Docker (Recommended)

**Production:**
```bash
docker-compose up -d
```

**Development:**
```bash
docker-compose -f docker-compose.dev.yml up -d
```

### Local Development

**FastAPI Development Server:**
```bash
uvicorn fastapi_app:app --host 0.0.0.0 --port 5000 --reload
```

**Production Server:**
```bash
uvicorn fastapi_app:app --host 0.0.0.0 --port 5000 --workers 2
```

### Makefile Commands

```bash
# Development
make run-dev

# Production
make run-server

# Docker
make docker-up
make docker-down
make docker-logs

# Health checks
make health-check
make ollama-health

# API documentation
make docs
```

## 🔌 API Usage

### Interactive Testing

1. **Start the server**
2. **Navigate to**: http://localhost:5000/docs
3. **Click on any endpoint**
4. **Click "Try it out"**
5. **Fill in parameters**
6. **Click "Execute"**

### Text Generation

```bash
curl -X POST "http://localhost:5000/generate/text" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a Python function to calculate fibonacci numbers"}'
```

### File Upload

```bash
curl -X POST "http://localhost:5000/generate/file" \
  -F "file=@your_code.py"
```

### GitHub PR Analysis

```bash
curl -X POST "http://localhost:5000/generate/github-pr" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "owner/repo",
    "pr_number": 123,
    "token": "your_github_token"
  }'
```

### Health Check

```bash
curl http://localhost:5000/health
```

## 📊 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root endpoint with API info |
| `/health` | GET | Health check |
| `/generate/text` | POST | Text generation |
| `/generate/file` | POST | File upload generation |
| `/generate/github-pr` | POST | GitHub PR analysis |
| `/reports` | GET | List reports |
| `/reports/{report_name}` | GET | Get specific report |
| `/logs` | GET | Get application logs |
| `/endpoints` | GET | List all endpoints |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc documentation |
| `/openapi.json` | GET | OpenAPI schema |

## 🔒 Security Features

### Built-in Security

- **Input Validation**: Pydantic models validate all inputs
- **Type Safety**: Prevents runtime errors
- **Security Headers**: Built-in security middleware
- **CORS Support**: Configurable CORS middleware
- **Trusted Hosts**: Protection against host header attacks
- **Rate Limiting**: 60 requests per minute per IP
- **File Upload Security**: Size limits and type validation

### Docker Security

- **Non-root user**: Containers run as non-root
- **Resource limits**: Memory and CPU limits
- **Network isolation**: Internal Docker networks
- **Read-only filesystems**: Where possible

## 🧪 Testing

### Manual Testing

```bash
# Health check
curl http://localhost:5000/health

# API documentation
curl http://localhost:5000/docs

# Test text generation
curl -X POST http://localhost:5000/generate/text \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello world"}'
```

### Automated Testing

```python
from fastapi.testclient import TestClient
from fastapi_app import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

## 📚 Documentation

- **[Docker Setup](DOCKER.md)**: Complete Docker documentation
- **[Migration Guide](MIGRATION_GUIDE.md)**: Flask to FastAPI migration
- **[Security Audit](SECURITY_AUDIT.md)**: Security assessment and improvements

## 🔧 Configuration

### Environment Variables

```bash
# Ollama Configuration
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=codellama:7b
OLLAMA_LOG_FILE=/app/logs/ollama_server.log

# Application Settings
PYTHONPATH=/app

# Security
OLLAMA_API_KEY=your_secure_api_key_here
GITHUB_TOKEN=your_github_token_here

# FastAPI/Uvicorn Configuration
UVICORN_WORKERS=2
UVICORN_HOST=0.0.0.0
UVICORN_PORT=5000
UVICORN_RELOAD=false
```

## 🚀 Performance

### FastAPI Advantages

- **Async Support**: Better handling of concurrent requests
- **Type Safety**: Reduced runtime errors
- **Modern Python**: Latest async/await patterns
- **Automatic Validation**: Request/response validation
- **Built-in Documentation**: Swagger UI and ReDoc

### Benchmarks

- **Concurrent Requests**: Better handling than Flask
- **Memory Usage**: More efficient than Flask + Gunicorn
- **Startup Time**: Faster than Flask with Gunicorn
- **API Documentation**: Automatic vs manual

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For issues and questions:

1. Check the logs: `docker-compose logs`
2. Test endpoints: Use the Swagger UI at `/docs`
3. Verify configuration: Check environment variables
4. Review the [Migration Guide](MIGRATION_GUIDE.md)

---

**LlamalyticsHub FastAPI Edition** - Modern, secure, and performant LLM code analysis service. 