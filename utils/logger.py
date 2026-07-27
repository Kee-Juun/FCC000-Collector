"""Logging configuration and setup."""

import logging
from pathlib import Path
from typing import Optional

from utils.config import LOG_FILENAME


def setup_logger(output_dir: Path = None, logger_name: str = 'FCC000Collector', 
                include_file_handler: bool = False) -> logging.Logger:
    """
    Setup and configure logger with console handler (and optionally file handler).
    
    Args:
        output_dir: Directory where log file will be saved (only used if include_file_handler=True)
        logger_name: Name of the logger
        include_file_handler: Whether to add a file handler (default: False, as run-specific handlers are added later)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler (always included)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (only if requested - run-specific handlers are added in collector)
    if include_file_handler and output_dir:
        log_file = output_dir / LOG_FILENAME
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

