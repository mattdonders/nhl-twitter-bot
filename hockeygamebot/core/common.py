# -*- coding: utf-8 -*-

"""
This module contains all common functions shared across core (game state) loops.
"""

def get_game_events(game):
    """ Queries the NHL Live Feed API endpoint and returns a JSON object.

    Args:
        game: Current game as a Game Object

    Output:
        response - JSON object of live feed results
    """

    try:
        live_feed_json = req_session.get(game.live_feed).json()
    except requests.exceptions.RequestException:
        logging.error("Game Events request (%s) timed out!", game.live_feed)
        return None

    if args.localdata:
        live_feed_json = json.load(open('localdata/sample-data.json'))

    # Update all object attributes (game, period & teams)
    update_object_attributes(live_feed_json, game)

    # Return a JSON object of all game events
    return live_feed_json