# Docker Setup for LlamalyticsHub

This document provides comprehensive instructions for running LlamalyticsHub using Docker and Docker Compose.

## Quick Start

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- At least 8GB RAM (for Ollama model)
- 10GB free disk space

### Basic Setup

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

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# Ollama Configuration
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=codellama:7b
OLLAMA_LOG_FILE=/app/logs/ollama_server.log

# Application Settings
FLASK_ENV=production
FLASK_APP=http_api.py

# Security - REQUIRED for production
OLLAMA_API_KEY=your_secure_api_key_here
GITHUB_TOKEN=your_github_token_here

# Server Configuration (optional)
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120
```

### Security Considerations

1. **API Keys and Tokens:**
   - Never commit `.env` files to version control
   - Use strong, unique API keys
   - Rotate tokens regularly
   - Use environment variables in production

2. **Network Security:**
   - The application runs on internal Docker network
   - Only port 5000 is exposed by default
   - Use reverse proxy (nginx) for production

3. **File Upload Security:**
   - File size limit: 2MB
   - Allowed extensions: `.txt`, `.py`, `.js`, `.java`, `.cpp`, `.c`, `.h`, `.md`, `.json`, `.xml`, `.yaml`, `.yml`
   - Path traversal protection enabled

## Service Architecture

### Services

1. **Ollama Service** (`ollama`)
   - Runs the Ollama LLM server
   - Exposes port 11434
   - Uses persistent volume for model storage
   - Health checks enabled

2. **Application Service** (`app`)
   - Runs the Flask API
   - Exposes port 5000
   - Uses Gunicorn for production
   - Depends on Ollama service

3. **Nginx Service** (`nginx`) - Optional
   - Reverse proxy with SSL
   - Rate limiting
   - Security headers
   - Load balancing

### Volumes

- `ollama_data`: Ollama model storage
- `app_logs`: Application logs
- `app_reports`: Generated reports
- `app_cache`: LLM analysis cache

## Development Setup

### Development Mode

For development with live reload:

```bash
# Use development compose file
docker-compose -f docker-compose.dev.yml up -d

# View development logs
docker-compose -f docker-compose.dev.yml logs -f app
```

### Development Features

- Source code mounted for live reload
- Flask development server
- Hot reload enabled
- Debug mode active

## Production Deployment

### With Nginx Reverse Proxy

1. **Generate SSL certificates:**
   ```bash
   mkdir ssl
   # Add your SSL certificates to ssl/ directory
   # cert.pem and key.pem
   ```

2. **Start with proxy:**
   ```bash
   docker-compose --profile proxy up -d
   ```

3. **Access via HTTPS:**
   - Application: https://your-domain/
   - API: https://your-domain/api/

### Without Nginx

```bash
# Direct access to Flask app
docker-compose up -d
```

Access at: http://your-domain:5000

## Health Checks

### Application Health

```bash
# Check application health
curl http://localhost:5000/health

# Expected response:
{
  "status": "ok",
  "llm_reply": "pong"
}
```

### Ollama Health

```bash
# Check Ollama health
curl http://localhost:11434/api/tags

# Expected response:
{
  "models": [
    {
      "name": "codellama:7b",
      "modified_at": "2024-01-01T00:00:00Z",
      "size": 1234567890
    }
  ]
}
```

## Troubleshooting

### Common Issues

1. **Out of Memory:**
   ```bash
   # Check memory usage
   docker stats
   
   # Increase Docker memory limit
   # In Docker Desktop: Settings > Resources > Memory
   ```

2. **Model Not Found:**
   ```bash
   # Pull the model manually
   docker-compose exec ollama ollama pull codellama:7b
   ```

3. **Port Already in Use:**
   ```bash
   # Check what's using the port
   lsof -i :5000
   
   # Change port in docker-compose.yml
   ports:
     - "5001:5000"  # Use port 5001 instead
   ```

4. **Permission Issues:**
   ```bash
   # Fix volume permissions
   sudo chown -R $USER:$USER ./logs ./reports
   ```

### Logs

```bash
# View all logs
docker-compose logs

