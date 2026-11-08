import logging

import requests

import managers.logging_manager as logging_manager

logging_manager.init_logger()
logger = logging.getLogger(__name__)

# Timeout configuration for the requests
timeout_connection = 30


def send_telegram_message(notification_config, item_id, item_title, item_desc, item_price, item_upload_time, item_url,
                          item_image, favourite_count, seller) -> bool:
    from html import escape

    telegram_bot_token = notification_config['telegram']['telegram_bot_token']
    telegram_chat_id = notification_config['telegram']['telegram_chat_id']
    include_desc = notification_config['message']['include_description']

    safe_title = escape(str(item_title))

    if len(safe_title) > 33:
        safe_title = safe_title[:30] + "…"

    safe_url = escape(str(item_url), quote=True)

    caption_lines = [
        f'🔗  <a href="{safe_url}">{safe_title}</a>',
        f"💰  {item_price}" + (f"    ❤️  {favourite_count}" if favourite_count > 0 else ""),
        f"⏳  {item_upload_time}"
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

        location = country_flag

        if country_title:
            location += f"  {country_title}"

        seller_info = (
            f"👤  {seller.get('login', 'N/D')}    "
            f"⭐  {seller.get('positive_feedback_count', 0)}/{seller.get('feedback_count', 0)}   "
            f"👥  {seller.get('followers_count', 0)}\n"
            f"{location}"
            f"{"\n\n" + item_desc if include_desc else ""}"
        )

        caption_lines.append("")
        caption_lines.append(seller_info)

    caption = "\n".join(caption_lines)

    try:
        if item_image:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendPhoto"
            params = {
                "chat_id": telegram_chat_id,
                "photo": item_image,
                "caption": caption,
                "parse_mode": "HTML",
            }
        else:
            url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            params = {
                "chat_id": telegram_chat_id,
                "text": caption,
                "parse_mode": "HTML",
            }

        response = requests.post(
            url,
            params=params,
            timeout=timeout_connection
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
