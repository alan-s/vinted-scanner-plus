import logging

import requests
from bs4 import BeautifulSoup

import managers.logging_manager as logging_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

# Timeout configuration for the requests
timeout_connection = 30

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3",
    # "DNT": "1",
    # "Connection": "keep-alive",
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

session = requests.Session()


def get_items_from_catalogue_search(search_config, params):
    vinted_url = search_config['vinted']['vinted_url']
    vinted_api_url = search_config['vinted']['vinted_api_url']
    pages = search_config['search']['pages']

    session.post(vinted_url, headers=headers, timeout=timeout_connection)

    page = 1
    items = []

    while page <= pages:

        page_params = {**params, "page": page}

        # Request items from the Vinted API based on the search parameters
        try:
            url = f"{vinted_api_url}/svc-catalogue/items"

            response = session.get(
                url,
                params={k: v for k, v in page_params.items() if k != "query_id"},
                headers=headers,
                timeout=timeout_connection,
            )

            logger.info("Vinted search API called: %s", response.url)

            response.raise_for_status()
            data = response.json()

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error("Unable to fetch Vinted page %s: %s", page, e)
            return None

        # Extract and validate items
        new_items = data.get("items") if isinstance(data, dict) else None

        if not isinstance(new_items, list):
            logger.error(
                "Vinted response did not contain an items list "
                "(status=%s, keys=%s)",
                response.status_code,
                list(data) if isinstance(data, dict) else "N/A"
            )
            return None

        # Add current page items to the existing collection
        items.extend(new_items)

        logger.info(
            "Vinted page %d returned %d item(s)", page, len(new_items)
        )

        # If fewer than 96 items were returned, this is the last page
        if len(new_items) < 96:
            break

        page += 1

    return items


def get_item_description_and_upload_datetime(search_config, item_id):
    vinted_url = search_config['vinted']['vinted_url']

    try:
        url = f"{vinted_url}/items/{item_id}"

        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )

        logger.info("Vinted item endpoint called: %s", response.url)

    except requests.exceptions.HTTPError as e:
        logger.error(e.args[0], exc_info=True)
        return None

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        upload_date = soup.find(
            "div",
            attrs={"itemprop": "upload_date"}
        )

        description = soup.find(
            "div",
            attrs={"itemprop": "description"}
        )
    except Exception as e:
        logger.error(e, exc_info=True)
        return None

    return (
        upload_date.get_text(strip=True) if upload_date else None,
        description.get_text(strip=True) if description else None
    )


def get_user_details(search_config, user_id):
    vinted_url = search_config['vinted']['vinted_url']

    try:
        url = f"{vinted_url}/api/v2/users/{user_id}"

        response = session.get(
            url,
            headers=headers,
            timeout=timeout_connection,
        )

        logger.info("Vinted seller API called: %s", response.url)

        response.raise_for_status()

        data = response.json()

        return data.get("user")

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error(f"Unable to fetch Vinted seller {user_id}: {e}")
        return None


def close_session():
    session.close()
