import logging
import sys


def init_logger(log_path):
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_path, encoding="utf-8", mode="a")
            ],
            force=True,
        )
    except OSError as e:
        print(f"Terminating; couldn't initialise log file at {log_path}")
        sys.exit(1)


def item_log_printer(identifier, state, log_type="query"):
    separator = "=" * 80 if log_type == "query" else "-" * 80
    label = "search query" if log_type == "query" else "item"

    logging.info(separator)
    logging.info("%s processing %s [%s]", state, label, identifier)
    logging.info(separator)


def log_end_of_run_stats(items, excluded_items, previously_notified_items, candidate_items, notified_items,
                         failed_notified_items, max_items, notifications_enabled):
    logging.info("Total number of items from Vinted search: %s", len(items))
    if max_items is not None:
        logging.info("From config, the maximum number of items processed: %s - [%s]", max_items,
                     ", ".join([str(item["id"]) for item in items[:max_items]]))
    logging.info("Items excluded due to filters: %s - [%s]", len(excluded_items),
                 ", ".join(str(item_id) for item_id in excluded_items))
    logging.info("Items previously notified: %s - [%s]", len(previously_notified_items),
                 ", ".join(str(item_id) for item_id in previously_notified_items))
    logging.info("Items for which to notify: %s - [%s]", len(candidate_items),
                 ", ".join(str(item_id) for item_id in candidate_items))
    logging.info(
        "Items notified: %s - [%s]%s",
        len(notified_items),
        ", ".join(str(item_id) for item_id in notified_items),
        " (Notifications not enabled)" if not notifications_enabled else "")
    logging.info(
        f"Items recorded as notified: {len(notified_items)} - [{', '.join(str(item_id) for item_id in notified_items)}]")
    logging.info("Items which failed to notify: %s - [%s]", len(failed_notified_items),
                 ", ".join(str(item_id) for item_id in failed_notified_items))
