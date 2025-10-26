import os
import time
import random
from typing import Dict, Any
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.topics import OBSERVABILITY_ALERT
from shared_modules.kafka_event_bus.event_schema import ObservabilityAlertEvent, SeverityEnum

REPO_BASE_PATH = "/tmp/gitops_repos"


def collect_metrics(repo_name: str, state: DevOpsAgentState) -> Dict[str, Any]:
    """
    Collects metrics from deployed resources.
    In a real implementation, this would query Prometheus, CloudWatch, etc.
    """
    config = state.repo_context.config or {}
    observability_cfg = config.get("observability", {})
    
    # Simulate metrics collection
    # In production, this would connect to actual monitoring systems
    metrics = {
        "cpu_usage": random.uniform(10, 80),  # Percentage
        "memory_usage": random.uniform(20, 70),  # Percentage
        "disk_usage": random.uniform(15, 50),  # Percentage
        "network_throughput": random.uniform(100, 1000),  # Mbps
        "request_latency": random.uniform(50, 500),  # Milliseconds
        "error_rate": random.uniform(0, 5),  # Percentage
        "requests_per_second": random.uniform(10, 100),  # RPS
    }
    
    logger.info(f"[Observability Agent] Collected metrics for {repo_name}: {metrics}")
    return metrics


def check_thresholds(metrics: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks if any metrics breach configured thresholds.
    Returns alert information if thresholds are breached.
    """
    thresholds = config.get("observability", {}).get("thresholds", {})
    
    default_thresholds = {
        "cpu_usage": 80,
        "memory_usage": 85,
        "disk_usage": 80,
        "error_rate": 2,
        "request_latency": 1000,
    }
    
    # Merge defaults with config thresholds
    for key, value in default_thresholds.items():
        if key not in thresholds:
            thresholds[key] = value
    
    alerts = []
    
    # Check CPU
    if metrics["cpu_usage"] > thresholds.get("cpu_usage", 80):
        alerts.append({
            "metric": "cpu_usage",
            "value": metrics["cpu_usage"],
            "threshold": thresholds.get("cpu_usage", 80),
            "severity": "critical" if metrics["cpu_usage"] > 90 else "warning"
        })
    
    # Check Memory
    if metrics["memory_usage"] > thresholds.get("memory_usage", 85):
        alerts.append({
            "metric": "memory_usage",
            "value": metrics["memory_usage"],
            "threshold": thresholds.get("memory_usage", 85),
            "severity": "critical" if metrics["memory_usage"] > 90 else "warning"
        })
    
    # Check Error Rate
    if metrics["error_rate"] > thresholds.get("error_rate", 2):
        alerts.append({
            "metric": "error_rate",
            "value": metrics["error_rate"],
            "threshold": thresholds.get("error_rate", 2),
            "severity": "critical" if metrics["error_rate"] > 5 else "warning"
        })
    
    # Check Latency
    if metrics["request_latency"] > thresholds.get("request_latency", 1000):
        alerts.append({
            "metric": "request_latency",
            "value": metrics["request_latency"],
            "threshold": thresholds.get("request_latency", 1000),
            "severity": "warning"
        })
    
    # Check Disk
    if metrics["disk_usage"] > thresholds.get("disk_usage", 80):
        alerts.append({
            "metric": "disk_usage",
            "value": metrics["disk_usage"],
            "threshold": thresholds.get("disk_usage", 80),
            "severity": "warning"
        })
    
    return {
        "has_alerts": len(alerts) > 0,
        "alerts": alerts
    }


def monitor_and_alert(event: dict, state: DevOpsAgentState) -> Dict[str, Any]:
    """
    Main monitoring function that collects metrics and publishes alerts if thresholds are breached.
    """
    repo_name = event.get("repo", "unknown")
    service_name = event.get("service_name", "default-service")
    
    logger.info(f"[Observability Agent] Starting monitoring for {repo_name}/{service_name}")
    
    try:
        # Collect metrics
        metrics = collect_metrics(repo_name, state)
        
        # Check thresholds
        threshold_check = check_thresholds(metrics, state.repo_context.config or {})
        
        # If alerts exist, publish them
        if threshold_check["has_alerts"]:
            for alert in threshold_check["alerts"]:
                severity_map = {
                    "critical": SeverityEnum.CRITICAL,
                    "warning": SeverityEnum.WARNING,
                    "info": SeverityEnum.INFO
                }
                
                alert_event = ObservabilityAlertEvent(
                    repo=repo_name,
                    service=service_name,
                    issue=f"{alert['metric']} threshold breached: {alert['value']:.2f} > {alert['threshold']}",
                    severity=severity_map.get(alert['severity'], SeverityEnum.WARNING),
                    logs=f"Metric: {alert['metric']}, Current: {alert['value']:.2f}, Threshold: {alert['threshold']}",
                    metrics=metrics,
                )
                
                publish_event(OBSERVABILITY_ALERT, alert_event.model_dump())
                logger.warning(
                    f"[Observability Agent] Alert published: {alert['metric']} = {alert['value']:.2f} "
                    f"(threshold: {alert['threshold']})"
                )
        else:
            logger.info(f"[Observability Agent] All metrics within thresholds for {repo_name}")
        
        # Update state
        state.observability.alerts = [a["metric"] for a in threshold_check["alerts"]]
        state.observability.metrics_url = f"metrics://{repo_name}/dashboard"  # Placeholder
        
        return {
            "status": "success",
            "metrics": metrics,
            "alerts_count": len(threshold_check["alerts"])
        }
    
    except Exception as e:
        logger.error(f"[Observability Agent] Error during monitoring: {e}")
        return {
            "status": "failed",
            "error": str(e)
        }
