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

from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.sessions import SessionFactory


def is_game_today(team_id):
    """Queries the NHL Schedule API to determine if there is a game today.

    Args:
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        (bool, games_info)
        bool - True if game today, False if not.
        games_info (dict) - A dictionary from the Schedule API that describes game information.
    """
    args = arguments.parse_arguments()
    config = utils.load_config()

    sf = SessionFactory()
    req_session = sf.get()

    now = datetime.now()
    if args.yesterday:
        now = now - timedelta(days=1)
    elif args.date is not None:
        try:
            now = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError as e:
            logging.error("Invalid override date - exiting.")
            logging.error(e)
            sys.exit()

    url = (
        "{api}/schedule?teamId={id}&expand="
        "schedule.broadcasts,schedule.teams&date={now:%Y-%m-%d}".format(
            api=config["endpoints"]["nhl_endpoint"], id=team_id, now=now
        )
    )
    try:
        logging.info("Sending API Request - %s", url)
        schedule = req_session.get(url).json()
        games_total = schedule["totalItems"]
    except requests.exceptions.RequestException:
        return False, None

    if games_total == 1:
        games_info = schedule["dates"][0]["games"][0]
        return True, games_info
    elif games_total == 2:
        dirname = os.path.dirname(os.path.realpath(__file__))
        if args.split is False:
            logging.info(
                "Split squad detected, spawning a second process to pick up second game."
            )
            game_index = 0
            if args.date is not None:
                spawn_args = " ".join(sys.argv[1:])
                logging.debug(
                    "Spawning Process: python3 %s/hockey_twitter_bot.py --split %s",
                    dirname,
                    spawn_args,
                )
                Popen(
                    [
                        "python3 "
                        + dirname
                        + "/hockey_twitter_bot.py --split "
                        + spawn_args
                    ],
                    shell=True,
                )
            else:
                Popen(
                    ["nohup python3 " + dirname + "/hockey_twitter_bot.py --split &"],
                    shell=True,
                )
        else:
            logging.info(
                "Split squad detected, this is the second spawned process to pick up second game (sleep for 5 seconds)."
            )
            time.sleep(5)
            game_index = 1
        games_info = schedule["dates"][0]["games"][game_index]
        return True, games_info
    return False, None
