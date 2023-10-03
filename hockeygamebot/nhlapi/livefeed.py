"""
Functions pertaining to the NHL schedule (via API).
"""

import logging
import random

from hockeygamebot.nhlapi import api


def get_livefeed(game_id):
    """Queries the NHL Live Feed API to determine if there is a game today.

    Args:
        game_id (int) - The unique identifier of the Game.

    Returns:
        response - JSON object of live feed results
    """
    randomnum = random.randint(1000, 9999)
    logging.info("Live Feed requested (random cache - %s)!", randomnum)
    api_endpoint = f"gamecenter/{game_id}/play-by-play?{randomnum}"
    # print(api_endpoint)
    response = api.nhl_api(api_endpoint).json()
    # print(response)
    return response


def get_gamecenter_landing(game_id):
    endpoint = f"/gamecenter/{game_id}/landing"
    response = api.nhl_api(endpoint)
    if response:
        gamecenter = response.json()
        return gamecenter
    else:
        return False, None


def get_gamecenter_boxscore(game_id):
    endpoint = f"/gamecenter/{game_id}/boxscore"
    response = api.nhl_api(endpoint)
    if response:
        gamecenter = response.json()
        return gamecenter
    else:
        return None
