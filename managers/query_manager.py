import logging
from itertools import islice

import managers.filter_manager as filter_manager
import managers.logging_manager as logging_manager
import managers.notification_manager as notifications_manager
import managers.state_manager as state_manager
import managers.vinted_api_manager as vinted_api_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

_all_configs = None


def initialise(configs):
    global _all_configs
    _all_configs = configs


def process_query(query, session, args):
    query_id = query.get("query_id")
    query_disabled = query.get("disabled", False)

    logging_manager.item_log_printer(query_id, "Started", log_type="query")

    search_config, state_config, item_filters_config, seller_filters_config, notification_config = _all_configs.values()

    # Skip if query is disabled
    if query_disabled:
        logger.info(
            f"Skipped query [{query_id}]; 'disabled' flag set in search config at '{state_config['file_path']}'")
        return

    # Request items from the Vinted API based on the search parameters
    items = vinted_api_manager.get_items_from_catalogue_search(session, search_config, query) or []
    logger.info("Vinted search API returned %d item(s) in total with IDs: %s", len(items),
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
        logger.info("The maximum number of items to process/notify (from config): %s", max_items)

    # Load the list of already notified items
    already_notified_items = state_manager.load_already_notified_items(state_config['file_path'])

    for item in islice(items, max_items):

        item_id = str(item["id"])
        logging_manager.item_log_printer(item_id, "Started", log_type="item")

        # Check if the item has already been notified to prevent sending it again
        if item_id in already_notified_items:
            logger.info(
                f"Skipped item [{item_id}]; listed as previously seen/notified in '{state_config['file_path']}'")
            previously_notified_items.append(item_id)
            continue

        # Check against item filters
        if args.log_filtering:
            logger.info(f"Checking item [{item_id}] against [item] filters")

        item_filters = item_filters_config['filters']
        if not filter_manager.filter_item(item_id, item, query_id, item_filters, "item", args):
            excluded_items.append(item_id)
            logging_manager.item_log_printer(item_id, "Completed", log_type="item")
            continue

        # Get seller detail for item
        logger.info(f"Getting seller details for item [{item_id}]")
        seller = get_seller_details(item, session, search_config)

        # Check against seller filters
        if args.log_filtering:
            logger.info(f"Checking item [{item_id}] against [seller] filters")

        seller_filters = seller_filters_config['filters']
        if not filter_manager.filter_item(item_id, seller, query_id, seller_filters, "seller", args):
            excluded_items.append(item_id)
            logging_manager.item_log_printer(item_id, "Completed", log_type="item")
            continue

        if args.log_filtering:
            logger.info(f"Item [{item_id}] meets all selection filters and no exclusions apply")

        # Send notification is set
        if args.enable_notifications:

            # Construct message details for item
            message_details = get_item_details_for_message(item, search_config, session)
            if notification_config['telegram']['telegram_bot_token'] and notification_config['telegram'][
                'telegram_chat_id']:
                if send_notification(notification_config, message_details, seller, args, state_config):
                    notified_items.append(item_id)
                else:
                    failed_notified_items.append(item_id)
        else:
            candidate_items.append(item_id)
            logger.info(f"No notification sent for item [{item_id}]; '--{list(vars(args))[1]}' not set")

        logging_manager.item_log_printer(item_id, "Completed", log_type="item")

    logging_manager.item_log_printer(query_id, "Completed", log_type="query")

    # Print end-of-query stats
    logging_manager.log_end_of_run_stats(items, excluded_items, previously_notified_items, candidate_items,
                                         notified_items, failed_notified_items, max_items, args.enable_notifications)


def get_item_details_for_message(item, search_config, session):
    item_id = str(item["id"])
    item_title = item["title"]

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

    item_favourite_count = item.get("favourite_count") or 0

    item_photo = item.get("photo") or {}
    item_image = item_photo.get("full_size_url")

    # Scrape the HTML response for the upload time
    item_description, item_upload_time = vinted_api_manager.get_item_description_and_upload_datetime(session,
                                                                                                     search_config,
                                                                                                     item_id)

    item_details = {
        'item_id': item_id,
        'item_title': item_title,
        'item_url': item_url,
        'item_price': item_price,
        'item_favourite_count': item_favourite_count,
        'item_image': item_image,
        'item_upload_time': item_upload_time,
        'item_description': item_description
    }

    return item_details


def get_seller_details(item, session, search_config):
    user = item.get("user") or {}
    user_id = user.get("id")
    seller = vinted_api_manager.get_user_details(session, search_config, user_id)

    return seller


def send_notification(notification_config, message_details, seller, args, state_config):
    # Send Telegram notifications if configured
    if notifications_manager.send_telegram_message(notification_config, message_details['item_id'],
                                                   message_details['item_title'],
                                                   ['item_description'], message_details['item_price'],
                                                   message_details['item_upload_time'],
                                                   message_details['item_url'], message_details['item_image'],
                                                   message_details['item_favourite_count'], seller):

        # Record item as notified in state file if set
        if not args.disable_state_file:
            state_manager.record_already_notified_item(state_config['file_path'], message_details['item_id'],
                                                       message_details['item_title'],
                                                       message_details['item_price'])
            logger.info(
                f"Recorded notification for item [{message_details['item_id']}] in '{state_config['file_path']}'")
        else:
            logger.info(
                f"Not recording notification for item [{message_details['item_id']}] in '{state_config['file_path']}'; '--{list(vars(args))[2]}' set")

        return True
    else:
        return False
