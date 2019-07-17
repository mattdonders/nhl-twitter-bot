"""
All functions related to posting messages, files & embeds to Discord.
"""
import logging

import requests

from hockeygamebot.helpers.config import config


def send_discord_textonly(msg):
    """ Sends a text-only Discord message.

    Args:
        msg: Message to send to the channel.

    Returns:
        None
    """
    linebreak_msg = f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{msg}"
    payload = {"content": linebreak_msg}
    response = requests.post(config.discord["webhook_url"], json=payload)
    if not response.ok:
        logging.warning(response.json())
