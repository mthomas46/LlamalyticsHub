#!/usr/bin/env python3
"""
Performance Monitor for LlamalyticsHub Test Suite
Analyzes test execution patterns and identifies optimization opportunities
"""
import time
import psutil
import subprocess
import json
import os
import sys
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict, deque
import threading
import signal
import argparse


class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'cpu_usage': deque(maxlen=1000),
            'memory_usage': deque(maxlen=1000),
            'disk_io': deque(maxlen=1000),
            'test_execution_times': {},
            'suite_execution_times': {},
            'bottlenecks': [],
            'timestamps': deque(maxlen=1000)
        }
        self.monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self):
        """Start background monitoring thread"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_system)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
            
    def _monitor_system(self):
        """Background system monitoring"""
        while self.monitoring:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=0.1)
                
                # Memory usage
                memory = psutil.virtual_memory()
                
                # Disk I/O
                disk_io = psutil.disk_io_counters()
                
                timestamp = time.time()
                
                self.metrics['cpu_usage'].append(cpu_percent)
                self.metrics['memory_usage'].append(memory.percent)
                self.metrics['disk_io'].append({
                    'read_bytes': disk_io.read_bytes if disk_io else 0,
                    'write_bytes': disk_io.write_bytes if disk_io else 0
                })
                self.metrics['timestamps'].append(timestamp)
                
                time.sleep(0.5)  # Sample every 500ms
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                time.sleep(1)
                
    def run_test_with_monitoring(self, test_command, test_name):
        """Run a test command while monitoring performance"""
        print(f"🔍 Monitoring: {test_name}")
        print(f"Command: {test_command}")
        
        start_time = time.time()
        self.start_monitoring()
        
        try:
            # Run the test command
            process = subprocess.Popen(
                test_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            exit_code = process.returncode
            
        finally:
            self.stop_monitoring()
            
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Store metrics
        self.metrics['test_execution_times'][test_name] = {
            'execution_time': execution_time,
            'exit_code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
            'cpu_avg': sum(self.metrics['cpu_usage']) / len(self.metrics['cpu_usage']) if self.metrics['cpu_usage'] else 0,
            'memory_avg': sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage']) if self.metrics['memory_usage'] else 0
        }
        
        return exit_code == 0
        
    def analyze_bottlenecks(self):
        """Analyze performance bottlenecks"""
        bottlenecks = []
        
        # Analyze CPU usage patterns
        if self.metrics['cpu_usage']:
            cpu_avg = sum(self.metrics['cpu_usage']) / len(self.metrics['cpu_usage'])
            cpu_max = max(self.metrics['cpu_usage'])
            
            if cpu_avg < 30:
                bottlenecks.append({
                    'type': 'low_cpu_utilization',
                    'severity': 'medium',
                    'description': f'Average CPU usage is {cpu_avg:.1f}% (max: {cpu_max:.1f}%)',
                    'recommendation': 'Consider increasing parallelism or reducing test isolation overhead'
                })
            elif cpu_max > 90:
                bottlenecks.append({
                    'type': 'high_cpu_utilization',
                    'severity': 'high',
                    'description': f'Peak CPU usage is {cpu_max:.1f}%',
                    'recommendation': 'Consider reducing parallelism or optimizing CPU-intensive operations'
                })
                
        # Analyze memory usage
        if self.metrics['memory_usage']:
            memory_avg = sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage'])
            memory_max = max(self.metrics['memory_usage'])
            
            if memory_avg > 80:
                bottlenecks.append({
                    'type': 'high_memory_usage',
                    'severity': 'high',
                    'description': f'Average memory usage is {memory_avg:.1f}% (max: {memory_max:.1f}%)',
                    'recommendation': 'Consider reducing memory footprint or increasing available memory'
                })
                
        # Analyze test execution times
        if self.metrics['test_execution_times']:
            slow_tests = []
            for test_name, metrics in self.metrics['test_execution_times'].items():
                if metrics['execution_time'] > 10:  # Tests taking more than 10 seconds
                    slow_tests.append((test_name, metrics['execution_time']))
                    
            if slow_tests:
                slow_tests.sort(key=lambda x: x[1], reverse=True)
                bottlenecks.append({
                    'type': 'slow_tests',
                    'severity': 'medium',
                    'description': f'Found {len(slow_tests)} slow tests',
                    'details': slow_tests[:5],  # Top 5 slowest tests
                    'recommendation': 'Consider optimizing slow tests or splitting them into smaller units'
                })
                
        self.metrics['bottlenecks'] = bottlenecks
        return bottlenecks
        
    def generate_performance_report(self, output_dir='performance_reports'):
        """Generate comprehensive performance report with visualizations"""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create the main report
        report_data = {
            'timestamp': timestamp,
            'metrics': self.metrics,
            'bottlenecks': self.analyze_bottlenecks(),
            'summary': self._generate_summary()
        }
        
        # Save raw data
        with open(f'{output_dir}/performance_data_{timestamp}.json', 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
            
        # Generate visualizations
        self._create_performance_charts(output_dir, timestamp)
        
        # Generate text report
        self._generate_text_report(output_dir, timestamp, report_data)
        
        print(f"📊 Performance report generated: {output_dir}/performance_report_{timestamp}.md")
        
    def _generate_summary(self):
        """Generate performance summary"""
        summary = {
            'total_tests': len(self.metrics['test_execution_times']),
            'total_execution_time': sum(m['execution_time'] for m in self.metrics['test_execution_times'].values()),
            'avg_cpu_usage': sum(self.metrics['cpu_usage']) / len(self.metrics['cpu_usage']) if self.metrics['cpu_usage'] else 0,
            'avg_memory_usage': sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage']) if self.metrics['memory_usage'] else 0,
            'bottlenecks_found': len(self.analyze_bottlenecks())
        }
        return summary
        
    def _create_performance_charts(self, output_dir, timestamp):
        """Create performance visualization charts"""
        plt.style.use('default')
        
        # Create figure with subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('LlamalyticsHub Test Performance Analysis', fontsize=16, fontweight='bold')
        
        # 1. CPU Usage Over Time
        if self.metrics['cpu_usage'] and self.metrics['timestamps']:
            timestamps = [t - self.metrics['timestamps'][0] for t in self.metrics['timestamps']]
            ax1.plot(timestamps, list(self.metrics['cpu_usage']), 'b-', linewidth=1)
            ax1.set_title('CPU Usage Over Time')
            ax1.set_xlabel('Time (seconds)')
            ax1.set_ylabel('CPU Usage (%)')
            ax1.grid(True, alpha=0.3)
            
        # 2. Memory Usage Over Time
        if self.metrics['memory_usage'] and self.metrics['timestamps']:
            timestamps = [t - self.metrics['timestamps'][0] for t in self.metrics['timestamps']]
            ax2.plot(timestamps, list(self.metrics['memory_usage']), 'r-', linewidth=1)
            ax2.set_title('Memory Usage Over Time')
            ax2.set_xlabel('Time (seconds)')
            ax2.set_ylabel('Memory Usage (%)')
            ax2.grid(True, alpha=0.3)
            
        # 3. Test Execution Times
        if self.metrics['test_execution_times']:
            test_names = list(self.metrics['test_execution_times'].keys())
            execution_times = [m['execution_time'] for m in self.metrics['test_execution_times'].values()]
            
            bars = ax3.bar(range(len(test_names)), execution_times, color='skyblue', alpha=0.7)
            ax3.set_title('Test Execution Times')
            ax3.set_xlabel('Test Name')
            ax3.set_ylabel('Execution Time (seconds)')
            ax3.set_xticks(range(len(test_names)))
            ax3.set_xticklabels(test_names, rotation=45, ha='right')
            ax3.grid(True, alpha=0.3)
            
            # Add value labels on bars
            for bar, time_val in zip(bars, execution_times):
                ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                        f'{time_val:.1f}s', ha='center', va='bottom', fontsize=8)
                
        # 4. Resource Utilization Summary
        if self.metrics['cpu_usage'] and self.metrics['memory_usage']:
            cpu_avg = sum(self.metrics['cpu_usage']) / len(self.metrics['cpu_usage'])
            memory_avg = sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage'])
            
            labels = ['CPU', 'Memory']
            values = [cpu_avg, memory_avg]
            colors = ['lightblue', 'lightcoral']
            
            bars = ax4.bar(labels, values, color=colors, alpha=0.7)
            ax4.set_title('Average Resource Utilization')
            ax4.set_ylabel('Usage (%)')
            ax4.set_ylim(0, 100)
            ax4.grid(True, alpha=0.3)
            
            # Add value labels
            for bar, value in zip(bars, values):
                ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f'{value:.1f}%', ha='center', va='bottom', fontweight='bold')
                
        plt.tight_layout()
        plt.savefig(f'{output_dir}/performance_charts_{timestamp}.png', dpi=300, bbox_inches='tight')
        plt.close()
        
    def _generate_text_report(self, output_dir, timestamp, report_data):
        """Generate text-based performance report"""
        report_content = f"""# LlamalyticsHub Performance Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

