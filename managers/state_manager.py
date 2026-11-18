import csv
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

HEADER = ["item_id", "item_title", "item_price", "item_total_price"]
already_notified_items = {}


# Load already notified items to avoid duplicates
def load_already_notified_items(path):
    try:
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f, strict=True)
            next(reader, None)  # Skip first row which is the header

            for row in reader:
                if row:
                    item_id, item_title, item_price, item_total_price = row
                    already_notified_items[item_id] = {
                        "title": item_title,
                        "item_price": item_price,
                        "item_total_price": item_total_price
                    }
            logger.info(
                f"Loaded {len(already_notified_items)} already notified item(s) from '{path}'")
            logger.info(f"Already notified items: [{', '.join(already_notified_items.keys())}]")

    except FileNotFoundError:
        logger.info(f"No previous state file at '{path}' found; clean run")
    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)
    except (csv.Error, UnicodeDecodeError, ValueError) as e:
        logger.error("CSV validation failed. Error: %s in row %s", e, row)
        sys.exit(1)

    return already_notified_items


# Save a new notified item to prevent repeated alerts
def record_already_notified_item(path, item_id, item_title, item_price, item_total_price):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a+", newline="", encoding="utf-8-sig") as f:

            # Check for whitespace
            f.seek(0)
            is_empty = not f.read().strip()

            f.seek(0, os.SEEK_END)
            writer = csv.writer(f)

            # Add header if new file
            if is_empty:
                writer.writerow(HEADER)

            writer.writerow([item_id, item_title, item_price, item_total_price])

        return True

    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)
