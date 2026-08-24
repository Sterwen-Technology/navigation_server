#-------------------------------------------------------------------------------
# Name:        translated_logging
# Purpose:     Wrapper for logging that supports translation
#
# Author:      Vibe Code
#
# Created:     2025
# Copyright:   (c) Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from typing import Any, Optional
from .translation import translate, t


class TranslatedLogger:
    """
    A logger wrapper that automatically translates log messages.
    """
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize the translated logger.
        
        Args:
            logger: The underlying logger to wrap
        """
        self._logger = logger
    
    def debug(self, msg: str, *args: Any, **kwargs: Any):
        """Log debug message with translation."""
        translated_msg = translate(msg, msg)  # Try to translate, fallback to original
        self._logger.debug(translated_msg, *args, **kwargs)
    
    def info(self, msg: str, *args: Any, **kwargs: Any):
        """Log info message with translation."""
        translated_msg = translate(msg, msg)
        self._logger.info(translated_msg, *args, **kwargs)
    
    def warning(self, msg: str, *args: Any, **kwargs: Any):
        """Log warning message with translation."""
        translated_msg = translate(msg, msg)
        self._logger.warning(translated_msg, *args, **kwargs)
    
    def error(self, msg: str, *args: Any, **kwargs: Any):
        """Log error message with translation."""
        translated_msg = translate(msg, msg)
        self._logger.error(translated_msg, *args, **kwargs)
    
    def critical(self, msg: str, *args: Any, **kwargs: Any):
        """Log critical message with translation."""
        translated_msg = translate(msg, msg)
        self._logger.critical(translated_msg, *args, **kwargs)
    
    def exception(self, msg: str, *args: Any, **kwargs: Any):
        """Log exception with translation."""
        translated_msg = translate(msg, msg)
        self._logger.exception(translated_msg, *args, **kwargs)
    
    def log(self, level: int, msg: str, *args: Any, **kwargs: Any):
        """Log message at specified level with translation."""
        translated_msg = translate(msg, msg)
        self._logger.log(level, translated_msg, *args, **kwargs)
    
    @property
    def logger(self) -> logging.Logger:
        """Get the underlying logger."""
        return self._logger


def get_translated_logger(name: str) -> TranslatedLogger:
    """
    Get a translated logger for the specified name.
    
    Args:
        name: The logger name
        
    Returns:
        A TranslatedLogger instance
    """
    logger = logging.getLogger(name)
    return TranslatedLogger(logger)


def create_translated_logger(name: str, level: int = logging.INFO) -> TranslatedLogger:
    """
    Create a translated logger with the specified level.
    
    Args:
        name: The logger name
        level: The logging level
        
    Returns:
        A TranslatedLogger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return TranslatedLogger(logger)


# Helper functions for common log messages
def log_server_starting(server_name: str, version: str):
    """Log server starting message."""
    logger = logging.getLogger("ShipDataServer")
    msg = translate("server.starting", "Starting {server_name} version {version} - copyright Sterwen Technology 2021-2026",
                    server_name=server_name, version=version)
    logger.info(msg)


def log_server_error(error: str):
    """Log server error message."""
    logger = logging.getLogger("ShipDataServer")
    msg = translate("server.error", "Server error: {error}", error=error)
    logger.error(msg)


def log_config_error(settings_file: str, error: str):
    """Log configuration error message."""
    logger = logging.getLogger("ShipDataServer")
    msg = translate("config.error", "Error on configuration file => STOP")
    logger.error(msg)


def log_config_loading(settings_file: str, settings_path: str):
    """Log configuration loading message."""
    logger = logging.getLogger("ShipDataServer")
    msg = translate("config.loading", "Building configuration from settings file {settings_file} in path {settings_path}",
                    settings_file=settings_file, settings_path=settings_path)
    logger.info(msg)
