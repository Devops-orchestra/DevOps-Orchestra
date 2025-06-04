"""
config_loader.py

Utility module for loading YAML configuration files used across the DevOps Orchestration System.

This module provides a single helper function `load_yaml` that reads and parses a YAML file
into a Python dictionary. It is typically used to load configuration files such as 
`devops_orchestra.yaml` or agent-specific settings.

Functions:
    load_yaml(path: str) -> dict:
        Loads a YAML file and returns its contents as a dictionary.
"""

import yaml

def load_yaml(path: str) -> dict:
    """
    Loads and parses a YAML file.

    Args:
        path (str): Path to the YAML file.

    Returns:
        dict: Parsed YAML content as a dictionary.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the file contains invalid YAML.
    """
    with open(path, 'r') as f:
        return yaml.safe_load(f)
