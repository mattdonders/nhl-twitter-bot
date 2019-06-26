"""
This module contains all utility functions such as
configuration, log management & other miscellaneous.
"""

import logging
import os
from datetime import datetime, timedelta

import yaml

from hockeygamebot.definitions import CONFIG_PATH, LOGS_PATH
from hockeygamebot.helpers import arguments


def load_config():
    """ Loads the configuration yaml file and returns a yaml object / dictionary..

    Args:
        None

    Returns:
        A yaml (dictionary) object.
    """

    with open(CONFIG_PATH) as ymlfile:
        config = yaml.load(ymlfile, Loader=yaml.BaseLoader)

    return config


def setup_logging():
    """Configures application logging and prints the first three log lines."""

    # pylint: disable=line-too-long

    # logger = logging.getLogger(__name__)
    args = arguments.parse_arguments()

    log_file_name = datetime.now().strftime(
        load_config()["script"]["log_file_name"] + "-%Y%m%d%H%M%s.log"
    )
    log_file = os.path.join(LOGS_PATH, log_file_name)
    if args.console and args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
        )
    elif args.console:
        logging.basicConfig(
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


def clock_emoji(time):
    """
    Accepts an hour (in 12 or 24 hour format) and returns the correct clock emoji.

    Args:
        time: 12 or 24 hour format time (:00 or :30)

    Returns:
        clock: corresponding clock emoji.
    """

    hour_emojis = {
        "0": "🕛",
        "1": "🕐",
        "2": "🕑",
        "3": "🕒",
        "4": "🕓",
        "5": "🕔",
        "6": "🕕",
        "7": "🕖",
        "8": "🕗",
        "9": "🕘",
        "10": "🕙",
        "11": "🕚",
    }

    half_emojis = {
        "0": "🕧",
        "1": "🕜",
        "2": "🕝",
        "3": "🕞",
        "4": "🕟",
        "5": "🕠",
        "6": "🕡",
        "7": "🕢",
        "8": "🕣",
        "9": "🕤",
        "10": "🕥",
        "11": "🕦",
    }

    # Split up the time to get the hours & minutes sections
    time_split = time.split(":")
    hour = int(time_split[0])
    minutes = time_split[1].split(" ")[0]

    # We need to adjust the hour if we use 24 hour-time.
    hour = 12 - hour if hour > 11 else hour
    clock = half_emojis[str(hour)] if int(minutes) == 30 else hour_emojis[str(hour)]
    return clock
