"""
Functions pertaining to the NHL Roster (via API).
"""
import logging

from hockeygamebot.nhlapi import livefeed, api
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.sessions import SessionFactory


def gameday_roster_update(game):
    """Gets the gameday rosters from the live feed endpoint.
        This is needed because in some instances a player is not included
        on the /teams/{id}/roster page for some reason.

    Args:
        game: Current Game object

    Returns:
        None
    """

    args = arguments.get_arguments()

    home_team = game.home_team
    away_team = game.away_team

    logging.info("Getting gameday rosters from Live Feed endpoint.")

    try:
        gameday_roster = livefeed.get_livefeed(game.game_id)
        all_players = gameday_roster.get("rosterSpots")
        if not all_players:
            logging.warning("Gameday Roster currently not available - try again next loop.")
            return

        for player in all_players:
            try:
                team_id = player.get("teamId")
                player_id = player.get("playerId")
                first_name = player.get("firstName")
                last_name = player.get("lastName")
                player["fullName"] = f"{first_name} {last_name}"
                # Add Player to Full Game Roster & Team Roster
                game.full_roster[player_id] = player

                if team_id == home_team.team_id:
                    home_team.gameday_roster[player_id] = player
                else:
                    away_team.gameday_roster[player_id] = player
            except Exception as e:
                logging.error("%s doesn't have a team - skipping.", player["fullName"])
    except Exception as e:
        logging.error("Unable to get all players.")
        logging.error(e)


def get_full_roster(team_tri_code):
    """Gets the full rosters from the new roster endpoint. Flattens and formats properly.

    Args:
        game: Current Game object

    Returns:
        None
    """

    logging.info("Getting the full roster for %s (via current roster endpoint).", team_tri_code)
    endpoint = f"/roster/{team_tri_code}/current"
    response = api.nhl_api(endpoint)
    if response:
        roster = response.json()
    else:
        return False, None

    forwards = roster["forwards"]
    defense = roster["defensemen"]
    goalies = roster["goalies"]
    all_players = forwards + defense + goalies

    for player in all_players:
        first_name = player["firstName"]["default"]
        last_name = player["lastName"]["default"]
        full_name = f"{first_name} {last_name}"
        short_name = f"{full_name[0]}. {' '.join(full_name.split()[1:])}"
        player["full_name"] = full_name
        player["short_name"] = short_name

    all_players_dict = {x["id"]: x for x in all_players}
    return all_players_dict


def player_attr_by_id_v1(roster, player_id, attribute):
    """Returns the attribute of a player given a roaster and a player_id.

    Args:
        roster (dict): Team roster (returned from API)
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """
    new_player_id = player_id.replace("ID", "")
    for roster_item in roster:
        person_id = str(roster_item["person"]["id"])
        person_attr = roster_item["person"][attribute]
        if person_id == new_player_id:
            return person_attr


def player_attr_by_id(roster, player_id, attribute):
    """Returns the attribute of a player given a roaster and a player_id.

    Args:
        roster (dict): Team roster (returned from API)
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """

    player = roster.get(player_id)
    if not player:
        logging.info("Player is not on current team roster, ask NHL Player API for details.")
        player_attr_by_id = nonroster_player_attr_by_id(player_id, attribute)
        return player_attr_by_id

    player_attr_by_id = player.get(attribute, None)
    return player_attr_by_id


def nonroster_player_attr_by_id_v1(player_id, attribute):
    """Returns the attribute of a non-roster player via the NHL People API.

    Args:
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """
    api_player_url = f"/people/{player_id}"
    api_player = api.nhl_api(api_player_url).json()
    player_attr = api_player["people"][0][attribute]
    return player_attr


def nonroster_player_attr_by_id(player_id, attribute):
    """Returns the attribute of a non-roster player via the NHL People API.

    Args:
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """

    endpoint = f"/player/{player_id}/landing"

    response = api.nhl_api(endpoint)
    if response:
        player_details = response.json()
    else:
        return False, None

    # Calculate Short Name (Extra Attribute)
    first_name = player_details["firstName"]
    last_name = player_details["lastName"]
    full_name = f"{first_name} {last_name}"
    short_name = f"{full_name[0]}. {' '.join(full_name.split()[1:])}"
    player_details["full_name"] = full_name
    player_details["short_name"] = short_name

    player_attr = player_details.get(attribute, None)
    return player_attr
