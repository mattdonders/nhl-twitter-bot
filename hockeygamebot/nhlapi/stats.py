"""
This module contains the any stats related functions from the NHL API for players or teams.
"""

import logging
import requests

from hockeygamebot.helpers import utils

# Load configuration file in global scope
config = utils.load_config()


def get_player_career_stats(player_id):
    """Returns the career stats of an NHL player by their given player ID.

    Args:
        player_id: A 7-digit NHL player id.

    Returns:
        career_stats: A dictionary of a players career stats
    """
    try:
        PERSON_API = "{api}/people/{id}?expand=person.stats&stats=careerRegularSeason".format(
            api=config["endpoints"]["nhl_endpoint"], id=player_id
        )
        response = requests.get(PERSON_API).json()
        person = response.get("people")[0]
        stats = person.get("stats")[0].get("splits")[0].get("stat")
        return stats
    except IndexError as e:
        logging.error("For some reason, %s doesn't have regular season stats. (%s)", player_id, e)
        return {"assists": 0, "points": 0, "goals": 0}
