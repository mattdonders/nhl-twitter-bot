"""
All functions related to posting messages, files & embeds to Discord.
"""
import requests

from hockeygamebot.helpers.config import config


def send_discord_textonly(msg):
    """ Sends a text-only Discord message.

    Args:
        msg: Message to send to the channel.

    Returns:
        None
    """
    payload = {"content": msg}
    requests.post(config.discord["webhook_url"], json=payload)
