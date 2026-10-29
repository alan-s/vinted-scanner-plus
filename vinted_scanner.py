#!/usr/bin/env python3
import argparse
import csv
import sys
import yaml
import search_config
import logging
import requests
import unicodedata
import telegram_config

from pathlib import Path
from vinted_html_parser import get_upload_time

parser = argparse.ArgumentParser()

parser.add_argument(
    "--log_excluded",
    action="store_true",
    help="Log excluded items and the matching keyword"
)

parser.add_argument(
    "--notification_disabled",
    action="store_true",
    help="Disable Telegram notifications"
)

parser.add_argument(
    "--state_file_disabled",
    action="store_true",
    help="Disable storing previously notified items in already_notified_items.txt"
)

args = parser.parse_args()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("vinted_scanner.log", encoding="utf-8"), ],
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Timeout configuration for the requests
timeoutconnection = 30

# List to keep track of already notified items
already_notified_items = {}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3",
    #"DNT": "1",
    #"Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Priority": "u=0, i",
    "Sec-GPC": "1",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "macOS",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}


# Load already notified items to avoid duplicates
def load_already_notified_items():
    try:
        with open(
            "already_notified_items.txt", "r", newline="", errors="ignore"
        ) as f:
            reader = csv.reader(f)

            for row in reader:
                if row:
                    if len(row) != 3:
                        logger.warning(f"Skipping invalid item record: {row}")
                        continue

                    item_id, title, price = row
                    already_notified_items[item_id] = {
                        "title": title,
                        "price": price,
                    }

            logger.info(
                f"Loaded {len(already_notified_items)} already notified item(s) from "
                f"{Path.cwd() / f.name}"
            )
    except FileNotFoundError:
        logger.info("No previous already_notified_items.txt found, starting fresh")
    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


