"""
Functions pertaining to the NHL schedule (via API).
"""

import logging
import random

from hockeygamebot.nhlapi import api


def get_gamecenter_landing(game_id):
    endpoint = f"/gamecenter/{game_id}/landing"
    response = api.nhl_api(endpoint)
    if response:
        gamecenter = response.json()
        return gamecenter
    else:
        return None


def get_gamecenter_boxscore(game_id, boxscore_only=False):
    endpoint = f"/gamecenter/{game_id}/boxscore"
    response = api.nhl_api(endpoint)
    if response:
        gamecenter = response.json()
        boxscore = gamecenter.get("boxscore")
        return boxscore if boxscore_only else gamecenter
    else:
        return None


def get_gamecenter_playbyplay(game_id):
    endpoint = f"/gamecenter/{game_id}/play-by-play"
    response = api.nhl_api(endpoint)
    if response:
        gamecenter = response.json()
        return gamecenter
    else:
        return None
