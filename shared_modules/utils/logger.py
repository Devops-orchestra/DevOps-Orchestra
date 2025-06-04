"""
logger.py

Provides a pre-configured logger instance named 'DevOpsOrchestra' with INFO level logging
and a standardized log message format including timestamp and log level.

This logger can be imported and used across the project for consistent logging output.
"""
import logging

logger = logging.getLogger("DevOpsOrchestra")
logger.setLevel(logging.INFO)

# Create console handler with a specific log format
console_handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
console_handler.setFormatter(formatter)

# Add the handler to the logger
if not logger.hasHandlers():
    logger.addHandler(console_handler)
