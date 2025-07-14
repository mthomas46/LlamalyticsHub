"""
Ultra-Optimized API Core Test Suite
Addresses the 31.65s bottleneck identified in performance analysis
"""
import pytest
import time
import psutil
import os
import sys
from unittest.mock import patch, MagicMock
from io import StringIO
import tempfile
import shutil

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from http_api import app
from llm.ollama_client import OllamaCodeLlama
from utils.helpers import safe_name
from config.config_manager import *

# Performance and memory baselines for test environment
PERFORMANCE_BASELINES = {
    'health_check_ms': 500,
    'text_generation_ms': 2000,
    'file_upload_ms': 1000,
    'memory_mb': 150,
    'cpu_percent': 80,
}

@pytest.fixture(scope="function")
def client():
    """Flask test client with optimized settings"""
    return app.test_client()

@pytest.fixture(scope="function")
def mock_llm_client():
    """Mock LLM client to avoid real API calls"""
    with patch('http_api.llama') as mock_llama:
        mock_llama.generate.return_value = "Mocked response"
        mock_llama.async_generate.return_value = "Mocked async response"
        yield mock_llama

@pytest.fixture(scope="function")
def temp_dir():
    """Temporary directory for file operations"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024

def get_cpu_usage():
    """Get current CPU usage percentage"""
    return psutil.cpu_percent(interval=0.1)

class TestUltraOptimizedAPICore:
    """Ultra-optimized API core functionality tests with performance monitoring"""
    
    def test_health_endpoint_performance(self, client, mock_llm_client):
        """Test health endpoint with performance monitoring"""
        start_time = time.time()
        start_memory = get_memory_usage()
        
        response = client.get("/health")
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        execution_time = (end_time - start_time) * 1000  # Convert to ms
        memory_used = end_memory - start_memory
        
        assert response.status_code == 200
        assert execution_time < PERFORMANCE_BASELINES['health_check_ms'], \
            f"Health check took {execution_time:.2f}ms, expected < {PERFORMANCE_BASELINES['health_check_ms']}ms"
        assert memory_used < PERFORMANCE_BASELINES['memory_mb'], \
            f"Memory usage increased by {memory_used:.2f}MB, expected < {PERFORMANCE_BASELINES['memory_mb']}MB"
    
    def test_text_generation_performance(self, client, mock_llm_client):
        """Test text generation endpoint with performance monitoring"""
        start_time = time.time()
        start_memory = get_memory_usage()
        
        response = client.post("/generate/text", json={"prompt": "Test prompt"})
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        execution_time = (end_time - start_time) * 1000
        memory_used = end_memory - start_memory
        
        assert response.status_code == 200
        assert execution_time < PERFORMANCE_BASELINES['text_generation_ms'], \
            f"Text generation took {execution_time:.2f}ms, expected < {PERFORMANCE_BASELINES['text_generation_ms']}ms"
        assert memory_used < PERFORMANCE_BASELINES['memory_mb'], \
            f"Memory usage increased by {memory_used:.2f}MB, expected < {PERFORMANCE_BASELINES['memory_mb']}MB"
    
    def test_file_upload_performance(self, client, temp_dir, mock_llm_client):
        """Test file upload endpoint with performance monitoring"""
        # Create a test file
        test_file_path = os.path.join(temp_dir, "test.txt")
        with open(test_file_path, "w") as f:
            f.write("Test content" * 100)  # Create some content
        
        start_time = time.time()
        start_memory = get_memory_usage()
        
        with open(test_file_path, "rb") as f:
            data = {'file': (f, 'test.txt')}
            response = client.post("/generate/file", data=data, content_type='multipart/form-data')
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        execution_time = (end_time - start_time) * 1000
        memory_used = end_memory - start_memory
        
        assert response.status_code in [200, 201]
        assert execution_time < PERFORMANCE_BASELINES['file_upload_ms'], \
            f"File upload took {execution_time:.2f}ms, expected < {PERFORMANCE_BASELINES['file_upload_ms']}ms"
        assert memory_used < PERFORMANCE_BASELINES['memory_mb'], \
            f"Memory usage increased by {memory_used:.2f}MB, expected < {PERFORMANCE_BASELINES['memory_mb']}MB"
    
    def test_concurrent_requests_performance(self, client, mock_llm_client):
        """Test concurrent request handling performance"""
        import threading
        import queue
        
        results = queue.Queue()
        start_time = time.time()
        start_memory = get_memory_usage()
        
        def make_request():
            try:
                response = client.get("/health")
                results.put(response.status_code)
            except Exception as e:
                results.put(f"Error: {e}")
        
        # Start multiple concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        execution_time = (end_time - start_time) * 1000
        memory_used = end_memory - start_memory
        
        # Check all requests succeeded
        success_count = 0
        while not results.empty():
            result = results.get()
            if result == 200:
                success_count += 1
        
        assert success_count == 5, f"Expected 5 successful requests, got {success_count}"
        assert execution_time < 2000, f"Concurrent requests took {execution_time:.2f}ms, expected < 2000ms"
        assert memory_used < PERFORMANCE_BASELINES['memory_mb'], \
            f"Memory usage increased by {memory_used:.2f}MB, expected < {PERFORMANCE_BASELINES['memory_mb']}MB"
    
    def test_memory_efficiency(self, client, mock_llm_client):
        """Test memory efficiency during multiple operations"""
        initial_memory = get_memory_usage()
        memory_readings = []
        
        # Perform multiple operations
        for i in range(10):
            response = client.get("/health")
            assert response.status_code == 200
            memory_readings.append(get_memory_usage())
        
        final_memory = get_memory_usage()
        memory_increase = final_memory - initial_memory
        
        # Check for memory leaks
        assert memory_increase < PERFORMANCE_BASELINES['memory_mb'], \
            f"Memory increased by {memory_increase:.2f}MB over 10 operations, expected < {PERFORMANCE_BASELINES['memory_mb']}MB"
        
        # Check that memory usage is relatively stable
        max_variance = max(memory_readings) - min(memory_readings)
        assert max_variance < 50, f"Memory variance was {max_variance:.2f}MB, expected < 50MB"
    
    def test_cpu_efficiency(self, client, mock_llm_client):
        """Test CPU efficiency during operations"""
        initial_cpu = get_cpu_usage()
        
        # Perform operations
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200
        
        final_cpu = get_cpu_usage()
        cpu_usage = max(initial_cpu, final_cpu)
        
        assert cpu_usage < PERFORMANCE_BASELINES['cpu_percent'], \
            f"CPU usage was {cpu_usage:.1f}%, expected < {PERFORMANCE_BASELINES['cpu_percent']}%"
    
    def test_response_time_consistency(self, client, mock_llm_client):
        """Test that response times are consistent"""
        times = []
        
        for _ in range(10):
            start_time = time.time()
            response = client.get("/health")
            end_time = time.time()
            
            assert response.status_code == 200
            times.append((end_time - start_time) * 1000)
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # Check that average time is reasonable
        assert avg_time < 200, f"Average response time was {avg_time:.2f}ms, expected < 200ms"
        
        # Check that max time isn't too much higher than average
        assert max_time < avg_time * 3, f"Max time {max_time:.2f}ms is too high compared to average {avg_time:.2f}ms"
    
    def test_error_handling_performance(self, client, mock_llm_client):
        """Test error handling performance"""
        start_time = time.time()
        start_memory = get_memory_usage()
        
        # Test with invalid input
        response = client.post("/generate/text", json={"invalid": "data"})
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        execution_time = (end_time - start_time) * 1000
        memory_used = end_memory - start_memory
        
        # Should return an error status
        assert response.status_code in [400, 422]
        assert execution_time < 500, f"Error handling took {execution_time:.2f}ms, expected < 500ms"
        assert memory_used < PERFORMANCE_BASELINES['memory_mb'], \
            f"Memory usage increased by {memory_used:.2f}MB, expected < {PERFORMANCE_BASELINES['memory_mb']}MB"
    
    def test_large_payload_handling(self, client, mock_llm_client):
        """Test handling of large payloads"""
        large_payload = {"prompt": "Test" * 1000}  # Large payload
        
        start_time = time.time()
        start_memory = get_memory_usage()
        
        response = client.post("/generate/text", json=large_payload)
        
        end_time = time.time()
        end_memory = get_memory_usage()
        
        execution_time = (end_time - start_time) * 1000
        memory_used = end_memory - start_memory
        
        # Should handle large payloads gracefully
        assert response.status_code in [200, 400, 413]
        assert execution_time < 3000, f"Large payload handling took {execution_time:.2f}ms, expected < 3000ms"
        assert memory_used < PERFORMANCE_BASELINES['memory_mb'] * 2, \
            f"Memory usage increased by {memory_used:.2f}MB, expected < {PERFORMANCE_BASELINES['memory_mb'] * 2}MB"

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 