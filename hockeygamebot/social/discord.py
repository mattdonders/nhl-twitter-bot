"""
All functions related to posting messages, files & embeds to Discord.
"""
import logging

import requests

from hockeygamebot.helpers import arguments
from hockeygamebot.helpers.config import config


def send_discord(msg, media=None):
    """ Sends a text-only Discord message.

    Args:
        msg: Message to send to the channel.
        media: Any media to be sent to the Webhook

    Returns:
        None
    """

    args = arguments.get_arguments()

    discordenv = "debug" if args.debugsocial else "prod"
    discord_config = config.discord[discordenv]
    webhook_url = discord_config["webhook_url"]

    linebreak_msg = f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{msg}"
    payload = {"content": linebreak_msg}

    if not media:
        response = requests.post(webhook_url, json=payload)
    else:
        files = {"file": open(media, "rb")}
        response = requests.post(webhook_url, files=files, data=payload)

    # If we get a non-OK code back from the Discord endpoint, log it.
    if not response.ok:
        logging.warning(response.json())
