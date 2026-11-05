import logging

import requests
from bs4 import BeautifulSoup

import config.search_config as search_cfg
from managers import logging_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

# Timeout configuration for the requests
timeout_connection = 30

vinted_url = search_cfg.vinted_url

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

# Initialise session
session = requests.Session()
session.post(vinted_url, headers=headers, timeout=timeout_connection)

def get_items_from_catalogue_search(params):

    items = {}

    page = 1

    while page <= getattr(search_cfg, "pages", 2):
        params["page"] = page

        # Request items from the Vinted API based on the search parameters
        try:
            url = f"{search_cfg.vinted_api_url}/svc-catalogue/items"

            response = session.get(
                url,
                params={k: v for k, v in params.items() if k != "query_id"},
                headers=headers,
                timeout=timeout_connection,
            )

            logger.info("Vinted search API called: %s", response.url)

            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error(f"Unable to fetch Vinted page {page}: {e}")
            return None

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            logger.error(
                "Vinted response did not contain an items list "
                f"(status={response.status_code}, keys={list(data) if isinstance(data, dict) else 'N/A'})"
            )

        # If fewer than 96 items were returned, this is the last page
        if len(items) < 96:
            return items
        page += 1

    return None


def get_item_upload_datetime(item_id):

    try:
        url = f"{search_cfg.vinted_url}/items/{item_id}"

        response = requests.get(
            f"https://www.vinted.co.uk/items/{item_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )

        logger.info("Vinted seller API called: %s", response.url)

    except requests.exceptions.HTTPError as e:
        logger.error(e.args[0], exc_info=True)
        return None

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        element = soup.find(
            "div",
            attrs={"itemprop": "upload_date"}
        )
    except Exception as e:
        logger.error(e, exc_info=True)
        return None

    return element.get_text(strip=True) if element else None


def get_user_details(user_id):

    try:
        url = f"{search_cfg.vinted_url}/api/v2/users/{user_id}"

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
