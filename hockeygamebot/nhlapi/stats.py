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
    PERSON_API = "{api}/people/{id}?expand=person.stats&stats=careerRegularSeason".format(
        api=config["endpoints"]["nhl_endpoint"], id=player_id
    )
    response = requests.get(PERSON_API).json()
    person = response.get("people")[0]
    stats = person.get("stats")[0].get("splits")[0].get("stat")
    return stats
