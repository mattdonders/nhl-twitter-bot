"""
This module deals with parsing of command line arguments
or environment variables (if using Docker containers).
"""

import argparse
import os
import sys

import pytz


class ArgumentFactory:
    def __init__(self):
        self.args = None

    def get(self):
        if self.args == None:
            self.args = parse_arguments()
        return self.args


def parse_arguments():
    """Executes local argument parsing and then checks for Docker arguments.

    Args:
        None

    Returns:
        args: Arguments Namespace
    """
    # print("!!! Parsing arguments !!!")
    args = parse_local_arguments()

    # If running in Docker, parse environment variables (instead of arguments)
    # And set args.console to True to make `docker logs` easier to use
    if args.docker:
        # Check to see if Time Zone is set
        if "TZ" not in os.environ:
            print(
                "[ERROR] Timezone environment variable not set, please add to `docker run` commmand."
            )
            sys.exit()

        if os.environ["TZ"] not in pytz.all_timezones:
            print(
                f"[ERROR] {os.environ['TZ']} is not a valid time zone, please fix in `docker run` commmand."
            )
            sys.exit()

        # Force console argument & parse the remainder of the environment variables
        args.console = True
        parse_env_variables(args)

    return args


def parse_local_arguments():
    """
    Parses arguments passed into the python script on the command line.command

    Input:
    None

    Output:
    args - argument Namespace
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--notweets", help="log tweets to console instead of Twitter", action="store_true"
    )
    parser.add_argument("--console", help="log to console instead of file", action="store_true")
    parser.add_argument("--debug", help="print debug log items", action="store_true")
    parser.add_argument("--team", help="override team in configuration", action="store")
    parser.add_argument("--debugtweets", help="send tweets from debug account", action="store_true")
    parser.add_argument("--localdata", help="use local data instead of API", action="store_true")
    parser.add_argument(
        "--overridelines", help="override lines if None are returned", action="store_true"
    )
    parser.add_argument(
        "--yesterday", help="get yesterday game on the schedule", action="store_true"
    )
    parser.add_argument("--date", help="override game date", action="store")
    parser.add_argument("--split", help="split squad game index", action="store_true")
    parser.add_argument("--docker", help="running in a docker container", action="store_true")
    parser.add_argument("--discord", help="Send messages to discord channel", action="store_true")
    parser.add_argument("-v", help="Increased verbosity.", action="store_true")
    arguments = parser.parse_args()
    return arguments


def parse_env_variables(args):
    """
    For when running via Docker, parse Environment variables.
    Environment variables replace command line arguments.

    Args:
        args - argument Namespace

    Returns:
        None
    """

    if "ARGS_NOTWEETS" in os.environ and os.environ["ARGS_NOTWEETS"] == "TRUE":
        args.notweets = True

    if "ARGS_DEBUG" in os.environ and os.environ["ARGS_DEBUG"] == "TRUE":
        args.debug = True

    if "ARGS_TEAM" in os.environ:
        args.team = os.environ["ARGS_TEAM"]

    if "ARGS_DEBUGTWEETS" in os.environ and os.environ["ARGS_DEBUGTWEETS"] == "TRUE":
        args.debugtweets = True

    if "ARGS_DATE" in os.environ:
        args.date = os.environ["ARGS_DATE"]

