import logging
from datetime import datetime

from hockeygamebot.definitions import VERSION
from hockeygamebot.helpers import arguments, utils


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
        "ARGS - notweets: %s, console: %s, teamoverride: %s",
        args.notweets,
        args.console,
        args.team,
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
