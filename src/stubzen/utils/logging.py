"""
Logging utilities for the stub generator
"""

import logging
import sys
import colorlog

# Between INFO (20) and WARNING (30)
SUCCESS_LEVEL = 25

class SuccessLogger(logging.Logger):
    def success(self, msg, *args, **kwargs):
        """Log a message with severity 'SUCCESS' (level 25)."""
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, msg, args, **kwargs)

def configure_logging(level=logging.INFO):
    """Configure global logging with reduced duplication"""
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    logging.addLevelName(SUCCESS_LEVEL, 'SUCCESS')
    logging.setLoggerClass(SuccessLogger)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create handler with reduced duplication
    handler = logging.StreamHandler(stream=sys.stdout)

    class ExceptionFormatter(colorlog.ColoredFormatter):
        def format(self, record):
            # Only auto-include exception info if it wasn't already explicitly set
            # and we're not in a nested exception context
            if (record.levelno >= logging.ERROR and
                    not record.exc_info and
                    sys.exc_info()[0] is not None and
                    not getattr(record, '_exception_already_logged', False)):
                record.exc_info = sys.exc_info()
                record._exception_already_logged = True
            return super().format(record)

    formatter = ExceptionFormatter(
        '%(log_color)s%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'blue',
            'SUCCESS': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )

    handler.setFormatter(formatter)

    # Add a filter to prevent duplicate exception logging
    def exception_filter(record):
        # Skip if this exact exception was already logged recently
        if hasattr(record, 'exc_info') and record.exc_info:
            exc_hash = hash(str(record.exc_info))
            if hasattr(exception_filter, '_recent_exceptions'):
                if exc_hash in exception_filter._recent_exceptions:
                    return False
                exception_filter._recent_exceptions.add(exc_hash)
                # Keep only recent exceptions (simple cleanup)
                if len(exception_filter._recent_exceptions) > 10:
                    exception_filter._recent_exceptions.clear()
            else:
                exception_filter._recent_exceptions = {exc_hash}
        return True

    handler.addFilter(exception_filter)
    root_logger.addHandler(handler)

    # Set higher levels for noisy third-party libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('click').setLevel(logging.WARNING)

    return root_logger