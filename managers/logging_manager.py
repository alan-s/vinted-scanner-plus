import logging
import sys

log_name = "vinted_scanner_plus.log"
logger = logging.getLogger(__name__)


def init_logger():
    """Initialises the global logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_name, encoding="utf-8", mode="a")
        ]
    )


def item_log_printer(identifier, state, log_type="query"):
    separator = "=" * 80 if log_type == "query" else "-" * 80
    label = "search query" if log_type == "query" else "item"

    logger.info(separator)
    logger.info("%s processing %s [%s]", state, label, identifier)
    logger.info(separator)


def log_end_of_run_stats(items, excluded_items, previously_notified_items, candidate_items, notified_items,
                         failed_notified_items, max_items, notifications_enabled):
    logger.info("Maximum number of items to process/notify (from config): %s", max_items)
    logger.info("Items from Vinted search: %s - [%s]", len(items),
                ", ".join([str(item["id"]) for item in items]))
    logger.info("Items excluded: %s - [%s]", len(excluded_items),
                ", ".join(str(item_id) for item_id in excluded_items))
    logger.info("Items previously notified: %s - [%s]", len(previously_notified_items),
                ", ".join(str(item_id) for item_id in previously_notified_items))
    logger.info("Item candidates: %s - [%s]", len(candidate_items),
                ", ".join(str(item_id) for item_id in candidate_items))
    logger.info(
        "Items notified: %s - [%s]%s",
        len(notified_items),
        ", ".join(str(item_id) for item_id in notified_items),
        " (Notifications not enabled)" if not notifications_enabled else "")
    logger.info("Items failed to notify: %s - [%s]", len(failed_notified_items),
                ", ".join(str(item_id) for item_id in failed_notified_items))
    logger.info(
        f"Items recorded as notified: {len(notified_items)} - [{', '.join(str(item_id) for item_id in notified_items)}]")
