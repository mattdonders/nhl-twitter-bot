import logging
import os
import sys
from datetime import datetime

# If running as app.py directly, we may need to import the module manually.
try:
    from hockeygamebot.models.team import Team
    from hockeygamebot.models.game import Game
    from hockeygamebot.definitions import VERSION
    from hockeygamebot.helpers import arguments, utils
    from hockeygamebot.nhlapi import schedule
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
    from hockeygamebot.models.team import Team
    from hockeygamebot.models.game import Game
    from hockeygamebot.definitions import VERSION
    from hockeygamebot.helpers import arguments, utils
    from hockeygamebot.nhlapi import schedule


def run():
    args = arguments.parse_arguments()

    # Setup the logging for this script run (console, file, etc)
    utils.setup_logging()

    # ------------------------------------------------------------------------------
    # SCRIPT STARTS PROCESSING BELOW
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

    logging.info("%s", game_info)
    away_team = Team.from_json(game_info, "away")
    home_team = Team.from_json(game_info, "home")
    print(vars(away_team))
    print(vars(home_team))


if __name__ == "__main__":
    run()
