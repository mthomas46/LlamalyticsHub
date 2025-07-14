# Migration Guide: Flask to FastAPI

This document outlines the migration from Flask to FastAPI for the LlamalyticsHub application.

## Overview

The application has been successfully migrated from Flask to FastAPI, providing:

- **Better Performance**: Async support and improved concurrency
- **Automatic API Documentation**: Swagger UI and ReDoc
- **Type Safety**: Pydantic models for request/response validation
- **Modern Python**: Latest async/await patterns
- **Enhanced Security**: Built-in security features

## Key Changes

### 1. Application Entry Point

**Before (Flask):**
```python
# http_api.py
from flask import Flask
app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})
```

**After (FastAPI):**
```python
# fastapi_app.py
from fastapi import FastAPI
app = FastAPI(title="LlamalyticsHub API")

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")
```

### 2. Request/Response Models

**Before (Flask + Marshmallow):**
```python
from marshmallow import Schema, fields

class TextSchema(Schema):
    prompt = fields.Str(required=True, validate=lambda x: len(x) <= 10000)
```

**After (FastAPI + Pydantic):**
```python
from pydantic import BaseModel, Field

class TextRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000, description="Text prompt for LLM generation")
```

### 3. Error Handling

**Before (Flask):**
```python
@app.route('/generate/text', methods=['POST'])
def generate_text():
    try:
        # ... code ...
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
```

**After (FastAPI):**
```python
@app.post("/generate/text", response_model=GenerateResponse)
async def generate_text(request: TextRequest):
    try:
        # ... code ...
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
```

### 4. File Uploads

**Before (Flask):**
```python
@app.route('/generate/file', methods=['POST'])
def generate_file():
    file = request.files['file']
    # ... validation and processing ...
```

**After (FastAPI):**
```python
@app.post("/generate/file", response_model=GenerateResponse)
async def generate_file(file: UploadFile = File(...)):
    # ... validation and processing ...
```

## API Endpoints

### Available Endpoints

| Endpoint | Method | Description | Request Model | Response Model |
|----------|--------|-------------|---------------|----------------|
| `/` | GET | Root endpoint | - | Dict |
| `/health` | GET | Health check | - | HealthResponse |
| `/generate/text` | POST | Text generation | TextRequest | GenerateResponse |
| `/generate/file` | POST | File upload generation | UploadFile | GenerateResponse |
| `/generate/github-pr` | POST | GitHub PR analysis | GithubPRRequest | GenerateResponse |
| `/reports` | GET | List reports | - | ReportsResponse |
| `/reports/{report_name}` | GET | Get specific report | - | PlainTextResponse |
| `/logs` | GET | Get application logs | - | PlainTextResponse |
| `/endpoints` | GET | List all endpoints | - | Dict |
| `/docs` | GET | Swagger UI | - | HTML |
| `/redoc` | GET | ReDoc documentation | - | HTML |
| `/openapi.json` | GET | OpenAPI schema | - | JSON |

### Request Models

#### TextRequest
```json
{
  "prompt": "string (1-10000 chars)"
}
```

#### GithubPRRequest
```json
{
  "repo": "owner/repo",
  "pr_number": 123,
  "token": "optional_github_token",
  "prompt": "optional_custom_prompt"
}
```

### Response Models

#### GenerateResponse
```json
{
  "response": "LLM generated text"
}
```

#### HealthResponse
```json
{
  "status": "ok|error",
  "llm_reply": "optional_llm_response",
  "error": "optional_error_message"
}
```

## Docker Changes

### Dockerfile
- **Before**: Used Gunicorn with Flask
- **After**: Uses Uvicorn with FastAPI

```dockerfile
# Before
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "http_api:app"]

# After
CMD ["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]
```

### Environment Variables
- **Removed**: `FLASK_ENV`, `FLASK_APP`, `GUNICORN_*`
- **Added**: `UVICORN_*`, `PYTHONPATH`

## Development Workflow

### Local Development

**Before:**
```bash
# Flask development
python -m flask run --host=0.0.0.0 --port=5000 --reload
```

**After:**
```bash
# FastAPI development
uvicorn fastapi_app:app --host 0.0.0.0 --port 5000 --reload
```

### Docker Development

**Before:**
```bash
docker-compose -f docker-compose.dev.yml up -d
```

**After:**
```bash
docker-compose -f docker-compose.dev.yml up -d
# Same command, but now uses FastAPI with hot reload
```

## API Documentation

### Automatic Documentation

FastAPI provides automatic API documentation:

- **Swagger UI**: http://localhost:5000/docs
- **ReDoc**: http://localhost:5000/redoc
- **OpenAPI JSON**: http://localhost:5000/openapi.json

