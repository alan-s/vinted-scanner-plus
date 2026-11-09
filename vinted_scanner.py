#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys
from itertools import islice

import managers.config_manager as config_manager
import managers.filter_manager as filter_manager
import managers.logging_manager as logging_manager
import managers.notification_manager as notifications_manager
import managers.state_manager as state_manager
import managers.vinted_api_manager as vinted_api_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()

parser.add_argument(
    "--log_filtering",
    action="store_true",
    dest="log_filtering",
    default=False,
    help="Enable logging when filtering items"
)

parser.add_argument(
    "--enable_notifications",
    action="store_true",
    dest="enable_notifications",
    default=False,
    help="Enable notifications to external connectors e.g. Telegram. By default, no notifications are sent"
)

parser.add_argument(
    "--disable_state_file",
    action="store_true",
    dest="disable_state_file",
    default=False,
    help="Disable storing previously notified items in a state file. By default, notified items are stored"
)

args = parser.parse_args()


def main():
    logger.info("")
    logger.info("================================================================================")
    logger.info("                                  VINTED SCANNER PLUS                           ")
    logger.info("================================================================================")
    logger.info("")

    # Print what options app has been launched with
    args_str = " ".join(sys.argv[1:])
    logger.info(f"Launched with the following args: {args_str}")

    # Get all the required file paths from config
    base_dir = pathlib.Path.cwd()
    config_file_path = base_dir / "config" / "configs.yaml"
    configs = config_manager.load_configs_from_config_file(config_file_path)

    # Load search queries
    queries = configs['search_config']['queries']

    # Load the list of already notified items
    already_notified_items = configs['state']

    # Load item filters
    item_filters = configs['item_filters']

    # Load seller filters
    seller_filters = configs['seller_filters']

    # No search queries
    if not queries:
        search_config_file_path = config_manager.get_config_file_paths(config_file_path)['search_config']
        logger.info(f"Terminating; no search queries defined in '{search_config_file_path}'")
        sys.exit(0)

    # Loop through each search query defined in search_cfg.py
    search_config = configs['search_config']
    for params in queries:

        logging_manager.item_log_printer(params.get("query_id"), "Started", log_type="query")

        # Request items from the Vinted API based on the search parameters
        items = vinted_api_manager.get_items_from_catalogue_search(search_config, params) or []

        logger.info("Vinted search API returned %d item(s) with IDs: %s", len(items),
                    [item.get("id") for item in items])

        # Keep track for end-of-run stats
        excluded_items = []
        previously_notified_items = []
        candidate_items = []
        notified_items = []
        failed_notified_items = []

        # Process each item returned in the response, and notify based on filters
        max_items = search_config['search']['max_items']
        if items:
            logger.info("From Config, the maximum number of items to process/notify: %s", max_items)

        for item in islice(items, max_items):

            item_id = str(item["id"])
            item_title = item["title"]

            logging_manager.item_log_printer(item_id, "Started", log_type="item")

            item_url = search_config['vinted']['vinted_url'] + item["url"]

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

            # Scrape the HTML response for the upload time
            item_upload_time, item_description = vinted_api_manager.get_item_description_and_upload_datetime(
                search_config, item_id)

            # Check against item filters
            if args.log_filtering:
                logger.info(f"Checking item [{item_id}] against optional [item] filters")
            if not filter_manager.filter_item(item_id, item, params.get("query_id"), item_filters, "item", args):
                excluded_items.append(item_id)
                logging_manager.item_log_printer(item_id, "Completed", log_type="item")
                continue

            # Get seller detail for item
            logger.info(f"Getting seller details for item [{item_id}]")
            user = item.get("user") or {}
            user_id = user.get("id")
            seller = vinted_api_manager.get_user_details(search_config, user_id)

            # Check against seller filters
            if args.log_filtering:
                logger.info(f"Checking item [{item_id}] against optional [seller] filters")
            if not filter_manager.filter_item(item_id, seller, params.get("query_id"), seller_filters, "seller", args):
                excluded_items.append(item_id)
                logging_manager.item_log_printer(item_id, "Completed", log_type="item")
                continue

            if args.log_filtering:
                logger.info(f"Item [{item_id}] meets all selection filters and no exclusions apply")

            # Send notification is set
            if args.enable_notifications:

                # Check if the item has already been notified to prevent sending it again
                state_file_path = config_manager.get_config_file_paths(config_file_path)['state']
                if item_id not in already_notified_items:

                    # Send Telegram notifications if configured
                    notification_config = configs['notification_config']
                    if notification_config['telegram']['telegram_bot_token'] and notification_config['telegram'][
                        'telegram_chat_id']:
                        if notifications_manager.send_telegram_message(notification_config, item_id, item_title,
                                                                       item_description, item_price, item_upload_time,
                                                                       item_url, item_image, favourite_count, seller):
                            notified_items.append(item_id)
                        else:
                            failed_notified_items.append(item_id)

                    # Record item as notified in state file if set
                    if not args.disable_state_file:
                        state_manager.record_already_notified_item(state_file_path, item_id, item_title, total_amount)
                        logger.info(f"Recorded notification for item [{item_id}] in '{state_file_path}'")
                    else:
                        logger.info(
                            f"Not recording notification for item [{item_id}] in '{state_file_path}'; '--{list(vars(args))[2]}' set")
                else:
                    logger.info(
                        f"No notification will be sent on this run for item [{item_id}]; it has been previously notified ('{state_file_path}')")
                    previously_notified_items.append(item_id)

            else:
                candidate_items.append(item_id)
                logger.info(f"No notification sent for item [{item_id}]; '--{list(vars(args))[1]}' not set")

            logging_manager.item_log_printer(item_id, "Completed", log_type="item")

        logging_manager.item_log_printer(params.get("query_id"), "Completed", log_type="query")

        # Print end-of-query stats
        logging_manager.log_end_of_run_stats(items, excluded_items, previously_notified_items, candidate_items,
                                             notified_items, failed_notified_items, max_items)

    # Close api sessions
    vinted_api_manager.close_session()


if __name__ == "__main__":
    main()
