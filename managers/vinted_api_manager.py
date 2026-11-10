import logging
import requests
from bs4 import BeautifulSoup
import managers.logging_manager as logging_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

# Timeout configuration for the requests
timeout_connection = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
        "image/webp,image/png,image/svg+xml,*/*;q=0.8"
    ),
    #"Accept-Language": "en-GB,en;q=0.9",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3",
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

api_headers = {}


def initialise_vinted_session(search_config):

    # Initialise session
    vinted_url = search_config['vinted']['vinted_url']
    api_headers.update(build_api_headers(search_config))

    session = requests.Session()

    if session is None:
        raise RuntimeError("Session has not been initialised")

    response = session.get(
        url=vinted_url,
        headers=HEADERS,
        timeout=timeout_connection,
    )

    response.raise_for_status()

    return session

def build_api_headers(search_config):

    vinted_url = search_config['vinted']['vinted_url']

    api_headers.update({
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": HEADERS["Accept-Language"],
        "Platform": "web",
        "x-next-app": "marketplace-web",
        "Origin": vinted_url,
        "Referer": f"{vinted_url}/",
        }
    )

    # locale = getattr(search_config, "vinted_locale", None)
    # if locale:
    #     api_headers["Locale"] = locale


    return api_headers

def get_items_from_catalogue_search(session, anon_id, search_config, params):

    vinted_api_url = search_config['vinted']['vinted_api_url']
    url = f"{vinted_api_url}/svc-catalogue/items"
    pages = search_config['search']['pages']
    params = {k: v for k, v in params.items() if k != "query_id"}
    api_headers["X-Anon-Id"] = anon_id

    if session is None:
        raise RuntimeError("Session has not been initialised")

    page = 1
    items = []

    while page <= pages:

        params = {**params, "page": page}

        # Request items from the Vinted API based on the search parameters
        try:

            response = session.get(
                url=url,
                params=params,
                headers=api_headers,
                timeout=timeout_connection,
            )

            logger.info("Vinted search API called: %s", response.url)

            logger.info("Request URL: %s", response.url)
            logger.info("HTTP status: %s", response.status_code)
            logger.info("Response length: %s", len(response.content))
            logger.info("Response headers: %s", dict(response.headers))

            # Exclude potentially sensitive headers
            safe_headers = {
                k: v for k, v in response.request.headers.items()
                if k.lower() not in ("cookie", "authorization")
            }

            logger.info("Outgoing request headers: %s", safe_headers)

            data = response.json()

            logger.info("Response keys: %s", list(data.keys()))
            logger.info("Items returned: %s", len(data.get("items", [])))
            logger.info("Response body: %s", response.text[:3000])

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


def get_item_description_and_upload_datetime(session, anon_id, search_config, item_id):

    vinted_url = search_config['vinted']['vinted_url']
    api_headers["X-Anon-Id"] = anon_id

    if session is None:
        raise RuntimeError("Session has not been initialised")

    try:
        url = f"{vinted_url}/items/{item_id}"

        response = requests.get(
            url=url,
            headers=api_headers,
            timeout=timeout_connection,
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


def get_user_details(session, anon_id, search_config, user_id):

    vinted_url = search_config['vinted']['vinted_url']
    api_headers["X-Anon-Id"] = anon_id

    if session is None:
        raise RuntimeError("Session has not been initialised")

    try:
        url = f"{vinted_url}/api/v2/users/{user_id}"

        response = session.get(
            url=url,
            headers=api_headers,
            timeout=timeout_connection,
        )

        logger.info("Vinted seller API called: %s", response.url)

        response.raise_for_status()

        data = response.json()

        return data.get("user")

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.error(f"Unable to fetch Vinted seller {user_id}: {e}")
        return None


# def close_session():
#
#     if session is None:
#         raise RuntimeError("Session has not been initialised")
#
#     session.close()
