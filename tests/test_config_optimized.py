"""
Optimized Test Configuration for LlamalyticsHub
Addresses performance bottlenecks identified in analysis
"""
import os
import sys
import pytest
import psutil
import gc
from typing import Generator, Any
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import functools


class PerformanceOptimizedConfig:
    """Performance-optimized test configuration"""
    
    def __init__(self):
        self.cpu_cores = multiprocessing.cpu_count()
        self.memory_threshold = 80  # Memory usage threshold
        self.cpu_threshold = 90     # CPU usage threshold
        self.cleanup_interval = 10  # Cleanup every N tests
        
    def get_optimal_workers(self) -> int:
        """Calculate optimal number of workers based on system resources"""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent()
        
        # Base workers on CPU cores
        base_workers = self.cpu_cores
        
        # Reduce workers if memory usage is high
        if memory.percent > self.memory_threshold:
            base_workers = max(1, base_workers // 2)
            
        # Reduce workers if CPU usage is high
        if cpu_percent > self.cpu_threshold:
            base_workers = max(1, base_workers // 2)
            
        return base_workers


class MemoryOptimizer:
    """Memory optimization utilities"""
    
    @staticmethod
    def force_garbage_collection():
        """Force garbage collection to free memory"""
        gc.collect()
        
    @staticmethod
    def cleanup_test_data():
        """Clean up test data and temporary files"""
        # Clean up any temporary files
        temp_dirs = ['/tmp', './temp', './cache']
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    for file in os.listdir(temp_dir):
                        if file.startswith('test_') or file.endswith('.tmp'):
                            os.remove(os.path.join(temp_dir, file))
                except (OSError, PermissionError):
                    pass
                    
    @staticmethod
    def monitor_memory_usage():
        """Monitor current memory usage"""
        memory = psutil.virtual_memory()
        return {
            'percent': memory.percent,
            'available': memory.available,
            'used': memory.used,
            'total': memory.total
        }


class CPUOptimizer:
    """CPU optimization utilities"""
    
    @staticmethod
    def get_cpu_usage() -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=0.1)
        
    @staticmethod
    def should_throttle() -> bool:
        """Determine if CPU throttling is needed"""
        return psutil.cpu_percent(interval=0.1) > 90
        
    @staticmethod
    def adaptive_sleep():
        """Adaptive sleep based on CPU usage"""
        cpu_usage = psutil.cpu_percent(interval=0.1)
        if cpu_usage > 80:
            time.sleep(0.1)  # Short sleep to reduce CPU pressure


class TestResourceManager:
    """Manages test resources and cleanup"""
    
    def __init__(self):
        self.memory_optimizer = MemoryOptimizer()
        self.cpu_optimizer = CPUOptimizer()
        self.test_count = 0
        self.last_cleanup = 0
        
    def pre_test_setup(self):
        """Setup before each test"""
        self.test_count += 1
        
        # Check if cleanup is needed
        if self.test_count - self.last_cleanup >= 10:
            self.perform_cleanup()
            
        # Adaptive CPU management
        if self.cpu_optimizer.should_throttle():
            self.cpu_optimizer.adaptive_sleep()
            
    def post_test_cleanup(self):
        """Cleanup after each test"""
        # Force garbage collection
        self.memory_optimizer.force_garbage_collection()
        
        # Monitor memory usage
        memory_info = self.memory_optimizer.monitor_memory_usage()
        if memory_info['percent'] > 85:
            self.perform_cleanup()
            
    def perform_cleanup(self):
        """Perform comprehensive cleanup"""
        self.memory_optimizer.force_garbage_collection()
        self.memory_optimizer.cleanup_test_data()
        self.last_cleanup = self.test_count


# Global resource manager
resource_manager = TestResourceManager()


@pytest.fixture(scope="function")
def optimized_test_environment() -> Generator[None, None, None]:
    """Optimized test environment fixture"""
    # Pre-test setup
    resource_manager.pre_test_setup()
    
    yield
    
    # Post-test cleanup
    resource_manager.post_test_cleanup()


@pytest.fixture(scope="session")
def performance_monitor() -> Generator[dict, None, None]:
    """Performance monitoring fixture"""
    start_time = time.time()
    start_memory = MemoryOptimizer.monitor_memory_usage()
    start_cpu = CPUOptimizer.get_cpu_usage()
    
    yield {
        'start_time': start_time,
        'start_memory': start_memory,
        'start_cpu': start_cpu
    }
    
    # Final performance report
    end_time = time.time()
    end_memory = MemoryOptimizer.monitor_memory_usage()
    end_cpu = CPUOptimizer.get_cpu_usage()
    
    duration = end_time - start_time
    memory_increase = end_memory['used'] - start_memory['used']
    cpu_change = end_cpu - start_cpu
    
    print(f"\n📊 Performance Summary:")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Memory Change: {memory_increase / 1024 / 1024:.2f}MB")
    print(f"  CPU Change: {cpu_change:.1f}%")


class OptimizedTestBase:
    """Base class for optimized tests"""
    
    def setup_method(self):
        """Setup method with performance optimization"""
        resource_manager.pre_test_setup()
        
    def teardown_method(self):
        """Teardown method with performance optimization"""
        resource_manager.post_test_cleanup()
        
    def assert_performance(self, max_duration: float = 5.0, max_memory_mb: float = 100.0):
        """Assert performance constraints"""
        # This would be implemented with actual performance monitoring
        # For now, it's a placeholder for performance assertions
        pass


# Performance optimization decorators
def performance_critical(max_duration: float = 5.0):
    """Decorator for performance-critical tests"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import inspect
            # Support pytest fixtures by passing all args/kwargs
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            if duration > max_duration:
                pytest.fail(f"Performance test exceeded {max_duration}s: {duration:.2f}s")
            return result
        return wrapper
    return decorator


def memory_efficient(max_memory_mb: float = 100.0):
    """Decorator for memory-efficient tests"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_memory = MemoryOptimizer.monitor_memory_usage()
            result = func(*args, **kwargs)
            end_memory = MemoryOptimizer.monitor_memory_usage()
            memory_used = (end_memory['used'] - start_memory['used']) / 1024 / 1024
            if memory_used > max_memory_mb:
                pytest.fail(f"Memory usage exceeded {max_memory_mb}MB: {memory_used:.2f}MB")
            return result
        return wrapper
    return decorator


# Configuration for different test types
class TestConfigurations:
    """Test configurations for different performance profiles"""
    
    @staticmethod
    def fast_tests():
        """Configuration for fast tests"""
        return {
            'timeout': 5,
            'max_memory_mb': 50,
            'workers': 1
        }
        
    @staticmethod
    def medium_tests():
        """Configuration for medium tests"""
        return {
            'timeout': 15,
            'max_memory_mb': 100,
            'workers': 2
        }
        
    @staticmethod
    def slow_tests():
        """Configuration for slow tests"""
        return {
            'timeout': 60,
            'max_memory_mb': 200,
            'workers': 1
        }
        
    @staticmethod
    def parallel_tests():
        """Configuration for parallel tests"""
        optimizer = PerformanceOptimizedConfig()
        return {
            'timeout': 30,
            'max_memory_mb': 150,
            'workers': optimizer.get_optimal_workers()
        }


# Export configuration for use in test files
__all__ = [
    'PerformanceOptimizedConfig',
    'MemoryOptimizer', 
    'CPUOptimizer',
    'TestResourceManager',
    'OptimizedTestBase',
    'performance_critical',
    'memory_efficient',
    'TestConfigurations',
    'optimized_test_environment',
    'performance_monitor'
] 

# Register custom marks for pytest to avoid warnings
def pytest_configure(config):
    config.addinivalue_line("markers", "performance: mark test as performance-critical")
    config.addinivalue_line("markers", "memory_intensive: mark test as memory-intensive")
    config.addinivalue_line("markers", "cpu_intensive: mark test as CPU-intensive")
    config.addinivalue_line("markers", "api_core: mark test as API core")
    config.addinivalue_line("markers", "ultra_optimized: mark test as ultra-optimized")
    # Set optimal number of workers for xdist
    if hasattr(config.option, 'numprocesses'):
        optimizer = PerformanceOptimizedConfig()
        optimal_workers = optimizer.get_optimal_workers()
        config.option.numprocesses = optimal_workers


def pytest_collection_modifyitems(config, items):
    """Modify test collection for performance optimization"""
    # Sort tests by expected duration (fastest first)
    # This is a simple heuristic - in practice, you'd have historical data
    fast_tests = []
    slow_tests = []
    
    for item in items:
        # Simple heuristic based on test name
        if any(keyword in item.name.lower() for keyword in ['fast', 'basic', 'simple']):
            fast_tests.append(item)
        else:
            slow_tests.append(item)
            
    # Reorder items: fast tests first
    items[:] = fast_tests + slow_tests


def pytest_runtest_setup(item):
    """Setup before each test with performance optimization"""
    resource_manager.pre_test_setup()


def pytest_runtest_teardown(item, nextitem):
    """Teardown after each test with performance optimization"""
    resource_manager.post_test_cleanup() 