- **Total Tests Executed**: {report_data['summary']['total_tests']}
- **Total Execution Time**: {report_data['summary']['total_execution_time']:.2f} seconds
- **Average CPU Usage**: {report_data['summary']['avg_cpu_usage']:.1f}%
- **Average Memory Usage**: {report_data['summary']['avg_memory_usage']:.1f}%
- **Bottlenecks Identified**: {report_data['summary']['bottlenecks_found']}

## Performance Bottlenecks

"""
        
        for i, bottleneck in enumerate(report_data['bottlenecks'], 1):
            report_content += f"### {i}. {bottleneck['type'].replace('_', ' ').title()}\n"
            report_content += f"- **Severity**: {bottleneck['severity'].title()}\n"
            report_content += f"- **Description**: {bottleneck['description']}\n"
            report_content += f"- **Recommendation**: {bottleneck['recommendation']}\n\n"
            
            if 'details' in bottleneck:
                report_content += "**Details**:\n"
                for test_name, time_val in bottleneck['details']:
                    report_content += f"- {test_name}: {time_val:.2f}s\n"
                report_content += "\n"
                
        report_content += """## Test Execution Details

| Test Name | Execution Time | Exit Code | Avg CPU | Avg Memory |
|-----------|----------------|-----------|---------|------------|
"""
        
        for test_name, metrics in report_data['metrics']['test_execution_times'].items():
            report_content += f"| {test_name} | {metrics['execution_time']:.2f}s | {metrics['exit_code']} | {metrics['cpu_avg']:.1f}% | {metrics['memory_avg']:.1f}% |\n"
            
        report_content += f"""

