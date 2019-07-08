"""
Functions pertaining to the NHL schedule (via API).
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from subprocess import Popen

import requests

from hockeygamebot.helpers import arguments, process, utils
from hockeygamebot.models.sessions import SessionFactory
from hockeygamebot.nhlapi import api, roster


def get_livefeed(game_id):
    """Queries the NHL Live Feed API to determine if there is a game today.

    Args:
        game_id (int) - The unique identifier of the Game (from get_team function).

    Returns:
        response - JSON object of live feed results
    """

    args = arguments.get_arguments()
    config = utils.load_config()

    logging.info("Live Feed requested!")
    api_endpoint = f"game/{game_id}/feed/live"
    response = api.nhl_api(api_endpoint).json()
    return response
