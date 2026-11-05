import csv
import logging
import sys
from pathlib import Path
import managers.logging_manager as logging_manager

file_name = "already_notified_items.csv"

logging_manager.init_logger()
logger = logging.getLogger(__name__)

already_notified_items = {}

# Load already notified items to avoid duplicates
def load_already_notified_items():

    try:
        with open(get_state_file_path(), "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f, strict=True)

            for row in reader:
                if row:
                    item_id, title, price = row
                    already_notified_items[item_id] = {
                        "title": title,
                        "price": price,
                    }
            logger.info(
                f"Loaded {len(already_notified_items)} already notified item(s) from {get_state_file_path()}")
            logger.info(f"Already notified items: [{', '.join(already_notified_items.keys())}]")

    except FileNotFoundError:
        logger.info(f"No previous '{get_state_file_path()}' found; clean run")
    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)
    except (csv.Error, UnicodeDecodeError, ValueError) as e:
        logger.error("CSV validation failed. Error: %s in row %s", e, row)
        sys.exit(1)

    return already_notified_items


# Save a new notified item to prevent repeated alerts
def save_already_notified_item(item_id, title, price):

    try:
        with open(get_state_file_path(), "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([item_id, title, price])


    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


def get_state_file_path():
    return Path.cwd() / "state" / file_name