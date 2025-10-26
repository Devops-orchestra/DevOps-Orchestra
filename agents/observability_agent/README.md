# Observability Agent

The Observability Agent monitors deployed resources for health, latency, and error rates. It collects metrics and publishes alerts when configured thresholds are breached.

## Overview

The Observability Agent listens to `DEPLOYMENT_TRIGGERED` events on Kafka and performs the following:

1. **Metrics Collection**: Collects system metrics (CPU, memory, disk, network, latency, error rates)
2. **Threshold Validation**: Checks metrics against configured thresholds
3. **Alert Publishing**: Publishes `OBSERVABILITY_ALERT` events when thresholds are breached

## Architecture

```
┌─────────────────────────┐
│  DEPLOYMENT_TRIGGERED   │
│      (Kafka Topic)      │
└──────────┬──────────────┘
           │
           v
┌─────────────────────────┐
│  Observability Agent    │
│  (Kafka Listener)       │
└──────────┬──────────────┘
           │
           v
┌─────────────────────────┐
│  monitor_and_alert()    │
│  - Collect metrics      │
│  - Check thresholds     │
└──────────┬──────────────┘
           │
           v
┌─────────────────────────┐
│  OBSERVABILITY_ALERT    │
│      (Kafka Topic)      │
└─────────────────────────┘
```

## Configuration

The agent reads configuration from `devops_orchestra.yaml`:

```yaml
observability:
  enabled: true
  tools: ["prometheus", "grafana"]
  alerts: []
  thresholds:
    cpu_usage: 80
    memory_usage: 85
    disk_usage: 80
    error_rate: 2
    request_latency: 1000
```

## Metrics Monitored

- **CPU Usage**: Percentage of CPU utilization
- **Memory Usage**: Percentage of memory utilization
- **Disk Usage**: Percentage of disk utilization
- **Network Throughput**: Network throughput in Mbps
- **Request Latency**: Average request latency in milliseconds
- **Error Rate**: Percentage of failed requests
- **Requests Per Second**: Request throughput

## Alert Severity Levels

- **INFO**: Informational messages
- **WARNING**: Metrics approaching thresholds
- **CRITICAL**: Metrics have exceeded critical thresholds

## Kafka Topics

### Consumes
- `DEPLOYMENT_TRIGGERED`: Triggered when a deployment is completed

### Publishes
- `OBSERVABILITY_ALERT`: Published when monitoring detects threshold breaches

## Files

- `main.py`: Entry point, Kafka listener setup
- `tools/monitor.py`: Core monitoring logic
  - `collect_metrics()`: Gathers system metrics
  - `check_thresholds()`: Validates metrics against thresholds
  - `monitor_and_alert()`: Main monitoring orchestrator

## State Updates

The agent updates the shared state:

```python
state.observability.alerts = [list of breached metrics]
state.observability.metrics_url = "metrics://repo/dashboard"
```

## Future Enhancements

- Integration with real monitoring tools (Prometheus, CloudWatch)
- Custom metric collectors
- Anomaly detection algorithms
- Alert routing and notification channels
- Performance dashboards
