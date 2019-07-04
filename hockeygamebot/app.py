"""
The main application entrypoint in the hockeygamebot script!
"""

# pylint: disable=broad-except

import logging
import os
import sys
import time
from datetime import datetime

# If running as app.py directly, we may need to import the module manually.
try:
    import hockeygamebot  # pylint: disable=unused-import
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from hockeygamebot.core import preview
from hockeygamebot.models.team import Team
from hockeygamebot.models.game import Game
from hockeygamebot.models.gamestate import GameState
from hockeygamebot.definitions import VERSION
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.nhlapi import schedule, roster


def start_game_loop(game):
    """ The main game loop - tracks game state & calls all relevant functions.

    Args:
        game: Current Game object

    Returns:
        None
    """
    config = utils.load_config()

    # ------------------------------------------------------------------------------
    # START THE MAIN LOOP
    # ------------------------------------------------------------------------------

    while True:
        if GameState(game.game_state) == GameState.PREVIEW:
            if game.game_time_countdown > 0:
                logging.info("Game is in Preview state - send out all pregame information.")
                preview.generate_game_preview(game)
                time.sleep(config["script"]["preview_sleep_time"])
            else:
                logging.info(
                    "Game is in Preview state, but past game start time - sleep for a bit."
                )
                # get_game_events()
                time.sleep(config["script"]["pregame_sleep_time"])
        elif GameState(game.game_state) == GameState.LIVE:
            try:
                logging.info(
                    "Game is currently live - checking events after event Idx %s.",
                    game.last_event_idx,
                )
                # game_events = get_game_events(game_obj)
                # loop_game_events(game_events, game_obj)
                logging.info("Sleeping for configured live game time.")
            except Exception as error:
                logging.error(
                    "Uncaught exception in live game loop - sleep for configured live game time."
                )
                logging.error(error)

            time.sleep(config["script"]["live_sleep_time"])
        elif GameState(game.game_state) == GameState.FINAL:
            pass
        else:
            logging.warning(
                "Game State %s is unknown - sleep for 5 seconds and check again.", game.game_state
            )
            time.sleep(config["script"]["live_sleep_time"])


def run():
    """ The main script runner - everything starts here! """
    config = utils.load_config()
    args = arguments.get_arguments()

    # Setup the logging for this script run (console, file, etc)
    utils.setup_logging()

    # Get the team name the bot is running as
    team_name = config["default"]["team_name"]

    # ------------------------------------------------------------------------------
    # PRE-SCRIPT STARTS PROCESSING BELOW
    # ------------------------------------------------------------------------------

    # Log script start lines
    logging.info("#" * 80)
    logging.info("New instance of the Hockey Twitter Bot (V%s) started.", VERSION)
    if args.docker:
        logging.info("Running in a Docker container - environment variables parsed.")
    logging.info("TIME: %s", datetime.now())
    logging.info(
        "ARGS - notweets: %s, console: %s, teamoverride: %s", args.notweets, args.console, args.team
    )
    logging.info(
        "ARGS - debug: %s, debugtweets: %s, overridelines: %s",
        args.debug,
        args.debugtweets,
        args.overridelines,
    )
    logging.info(
        "ARGS - date: %s, split: %s, localdata: %s, discord: %s",
        args.date,
        args.split,
        args.localdata,
        args.discord,
    )
    logging.info("%s\n", "#" * 80)

    # Check if there is a game scheduled for today -
    # If there is no game, exit the script.
    date = utils.date_parser(args.date) if args.date else datetime.now()
    game_today, game_info = schedule.is_game_today(1, date)
    if not game_today:
        sys.exit()

    # logging.info("%s", game_info)

    # Create the Home & Away Team objects
    away_team = Team.from_json(game_info, "away")
    home_team = Team.from_json(game_info, "home")

    # If lines are being overriden by a local lineup file,
    # set the overrlide lines property to True
    if args.overridelines:
        home_team.overridelines = True
        away_team.overridelines = True

    # The preferred team is the team the bot is running as
    # This allows us to track if the preferred team is home / away
    home_team.preferred = bool(home_team.team_name == team_name)
    away_team.preferred = bool(away_team.team_name == team_name)

    # Create the Game Object!
    game = Game.from_json_and_teams(game_info, home_team, away_team)

    # Update the Team Objects with the gameday rosters
    roster.gameday_roster_update(game)

    # print(vars(game))
    # print(vars(away_team))
    # print(vars(home_team))

    # All necessary Objects are created, start the game loop!
    start_game_loop(game)


if __name__ == "__main__":
    run()
