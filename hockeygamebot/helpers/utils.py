"""
This module contains all utility functions such as
configuration, log management & other miscellaneous.
"""

import functools
import logging
import os
from datetime import datetime, timezone

import yaml

from hockeygamebot.definitions import CONFIG_PATH, LOGS_PATH
from hockeygamebot.helpers import arguments
from hockeygamebot.models.gametype import GameType


# Social Media Decorator
def check_social_timeout(func):
    """ A function decorate used within the GameEvent module to determine
        if we should send this event to social media. This can only wrap
        functions that have an attribute of a GameEvent.
    """

    @functools.wraps(func)
    def wrapper_social_timeout(*args, **kwargs):
        parsed_args = arguments.get_arguments()
        config = load_config()

        # If notweets is specified, always run the social methods
        if parsed_args.notweets:
            return func(*args, **kwargs)

        event = args[0]
        event_time = event.date_time
        timeout = config["script"]["event_timeout"]
        utcnow = datetime.now(timezone.utc)
        time_since_event = (utcnow - event_time).total_seconds()
        if time_since_event < timeout:
            return func(*args, **kwargs)
        else:
            logging.info(
                "Event #%s (%s) occurred %s second(s) in the past - older than our social timeout.",
                event.event_idx,
                event.event_type,
                time_since_event,
            )
            return False

    return wrapper_social_timeout


def load_config():
    """ Loads the configuration yaml file and returns a yaml object / dictionary..

    Args:
        None

    Returns:
        A yaml (dictionary) object.
    """

    with open(CONFIG_PATH) as ymlfile:
        config = yaml.load(ymlfile, Loader=yaml.FullLoader)

    return config


def setup_logging():
    """Configures application logging and prints the first three log lines."""
    # pylint: disable=line-too-long
    # logger = logging.getLogger(__name__)

    args = arguments.get_arguments()

    # Reset root handler to default so BasicConfig is respected
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)

    log_file_name = datetime.now().strftime(
        load_config()["script"]["log_file_name"] + "-%Y%m%d%H%M%s.log"
    )
    log_file = os.path.join(LOGS_PATH, log_file_name)
    if args.console and args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s",
        )

    elif args.console:
        logging.basicConfig(
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(module)s.%(funcName)s - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            datefmt="%Y-%m-%d %H:%M:%S",
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    # Reset logging level (outside of Basic Config)
    logger = logging.getLogger()
    logger_level = logging.DEBUG if args.debug else logging.INFO
    logger.setLevel(logger_level)


def date_parser(date):
    try:
        date_dt = datetime.strptime(date, "%Y-%m-%d")
        return date_dt
    except ValueError as e:
        logging.error("Invalid override date - exiting.")
        logging.error(e)
        raise e


def clock_emoji(time):
    """
    Accepts an hour (in 12 or 24 hour format) and returns the correct clock emoji.

    Args:
        time: 12 or 24 hour format time (:00 or :30)

    Returns:
        clock: corresponding clock emoji.
    """

    hour_emojis = {
        "0": "🕛",
        "1": "🕐",
        "2": "🕑",
        "3": "🕒",
        "4": "🕓",
        "5": "🕔",
        "6": "🕕",
        "7": "🕖",
        "8": "🕗",
        "9": "🕘",
        "10": "🕙",
        "11": "🕚",
    }

    half_emojis = {
        "0": "🕧",
        "1": "🕜",
        "2": "🕝",
        "3": "🕞",
        "4": "🕟",
        "5": "🕠",
        "6": "🕡",
        "7": "🕢",
        "8": "🕣",
        "9": "🕤",
        "10": "🕥",
        "11": "🕦",
    }

    # Split up the time to get the hours & minutes sections
    time_split = time.split(":")
    hour = int(time_split[0])
    minutes = time_split[1].split(" ")[0]

    # We need to adjust the hour if we use 24 hour-time.
    hour = 12 - hour if hour > 11 else hour
    clock = half_emojis[str(hour)] if int(minutes) == 30 else hour_emojis[str(hour)]
    return clock


def team_hashtag(team, game_type):
    """Generates a team hashtag from a team name & game type.

    UPDATED: 2019-06-30

    Args:
        team: full team name
        game_type: Game type text

    Returns:
        hashtag: team specific hashtag
    """

    team_hashtags = {
        "Anaheim Ducks": "#LetsGoDucks",
        "Arizona Coyotes": "#OurPack",
        "Boston Bruins": "#NHLBruins",
        "Buffalo Sabres": "#Sabres",
        "Calgary Flames": "#Flames",
        "Carolina Hurricanes": "#TakeWarning",
        "Chicago Blackhawks": "#Blackhawks",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Dallas Stars": "#GoStars",
        "Detroit Red Wings": "#LGRW",
        "Edmonton Oilers": "#LetsGoOilers",
        "Florida Panthers": "#FlaPanthers",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#mnwild",
        "Montréal Canadiens": "#GoHabsGo",
        "Nashville Predators": "#Preds",
        "New Jersey Devils": "#NJDevils",
        "New York Islanders": "#Isles",
        "New York Rangers": "#NYR",
        "Ottawa Senators": "#Sens",
        "Philadelphia Flyers": "#LetsGoFlyers",
        "Pittsburgh Penguins": "#LetsGoPens",
        "San Jose Sharks": "#SJSharks",
        "St. Louis Blues": "#stlblues",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#LeafsForever",
        "Vancouver Canucks": "#Canucks",
        "Vegas Golden Knights": "#VegasBorn",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#GoJetsGo",
    }

    team_hashtags_playoffs = {
        "Anaheim Ducks": "#LetsGoDucks",
        "Boston Bruins": "#GoBruins",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#mnwild",
        "Nashville Predators": "#standwithus",
        "New Jersey Devils": "#NowWeRise",
        "Philadelphia Flyers": "#EarnTomorrow",
        "Pittsburgh Penguins": "#3elieve",
        "San Jose Sharks": "#SJSharks",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#TMLTalk",
        "Vegas Golden Knights": "#VegasBorn",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#WPGWhiteout",
    }

    if GameType(game_type) == GameType.PLAYOFFS:
        return team_hashtags_playoffs[team]
    else:
        return team_hashtags[team]
