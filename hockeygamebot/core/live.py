# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Live State.
"""

import logging
import time

from hockeygamebot.helpers import utils
from hockeygamebot.models import gameevent


def live_loop(livefeed, game):
    """ The master live-game loop. All logic spawns from here.

    Args:
        livefeed: Live Feed API response
        game: Game Object

    Returns:
        None
    """
    config = utils.load_config()

    # Load all plays, the next event ID & new plays into lists
    all_plays = livefeed.get("liveData").get("plays").get("allPlays")
    # next_event = game.last_event_idx + 1
    # new_plays = all_plays[next_event:]

    all_plays_objs = [gameevent.event_factory(game, play, livefeed) for play in all_plays]
    return all_plays_objs
    # print(all_plays_objs)
