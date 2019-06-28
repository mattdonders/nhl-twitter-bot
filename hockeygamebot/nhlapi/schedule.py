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

from hockeygamebot.helpers import process, utils
from hockeygamebot.helpers.arguments import ArgumentFactory
from hockeygamebot.models.sessions import SessionFactory
from hockeygamebot.nhlapi import api


def is_game_today(team_id, date):
    """Queries the NHL Schedule API to determine if there is a game today.

    Args:
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        (bool, games_info)
        bool - True if game today, False if not.
        games_info (dict) - A dictionary from the Schedule API that describes game information.
    """
    args = ArgumentFactory().get()
    config = utils.load_config()

    url = (
        "{api}/schedule?teamId={id}&expand="
        "schedule.broadcasts,schedule.teams&date={date:%Y-%m-%d}".format(
            api=config["endpoints"]["nhl_endpoint"], id=team_id, date=date
        )
    )

    response = api.nhl_api(url)
    if response:
        schedule = response.json()
        games_total = schedule["totalItems"]
    else:
        return False, None

    if games_total == 1:
        games_info = schedule["dates"][0]["games"][0]
        return True, games_info

    if games_total == 2:
        if args.split is False:
            logging.info("Split Squad - spawning a second process to pick up second game.")
            game_index = 0
            process.spawn_another_process()
            time.sleep(10)
        else:
            game_index = 1
            logging.info(
                "Split Squad - this is the process to pick up second game (sleep 5 seconds)."
            )
            time.sleep(5)

        games_info = schedule["dates"][0]["games"][game_index]
        return True, games_info

    date_string = date.date() if args.date else "today"
    logging.info("There are no games scheduled for %s, SAD!", date_string)
    return False, schedule


def get_broadcasts(resp):
    """Parses an NHL schedule response to get broadcast information.

    Args:
        resp: JSON response from NHL Schedule API call.

    Returns:
        broadcasts: Dictionary of home & away broadcasts.
    """
    broadcasts = {}

    try:
        resp_broadcasts = resp["broadcasts"]
        for broadcast in resp_broadcasts:
            broadcast_team = broadcast["type"]
            if broadcast_team == "national":
                broadcasts["away"] = broadcast["name"]
                broadcasts["home"] = broadcast["name"]
                break
            else:
                broadcast_channel = resp_broadcasts["name"]
                broadcasts[broadcast_team] = broadcast_channel
    except KeyError:
        logging.warning("Broadcasts not available - setting them to TBD.")
        broadcasts["home"] = "TBD"
        broadcasts["home"] = "TBD"

    return broadcasts