# Save a new notified item to prevent repeated alerts
def save_already_notified_item(item_id, title, price):
    try:
        already_notified_items[item_id] = {
            "title": title,
            "price": price,
        }

        with open("already_notified_items.txt", "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([item_id, title, price])

    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


# Send a Telegram message when a new item is found
def send_telegram_message(item_title, item_price, item_upload_time, item_url, item_image, favourite_count, seller):
    from html import escape

    safe_title = escape(str(item_title))

    if len(safe_title) > 33:
        safe_title = safe_title[:30] + "…"

    safe_url = escape(str(item_url), quote=True)

    caption_lines = [
        f'🔗 <a href="{safe_url}">{safe_title}</a>',
        f"💰 {item_price}" + (f" · ❤️ {favourite_count}" if favourite_count > 0 else ""),
        f"⏳ {item_upload_time}"
    ]

    if seller:

        country_iso_code = (seller.get("country_iso_code") or "").upper()
        country_title = (seller.get("country_title") or "")

        if len(country_iso_code) == 2:
            country_flag = "".join(
                chr(ord(char) + 127397)
                for char in country_iso_code
            )
        else:
            country_flag = ""

        #city = (seller.get("city") or "").strip()

        location = country_flag

        if country_title:
            location += f" {country_title}"

        seller_info = (
            f"👤 {seller.get('login', 'N/D')} · "
            f"⭐ {seller.get('positive_feedback_count', 0)}/{seller.get('feedback_count', 0)} . "
            #f"📦 {seller.get('item_count', 0)} for sale · "
            #f"{seller.get('total_items_count', 0)} total · "
            f"👥 {seller.get('followers_count', 0)}\n"
            f"{location}"
        )

        caption_lines.append("")
        caption_lines.append(seller_info)

    caption = "\n".join(caption_lines)

    try:
        if item_image:
            url = f"https://api.telegram.org/bot{telegram_config.telegram_bot_token}/sendPhoto"
            params = {
                "chat_id": telegram_config.telegram_chat_id,
                "photo": item_image,
                "caption": caption,
                "parse_mode": "HTML",
            }
        else:
            url = f"https://api.telegram.org/bot{telegram_config.telegram_bot_token}/sendMessage"
            params = {
                "chat_id": telegram_config.telegram_chat_id,
                "text": caption,
                "parse_mode": "HTML",
            }

        response = requests.post(
            url,
            params=params,
            timeout=timeoutconnection
        )

        if response.status_code != 200:
            logger.error(
                f"Telegram notification failed. "
                f"Status code: {response.status_code}, Response: {response.text}"
            )
        else:
            logger.info("Telegram notification sent: %s", item_url)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending Telegram message: {e}")


def values_match(actual, expected, match_type="exact"):
    if match_type not in ("exact", "contains"):
        raise ValueError(f"Invalid match type: {match_type}")

    if match_type == "contains":
        if not isinstance(actual, str) or not isinstance(expected, str):
            raise ValueError(
                "Match type 'contains' requires string values"
            )

        return normalize(expected) in normalize(actual)

    if isinstance(actual, str) and isinstance(expected, str):
        return normalize(actual) == normalize(expected)

    # Preserve type distinctions: True must not equal 1.
    return type(actual) is type(expected) and actual == expected


def normalize(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    ).casefold().strip()


def load_item_excluded_keywords():
    keywords = set()

    try:
        with open("excluded_keywords.txt", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                keyword = line.strip()

                if keyword and not keyword.startswith("#"):
                    keywords.add(normalize(keyword))

        logger.info(f"Loaded %s excluded keyword(s) from {Path.cwd() / f.name}", len(keywords))

    except FileNotFoundError:
        logger.info("No excluded_keywords.txt found, no keywords will be excluded")

    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit()

    return keywords


def is_item_excluded_by_keyword(item_id, item_title, item_description, excluded_keywords, log_excluded):
    if not excluded_keywords:
        return False

    text = normalize(f"{item_title} {item_description}")

    for keyword in excluded_keywords:
        if keyword in text:
            if log_excluded:
                logger.info(f"Excluded item [{item_id}] - matching keyword: '{keyword}'")

            return True

    return False


def get_nested_value(data, key):
    """Return (exists, value) for a dot-separated nested key."""
    current = data

    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None

        current = current[part]

    return True, current


def load_filters(type, path="item_filters.yaml"):
    with open(path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
        logger.info(f"Loaded %s [{type}] filter(s) from {Path.cwd() / file.name}", len(config))
    return config

def filter_item(item_id, data_to_filter: dict, query_id: str, filters: dict, filter_type, log_excluded) -> bool:

    filter_label = {"item": "item", "seller": "seller"}.get(filter_type, "item")

    matching_queries = [
        query
        for query in filters.get("filters", [])
        if query.get("query_id") == query_id
    ]

    if not matching_queries:
        if log_excluded:
            logger.info(f"Item [{item_id}] matched {len(matching_queries)} [{filter_label}] filters")

        return True

    for query in matching_queries:
        mode = query.get("mode", "exclude")
        rules = query.get("rules", [])

        if mode == "include":
            # All rules must match.
            for rule in rules:
                if not _item_matches_rule(data_to_filter, rule):
                    if log_excluded:
                        logger.info(
                            f"Excluded item [{item_id}] for not matching "
                            f"[{filter_label}] filter rule [{query_id}][{rule['key']}] in include mode"
                        )
                    return False

        elif mode == "exclude":
            # Any matching rule excludes the item.
            for rule in rules:
                if _item_matches_rule(data_to_filter, rule):
                    if log_excluded:
                        logger.info(
                            f"Excluded item [{item_id}] for matching "
                            f"[{filter_label}] filter rule [{query_id}][{rule['key']}] in exclude mode"
                        )
                    return False

        else:
            raise ValueError(f"Invalid filter mode: {mode}")

        if log_excluded:
            logger.info(f"Item [{item_id}] matched 0 [{filter_label}] filters")

    return True


def _item_matches_rule(item: dict, rule: dict) -> bool:
    """Match an item's value against a rule, supporting nested keys."""
    exists, actual = get_nested_value(item, rule["key"])

    if not exists:
        return False

    return values_match(
        actual,
        rule["value"],
        rule.get("match_type", "exact"),
    )

def get_user_details(user_id, session):
    try:
        url = f"{search_config.vinted_url}/api/v2/users/{user_id}"

        response = session.get(
            url,
            headers=headers,
            timeout=timeoutconnection,
        )

        logger.info("URL triggered: %s", response.url)

        response.raise_for_status()

        data = response.json()

        return data.get("user")

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error(f"Unable to fetch Vinted user {user_id}: {e}")
        return None


def main(log_excluded=False, notification_disabled=False, state_file_disabled=False):
    logger.info("")
    logger.info("========================================")
    logger.info("           VINTED SCANNER")
    logger.info("========================================")
    logger.info("")

    vinted_url = search_config.vinted_url

    # Load the list of already notified items
    #logger.info("Loading the list of already notified items")
    load_already_notified_items()

    # Load excluded keywords
    excluded_keywords = load_item_excluded_keywords()

    # Load item filters
    item_filters = load_filters("item", "item_filters.yaml")

    # Load seller filters
    seller_filters = load_filters("seller", "seller_filters.yaml")

    # Initialize session
    session = requests.Session()
    session.post(vinted_url, headers=headers, timeout=timeoutconnection)

    # Loop through each search query defined in search_config.py
    for params in search_config.queries:

        logger.info(f"========================================")
        logger.info("Processing query [%s]", params.get("query_id"))
        logger.info(f"========================================")
        page = 1

        while page <= getattr(search_config, "pages", 2):
            params["page"] = page

            # Request items from the Vinted API based on the search parameters
            try:
                url = f"{search_config.vinted_api_url}/svc-catalogue/items"

                response = session.get(
                    url,
                    params={k: v for k, v in params.items() if k != "query_id"},
                    headers=headers,
                    timeout=timeoutconnection,
                )

                logger.info("URL triggered: %s", response.url)

                response.raise_for_status()
                data = response.json()
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.error(f"Unable to fetch Vinted page {page}: {e}")
                break

            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                logger.error(
                    "Vinted response did not contain an items list "
                    f"(status={response.status_code}, keys={list(data) if isinstance(data, dict) else 'N/A'})"
                )
                break

            logger.info("API has returned %s item(s) with IDs: %s", len(items), [item["id"] for item in items])

            # Process each item returned in the response

            # excluded_counters = 0
            # already_notified_counter = 0
            # notified_counter = 0

            excluded_counters = []
            already_notified_counter = []
            notified_counter = []

            for item in items:
                item_id = str(item["id"])
                item_title = item["title"]

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

                item_upload_time = get_upload_time(item_id)

                # Skip items whose title or description match any excluded keyword
                if is_item_excluded_by_keyword(item_id, item_title, item_description, excluded_keywords, log_excluded):
                    #excluded_counters += 1
                    excluded_counters.append(item_id)
                    continue

                # Filter using items filters
                if not filter_item(item_id, item, params.get("query_id"), item_filters, "item", log_excluded):
                    #excluded_counters += 1
                    excluded_counters.append(item_id)
                    continue

                # Filter using seller filters now
                user = item.get("user") or {}
                user_id = user.get("id")
                seller = get_user_details(user_id, session)

                if not filter_item(item_id, seller, params.get("query_id"), seller_filters,"seller", log_excluded):
                    #excluded_counters += 1
                    excluded_counters.append(item_id)
                    continue

                # Check if the item has already been notified to prevent sending it again
                if item_id not in already_notified_items:

                    if not notification_disabled:
                        #notified_counter += 1
                        notified_counter.append(item_id)

                        # Send Telegram notifications if configured
                        if telegram_config.telegram_bot_token and telegram_config.telegram_chat_id:
                            send_telegram_message(item_title, item_price, item_upload_time, item_url, item_image,
                                                  favourite_count, seller)

                    # Mark item as notified and save it
                   #already_notified_items[item_id] = item_title, item_price
                    if not state_file_disabled:
                        save_already_notified_item(item_id, item_title, total_amount)

                else:
                    #already_notified_counter += 1
                    already_notified_counter.append(item_id)

            logger.info(f"Already notified items updated at {Path.cwd() / 'already_notified_items.txt'}")
            logger.info(f"========================================")
            logger.info("Items excluded: %s - [%s]", len(excluded_counters),
                        ", ".join(str(item_id) for item_id in excluded_counters))
            logger.info("Items already notified: %s - [%s]", len(already_notified_counter),
                        ", ".join(str(item_id) for item_id in already_notified_counter))
            logger.info("Items notified: %s - [%s]", len(notified_counter), ", ".join(str(item_id) for item_id in notified_counter))

            # If fewer than 96 items were returned, this is the last page
            if len(items) < 96:
                break

            page += 1

    logger.info("Completed query [%s]", params.get("query_id"))
    logger.info(f"========================================")

if __name__ == "__main__":
    main(args.log_excluded, args.notification_disabled)
