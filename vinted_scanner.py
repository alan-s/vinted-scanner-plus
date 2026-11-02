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
    "--disable_notifications",
    action="store_true",
    help="Disable Telegram notifications"
)

parser.add_argument(
    "--disable_state_file",
    action="store_true",
    help="Disable storing previously notified items in already_notified_items.csv"
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
        with open("already_notified_items.csv", "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f, strict=True)

            for row in reader:
                    if row:

                        item_id, title, price = row
                        already_notified_items[item_id] = {
                            "title": title,
                            "price": price,
                        }
            logger.info(
                f"Loaded {len(already_notified_items)} already notified item(s) from "
                f"{Path.cwd() / f.name}"
                )
            logger.info(f"Already notified items: [{', '.join(already_notified_items.keys())}]")

    except FileNotFoundError:
        logger.info("No previous already_notified_items.csv found, starting fresh")
    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)
    except (csv.Error, UnicodeDecodeError, ValueError) as e:
        logger.error("CSV validation failed. Error: %s in row %s", e, row)
        sys.exit(1)


# Save a new notified item to prevent repeated alerts
def save_already_notified_item(item_id, title, price):
    try:
        already_notified_items[item_id] = {
            "title": title,
            "price": price,
        }

        with open("already_notified_items.csv", "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([item_id, title, price])

    except IOError as e:
        logger.error(e, exc_info=True)
        sys.exit(1)


# Send a Telegram message when a new item is found
def send_telegram_message(item_id, item_title, item_price, item_upload_time, item_url, item_image, favourite_count, seller) -> bool:
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
                f"Telegram notification failed for item [{item_id}]. "
                f"Status code: {response.status_code}, Response: {response.text}"
            )
            return False
        else:
            logger.info("Telegram notification sent for item [%s]. API called: %s", item_id, url)
            return True

    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending Telegram message: {e}")

        return False

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
        if log_excluded:
            logger.info(f"Item [{item_id}] matched 0 excluded words")

        return False

    text = normalize(f"{item_title} {item_description}")

    for keyword in excluded_keywords:
        if keyword in text:
            if log_excluded:
                logger.info(f"Excluded item [{item_id}] for matching excluded keyword '{keyword}'")

            return True

    return False

def load_filters(filter_type, path="item_filters.yaml"):
    try:
        with open(path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        validate_filters(config)

    except yaml.YAMLError as e:
        logger.error("Invalid YAML syntax. Error: %s",e)
        sys.exit(1)

    except ValueError as e:
        logger.error("Invalid filter configuration in %s. Error: %s",path, e)
        sys.exit(1)

    # No YAML content means no filters
    config = config or {"filters": []}

    logger.info(
        "Loaded %s [%s] filter(s) from %s",
        len(config["filters"]),
        filter_type,
        Path(path).resolve(),
    )
    return config

def validate_filters(config):
    """Validate YAML filter configuration if content is defined."""

    # Empty YAML content is valid
    if config is None:
        return True

    def check_keys(data, required_keys, context):
        if not isinstance(data, dict):
            raise ValueError(f"{context} must be a mapping")

        missing = required_keys - data.keys()
        unexpected = data.keys() - required_keys

        if missing:
            raise ValueError(f"{context}: missing keys {sorted(missing)}")
        if unexpected:
            raise ValueError(f"{context}: unexpected keys {sorted(unexpected)}")

    check_keys(config, {"filters"}, "Root")

    if not isinstance(config["filters"], list):
        raise ValueError("'filters' must be a list")

    for i, item in enumerate(config["filters"]):
        context = f"filters[{i}]"
        check_keys(item, {"query_id", "mode", "rules"}, context)

        if not isinstance(item["mode"], str) or item["mode"] not in {"include", "exclude"}:
            raise ValueError(
                f"{context}.mode must be a string: 'include' or 'exclude'"
            )

        if not isinstance(item["rules"], list):
            raise ValueError(f"{context}.rules must be a list")

        for j, rule in enumerate(item["rules"]):
            rule_context = f"{context}.rules[{j}]"
            check_keys(rule, {"key", "value", "match_type"}, rule_context)

            if (
                not isinstance(rule["match_type"], str)
                or rule["match_type"] not in {"exact", "contains"}
            ):
                raise ValueError(
                    f"{rule_context}.match_type must be a string: "
                    "'exact' or 'contains'"
                )

    return True


def filter_item(item_id, data_to_filter: dict, query_id: str, filters: dict, filter_type, log_excluded) -> bool:

    filter_label = {"item": "item", "seller": "seller"}.get(filter_type, "item")

    matching_queries = [
        query
        for query in filters.get("filters", [])
        if query.get("query_id") == query_id
    ]

    if not matching_queries:
        if log_excluded:
            logger.info(f"Item [{item_id}] in scope for {len(matching_queries)} [{filter_label}] filter(s)")

        return True

    if log_excluded:
        logger.info(f"Item [{item_id}] in scope for {len(matching_queries)} [{filter_label}] filter(s)")

    for query in matching_queries:
        mode = query.get("mode", "exclude")
        rules = query.get("rules", [])

        if mode == "include":
            # All rules must match.
            for rule in rules:
                if log_excluded:
                    logger.info(
                        f"Checking item [{item_id}] against [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")

                if not _item_matches_rule(data_to_filter, rule):
                    if log_excluded:
                        logger.info(f"[ FAIL ✗ ] excluded item [{item_id}] for not matching [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")
                    return False
                else:
                    if log_excluded:
                        logger.info(f"[ PASS ✓ ] item [{item_id}] not excluded for current rule. Checking next rule if any")

        elif mode == "exclude":
            # Any matching rule excludes the item.
            for rule in rules:
                if log_excluded:
                    logger.info(
                        f"Checking item [{item_id}] against [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")

                if _item_matches_rule(data_to_filter, rule):
                    if log_excluded:
                        logger.info(f"[ FAIL ✗ ] excluded item [{item_id}] for matching [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")
                    return False
                else:
                    if log_excluded:
                        logger.info(f"[ PASS ✓ ] item [{item_id}] not excluded for current rule. Checking next rule if any")

        else:
            raise ValueError(f"Invalid filter mode: {mode}")

    return True


def _item_matches_rule(item: dict, rule: dict) -> bool:
    """Match an item's value against a rule, supporting nested keys."""
    exists, actual = get_nested_value(item, rule["key"])
    expected = rule["value"]
    match_type = rule.get("match_type", "exact")

    if not exists:
        logger.info(f"Key [{rule['key']}] not found in item [{item['id']}]")
        return False

    logger.info(
        f"Expected value [{expected}], actual value [{actual}], match type used [{match_type}]")

    return values_match(actual, expected, match_type)


def values_match(actual, expected, match_type="exact"):
    if match_type not in ("exact", "contains"):
        raise ValueError(f"Invalid match type: {match_type}")

    if match_type == "contains":
        if not isinstance(actual, str) or not isinstance(expected, str):
            raise ValueError("Match type 'contains' requires string values")

        return normalize(expected) in normalize(actual)

    if isinstance(actual, str) and isinstance(expected, str):
        return normalize(actual) == normalize(expected)

    # Preserve type distinctions: True must not equal 1.
    return type(actual) is type(expected) and actual == expected


def get_nested_value(data, key):
    """Return (exists, value) for a dot-separated nested key."""
    current = data

    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None

        current = current[part]

    return True, current

def get_user_details(user_id, session):
    try:
        url = f"{search_config.vinted_url}/api/v2/users/{user_id}"

        response = session.get(
            url,
            headers=headers,
            timeout=timeoutconnection,
        )

        logger.info("Vinted seller API called: %s", response.url)

        response.raise_for_status()

        data = response.json()

        return data.get("user")

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error(f"Unable to fetch Vinted seller {user_id}: {e}")
        return None


def main(log_excluded=False, disable_notifications=False, disable_state_file=False):
    logger.info("")
    logger.info("========================================")
    logger.info("           VINTED SCANNER")
    logger.info("========================================")
    logger.info("")
    logger.info(f"Launched with the followings args: {" ".join(sys.argv[1:])}")

    vinted_url = search_config.vinted_url

    # Load the list of already notified items
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

        query_log_printer(params.get("query_id"), "Started")
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

                logger.info("Vinted search API called: %s", response.url)

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

            logger.info("Vinted search API has returned %s item(s) with IDs: %s", len(items), [item["id"] for item in items])

            # Process each item returned in the response
            excluded_items = []
            previously_notified_items = []
            notified_items = []
            failed_notified_items = []

            for item in items:

                item_id = str(item["id"])
                item_title = item["title"]

                item_log_printer(item_id, "Started")

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
                if log_excluded:
                    logger.info(f"Checking item [{item_id}] against excluded words")
                if is_item_excluded_by_keyword(item_id, item_title, item_description, excluded_keywords, log_excluded):
                    excluded_items.append(item_id)
                    item_log_printer(item_id, "Completed")
                    continue

                # Filter using items filters
                if log_excluded:
                    logger.info(f"Checking item [{item_id}] against [item] filters")
                if not filter_item(item_id, item, params.get("query_id"), item_filters, "item", log_excluded):
                    excluded_items.append(item_id)
                    item_log_printer(item_id, "Completed")
                    continue

                logger.info(f"Getting seller details for item [{item_id}]")
                user = item.get("user") or {}
                user_id = user.get("id")
                seller = get_user_details(user_id, session)

                # Filter using seller filters now
                if log_excluded:
                    logger.info(f"Checking item [{item_id}] against [seller] filters")
                if not filter_item(item_id, seller, params.get("query_id"), seller_filters,"seller", log_excluded):
                    excluded_items.append(item_id)
                    item_log_printer(item_id, "Completed")
                    continue

                if log_excluded:
                    logger.info(f"Item [{item_id}] meets all selection filters and no exclusions apply")

                # Check if the item has already been notified to prevent sending it again
                if item_id not in already_notified_items:

                    if not disable_notifications:

                        # Send Telegram notifications if configured
                        if telegram_config.telegram_bot_token and telegram_config.telegram_chat_id:
                            if send_telegram_message(item_id, item_title, item_price, item_upload_time, item_url, item_image, favourite_count, seller):
                                notified_items.append(item_id)
                            else:
                                failed_notified_items.append(item_id)

                        # Mark item as notified and save it
                        if not disable_state_file:
                            save_already_notified_item(item_id, item_title, total_amount)
                            logger.info(f"Recorded notification for item [{item_id}] in 'already_notified_items.csv'")
                        else:
                            logger.info(f"Not recording notification for item [{item_id}] in 'already_notified_items.csv'; '--disable_state_file' set")

                    else:
                        logger.info(f"No notification sent for item [{item_id}]; '--disable_notifications' set")

                else:
                    logger.info(f"No notification will be sent on this run for item [{item_id}]; it has been previously notified ('already_notified_items.csv')")
                    previously_notified_items.append(item_id)

                item_log_printer(item_id, "Completed")

            logger.info("Total items matched: %s - [%s]", len(items),
                        ", ".join([str(item["id"]) for item in items]))
            logger.info("Items excluded: %s - [%s]", len(excluded_items),
                        ", ".join(str(item_id) for item_id in excluded_items))
            logger.info("Items previously notified: %s - [%s]", len(previously_notified_items),
                        ", ".join(str(item_id) for item_id in previously_notified_items))
            logger.info("Items notified: %s - [%s]", len(notified_items), ", ".join(str(item_id) for item_id in notified_items))
            logger.info("Items failed to notify: %s - [%s]", len(failed_notified_items),
                        ", ".join(str(item_id) for item_id in failed_notified_items))
            logger.info(f"Items recorded as notified: {len(notified_items)} - [{', '.join(str(item_id) for item_id in notified_items)}]")

            # If fewer than 96 items were returned, this is the last page
            if len(items) < 96:
                break

            page += 1

    query_log_printer(params.get("query_id"), "Completed")

def query_log_printer(query_id, state):
    logger.info(f"================================================================================")
    logger.info("%s processing search query [%s]", state, query_id)
    logger.info(f"================================================================================")

def item_log_printer(item_id, state):
    logger.info(f"--------------------------------------------------------------------------------")
    logger.info("%s processing item [%s]", state,item_id)
    logger.info(f"--------------------------------------------------------------------------------")

if __name__ == "__main__":
    main(args.log_excluded, args.disable_notifications, args.disable_state_file)
