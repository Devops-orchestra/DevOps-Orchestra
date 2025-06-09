from shared_modules.utils.config_loader import load_yaml
from shared_modules.utils.logger import logger

def parse_orchestra_config(config_path: str) -> dict:
    """
    Parses the devops_orchestra.yaml file using the shared config loader.

    Args:
        config_path (str): Path to the devops_orchestra.yaml file

    Returns:
        dict: Parsed YAML content as a dictionary

    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If the file cannot be parsed
    """
    try:
        config_data = load_yaml(config_path)
        logger.info("Parsed devops_orchestra.yaml successfully.")
        return config_data
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}")
        raise
    except Exception as e:
        logger.error(f"Error parsing configuration file: {str(e)}")
        raise ValueError(f"Invalid configuration file: {e}")
