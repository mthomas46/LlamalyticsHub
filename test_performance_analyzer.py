#!/usr/bin/env python3
"""
Comprehensive Test Performance Analyzer for LlamalyticsHub
Monitors all test suites and provides optimization recommendations
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
from performance_monitor import PerformanceMonitor


class TestPerformanceAnalyzer:
    def __init__(self):
        self.monitor = PerformanceMonitor()
        self.test_suites = {
            'cli_optimized': 'make test-cli-optimized-only',
            'utils': 'make test-utils-only',
            'github_audit': 'make test-github-audit-only',
            'api_core_optimized': 'make test-api-core-optimized-only',
            'api_file_optimized': 'make test-api-file-optimized-only',
            'api_github_optimized': 'make test-api-github-optimized-only',
            'parallel_optimized': 'make test-parallel-fast-optimized',
            'parallel_xdist': 'make test-parallel-fast-xdist'
        }
        
    def analyze_all_suites(self, output_dir='performance_analysis'):
        """Analyze performance of all test suites"""
        print("🔍 Starting comprehensive test performance analysis...")
        
        results = {}
        
        for suite_name, command in self.test_suites.items():
            print(f"\n📊 Analyzing: {suite_name}")
            print(f"Command: {command}")
            
            try:
                success = self.monitor.run_test_with_monitoring(command, suite_name)
                results[suite_name] = {
                    'success': success,
                    'metrics': self.monitor.metrics['test_execution_times'].get(suite_name, {})
                }
                
                if success:
                    print(f"✅ {suite_name} completed successfully")
                else:
                    print(f"❌ {suite_name} failed")
                    
            except Exception as e:
                print(f"❌ Error analyzing {suite_name}: {e}")
                results[suite_name] = {
                    'success': False,
                    'error': str(e)
                }
                
        # Generate comprehensive analysis
        self._generate_comprehensive_report(results, output_dir)
        
    def _generate_comprehensive_report(self, results, output_dir):
        """Generate comprehensive performance analysis report"""
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Analyze bottlenecks
        bottlenecks = self.monitor.analyze_bottlenecks()
        
        # Generate summary statistics
        summary = self._generate_summary_statistics(results)
        
        # Create comprehensive report data
        report_data = {
            'timestamp': timestamp,
            'results': results,
            'bottlenecks': bottlenecks,
            'summary': summary,
            'recommendations': self._generate_optimization_recommendations(results, bottlenecks)
        }
        
        # Save raw data
        with open(f'{output_dir}/comprehensive_analysis_{timestamp}.json', 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
            
        # Generate visualizations
        self._create_comprehensive_charts(results, output_dir, timestamp)
        
        # Generate text report
        self._generate_comprehensive_text_report(output_dir, timestamp, report_data)
        
        print(f"\n📊 Comprehensive analysis report generated: {output_dir}/comprehensive_analysis_{timestamp}.md")
        
    def _generate_summary_statistics(self, results):
        """Generate summary statistics for all test suites"""
        successful_tests = [name for name, data in results.items() if data.get('success', False)]
        failed_tests = [name for name, data in results.items() if not data.get('success', False)]
        
        execution_times = []
        cpu_usage = []
        memory_usage = []
        
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'execution_time' in metrics:
                    execution_times.append((suite_name, metrics['execution_time']))
                if 'cpu_avg' in metrics:
                    cpu_usage.append((suite_name, metrics['cpu_avg']))
                if 'memory_avg' in metrics:
                    memory_usage.append((suite_name, metrics['memory_avg']))
                    
        # Sort by execution time
        execution_times.sort(key=lambda x: x[1], reverse=True)
        
        summary = {
            'total_suites': len(results),
            'successful_suites': len(successful_tests),
            'failed_suites': len(failed_tests),
            'success_rate': len(successful_tests) / len(results) * 100 if results else 0,
            'total_execution_time': sum(time_val for _, time_val in execution_times),
            'avg_execution_time': sum(time_val for _, time_val in execution_times) / len(execution_times) if execution_times else 0,
            'slowest_suite': execution_times[0] if execution_times else None,
            'fastest_suite': execution_times[-1] if execution_times else None,
            'avg_cpu_usage': sum(cpu_val for _, cpu_val in cpu_usage) / len(cpu_usage) if cpu_usage else 0,
            'avg_memory_usage': sum(mem_val for _, mem_val in memory_usage) / len(memory_usage) if memory_usage else 0,
            'execution_times': execution_times,
            'cpu_usage': cpu_usage,
            'memory_usage': memory_usage
        }
        
        return summary
        
    def _generate_optimization_recommendations(self, results, bottlenecks):
        """Generate optimization recommendations based on analysis"""
        recommendations = []
        
        # Analyze execution times
        execution_times = []
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'execution_time' in metrics:
                    execution_times.append((suite_name, metrics['execution_time']))
                    
        if execution_times:
            execution_times.sort(key=lambda x: x[1], reverse=True)
            slowest_suite, slowest_time = execution_times[0]
            
            if slowest_time > 30:
                recommendations.append({
                    'type': 'slow_suite_optimization',
                    'priority': 'high',
                    'suite': slowest_suite,
                    'description': f'{slowest_suite} is the slowest suite at {slowest_time:.2f}s',
                    'recommendation': f'Consider splitting {slowest_suite} into smaller test units or optimizing its slowest tests'
                })
                
        # Analyze CPU utilization
        cpu_usage = []
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'cpu_avg' in metrics:
                    cpu_usage.append((suite_name, metrics['cpu_avg']))
                    
        if cpu_usage:
            avg_cpu = sum(cpu_val for _, cpu_val in cpu_usage) / len(cpu_usage)
            
            if avg_cpu < 30:
                recommendations.append({
                    'type': 'low_cpu_utilization',
                    'priority': 'medium',
                    'description': f'Average CPU usage across all suites is {avg_cpu:.1f}%',
                    'recommendation': 'Consider increasing parallelism or reducing test isolation overhead'
                })
            elif avg_cpu > 80:
                recommendations.append({
                    'type': 'high_cpu_utilization',
                    'priority': 'medium',
                    'description': f'Average CPU usage across all suites is {avg_cpu:.1f}%',
                    'recommendation': 'Consider reducing parallelism or optimizing CPU-intensive operations'
                })
                
        # Analyze memory usage
        memory_usage = []
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'memory_avg' in metrics:
                    memory_usage.append((suite_name, metrics['memory_avg']))
                    
        if memory_usage:
            avg_memory = sum(mem_val for _, mem_val in memory_usage) / len(memory_usage)
            
            if avg_memory > 80:
                recommendations.append({
                    'type': 'high_memory_usage',
                    'priority': 'high',
                    'description': f'Average memory usage across all suites is {avg_memory:.1f}%',
                    'recommendation': 'Consider reducing memory footprint or increasing available memory'
                })
                
        # Parallel execution recommendations
        parallel_suites = [name for name in results.keys() if 'parallel' in name]
        if parallel_suites:
            parallel_times = []
            for suite_name in parallel_suites:
                if results[suite_name].get('success') and 'metrics' in results[suite_name]:
                    metrics = results[suite_name]['metrics']
                    if 'execution_time' in metrics:
                        parallel_times.append((suite_name, metrics['execution_time']))
                        
            if len(parallel_times) >= 2:
                parallel_times.sort(key=lambda x: x[1])
                fastest_parallel = parallel_times[0]
                
                recommendations.append({
                    'type': 'parallel_optimization',
                    'priority': 'medium',
                    'description': f'{fastest_parallel[0]} is the fastest parallel execution at {fastest_parallel[1]:.2f}s',
                    'recommendation': f'Use {fastest_parallel[0]} for optimal parallel execution'
                })
                
        return recommendations
        
    def _create_comprehensive_charts(self, results, output_dir, timestamp):
        """Create comprehensive performance visualization charts"""
        plt.style.use('default')
        
        # Create figure with subplots
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('LlamalyticsHub Comprehensive Test Performance Analysis', fontsize=16, fontweight='bold')
        
        # 1. Execution Times Comparison
        execution_times = []
        suite_names = []
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'execution_time' in metrics:
                    execution_times.append(metrics['execution_time'])
                    suite_names.append(suite_name)
                    
        if execution_times:
            bars = ax1.bar(range(len(suite_names)), execution_times, color='skyblue', alpha=0.7)
            ax1.set_title('Test Suite Execution Times')
            ax1.set_xlabel('Test Suite')
            ax1.set_ylabel('Execution Time (seconds)')
            ax1.set_xticks(range(len(suite_names)))
            ax1.set_xticklabels(suite_names, rotation=45, ha='right')
            ax1.grid(True, alpha=0.3)
            
            # Add value labels on bars
            for bar, time_val in zip(bars, execution_times):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                        f'{time_val:.1f}s', ha='center', va='bottom', fontsize=8)
                
        # 2. CPU Usage Comparison
        cpu_usage = []
        cpu_suite_names = []
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'cpu_avg' in metrics:
                    cpu_usage.append(metrics['cpu_avg'])
                    cpu_suite_names.append(suite_name)
                    
        if cpu_usage:
            bars = ax2.bar(range(len(cpu_suite_names)), cpu_usage, color='lightcoral', alpha=0.7)
            ax2.set_title('Average CPU Usage by Test Suite')
            ax2.set_xlabel('Test Suite')
            ax2.set_ylabel('CPU Usage (%)')
            ax2.set_xticks(range(len(cpu_suite_names)))
            ax2.set_xticklabels(cpu_suite_names, rotation=45, ha='right')
            ax2.grid(True, alpha=0.3)
            ax2.set_ylim(0, 100)
            
            # Add value labels on bars
            for bar, cpu_val in zip(bars, cpu_usage):
                ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f'{cpu_val:.1f}%', ha='center', va='bottom', fontsize=8)
                
        # 3. Memory Usage Comparison
        memory_usage = []
        memory_suite_names = []
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                if 'memory_avg' in metrics:
                    memory_usage.append(metrics['memory_avg'])
                    memory_suite_names.append(suite_name)
                    
        if memory_usage:
            bars = ax3.bar(range(len(memory_suite_names)), memory_usage, color='lightgreen', alpha=0.7)
            ax3.set_title('Average Memory Usage by Test Suite')
            ax3.set_xlabel('Test Suite')
            ax3.set_ylabel('Memory Usage (%)')
            ax3.set_xticks(range(len(memory_suite_names)))
            ax3.set_xticklabels(memory_suite_names, rotation=45, ha='right')
            ax3.grid(True, alpha=0.3)
            ax3.set_ylim(0, 100)
            
            # Add value labels on bars
            for bar, mem_val in zip(bars, memory_usage):
                ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                        f'{mem_val:.1f}%', ha='center', va='bottom', fontsize=8)
                
        # 4. Success Rate and Performance Summary
        successful = sum(1 for data in results.values() if data.get('success', False))
        total = len(results)
        success_rate = (successful / total * 100) if total > 0 else 0
        
        # Create a summary pie chart
        labels = ['Successful', 'Failed']
        sizes = [successful, total - successful]
        colors = ['lightgreen', 'lightcoral']
        
        ax4.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax4.set_title('Test Suite Success Rate')
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/comprehensive_charts_{timestamp}.png', dpi=300, bbox_inches='tight')
        plt.close()
        
    def _generate_comprehensive_text_report(self, output_dir, timestamp, report_data):
        """Generate comprehensive text-based performance report"""
        results = report_data['results']
        summary = report_data['summary']
        recommendations = report_data['recommendations']
        
        report_content = f"""# LlamalyticsHub Comprehensive Test Performance Analysis

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