# View specific service logs
docker-compose logs app
docker-compose logs ollama

# Follow logs in real-time
docker-compose logs -f
```

### Debugging

```bash
# Access container shell
docker-compose exec app /bin/bash

# Check environment variables
docker-compose exec app env

# Test Ollama connection
docker-compose exec app curl http://ollama:11434/api/tags
```

## Performance Tuning

### Resource Limits

Edit `docker-compose.yml` to set resource limits:

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
```

### Gunicorn Configuration

Adjust workers and threads based on your system:

```yaml
environment:
  - GUNICORN_WORKERS=4    # Number of worker processes
  - GUNICORN_THREADS=8    # Threads per worker
  - GUNICORN_TIMEOUT=300  # Request timeout in seconds
```

### Ollama Configuration

For better performance with large models:

```yaml
services:
  ollama:
    environment:
      - OLLAMA_HOST=0.0.0.0
      - OLLAMA_ORIGINS=*
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4.0'
```

## Security Hardening

### Network Security

1. **Use internal networks only:**
   ```yaml
   networks:
     llamalytics-network:
       driver: bridge
       internal: true  # No external access
   ```

2. **Limit exposed ports:**
   ```yaml
   # Only expose necessary ports
   ports:
     - "127.0.0.1:5000:5000"  # Localhost only
   ```

### Container Security

1. **Run as non-root user** (already configured)
2. **Use read-only filesystem where possible**
3. **Limit container capabilities**
4. **Scan images regularly**

### API Security

1. **Enable authentication:**
   ```bash
   # Set strong API key
   OLLAMA_API_KEY=your_very_secure_key_here
   ```

2. **Use HTTPS in production**
3. **Implement rate limiting** (already configured)
4. **Validate all inputs** (already implemented)

## Monitoring

### Metrics

```bash
# Container resource usage
docker stats

# Service status
docker-compose ps

# Health check
curl http://localhost:5000/health
```

### Logging

Logs are automatically rotated and compressed:
- Location: `/app/logs/ollama_server.log`
- Rotation: 10MB
- Retention: 10 days
- Compression: ZIP

## Backup and Recovery

### Backup Strategy

1. **Configuration:**
   ```bash
   # Backup environment file
   cp .env .env.backup
   ```

2. **Data:**
   ```bash
   # Backup volumes
   docker run --rm -v llamalyticshub_ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama_data.tar.gz -C /data .
   ```

3. **Reports:**
   ```bash
   # Backup reports
   tar czf reports_backup.tar.gz reports/
   ```

### Recovery

1. **Restore configuration:**
   ```bash
   cp .env.backup .env
   ```

2. **Restore data:**
   ```bash
   docker run --rm -v llamalyticshub_ollama_data:/data -v $(pwd):/backup alpine tar xzf /backup/ollama_data.tar.gz -C /data
   ```

3. **Restart services:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

## Scaling

### Horizontal Scaling

For high availability, consider:

1. **Load balancer** (nginx/haproxy)
2. **Multiple app instances**
3. **Database for state** (Redis/PostgreSQL)
4. **Shared storage** (NFS/S3)

### Vertical Scaling

1. **Increase container resources**
2. **Optimize Gunicorn settings**
3. **Use larger Ollama models**
4. **Add caching layer**

## Maintenance

### Regular Tasks

1. **Update images:**
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

2. **Clean up:**
   ```bash
   docker system prune -f
   docker volume prune -f
   ```

3. **Monitor logs:**
   ```bash
   docker-compose logs --tail=100
   ```

### Updates

1. **Application updates:**
   ```bash
   git pull
   docker-compose build
   docker-compose up -d
   ```

2. **Ollama model updates:**
   ```bash
   docker-compose exec ollama ollama pull codellama:7b
   ```

## Support

For issues and questions:

1. Check the logs: `docker-compose logs`
2. Verify configuration: `docker-compose config`
3. Test connectivity: `curl http://localhost:5000/health`
4. Check resources: `docker stats`

## License

This Docker setup is part of the LlamalyticsHub project and follows the same license terms. 