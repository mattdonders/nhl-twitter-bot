"""
Functions pertaining to the NHL Standings (via API).
"""

# pylint: disable=redefined-builtin

import logging
import sys
import time
from datetime import datetime, timedelta
from dateutil.parser import parse

from hockeygamebot.helpers import arguments, process
from hockeygamebot.nhlapi import api, roster
from hockeygamebot.definitions import VERSION


def get_standings(team_abbreviation):
    endpoint = f"/standings/now"
    response = api.nhl_api(endpoint)
    if response:
        standings = response.json()
        standings = standings["standings"]
    else:
        return False, None

    team_standings = [x for x in standings if x["teamAbbrev"] == team_abbreviation]
    return team_standings[0] if team_standings else None


def get_record(standings, return_dict=True):
    wins = standings["wins"]
    losses = standings["losses"]
    ot_losses = standings["otLosses"]

    record_dict = {"wins": wins, "losses": losses, "ot": ot_losses}
    record_string = f"{wins} - {losses} - {ot_losses}"
    return record_dict if return_dict else record_string
