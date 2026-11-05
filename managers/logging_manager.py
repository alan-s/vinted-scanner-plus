# logger_helper.py
import logging
import sys

log_name = "vinted_scanner.log"

def init_logger():
    """Initialises the global logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_name, encoding="utf-8", mode="a")
        ]
    )
