#!/usr/bin/env python3
import argparse
import csv
import re
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

    operators = {
        "equals",
        "contains",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
        "exists",
        "is_null",
        "is_empty",
    }

    operators_without_value = {"exists", "is_null", "is_empty"}

    numeric_operators = {
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
    }

    def check_keys(data, required_keys, optional_keys, context):
        if not isinstance(data, dict):
            raise ValueError(f"{context} must be a mapping")

        missing = required_keys - data.keys()
        unexpected = data.keys() - (required_keys | optional_keys)

        if missing:
            raise ValueError(f"{context}: missing keys {sorted(missing)}")

        if unexpected:
            raise ValueError(f"{context}: unexpected keys {sorted(unexpected)}")

    def is_number(value):
        # bool is a subclass of int in Python, so explicitly exclude it.
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    check_keys(config, {"filters"}, set(), "Root")

    if not isinstance(config["filters"], list):
        raise ValueError("'filters' must be a list")

    for i, item in enumerate(config["filters"]):
        context = f"filters[{i}]"

        check_keys(
            item,
            {"query_id", "mode", "rules"},
            set(),
            context,
        )

        if not isinstance(item["query_id"], str) or not item["query_id"]:
            raise ValueError(f"{context}.query_id must be a non-empty string")

        if item["mode"] not in {"include", "exclude"}:
            raise ValueError(
                f"{context}.mode must be 'include' or 'exclude'"
            )

        if not isinstance(item["rules"], list) or not item["rules"]:
            raise ValueError(f"{context}.rules must be a non-empty list")

        for j, rule in enumerate(item["rules"]):
            rule_context = f"{context}.rules[{j}]"

            # Determine whether value is required based on the operator.
            if not isinstance(rule, dict):
                raise ValueError(f"{rule_context} must be a mapping")

            operator = rule.get("operator")

            if not isinstance(operator, str) or operator not in operators:
                raise ValueError(
                    f"{rule_context}.operator must be one of: "
                    f"{sorted(operators)}"
                )

            required_keys = {"key", "operator"}

            if operator not in operators_without_value:
                required_keys.add("value")

            check_keys(
                rule,
                required_keys,
                set(),
                rule_context,
            )

            if not isinstance(rule["key"], str) or not rule["key"]:
                raise ValueError(
                    f"{rule_context}.key must be a non-empty string"
                )

            # Validate numeric operators.
            if operator in numeric_operators:
                value = rule["value"]

                if operator == "between":
                    if not isinstance(value, dict):
                        raise ValueError(
                            f"{rule_context}.value must be a mapping "
                            "with 'min' and 'max' for operator 'between'"
                        )

                    check_keys(
                        value,
                        {"min", "max"},
                        set(),
                        f"{rule_context}.value",
                    )

                    if not is_number(value["min"]) or not is_number(value["max"]):
                        raise ValueError(
                            f"{rule_context}.value.min and max must be numeric"
                        )

                    if value["min"] > value["max"]:
                        raise ValueError(
                            f"{rule_context}.value.min cannot exceed max"
                        )

                elif not is_number(value):
                    raise ValueError(
                        f"{rule_context}.value must be numeric "
                        f"for operator '{operator}'"
                    )

            # Validate string operators (including CSV values).
            elif operator in {"equals", "contains"}:
                value = rule["value"]

                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"{rule_context}.value must be a non-empty string "
                        f"for operator '{operator}'"
                    )

                # Validate comma-separated values.
                expected_values = [v.strip() for v in value.split(",")]

                if any(not v for v in expected_values):
                    raise ValueError(
                        f"{rule_context}.value contains an empty CSV value"
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
                        f"Checking item [{item_id}] against [{filter_label}] filter rule [{query_id}][{rule['key']}][{rule['value']}] in [{mode}] mode")

                if not item_matches_rule(data_to_filter, rule):
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

                if item_matches_rule(data_to_filter, rule):
                    if log_excluded:
                        logger.info(f"[ FAIL ✗ ] excluded item [{item_id}] for matching [{filter_label}] filter rule [{query_id}, {rule['key']}, {rule['value']}] in [{mode}] mode")
                    return False
                else:
                    if log_excluded:
                        logger.info(f"[ PASS ✓ ] item [{item_id}] not excluded for current rule. Checking next rule if any")

        else:
            raise ValueError(f"Invalid filter mode: {mode}")

    return True


