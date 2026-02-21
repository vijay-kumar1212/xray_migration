import logging
from datetime import datetime
import os

_global_logger = None

def setup_custom_logger():
    if _global_logger:
        return _global_logger
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    if not logger.handlers:
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        logger.info(f"Log file created: {log_file}")
    
    return logger