- **Total Test Suites**: {summary['total_suites']}
- **Successful Suites**: {summary['successful_suites']}
- **Failed Suites**: {summary['failed_suites']}
- **Success Rate**: {summary['success_rate']:.1f}%
- **Total Execution Time**: {summary['total_execution_time']:.2f} seconds
- **Average Execution Time**: {summary['avg_execution_time']:.2f} seconds
- **Average CPU Usage**: {summary['avg_cpu_usage']:.1f}%
- **Average Memory Usage**: {summary['avg_memory_usage']:.1f}%

## Test Suite Performance Details

| Test Suite | Execution Time | Success | CPU Avg | Memory Avg |
|------------|----------------|---------|---------|------------|
"""
        
        for suite_name, data in results.items():
            if data.get('success') and 'metrics' in data:
                metrics = data['metrics']
                execution_time = metrics.get('execution_time', 0)
                cpu_avg = metrics.get('cpu_avg', 0)
                memory_avg = metrics.get('memory_avg', 0)
                report_content += f"| {suite_name} | {execution_time:.2f}s | ✅ | {cpu_avg:.1f}% | {memory_avg:.1f}% |\n"
            else:
                report_content += f"| {suite_name} | N/A | ❌ | N/A | N/A |\n"
                
        # Add performance rankings
        if summary['execution_times']:
            report_content += "\n## Performance Rankings\n\n"
            report_content += "### Fastest to Slowest Test Suites:\n"
            for i, (suite_name, time_val) in enumerate(summary['execution_times'], 1):
                report_content += f"{i}. {suite_name}: {time_val:.2f}s\n"
                
        # Add optimization recommendations
        if recommendations:
            report_content += "\n## Optimization Recommendations\n\n"
            for i, rec in enumerate(recommendations, 1):
                report_content += f"### {i}. {rec['type'].replace('_', ' ').title()}\n"
                report_content += f"- **Priority**: {rec['priority'].title()}\n"
                report_content += f"- **Description**: {rec['description']}\n"
                report_content += f"- **Recommendation**: {rec['recommendation']}\n\n"
                
        # Add bottleneck analysis
        if report_data['bottlenecks']:
            report_content += "## Performance Bottlenecks\n\n"
            for i, bottleneck in enumerate(report_data['bottlenecks'], 1):
                report_content += f"### {i}. {bottleneck['type'].replace('_', ' ').title()}\n"
                report_content += f"- **Severity**: {bottleneck['severity'].title()}\n"
                report_content += f"- **Description**: {bottleneck['description']}\n"
                report_content += f"- **Recommendation**: {bottleneck['recommendation']}\n\n"
                
        report_content += """## Action Items

