# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Live State.
"""

import logging
import time

from hockeygamebot.helpers import utils


def live_loop(game):
    """ The master live-game loop. All logic spawns from here.

    Args:
        game: Game Object

    Returns:
        None
    """
    config = utils.load_config()

    try:
        logging.info("-" * 80)
        logging.info("Game is LIVE - checking events after event Idx %s.", game.last_event_idx)
        # game_events = get_game_events(game)
        # loop_game_events(game_events, game)
        logging.info("Sleeping for 5 seconds...")
        time.sleep(config["script"]["live_sleep_time"])
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Uncaught exception in live game loop - still sleep for 5 seconds.")
        logging.error(e)
        time.sleep(config["script"]["live_sleep_time"])

