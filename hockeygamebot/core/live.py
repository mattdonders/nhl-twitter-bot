# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Live State.
"""

import logging
import time

from hockeygamebot.models.gameevent import GoalEvent
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
    # current_event_idx = livefeed.get("liveData").get("currentPlay").get("about").get("eventIdx")
    all_plays = livefeed.get("liveData").get("plays").get("allPlays")

    # Subset all_plays by last_event_idx to shorten the loop
    next_event_idx = game.last_event_idx + 1
    new_plays_list = all_plays[next_event_idx:]

    if not new_plays_list:
        new_plays = bool(new_plays_list)
        logging.info(
            "No new plays detected. This game event loop will catch any missed events & "
            "and also check for any scoring changes on existing goals."
        )
    elif len(new_plays_list) < 10:
        new_plays = bool(new_plays_list)
        new_plays_shortlist = list()
        for play in new_plays_list:
            event_type = play["result"]["eventTypeId"]
            event_idx = play["about"]["eventIdx"]
            event_kv = f"{event_idx}: {event_type}"
            new_plays_shortlist.append(event_kv)
        logging.info(
            "%s new event(s) detected - looping through them now: %s",
            len(new_plays_list),
            new_plays_shortlist,
        )
    else:
        new_plays = bool(new_plays_list)
        logging.info("%s new event(s) detected - looping through them now.", len(new_plays_list))

    # We pass in the entire all_plays list into our event_factory in case we missed an event
    # it will be created because it doesn't exist in the Cache.
    for play in all_plays:
        gameevent.event_factory(game=game, play=play, livefeed=livefeed, new_plays=new_plays)

    # Check here for goal object changes
    # if not new_plays:
    #     for k, v in GoalEvent.cache.entries:
    #         print(k, v)

    # all_plays_objs = [
    #     gameevent.event_factory(game, play, livefeed, new_plays) for play in all_plays
    # ]
    # return all_plays_objs
    # print(all_plays_objs)