def item_matches_rule(item: dict, rule: dict) -> bool:
    """Match an item's value against a rule, supporting nested keys."""
    key = rule["key"]
    operator = rule["operator"]

    exists, actual = get_nested_value(item, key)

    if operator == "exists":
        return exists

    if not exists:
        logger.info(f"Key [{key}] not found in item [{item.get('id')}]")
        return False

    if operator == "is_null":
        return actual is None

    if operator == "is_empty":
        return isinstance(actual, (str, list, dict)) and len(actual) == 0

    rule_value = rule["value"]

    logger.info(
        f"Rule value(s): [{rule_value}], actual value: [{actual}], operator: [{operator}]")

    return values_match(actual, rule_value, operator)


def values_match(actual, rule_value, operator="equals"):
    """Compare two values using the specified operator."""

    valid_operators = (
        "equals",
        "contains",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
    )

    if operator not in valid_operators:
        raise ValueError(f"Invalid operator: {operator}")

    # String operators
    if operator in ("equals", "contains"):

        if not isinstance(actual, str) or not isinstance(rule_value, str):
            raise ValueError(
                f"Operator '{operator}' requires string values"
            )

        # Support comma-separated rule values.
        # Any one of the values matching is sufficient.
        rule_values = [
            value.strip()
            for value in rule_value.split(",")
            if value.strip()
        ]

        if operator == "equals":
            return any(
                normalize(value) == normalize(actual)
                for value in rule_values
            )

        if operator == "contains":
            return any(
                re.search(
                    r"\b" + re.escape(normalize(value)) + r"\b",
                    normalize(actual)
                )
                for value in rule_values
            )

    # Numeric operators
    if operator in (
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "between",
    ):
        # bool is a subclass of int in Python, so explicitly exclude it.
        if (
            isinstance(actual, bool)
            or isinstance(rule_value, bool)
            or not isinstance(actual, (int, float))
        ):
            raise ValueError(f"Operator '{operator}' requires numeric values")

        if operator == "between":
            if not isinstance(rule_value, dict) or set(rule_value.keys()) != {"min", "max"}:
                raise ValueError(
                    "Operator 'between' requires a value with 'min' and 'max' keys"
                )

            minimum = rule_value["min"]
            maximum = rule_value["max"]

            if (
                isinstance(minimum, bool)
                or isinstance(maximum, bool)
                or not isinstance(minimum, (int, float))
                or not isinstance(maximum, (int, float))
            ):
                raise ValueError("'between' min and max must be numeric")

            if minimum > maximum:
                raise ValueError("'between' minimum cannot exceed maximum")

            return minimum <= actual <= maximum

        if (
            isinstance(rule_value, bool)
            or not isinstance(rule_value, (int, float))
        ):
            raise ValueError(f"Operator '{operator}' requires numeric values")

        if operator == "greater_than":
            return actual > rule_value

        if operator == "greater_than_or_equal":
            return actual >= rule_value

        if operator == "less_than":
            return actual < rule_value

        if operator == "less_than_or_equal":
            return actual <= rule_value

    # Equality operators
    if isinstance(actual, str) and isinstance(rule_value, str):
        return normalize(actual) == normalize(rule_value)

    # Preserve type distinctions: True must not equal 1.
    return type(actual) is type(rule_value) and actual == rule_value


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

    # Load item filters
    item_filters = load_filters("item", "item_filters.yaml")

    # Load seller filters
    seller_filters = load_filters("seller", "seller_filters.yaml")

    # Initialise session
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
            candidate_items = []
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

                # Filter using items filters
                if log_excluded:
                    logger.info(f"Checking item [{item_id}] against optional [item] filters")
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
                    logger.info(f"Checking item [{item_id}] against optional [seller] filters")
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
                        candidate_items.append(item_id)
                        logger.info(f"No notification sent for item [{item_id}]; '--disable_notifications' set")

                else:
                    logger.info(f"No notification will be sent on this run for item [{item_id}]; it has been previously notified ('already_notified_items.csv')")
                    previously_notified_items.append(item_id)

                item_log_printer(item_id, "Completed")

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
