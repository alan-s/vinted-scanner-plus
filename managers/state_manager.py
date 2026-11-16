import csv
import sys
from pathlib import Path

import managers.logging_manager as logging_manager

already_notified_items = {}


# Load already notified items to avoid duplicates
def load_already_notified_items(path):
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f, strict=True)

            for row in reader:
                if row:
                    item_id, title, price = row
                    already_notified_items[item_id] = {
                        "title": title,
                        "price": price,
                    }
            logging_manager.info(
                f"Loaded {len(already_notified_items)} already notified item(s) from '{path}'")
            logging_manager.info(f"Already notified items: [{', '.join(already_notified_items.keys())}]")

    except FileNotFoundError:
        logging_manager.info(f"No previous state file at '{path}' found; clean run")
    except IOError as e:
        logging_manager.error(e, exc_info=True)
        sys.exit(1)
    except (csv.Error, UnicodeDecodeError, ValueError) as e:
        logging_manager.error("CSV validation failed. Error: %s in row %s", e, row)
        sys.exit(1)

    return already_notified_items


# Save a new notified item to prevent repeated alerts
def record_already_notified_item(path, item_id, title, price):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([item_id, title, price])
        return True
    except IOError as e:
        logging_manager.error(e, exc_info=True)
        sys.exit(1)
