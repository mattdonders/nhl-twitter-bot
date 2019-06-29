"""
Functions pertaining to the NHL Roster (via API).
"""
import logging

from hockeygamebot import nhlapi
from hockeygamebot.helpers import utils
from hockeygamebot.helpers.arguments import ArgumentFactory
from hockeygamebot.models.sessions import SessionFactory


def gameday_roster_update(game):
    """ Gets the gameday rosters from the live feed endpoint.
        This is needed because in some instances a player is not included
        on the /teams/{id}/roster page for some reason.

    Args:
        game: Current Game object

    Returns:
        None
    """

    home_team = game.home_team
    away_team = game.away_team

    logging.info("Getting gameday rosters from Live Feed endpoint.")

    try:
        gameday_roster = nhlapi.api.nhl_api(game.live_feed).json()
        all_players = gameday_roster.get("gameData").get("players")
        for id, player in all_players.items():
            team = player.get("currentTeam").get("name")
            if team == home_team.team_name:
                home_team.gameday_roster[id] = player
            else:
                away_team.gameday_roster[id] = player
    except Exception as e:
        logging.error("Unable to get all players.")
        logging.error(e)