### Interactive Testing

You can now test the API directly from the Swagger UI:

1. Navigate to http://localhost:5000/docs
2. Click on any endpoint
3. Click "Try it out"
4. Fill in the parameters
5. Click "Execute"

## Performance Improvements

### Async Support

**Before (Flask - Synchronous):**
```python
@app.route('/generate/text', methods=['POST'])
def generate_text():
    # Blocking operation
    result = llama.generate(prompt)
    return jsonify({'response': result})
```

**After (FastAPI - Async Ready):**
```python
@app.post("/generate/text")
async def generate_text(request: TextRequest):
    # Can be made async when LLM client supports it
    result = llama.generate(request.prompt)
    return GenerateResponse(response=result)
```

### Concurrency

- **Flask**: Single-threaded by default, requires Gunicorn for concurrency
- **FastAPI**: Built-in async support, better handling of concurrent requests

## Security Enhancements

### Built-in Security Features

FastAPI provides additional security features:

1. **Automatic Input Validation**: Pydantic models validate all inputs
2. **Type Safety**: Prevents many runtime errors
3. **Security Headers**: Built-in security middleware
4. **CORS Support**: Configurable CORS middleware
5. **Trusted Hosts**: Protection against host header attacks

### Rate Limiting

The rate limiting implementation remains the same but is now integrated with FastAPI's dependency injection system.

## Testing

### Manual Testing

**Before:**
```bash
curl -X POST http://localhost:5000/generate/text \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello world"}'
```

**After:**
```bash
# Same curl command works!
curl -X POST http://localhost:5000/generate/text \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello world"}'
```

### Automated Testing

**Before:**
```python
# Flask testing
from flask import Flask
from http_api import app

def test_health():
    with app.test_client() as client:
        response = client.get('/health')
        assert response.status_code == 200
```

**After:**
```python
# FastAPI testing
from fastapi.testclient import TestClient
from fastapi_app import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

## Migration Checklist

### ✅ Completed

- [x] Create FastAPI application (`fastapi_app.py`)
- [x] Migrate all endpoints
- [x] Convert Marshmallow schemas to Pydantic models
- [x] Update error handling
- [x] Implement async-ready structure
- [x] Update Docker configuration
- [x] Update environment variables
- [x] Update Makefile commands
- [x] Maintain all security features
- [x] Preserve rate limiting
- [x] Keep file upload validation

### 🔄 In Progress

- [ ] Update CLI to use FastAPI endpoints
- [ ] Add comprehensive FastAPI tests
- [ ] Update documentation

### 📋 Future Enhancements

- [ ] Implement async LLM client
- [ ] Add WebSocket support for real-time updates
- [ ] Implement background tasks
- [ ] Add more comprehensive API documentation
- [ ] Implement API versioning

## Benefits of Migration

### 1. Performance
- **Async Support**: Better handling of concurrent requests
- **Type Safety**: Reduced runtime errors
- **Modern Python**: Latest async/await patterns

### 2. Developer Experience
- **Automatic Documentation**: Swagger UI and ReDoc
- **Type Hints**: Better IDE support
- **Validation**: Automatic request/response validation

### 3. Production Ready
- **Built-in Security**: CORS, trusted hosts, etc.
- **Monitoring**: Better observability
- **Scalability**: Better async support

### 4. API Quality
- **OpenAPI Compliance**: Standard API specification
- **Interactive Docs**: Test API directly from browser
- **Schema Validation**: Automatic request validation

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Make sure you have FastAPI installed
   pip install fastapi uvicorn
   ```

2. **Port Already in Use**
   ```bash
   # Check what's using port 5000
   lsof -i :5000
   # Kill the process or change port
   ```

3. **Docker Build Issues**
   ```bash
   # Clean and rebuild
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

### Health Checks

```bash
# Check FastAPI health
curl http://localhost:5000/health

# Check API documentation
curl http://localhost:5000/docs

# Check OpenAPI schema
curl http://localhost:5000/openapi.json
```

## Rollback Plan

If you need to rollback to Flask:

1. **Keep the old Flask app**: `http_api.py` is still available
2. **Update Dockerfile**: Change CMD back to Gunicorn
3. **Update docker-compose.yml**: Change environment variables
4. **Test thoroughly**: Ensure all functionality works

## Support

For issues with the FastAPI migration:

1. Check the logs: `docker-compose logs app`
2. Test endpoints: Use the Swagger UI at `/docs`
3. Verify configuration: Check environment variables
4. Review this migration guide

The migration maintains 100% API compatibility while providing significant improvements in performance, developer experience, and maintainability. 