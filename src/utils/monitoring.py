"""
Performance monitoring and metrics for Fantasy Football Draft Tools
"""
import functools
import logging
import os
import psutil
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
import threading
import json
from pathlib import Path

from config import DATA_DIR


logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Represents a single performance measurement"""
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def complete(self, success: bool = True, error: Optional[str] = None):
        """Mark this metric as complete"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error = error


@dataclass
class SystemMetrics:
    """System resource metrics"""
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    disk_io_read_mb: float
    disk_io_write_mb: float


class PerformanceMonitor:
    """Monitors application performance and system resources"""
    
    def __init__(self):
        self.metrics: List[PerformanceMetric] = []
        self.system_metrics: List[SystemMetrics] = []
        self._lock = threading.Lock()
        self._process = psutil.Process(os.getpid())
        
        # Create metrics directory
        self.metrics_dir = DATA_DIR / "metrics"
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def measure(self, name: str, **metadata):
        """Context manager to measure execution time"""
        metric = PerformanceMetric(
            name=name,
            start_time=time.time(),
            metadata=metadata
        )
        
        try:
            # Record system metrics at start
            self._record_system_metrics()
            yield metric
            metric.complete(success=True)
        except Exception as e:
            metric.complete(success=False, error=str(e))
            raise
        finally:
            with self._lock:
                self.metrics.append(metric)
            
            # Log slow operations
            if metric.duration and metric.duration > 5.0:
                logger.warning(f"Slow operation: {name} took {metric.duration:.2f}s")
    
    def measure_function(self, func: Optional[Callable] = None, name: Optional[str] = None):
        """Decorator to measure function execution time"""
        def decorator(f):
            metric_name = name or f"{f.__module__}.{f.__name__}"
            
            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                with self.measure(metric_name):
                    return f(*args, **kwargs)
            
            return wrapper
        
        if func:
            return decorator(func)
        return decorator
    
    def _record_system_metrics(self):
        """Record current system resource usage"""
        try:
            # Get memory info
            memory_info = self._process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = self._process.memory_percent()
            
            # Get CPU usage
            cpu_percent = self._process.cpu_percent()
            
            # Get disk I/O (not available on all platforms)
            try:
                io_counters = self._process.io_counters()
                disk_read_mb = io_counters.read_bytes / (1024 * 1024)
                disk_write_mb = io_counters.write_bytes / (1024 * 1024)
            except AttributeError:
                # io_counters not available on macOS
                disk_read_mb = 0
                disk_write_mb = 0
            
            metric = SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                disk_io_read_mb=disk_read_mb,
                disk_io_write_mb=disk_write_mb
            )
            
            with self._lock:
                self.system_metrics.append(metric)
                
                # Keep only last 1000 system metrics
                if len(self.system_metrics) > 1000:
                    self.system_metrics = self.system_metrics[-1000:]
                    
        except Exception as e:
            logger.debug(f"Error recording system metrics: {e}")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of performance metrics"""
        with self._lock:
            if not self.metrics:
                return {"message": "No metrics recorded"}
            
            # Group metrics by name
            metrics_by_name: Dict[str, List[PerformanceMetric]] = {}
            for metric in self.metrics:
                if metric.name not in metrics_by_name:
                    metrics_by_name[metric.name] = []
                metrics_by_name[metric.name].append(metric)
            
            # Calculate statistics for each operation
            summary = {}
            for name, metrics_list in metrics_by_name.items():
                durations = [m.duration for m in metrics_list if m.duration is not None]
                success_count = sum(1 for m in metrics_list if m.success)
                error_count = len(metrics_list) - success_count
                
                if durations:
                    summary[name] = {
                        'count': len(metrics_list),
                        'success_count': success_count,
                        'error_count': error_count,
                        'avg_duration': sum(durations) / len(durations),
                        'min_duration': min(durations),
                        'max_duration': max(durations),
                        'total_duration': sum(durations)
                    }
            
            # Add system resource summary
            if self.system_metrics:
                recent_metrics = self.system_metrics[-100:]  # Last 100 measurements
                
                summary['system'] = {
                    'avg_cpu_percent': sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics),
                    'max_cpu_percent': max(m.cpu_percent for m in recent_metrics),
                    'avg_memory_mb': sum(m.memory_mb for m in recent_metrics) / len(recent_metrics),
                    'max_memory_mb': max(m.memory_mb for m in recent_metrics),
                    'total_disk_read_mb': self.system_metrics[-1].disk_io_read_mb if self.system_metrics else 0,
                    'total_disk_write_mb': self.system_metrics[-1].disk_io_write_mb if self.system_metrics else 0
                }
            
            return summary
    
    def export_metrics(self, filename: Optional[str] = None) -> Path:
        """Export metrics to JSON file"""
        if not filename:
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.metrics_dir / filename
        
        with self._lock:
            data = {
                'timestamp': datetime.now().isoformat(),
                'performance_metrics': [
                    {
                        'name': m.name,
                        'start_time': m.start_time,
                        'end_time': m.end_time,
                        'duration': m.duration,
                        'success': m.success,
                        'error': m.error,
                        'metadata': m.metadata
                    }
                    for m in self.metrics
                ],
                'system_metrics': [
                    {
                        'timestamp': m.timestamp.isoformat(),
                        'cpu_percent': m.cpu_percent,
                        'memory_mb': m.memory_mb,
                        'memory_percent': m.memory_percent,
                        'disk_io_read_mb': m.disk_io_read_mb,
                        'disk_io_write_mb': m.disk_io_write_mb
                    }
                    for m in self.system_metrics
                ],
                'summary': self.get_performance_summary()
            }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported metrics to {filepath}")
        return filepath
    
    def clear_metrics(self):
        """Clear all recorded metrics"""
        with self._lock:
            self.metrics.clear()
            self.system_metrics.clear()
    
    def log_summary(self):
        """Log performance summary"""
        summary = self.get_performance_summary()
        
        if summary.get("message") == "No metrics recorded":
            return
        
        logger.info("Performance Summary:")
        
        # Log operation metrics
        for name, stats in summary.items():
            if name == 'system':
                continue
                
            logger.info(f"  {name}:")
            logger.info(f"    Count: {stats['count']} (Success: {stats['success_count']}, Errors: {stats['error_count']})")
            logger.info(f"    Duration: avg={stats['avg_duration']:.3f}s, min={stats['min_duration']:.3f}s, max={stats['max_duration']:.3f}s")
        
        # Log system metrics
        if 'system' in summary:
            sys_stats = summary['system']
            logger.info("  System Resources:")
            logger.info(f"    CPU: avg={sys_stats['avg_cpu_percent']:.1f}%, max={sys_stats['max_cpu_percent']:.1f}%")
            logger.info(f"    Memory: avg={sys_stats['avg_memory_mb']:.1f}MB, max={sys_stats['max_memory_mb']:.1f}MB")
            logger.info(f"    Disk I/O: read={sys_stats['total_disk_read_mb']:.1f}MB, write={sys_stats['total_disk_write_mb']:.1f}MB")


# Global performance monitor instance
monitor = PerformanceMonitor()


# Decorator for easy use
def measure_performance(name: Optional[str] = None):
    """Decorator to measure function performance"""
    return monitor.measure_function(name=name)