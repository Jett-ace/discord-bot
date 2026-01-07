"""Centralized logging configuration for the bot."""
import logging
import sys
from datetime import datetime

# Create logs directory if it doesn't exist
import os
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure logging format
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Create logger
def setup_logger(name: str = "DiscordBot", level=logging.INFO):
    """Setup and return a configured logger.
    
    Args:
        name: Logger name (typically module name)
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    
    # File handler (daily log file)
    today = datetime.now().strftime('%Y-%m-%d')
    file_handler = logging.FileHandler(f'logs/bot_{today}.log', encoding='utf-8')
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Create default logger
default_logger = setup_logger()

# Convenience functions
def info(message: str):
    default_logger.info(message)

def warning(message: str):
    default_logger.warning(message)

def error(message: str):
    default_logger.error(message)

def debug(message: str):
    default_logger.debug(message)