Based on the comprehensive analysis:

1. **Immediate Actions**: Address high-priority recommendations first
2. **Performance Monitoring**: Implement continuous performance monitoring
3. **Test Optimization**: Focus on the slowest test suites
4. **Resource Management**: Optimize CPU and memory usage
5. **Parallel Strategy**: Use the most efficient parallel execution method

## Files Generated

- `comprehensive_analysis_{timestamp}.json`: Raw analysis data
- `comprehensive_charts_{timestamp}.png`: Performance visualizations
- `comprehensive_analysis_{timestamp}.md`: This report

"""
        
        with open(f'{output_dir}/comprehensive_analysis_{timestamp}.md', 'w') as f:
            f.write(report_content)


def main():
    parser = argparse.ArgumentParser(description='Comprehensive Test Performance Analyzer')
    parser.add_argument('--output-dir', default='performance_analysis', help='Output directory for reports')
    parser.add_argument('--suite', help='Analyze specific test suite only')
    
    args = parser.parse_args()
    
    analyzer = TestPerformanceAnalyzer()
    
    try:
        if args.suite:
            # Analyze specific suite
            if args.suite in analyzer.test_suites:
                print(f"🔍 Analyzing specific suite: {args.suite}")
                success = analyzer.monitor.run_test_with_monitoring(
                    analyzer.test_suites[args.suite], 
                    args.suite
                )
                analyzer.monitor.generate_performance_report(args.output_dir)
                
                if success:
                    print("✅ Suite analysis completed successfully")
                else:
                    print("❌ Suite analysis failed")
            else:
                print(f"❌ Unknown test suite: {args.suite}")
                print(f"Available suites: {list(analyzer.test_suites.keys())}")
        else:
            # Analyze all suites
            analyzer.analyze_all_suites(args.output_dir)
            
    except KeyboardInterrupt:
        print("\n🛑 Analysis interrupted by user")
        analyzer.monitor.stop_monitoring()
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        analyzer.monitor.stop_monitoring()


if __name__ == '__main__':
    main() 