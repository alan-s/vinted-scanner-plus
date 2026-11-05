#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys

import config.telegram_config as telegram_cfg
import config.search_config as search_cfg
import managers.logging_manager as logging_manager
import managers.notification_manager as notifications_manager
import managers.state_manager as state_manager
import managers.filter_manager as filter_manager
import managers.vinted_api_manager as vinted_api_manager


BASE_DIR = pathlib.Path.cwd()

parser = argparse.ArgumentParser()

parser.add_argument(
    "--log_excluded",
    action="store_true",
    dest="log_excluded",
    default=False,
    help="Disable logging of excluded items and matching keywords"
)

parser.add_argument(
    "--disable_notifications",
    action="store_true",
    dest="disable_notifications",
    default=False,
    help="Disable Telegram notifications"
)

parser.add_argument(
    "--disable_state_file",
    action="store_true",
    dest="disable_state_file",
    default=False,
    help="Disable storing previously notified items in a state file"
)

args = parser.parse_args()

logging_manager.init_logger()
logger = logging.getLogger(__name__)



def main():
    logger.info("")
    logger.info("========================================")
    logger.info("           VINTED SCANNER")
    logger.info("========================================")
    logger.info("")
    args_str = " ".join(f"--{k}" for k, v in vars(args).items())
    logger.info(f"Launched with the following args: {args_str}")


    vinted_url = search_cfg.vinted_url

    # Load the list of already notified items
    already_notified_items = state_manager.load_already_notified_items()

    # Load item filters
    filters_dir_path = BASE_DIR / "filters"
    item_filters = filter_manager.load_filters("item", filters_dir_path / "item_filters.yaml")

    # Load seller filters
    filters_dir_path = BASE_DIR / "filters"
    seller_filters = filter_manager.load_filters("seller", filters_dir_path / "seller_filters.yaml")

    # No search queries
    if not search_cfg.queries:
        logger.info("Exiting: no search queries defined in '/config/search_config.py'")
        sys.exit(0)

    # Loop through each search query defined in search_cfg.py
    for params in search_cfg.queries:

        log_printer(params.get("query_id"), "Started", log_type="query")

        # Request items from the Vinted API based on the search parameters
        items = vinted_api_manager.get_items_from_catalogue_search(params)

        logger.info("Vinted search API has returned %s item(s) with IDs: %s", len(items), [item["id"] for item in items])

        # Process each item returned in the response
        excluded_items = []
        previously_notified_items = []
        candidate_items = []
        notified_items = []
        failed_notified_items = []

        for item in items:

            item_id = str(item["id"])
            item_title = item["title"]

            log_printer(item_id, "Started", log_type="item")

            item_box = item.get("item_box") or {}
            item_description = item_box.get("accessibility_label") or ""

            item_url = vinted_url + item["url"]

            item_price_data = item.get("price") or {}
            amount = item_price_data.get("amount")
            item_amount = (
                f"{float(amount):.2f}".replace(".", ".")
                if amount is not None
                else "N/D"
            )
            item_total_price_data = item.get("total_item_price") or {}
            total_amount = item_total_price_data.get("amount")
            item_total_amount = (
                f"{float(total_amount):.2f}".replace(".", ".")
                if total_amount is not None
                else "N/D"
            )
            item_currency = '£'
            item_price = (
                f"{item_currency}{item_amount} "
                f"({item_currency}{item_total_amount})"
                if item_amount != "N/D" and item_total_amount != "N/D"
                else "N/D"
            )

            favourite_count = item.get("favourite_count") or 0

            item_photo = item.get("photo") or {}
            item_image = item_photo.get("full_size_url")

            item_upload_time = vinted_api_manager.get_item_upload_datetime(item_id)

            # Filter using items filters
            if args.log_excluded:
                logger.info(f"Checking item [{item_id}] against optional [item] filters")
            if not filter_manager.filter_item(item_id, item, params.get("query_id"), item_filters, "item", args):
                excluded_items.append(item_id)
                log_printer(item_id, "Completed", log_type="item")
                continue

            # Get seller detail for item
            logger.info(f"Getting seller details for item [{item_id}]")
            user = item.get("user") or {}
            user_id = user.get("id")
            seller = vinted_api_manager.get_user_details(user_id)

            # Filter using seller filters now
            if args.log_excluded:
                logger.info(f"Checking item [{item_id}] against optional [seller] filters")
            if not filter_manager.filter_item(item_id, seller, params.get("query_id"), seller_filters, "seller", args):
                excluded_items.append(item_id)
                log_printer(item_id, "Completed", log_type="item")
                continue

            if args.log_excluded:
                logger.info(f"Item [{item_id}] meets all selection filters and no exclusions apply")

            # Notifications disabled?
            if not args.disable_notifications:

                # Check if the item has already been notified to prevent sending it again
                if item_id not in already_notified_items:

                    # Send Telegram notifications if configured
                    if telegram_cfg.telegram_bot_token and telegram_cfg.telegram_chat_id:
                        if notifications_manager.send_telegram_message(item_id, item_title, item_price, item_upload_time, item_url, item_image, favourite_count, seller):
                            notified_items.append(item_id)
                        else:
                            failed_notified_items.append(item_id)

                    # Mark item as notified to state file if enabled
                    if not args.disable_state_file:
                        state_manager.save_already_notified_item(item_id, item_title, total_amount)
                        logger.info(f"Recorded notification for item [{item_id}] in '{state_manager.get_state_file_path()}'")
                    else:
                        logger.info(f"Not recording notification for item [{item_id}] in '{state_manager.get_state_file_path()}'; '--{list(vars(args))[2]}' set")
                else:
                    logger.info(f"No notification will be sent on this run for item [{item_id}]; it has been previously notified ('{state_manager.get_state_file_path()}')")
                    previously_notified_items.append(item_id)

            else:
                candidate_items.append(item_id)
                logger.info(f"No notification sent for item [{item_id}]; '--{list(vars(args))[1]}' set")

            log_printer(item_id, "Completed", log_type="item")

        logger.info("Items from Vinted search: %s - [%s]", len(items),
                    ", ".join([str(item["id"]) for item in items]))
        logger.info("Items excluded: %s - [%s]", len(excluded_items),
                    ", ".join(str(item_id) for item_id in excluded_items))
        logger.info("Items previously notified: %s - [%s]", len(previously_notified_items),
                    ", ".join(str(item_id) for item_id in previously_notified_items))
        logger.info("Item candidates: %s - [%s]", len(candidate_items), ", ".join(str(item_id) for item_id in candidate_items))
        logger.info("Items notified: %s - [%s]", len(notified_items),
                    ", ".join(str(item_id) for item_id in notified_items))
        logger.info("Items failed to notify: %s - [%s]", len(failed_notified_items),
                    ", ".join(str(item_id) for item_id in failed_notified_items))
        logger.info(f"Items recorded as notified: {len(notified_items)} - [{', '.join(str(item_id) for item_id in notified_items)}]")


    log_printer(params.get("query_id"), "Completed", log_type="query")


def log_printer(identifier, state, log_type="query"):
    separator = "=" * 80 if log_type == "query" else "-" * 80
    label = "search query" if log_type == "query" else "item"

    logger.info(separator)
    logger.info("%s processing %s [%s]", state, label, identifier)
    logger.info(separator)

if __name__ == "__main__":
    main()
