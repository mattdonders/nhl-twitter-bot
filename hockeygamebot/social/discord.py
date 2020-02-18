"""
All functions related to posting messages, files & embeds to Discord.
"""
import logging

import requests

from hockeygamebot.helpers import arguments
from hockeygamebot.helpers.config import config


def send_discord(msg, embed=None, media=None):
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

    # Support multiple Discord Servers
    webhook_url = [webhook_url] if not isinstance(webhook_url, list) else webhook_url

    for url in webhook_url:
        if embed:
            requests.post(url, json=embed)
            continue

        linebreak_msg = f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{msg}"
        payload = {"content": linebreak_msg}

        if not media:
            response = requests.post(url, json=payload)
        else:
            if isinstance(media, list):
                files = dict()
                for idx, image in enumerate(media):
                    files_key = f"file{idx}"
                    files[files_key] = open(image, "rb")
            else:
                files = {"file": open(media, "rb")}
            response = requests.post(url, files=files, data=payload)

        # If we get a non-OK code back from the Discord endpoint, log it.
        if not response.ok:
            logging.warning(response.json())
