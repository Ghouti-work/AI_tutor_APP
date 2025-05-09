import logging
import os
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Create a unique log file name for each session (e.g., based on startup time)
current_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_DIR, f"tutor_session_{current_time_str}.log")

def setup_logger(name='gemini_tutor_app', log_file=LOG_FILE, level=logging.DEBUG):
    """Set up a logger instance."""

    # Avoid adding multiple handlers if logger already exists
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        # If you want to reconfigure, clear existing handlers
        # logger.handlers.clear()
        # For this setup, assume if it has handlers, it's already configured
        return logger

    logger.setLevel(level)

    # Create console handler with a higher log level (e.g., INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO) # Only show INFO and above on console
    console_formatter = logging.Formatter('%(levelname)-8s - %(name)s - %(message)s') # Added %(name)s for clarity
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)

    # Create file handler which logs even debug messages
    fh = logging.FileHandler(log_file, encoding='utf-8') # Added encoding
    fh.setLevel(logging.DEBUG) # Log everything to file
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)-8s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)

    logger.info(f"Logger '{name}' initialized. Logging to console (INFO+) and file (DEBUG+): {log_file}")
    return logger

# Get the root logger for the application
app_logger = setup_logger()

# Example of how to get a logger for a specific module, though direct use of app_logger is often fine
def get_module_logger(module_name):
    return logging.getLogger(f'gemini_tutor_app.{module_name}')