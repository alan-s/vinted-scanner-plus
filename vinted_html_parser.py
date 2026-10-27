import logging
import requests

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def get_upload_time(item_id):

    try:
        response = requests.get(
            f"https://www.vinted.co.uk/items/{item_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )

    except requests.exceptions.HTTPError as e:
        logger.error(e.args[0], exc_info=True)

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
