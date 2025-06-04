"""
file_utils.py

Utility functions for basic file operations such as checking existence, reading, and writing files.
"""

import os
from typing import Union

def file_exists(path: str) -> bool:
    """
    Checks whether the given file or directory path exists.

    Args:
        path (str): Path to check.

    Returns:
        bool: True if the path exists, False otherwise.
    """
    return os.path.exists(path)


def read_file(path: str) -> str:
    """
    Reads the entire content of a file.

    Args:
        path (str): Path to the file.

    Returns:
        str: Content of the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: If the file cannot be read.
    """
    with open(path, 'r') as f:
        return f.read()


def write_file(path: str, content: Union[str, bytes]) -> None:
    """
    Writes content to a file. Overwrites if the file already exists.

    Args:
        path (str): Path to the file.
        content (str or bytes): Content to write.

    Raises:
        IOError: If the file cannot be written.
    """
    mode = 'wb' if isinstance(content, bytes) else 'w'
    with open(path, mode) as f:
        f.write(content)