## Recommendations

Based on the performance analysis:

1. **Optimization Priority**: Focus on the highest severity bottlenecks first
2. **Resource Management**: Monitor CPU and memory usage during test execution
3. **Test Splitting**: Consider splitting slow tests into smaller units
4. **Parallelization**: Optimize parallel execution based on resource utilization

## Files Generated

- `performance_data_{timestamp}.json`: Raw performance data
- `performance_charts_{timestamp}.png`: Performance visualizations
- `performance_report_{timestamp}.md`: This report

"""
        
        with open(f'{output_dir}/performance_report_{timestamp}.md', 'w') as f:
            f.write(report_content)


def main():
    parser = argparse.ArgumentParser(description='Performance Monitor for LlamalyticsHub Tests')
    parser.add_argument('--test-command', required=True, help='Test command to monitor')
    parser.add_argument('--test-name', required=True, help='Name of the test being monitored')
    parser.add_argument('--output-dir', default='performance_reports', help='Output directory for reports')
    
    args = parser.parse_args()
    
    monitor = PerformanceMonitor()
    
    try:
        # Run test with monitoring
        success = monitor.run_test_with_monitoring(args.test_command, args.test_name)
        
        # Generate performance report
        monitor.generate_performance_report(args.output_dir)
        
        if success:
            print("✅ Test completed successfully")
        else:
            print("❌ Test failed")
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring interrupted by user")
        monitor.stop_monitoring()
    except Exception as e:
        print(f"❌ Error during monitoring: {e}")
        monitor.stop_monitoring()


if __name__ == '__main__':
    main() 