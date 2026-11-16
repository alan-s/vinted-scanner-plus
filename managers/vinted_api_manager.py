import logging

import requests
from bs4 import BeautifulSoup

import managers.logging_manager as logging_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

# Timeout configuration for the requests
TIMEOUT_CONNECTION = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/png,image/svg+xml,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-GPC": "1",
    "Priority": "u=0, i",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Platform": "web",
    "x-next-app": "marketplace-web",
    "Locale": "en-GB",
}


def initialise_vinted_session(search_config):
    # Initialise session
    vinted_url = search_config['vinted']['vinted_url']
    api_headers = build_api_headers(search_config)

    try:
        session = requests.Session()

        response = session.get(
            url=vinted_url,
            headers=HEADERS,
            timeout=TIMEOUT_CONNECTION,
        )

        anon_id = session.cookies.get("anon_id")

        if anon_id:
            # Add X-Anon-Id to all subsequent session requests
            api_headers["X-Anon-Id"] = anon_id

            session.headers.update(api_headers)

        response.raise_for_status()

        return session

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Unable to initialise Vinted session: %s", e)
        return None


def build_api_headers(search_config):
    vinted_url = search_config['vinted']['vinted_url']
    locale = search_config['vinted']['locale']

    request_headers = {
        **API_HEADERS,
        "User-Agent": HEADERS["User-Agent"],
        "Accept-Language": HEADERS["Accept-Language"],
        "Origin": vinted_url,
        "Referer": f"{vinted_url}/",
    }

    if locale:
        request_headers["Locale"] = locale

    return request_headers


def get_items_from_catalogue_search(session, search_config, query_params):
    url = f"{search_config['vinted']['vinted_api_url']}/svc-catalogue/items"
    pages = search_config['search']['pages']
    per_page = search_config['search']['per_page']
    query_params = {k: v for k, v in query_params.items() if k != "query_id"}

    page = 1
    items = []

    while page <= pages:

        query_params = {**query_params, "per_page": per_page, "page": page}

        # Request items from the Vinted API based on the search parameters
        try:

            response = session.get(url=url, params=query_params)

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
        data = response.json()

        # If fewer than 96 items were returned, this is the last page
        if len(new_items) < 96:
            break

        page += 1

    return items


def get_item_description_and_upload_datetime(session, search_config, item_id):
    vinted_url = search_config['vinted']['vinted_url']

    try:
        url = f"{vinted_url}/items/{item_id}"

        response = session.get(url=url)

        logger.info("Vinted item endpoint called: %s", response.url)

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error("Unable to fetch Vinted item page: %s", e)
        return None

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        description = soup.find(
            "div",
            attrs={"itemprop": "description"}
        )
        upload_date = soup.find(
            "div",
            attrs={"itemprop": "upload_date"}
        )
    except Exception as e:
        logger.error(e, exc_info=True)
        return None

    return (
        description.get_text(strip=True) if description else None,
        upload_date.get_text(strip=True) if upload_date else None
    )


def get_user_details(session, search_config, user_id):
    vinted_url = search_config['vinted']['vinted_url']

    try:
        url = f"{vinted_url}/api/v2/users/{user_id}"

        response = session.get(url=url)

        logger.info("Vinted seller API called: %s", response.url)

        response.raise_for_status()

        data = response.json()

        return data.get("user")

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error(f"Unable to fetch Vinted seller {user_id}: {e}")
        return None


def close_session(session):
    if session is not None:
        session.close()
        logger.info("Vinted session closed")
