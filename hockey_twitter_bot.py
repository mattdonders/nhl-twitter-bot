#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

"""
This module parses the NHL Schedule & Live Feed API endpoints
to gather rather relevant game events and tweet them to the
game bot Twitter acount.
"""

# pylint: disable=C0103
# pylint: disable=wildcard-import, pointless-string-statement
# pylint: disable=too-many-statements, too-many-branches, too-many-locals, too-many-lines

# Standard Imports
from __future__ import unicode_literals

import argparse
import configparser
import json
import logging
import math
import os
import platform
import socket
import sys
import time
from datetime import datetime, timedelta
import dateutil.tz

# 3rd Party Imports
import linode
import requests
import tweepy
from PIL import Image, ImageDraw, ImageFont

# My Local / Custom Imports
import nhl_game_events
from secret import *

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Congfiguration, Logging & Argument Parsing
# ------------------------------------------------------------------------------

config = configparser.ConfigParser()
conf_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.ini')
config.read(conf_path)

TEAM_BOT = config['DEFAULT']['TEAM_NAME']
NHLAPI_BASEURL = config['ENDPOINTS']['NHL_BASE']
TWITTER_URL = config['ENDPOINTS']['TWITTER_URL']
TWITTER_ID = config['ENDPOINTS']['TWITTER_HANDLE']
VPS_CLOUDHOST = config['VPS']['CLOUDHOST']
VPS_HOSTNAME = config['VPS']['HOSTNAME']


def setup_logging():
    """
    Configures application logging and prints the first three log lines.

    Input:
    None

    Output:
    None
    """

    #pylint: disable=line-too-long

    # logger = logging.getLogger(__name__)
    if args.console and args.debug:
        logging.basicConfig(level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S',
                            format='%(asctime)s - %(module)s.%(funcName)s - %(levelname)s - %(message)s')
    elif args.console:
        logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                            format='%(asctime)s - %(module)s.%(funcName)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(filename='NHLTwitterBot.log',
                            level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def parse_arguments():
    """
    Parses arguments passed into the python script on the command line.command

    Input:
    None

    Output:
    args - argument Namespace
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--notweets", help="log tweets to console instead of Twitter",
                        action="store_true")
    parser.add_argument("--console", help="log to console instead of file",
                        action="store_true")
    parser.add_argument("--debug", help="print debug log items",
                        action="store_true")
    parser.add_argument("--team", help="override team in configuration",
                        action="store")
    parser.add_argument("--debugtweets", help="send tweets from debug account",
                        action="store_true")
    parser.add_argument("--localdata", help="use local data instead of API",
                        action="store_true")
    parser.add_argument("--yesterday", help="get yesterday game on the schedule",
                        action="store_true")

    arguments = parser.parse_args()
    return arguments


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Linode Related Functions
# ------------------------------------------------------------------------------

def is_linode():
    """Checks if the python script is running on a Linode instance."""
    hostname = socket.gethostname()
    platform_release = platform.release()
    if hostname == VPS_HOSTNAME or VPS_CLOUDHOST in platform_release:
        logging.info("Script is running on a Cloud VPS - host detected!")
        return True

    logging.info("Script is not running on specified Cloud VPS host!")
    return False


def linode_shutdown():
    """
    Create a Linode client (via apikey) & shutdown Linode ID specified in config.

    Input:
    None

    Output:
    None
    """

    logging.info("Linode (%s) shutdown requested.", linode_id_devils)
    # Create the Linode client & initiate the Linode
    client = linode.linode_client.LinodeClient(linode_apikey)
    l = linode.objects.Linode(client, linode_id_devils)

    # Request the Linode to shutdown
    l.shutdown()


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Tweepy & Miscellaneous Methods
# ------------------------------------------------------------------------------

def get_api():
    """
    Returns an Authorized session of the Tweepy API.

    Input:
    None

    Output:
    tweepy_session - authorized twitter session that can send a tweet.
    """

    if args.debugtweets:
        auth = tweepy.OAuthHandler(debug_consumer_key, debug_consumer_secret)
        auth.set_access_token(debug_access_token, debug_access_secret)
    else:
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)

    tweepy_session = tweepy.API(auth)
    return tweepy_session


def send_tweet(tweet_text, reply=None):
    """
    Sends a tweet from the account returned from get_api method.

    Input:
    tweet_text - The text to send as a tweet (may contain URL at end to qote tweet)

    Output:
    last_tweet - A link to the last tweet sent (or search result if duplicate)
                 If duplicate cannot be found, returns base URL (also raises error)
    """
    # pylint: disable=bare-except

    # If the --notweets flag is passed, log tweets instead of Twitter
    if args.notweets:
        logging.info("%s", tweet_text)
        return TWITTER_URL

    try:
        api = get_api()
        tweet_length = len(tweet_text)
        logging.info("Tweet length - %s", tweet_length)
        if tweet_length < 280:
            if reply is None:
                logging.info("Plain tweet, no reply.")
                status = api.update_status(status=tweet_text)
            else:
                tweet_text = "@{} {}".format(TWITTER_ID, tweet_text)
                logging.info("Reply to tweet %s - \n%s", reply, tweet_text)
                status = api.update_status(tweet_text, in_reply_to_status_id=reply)
        else:
            tweet_array = []
            tweets_needed = math.ceil(tweet_length / 280)
            for i in range(tweets_needed):
                range_start = (i * 280)
                range_end = ((i+1) * 280)
                tweet_array.append(tweet_text[range_start:range_end])

        # Return a full link to the URL in case a quote-tweet is needed
        tweet_id = status.id_str

        # last_tweet = "{}{}".format(TWITTER_URL, tweet_id)
        # return last_tweet
        return tweet_id
    except tweepy.TweepError as tweep_error:
        try:
            error_code = tweep_error.api_code
            if error_code == 187:
                if "score" in tweet_text.lower():
                    logging.info(
                        "Duplicate status detected - search for duplicate tweet.")
                    results = api.search(q=tweet_text)
                    if results:
                        tweet_id = results[0].id_str
                        # last_tweet = "{}{}".format(TWITTER_URL, tweet_id)
                        # return last_tweet
                        return tweet_id
                else:
                    logging.info(
                        "Duplicate status detected, but not a goal - no need to search.")
                    return False
            else:
                logging.error("Non-duplicate tweet error: %s", tweep_error)
            return False
        except:
            logging.critical("%s", sys.exc_info()[0])
            return False


# Returns the ordinal variant of a number
ordinal = lambda n: "%d%s" % (n, "tsnrhtdd"[(math.floor(n/10)%10 != 1)*(n%10 < 4)*n%10::4])

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Event Object Related Methods
# ------------------------------------------------------------------------------

def update_object_attributes(json_feed, game):
    """
    Takes in a JSON object of the livefeed API and updates relevant
    object attributes.
    """

    # logging.info("Updating game & team object attributes.")

    linescore = json_feed["liveData"]["linescore"]

    # Updated game related attributes
    game.game_state = json_feed["gameData"]["status"]["abstractGameState"]
    game.power_play_strength = json_feed["liveData"]["linescore"]["powerPlayStrength"]

    # Update period related attributes
    if game.game_state != "Preview":
        game.period.current = linescore["currentPeriod"]
        game.period.current_ordinal = linescore["currentPeriodOrdinal"]
        game.period.time_remaining = linescore["currentPeriodTimeRemaining"]
        game.period.intermission = linescore["intermissionInfo"]["inIntermission"]

    # Update team related attributes
    linescore_home = linescore["teams"]["home"]
    linescore_away = linescore["teams"]["away"]

    game.home_team.skaters = linescore_home["numSkaters"]
    game.home_team.score = linescore_home["goals"]
    game.home_team.shots = linescore_home["shotsOnGoal"]
    game.home_team.power_play = linescore_home["powerPlay"]
    # game.home_team.goalie_pulled = linescore_home["goaliePulled"]


    game.away_team.skaters = linescore_away["numSkaters"]
    game.away_team.score = linescore_away["goals"]
    game.away_team.shots = linescore_away["shotsOnGoal"]
    game.away_team.power_play = linescore_away["powerPlay"]
    # game.away_team.goalie_pulled = linescore_away["goaliePulled"]


    # Logic for keeping goalie pulled with events in between
    try:
        all_plays = json_feed["liveData"]["plays"]["allPlays"]
        last_event = all_plays[game.last_event_idx]
        last_event_type = last_event["result"]["eventTypeId"]
        event_filter_list = ["GOAL", "PENALTY"]

        if not game.home_team.goalie_pulled:
            logging.debug("Home goalie in net - check and update attribute.")
            home_goalie_pulled = game.home_team.goalie_pulled_setter(linescore_home["goaliePulled"])
        elif game.home_team.goalie_pulled and last_event_type in event_filter_list:
            logging.info("Home goalie was pulled and an important event detected - update.")
            home_goalie_pulled = game.home_team.goalie_pulled_setter(linescore_home["goaliePulled"])
        else:
            logging.info("Home goalie is pulled and a non-important event detected, don't update.")

        if not game.away_team.goalie_pulled:
            logging.debug("Away goalie in net - check and update attribute.")
            away_goalie_pulled = game.away_team.goalie_pulled_setter(linescore_away["goaliePulled"])
        elif game.away_team.goalie_pulled and last_event_type in event_filter_list:
            logging.info("Away goalie was pulled and an important event detected - update.")
            away_goalie_pulled = game.away_team.goalie_pulled_setter(linescore_away["goaliePulled"])
        else:
            logging.info("Away goalie is pulled and a non-important event detected, don't update.")

        # Calls the goalie_pulled function if the goalie has been pulled
        if home_goalie_pulled:
            goalie_pull_tweet(game, "home")
        elif away_goalie_pulled:
            goalie_pull_tweet(game, "away")
    except IndexError:
        logging.warning("Tried to update goalie pulled attribute, but index error - try again.")


def recent_event(event):
    """Determines if an event has happened recently enough. Used to not send old tweets.

    Args:
        event (dict): A dictionary of the event to check.

    Returns:
        bool: True if the event happened within the past minute, False if not.
    """
    if args.yesterday:
        return True

    event_type = event["result"]["eventTypeId"]
    event_idx = event["about"]["eventIdx"]
    event_datetime = event["about"]["dateTime"]

    now = datetime.now()
    localtz = dateutil.tz.tzlocal()
    localoffset = localtz.utcoffset(datetime.now(localtz))
    date_time_obj = datetime.strptime(event_datetime, '%Y-%m-%dT%H:%M:%SZ')
    date_time_local = date_time_obj + localoffset

    seconds_since_event = int((now - date_time_local).total_seconds())
    logging.info("Event #%s (%s) occurred %s second(s) in the past - if greater than 120, skip.",
                 event_idx, event_type, seconds_since_event)
    return bool(seconds_since_event < 120)


def show_all_objects():
    """Outputs all relevant game objects to console."""

    # (preferred_team, other_team) = nhl_game_events.preferred_teams(home_team_obj, away_team_obj)
    preferred_team = game_obj.preferred_team

    print("** Game Attributes **")
    print(game_obj)
    for k, v in vars(game_obj).items():
        print("{}: {}".format(k, v))
    print(game_obj.game_time_local)
    print(game_obj.game_time_countdown)
    print(game_obj.game_hashtag)
    print(game_obj.live_feed)
    print("Preferred Team TV Channel: {}".format(preferred_team.tv_channel))

    print("\n** Home Team Attributes **")
    print(home_team_obj)
    for k, v in vars(home_team_obj).items():
        print("{}: {}".format(k, v))

    print("\n** Away Team Attributes **")
    print(away_team_obj)
    for k, v in vars(away_team_obj).items():
        print("{}: {}".format(k, v))

    print("\n** Period Attributes **")
    print(game_obj.period)
    for k, v in vars(game_obj.period).items():
        print("{}: {}".format(k, v))


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Image Generation Functions
# ------------------------------------------------------------------------------

def preview_image(game):
    """Generates the game preview image and returns the image instance.

    Args:
        game (Game): The current game instance.

    Returns:
        img (Image): Image object of game preview.
        None: Can return None if tweet already sent
    """

    # Check if the preview tweet has been sent already
    api = get_api()
    search_text = "{} tune".format(TWITTER_ID)
    search_results = api.search(q=search_text, count=1)
    if len(search_results) > 0:
        logging.info("Found an old tune-in tweet - checking if sent today.")
        latest_tweet_date = search_results[0].created_at

        # If preview tweet was sent today, return False and skip this section
        logging.info("Previous tune in tweet - %s", latest_tweet_date)
        if latest_tweet_date.date() == datetime.now().date():
            return None

    # Load required fonts & background image
    teams_font = 'resources/fonts/Adidas.otf'
    details_font = 'resources/fonts/Impact.ttf'
    bg = Image.open('resources/images/GamedayBlank.jpg')
    font_black = (0, 0, 0)

    # Create & format text for pre-game image
    teams_text = "{} vs {}".format(game.away_team.short_name, game.home_team.short_name)

    game_date_short = game.game_date_short
    game_time = game.game_time_local.replace(" ", "")
    details_game = ("{} of 82 | {} | {}"
                    .format(game.preferred_team.games + 1, game_date_short, game_time))

    full_details = "{}\n{}\n{}".format(details_game, game.venue, game.game_hashtag)

    # Calculate Font Sizes
    teams_length = len(teams_text)
    teams_font_size = math.floor(1440 / teams_length)
    longest_details = 0
    for line in iter(full_details.splitlines()):
        longest_details = len(line) if len(line) > longest_details else longest_details
    details_font_size = math.floor(1050 / longest_details)

    font_large = ImageFont.truetype(teams_font, teams_font_size)
    font_small = ImageFont.truetype(details_font, details_font_size)

    draw = ImageDraw.Draw(bg)
    team_coords = (40, 20)
    draw.text(team_coords, teams_text, font_black, font_large)

    details_coords = (145, 160)
    draw.multiline_text(details_coords, full_details, font_black, font_small, None, 10, "center")

    return bg


def final_image(game, boxscore_preferred, boxscore_other):
    """Generates the final boxscore image to send in the GAME_END tweet.

    Args:
        game (Game): The current game instance.
        boxscore_preferred (dict): The boxscore JSON dictionary of preferred team.
        boxscore_other (dict): The boxscore JSON dictionary of other team.

    Returns:
        Image: Image object (from PIL library) to be sent to Twitter.
    """
    teams_font = 'resources/fonts/Adidas.otf'
    details_font = 'resources/fonts/Impact.ttf'

    bg = Image.open('resources/images/GamedayFinalPrudentialBlank.jpg')

    # Get Game Info for Updated Record
    _, schedule_json = is_game_today(get_team(TEAM_BOT))
    if game.home_team.preferred:
        pref = schedule_json["teams"]["home"]
        other = schedule_json["teams"]["away"]
    else:
        pref = schedule_json["teams"]["away"]
        other = schedule_json["teams"]["home"]

    # Load & Resize Logos
    pref_logo = Image.open('resources/logos/{}.png'
                           .format(game.preferred_team.team_name.replace(" ", "")))
    other_logo = Image.open('resources/logos/{}.png'
                            .format(game.other_team.team_name.replace(" ", "")))

    resize = (125, 125)
    pref_logo.thumbnail(resize, Image.ANTIALIAS)
    other_logo.thumbnail(resize, Image.ANTIALIAS)

    font_large = ImageFont.truetype(teams_font, 80)
    font_small = ImageFont.truetype(details_font, 40)
    font_smaller = ImageFont.truetype(details_font, 20)
    font_black = (0, 0, 0)

    # Setup Coordinates
    coords_pref_score = (241, 238)
    coords_pref_logo = (279, 240)
    coords_pref_record = (270, 328)
    coords_other_score = (703, 238)
    coords_other_logo = (584, 240)
    coords_other_record = (648, 328)

    coords_shots = (242, 439)
    coords_pk = (465, 439)
    coords_pp = (676, 439)
    coords_faceoff = (215, 520)
    coords_hits = (478, 520)
    coords_blocks = (693, 520)

    # Setup Text Elements
    preferred_team = game.preferred_team
    other_team = game.other_team
    preferred_stats = boxscore_preferred["teamStats"]["teamSkaterStats"]
    other_stats = boxscore_other["teamStats"]["teamSkaterStats"]
    preferred_stats_faceoff_percent = float(preferred_stats["faceOffWinPercentage"])
    preferred_stats_hits = preferred_stats["hits"]
    preferred_stats_ppg = int(preferred_stats["powerPlayGoals"])
    preferred_stats_pp = int(preferred_stats["powerPlayOpportunities"])
    preferred_stats_blocked = preferred_stats["blocked"]
    preferred_stats_pk_against = int(other_stats["powerPlayOpportunities"])
    preferred_stats_pk_killed = preferred_stats_pk_against - int(other_stats["powerPlayGoals"])

    # Score & Record
    text_pref_score = game.preferred_team.score
    text_other_score = game.other_team.score

    # Update records & get new for final image
    if game.preferred_team.score > game.other_team.score:
        pref_outcome = "win"
        other_outcome = "loss" if game.period.current < 4 else "ot"
    else:
        other_outcome = "loss"
        pref_outcome = "loss" if game.period.current < 4 else "ot"


    # pref_record = pref["leagueRecord"]
    # pref_record_str = ("({} - {} - {})".format(pref_record["wins"], pref_record["losses"],
    #                                            pref_record["ot"]))

    # other_record = other["leagueRecord"]
    # other_record_str = ("({} - {} - {})".format(other_record["wins"], other_record["losses"],
    #                                             other_record["ot"]))

    pref_record_str = preferred_team.get_new_record(pref_outcome)
    other_record_str = other_team.get_new_record(other_outcome)

    text_shots = preferred_team.shots
    text_pk = "{} / {}".format(preferred_stats_pk_killed, preferred_stats_pk_against)
    text_pp = "{} / {}".format(preferred_stats_ppg, preferred_stats_pp)
    text_faceoff = "{}%".format(preferred_stats_faceoff_percent)
    text_hits = preferred_stats_hits
    text_blocks = preferred_stats_blocked

    bg.paste(pref_logo, coords_pref_logo, pref_logo)
    bg.paste(other_logo, coords_other_logo, other_logo)

    draw = ImageDraw.Draw(bg)
    draw.text(coords_pref_score, str(text_pref_score), font_black, font_large)
    draw.text(coords_other_score, str(text_other_score), font_black, font_large)
    draw.text(coords_pref_record, pref_record_str, font_black, font_smaller)
    draw.text(coords_other_record, other_record_str, font_black, font_smaller)

    draw.text(coords_shots, str(text_shots), font_black, font_small)
    draw.text(coords_pk, str(text_pk), font_black, font_small)
    draw.text(coords_pp, str(text_pp), font_black, font_small)
    draw.text(coords_faceoff, str(text_faceoff), font_black, font_small)
    draw.text(coords_hits, str(text_hits), font_black, font_small)
    draw.text(coords_blocks, str(text_blocks), font_black, font_small)

    return bg

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# NHL Score & Parsing Methods
# ------------------------------------------------------------------------------

def get_team(nhl_team):
    """
    Passes team name to NHL API and returns team ID.
    :param team: Valid NHL team name.
    """

    team_name = nhl_team.title()
    url = "{}/api/v1/teams".format(NHLAPI_BASEURL)
    logging.info("Sending API Request - %s", url)
    team_json = req_session.get(url).json()
    teams = team_json["teams"]

    team_id = None
    for team in teams:
        if team["name"] == team_name:
            team_id = team["id"]

    if not team_id:
        raise ValueError("{} is not a valid NHL team. Check your configuraiton file!"
                         .format(team_name))
    return team_id


def is_game_today(team_id):
    """Queries the NHL Schedule API to determine if there is a game today.

    Args:
        team_id (int) - The unique identifier of the team (from get_team function).

    Returns:
        (bool, games_info)
        bool - True if game today, False if not.
        games_info (dict) - A dictionary from the Schedule API that describes game information.
    """
    now = datetime.now()
    if args.yesterday:
        now = now - timedelta(days=1)
    url = ("{}/api/v1/schedule?teamId={}&expand="
           "schedule.broadcasts,schedule.teams&date={:%Y-%m-%d}"
           .format(NHLAPI_BASEURL, team_id, now))
    try:
        logging.info("Sending API Request - %s", url)
        schedule = req_session.get(url).json()
        games_total = schedule["totalItems"]
    except requests.exceptions.RequestException:
        return False, None

    if games_total == 1:
        games_info = schedule["dates"][0]["games"][0]
        return True, games_info
    return False, None


def get_lineup(game, period, on_ice, players):
    """Tweets out the starting lineup for the preferred team.

    Args:
        game (Game): The current game instance.
        period (Period): The current period instance.
        on_ice (list): A list of players on the ice for the preferred team.
        players (dict): A dictionary of all players of the preferred team.
    """

    logging.info("On Ice Players - {}".format(on_ice))

    forwards = []
    defense = []
    goalies = []

    for player in on_ice:
        key_id = "ID{}".format(player)
        player_obj = players[key_id]
        logging.debug("Getting information for %s -- %s", key_id, player_obj)
        # player_last_name = player_obj["person"]["lastName"]
        player_last_name = player_obj["lastName"]
        player_type = player_obj["primaryPosition"]["type"]
        if player_type == "Forward":
            forwards.append(player_last_name)
        elif player_type == "Defenseman":
            defense.append(player_last_name)
        elif player_type == "Goalie":
            goalies.append(player_last_name)

    if period == 1:
        tweet_forwards = "-".join(forwards)
        tweet_defense = "-".join(defense)
        tweet_goalie = goalies[0]

        tweet_text = ("Tonight's {} starting lineup for your {} -\n\n{}\n{}\n{}"
                      .format(game.game_hashtag, game.preferred_team.team_name,
                              tweet_forwards, tweet_defense, tweet_goalie))
        send_tweet(tweet_text)

    elif period == 4 and game.game_type in ("PR", "R"):
        all_players = forwards + defense
        tweet_players = "-".join(all_players)
        try:
            tweet_goalie = goalies[0]
            tweet_text = ("On the ice to start overtime for your {} are:\n\n{} & {}\n\n{}"
                        .format(game.preferred_team.team_name, tweet_players,
                                tweet_goalie, game.game_hashtag))
        except IndexError:
            # If for some reason a goalie isn't detected on ice
            tweet_text = ("On the ice to start overtime for your {} are:\n\n{}\n\n{}"
                        .format(game.preferred_team.team_name, tweet_players, game.game_hashtag))
        send_tweet(tweet_text)


def goalie_pull_tweet(game, team):
    """Tweets a goalie pulled if the detected

    Args:
        game (Game): The current game instance.
        team (str): A string equal to home or away to indicate team.
    """
    goalie_pull_team = game.home_team.short_name if team == "home" else game.away_team.short_name
    goalie_pull_text = ("The {} have pulled their goalie with {} left in the {} period. {}"
                        .format(goalie_pull_team, game.period.time_remaining,
                                game.period.current_ordinal, game.game_hashtag))

    send_tweet(goalie_pull_text)


def parse_penalty(play, game):
    """Parses a JSON object of a penalty passed from loop_game_events.

    Args:
        play (dict): A dictionary of a penalty play attributes.
        game (Game): The current game instance.

    Note:
        No return value, sends a tweet.
    """

    penalty_team_name = play["team"]["name"]
    if penalty_team_name == game.home_team.team_name:
        penalty_on_team = game.home_team
        penalty_draw_team = game.away_team
    else:
        penalty_on_team = game.away_team
        penalty_draw_team = game.home_team

    # Get current game & skater attributes
    power_play_strength = game.power_play_strength
    penalty_on_skaters = penalty_on_team.skaters
    penalty_draw_skaters = penalty_draw_team.skaters

    # Might be able to use these later to change wording
    # penalty_on_team_name = penalty_on_team.short_name
    # penalty_draw_team_name = penalty_draw_team.short_name

    logging.info("PP Strength - %s | PenaltyOn Skaters - %s | PenaltyDraw Skaters - %s",
                 power_play_strength, penalty_on_skaters, penalty_draw_skaters)

    preferred_shortname = game.preferred_team.short_name
    # Determine skaters per side
    if power_play_strength == "Even" and penalty_on_skaters == 4 and penalty_draw_skaters == 4:
        # Teams are skating 4 on 4
        penalty_text_skaters = "Teams will skate 4-on-4."
    elif power_play_strength == "Even" and penalty_on_skaters == 3 and penalty_draw_skaters == 3:
        # Teams are skating 3 on 3 in regulation
        penalty_text_skaters = "Teams will skate 3-on-3."
    elif power_play_strength != "Even":
        if game.preferred_team.skaters == 5 and game.other_team.skaters == 4:
            penalty_text_skaters = "{} are headed to the power play!".format(preferred_shortname)
        elif game.preferred_team.skaters == 5 and game.other_team.skaters == 3:
            penalty_text_skaters = "{} will have a two-man advantage!".format(preferred_shortname)
        elif game.preferred_team.skaters == 4 and game.other_team.skaters == 5:
            penalty_text_skaters = "{} are headed to the penalty kill.".format(preferred_shortname)
        elif game.preferred_team.skaters == 3 and game.other_team.skaters == 5:
            penalty_text_skaters = ("{} will have to kill off a two-man advantage."
                                    .format(preferred_shortname))
    else:
        penalty_text_skaters = ""


    for player in play["players"]:
        if player["playerType"] == "PenaltyOn":
            penalty_playeron = player["player"]["fullName"]
            break

    penalty_type = play["result"]["secondaryType"].lower()
    penalty_severity = play["result"]["penaltySeverity"].lower()
    penalty_minutes = play["result"]["penaltyMinutes"]

    penalty_period_remain = play["about"]["periodTimeRemaining"]
    penalty_period = play["about"]["ordinalNum"]

    penalty_text_players = ("{} takes a {}-minute {} penalty for {} and "
                            "heads to the penalty box with {} left in the {} period."
                            .format(penalty_playeron, penalty_minutes, penalty_severity,
                                    penalty_type, penalty_period_remain, penalty_period))

    # Build power play / penalty kill stats
    penalty_on_stats = penalty_on_team.get_stat_and_rank("penaltyKillPercentage")
    penalty_draw_stats = penalty_draw_team.get_stat_and_rank("powerPlayPercentage")

    penalty_on_team_name = penalty_on_team.short_name
    penalty_on_stat = penalty_on_stats[0]
    penalty_on_rank = penalty_on_stats[1]
    penalty_on_rankstat_str = ("{} PK: {}% ({})"
                              .format(penalty_on_team_name, penalty_on_stat, penalty_on_rank))

    penalty_draw_team_name = penalty_draw_team.short_name
    penalty_draw_stat = penalty_draw_stats[0]
    penalty_draw_rank = penalty_draw_stats[1]
    penalty_draw_rankstat_str = ("{} PP: {}% ({})"
                                 .format(penalty_draw_team_name, penalty_draw_stat, penalty_draw_rank))

    penalty_tweet = ("{} {}\n\n{}\n{}\n\n{}".format(penalty_text_players, penalty_text_skaters,
                                                   penalty_on_rankstat_str, penalty_draw_rankstat_str,
                                                   game.game_hashtag))
    penalty_tweet_id = send_tweet(penalty_tweet)



def parse_regular_goal(play, game):
    """Parses attributes of a goal and tweets out the result.

    Args:
        play (dict): A dictionary of a penalty play attributes.
        game (Game): The current game instance.
    """

    goal_eventidx = play["about"]["eventIdx"]
    if game.assists_check == 0:
        logging.info("Event #%s was a goal - initial parsing loop!", goal_eventidx)
    else:
        logging.info("Parsing event #%s for assists - check #%s.",
                     goal_eventidx, game.assists_check)

    # Get players associated with scoring the goal (scorer & assists [in an array])
    assists = []
    for player in play["players"]:
        if player["playerType"] == "Scorer":
            goal_scorer_name = player["player"]["fullName"]
            goal_scorer_total = player["seasonTotal"]

        elif player["playerType"] == "Assist":
            assists.append(player["player"]["fullName"])

        elif player["playerType"] == "Goalie":
            goalie_name = player["player"]["fullName"]

    # Get other goal-related attributes
    goal_team = play["team"]["name"]
    goal_description = play["result"]["description"]
    goal_type = play["result"]["secondaryType"].lower()
    goal_strength = play["result"]["strength"]["name"]
    goal_eng = play["result"]["emptyNet"]
    goal_period = play["about"]["period"]
    goal_period_type = play["about"]["periodType"]
    goal_period_ord = play["about"]["ordinalNum"]
    goal_period_remain = play["about"]["periodTimeRemaining"]

    goal_score_away = play["about"]["goals"]["away"]
    goal_score_home = play["about"]["goals"]["home"]

    # Make number of goal lights equal number of goals
    if game.preferred_team.home_away == "home":
        goal_score_preferred = goal_score_home
        goal_score_other = goal_score_away
    else:
        goal_score_preferred = goal_score_away
        goal_score_other = goal_score_home

    # Regulation Goal Announcements
    if goal_period_type == "REGULAR":
        if goal_strength != "Even":
            goal_announce = "{} {} GOAL!".format(goal_team, goal_strength)
        elif goal_eng:
            goal_announce = "{} Empty Net GOAL!".format(goal_team)
        else:
            goal_announce = "{} GOAL!".format(goal_team)
    # Overtime goal announcements should be more exciting
    else:
        goal_announce = "{} OVERTIME GOAL!!".format(goal_team)

    # Change some wording around to make it a bit more unique
    # TODO: Add some randomness to this section
    if goal_type == "deflected":
        goal_scorer_text = ("{} deflects a shot past {} for his {} goal of the "
                            "season with {} left in the {} period!"
                            .format(goal_scorer_name, goalie_name, ordinal(goal_scorer_total),
                                    goal_period_remain, goal_period_ord))
    else:
        goal_scorer_text = ("{} scores his {} goal of the season on a {} "
                            "with {} left in the {} period!"
                            .format(goal_scorer_name, ordinal(goal_scorer_total),
                                    goal_type, goal_period_remain, goal_period_ord))

    # In order to pickup assists we need to just wait a bit longer
    # Increasing or decreasing assist_break will change that wait time
    if not assists:
        # If this is the first check with an unassisted goal, wait & check again
        # Only check twice since we can quote-tweet assists
        if game.assists_check < 2:
            game.assists_check += 1
            return False
        else:
            logging.info("No assists found - goal may be unassisted.")
            # goal_assist_text = "The goal is unassisted!"
            goal_assist_text = ""
            game.assists_check = 0

    # If the assists array is populated (with one or two players), go ahead and move on
    elif len(assists) == 1:
        goal_assist_text = "Give the assist to {}!".format(assists[0])
    else:
        goal_assist_text = ("The goal was assisted by {} & {}."
                            .format(assists[0], assists[1]))

    # Goal scored by Preferred Team
    if goal_team == game.preferred_team.team_name:
        # Check previous goal to see if we can skip this goal
        if len(game.preferred_team.goals == goal_score_preferred):
            logging.warning("A duplicate goal was detected, skip this eventIdx!")
            return True

        # Count number of goals per game
        goals_per_game = 1
        preferred_goals = game.preferred_team.goals
        for idx, goal in enumerate(preferred_goals):
            if goal_scorer_name == preferred_goals[idx].scorer:
                goals_per_game += 1

        # Format Goal Scorer Text to include multi-goal games
        if goals_per_game == 2:
            goal_scorer_text = ("With his {} goal of the game, {}"
                                .format(ordinal(goals_per_game), goal_scorer_text))
        elif goals_per_game == 3:
            goal_scorer_text = "🎩🎩🎩 HAT TRICK! {}".format(goal_scorer_text)
        elif goals_per_game > 3:
            goal_scorer_text = "{} GOALS!! {}".format(goals_per_game, goal_scorer_text)


        num_lights = goal_score_home if game.preferred_team.home_away == "home" else goal_score_away
        # goal_lights_text = '🚨' * num_lights
        goal_lights_text = '\U0001F6A8' * num_lights
        team_hashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name)

        if not assists:
            goal_text_player = "{}".format(goal_scorer_text)
        else:
            goal_text_player = "{} {}".format(goal_scorer_text, goal_assist_text)

        goal_text_score = ("Score - {}: {} / {}: {}"
                           .format(game.preferred_team.short_name, goal_score_preferred,
                                   game.other_team.short_name, goal_score_other))
        goal_text_full = ("{} {}\n\n{}\n\n{}\n\n{} {}"
                          .format(goal_announce, goal_lights_text, goal_text_player,
                                  goal_text_score, team_hashtag, game.game_hashtag))
        goal_tweet = send_tweet(goal_text_full)

        # Create Goal Object & append to Team goals array
        goal = nhl_game_events.Goal(goal_description, goal_eventidx, goal_period, goal_period_type,
                                    goal_period_ord, goal_period_remain, goal_score_home,
                                    goal_score_away, goal_team, goal_type, goal_strength,
                                    goal_eng, goal_scorer_name, assists, goal_tweet)

        game.preferred_team.goals.append(goal)

    # Goal was scored by Other Team
    else:
        num_thumbs = goal_score_home if game.other_team.home_away == "home" else goal_score_away
        goal_thumbs_text = '\U0001F44E' * num_thumbs

        goal_announce = "{} scored. {}".format(goal_team, goal_thumbs_text)
        goal_text_player = ("{} with his {} of the season - {} left in the {} period."
                            .format(goal_scorer_name, ordinal(goal_scorer_total),
                                    goal_period_remain, goal_period_ord))
        goal_text_score = ("Score - {}: {} / {}: {}"
                           .format(game.preferred_team.short_name, goal_score_preferred,
                                   game.other_team.short_name, goal_score_other))
        goal_other_tweet = ("{}\n\n{}\n\n{}\n\n{}"
                            .format(goal_announce, goal_text_player,
                                    goal_text_score, game.game_hashtag))
        send_tweet(goal_other_tweet)

    return True


def parse_shootout_event(play, game):
    """Parses attributes of a shootout event and tweets out the result.

    Args:
        play (dict): A dictionary of a penalty play attributes.
        game (Game): The current game instance.
        period (Period): The current period instance.
    """

    for player in play["players"]:
        if player["playerType"] == "Goalie":
            goalie_name = player["player"]["fullName"]
        # Covers Shots & Goals
        else:
            shooter_name = player["player"]["fullName"]

    shootout_team = play["team"]["name"]
    shootout_event = play["result"]["eventTypeId"]
    shootout_emoji = "\U00002705" if shootout_event == "GOAL" else "\U0000274C"
    logging.info("Shootout event (%s - %s) detected for %s.",
                 shootout_event, shootout_emoji, shootout_team)

    # Preferred Team is shooting
    if shootout_team == game.preferred_team.team_name:
        game.shootout.preferred_score.append(shootout_emoji)
        if shootout_event == "GOAL":
            shootout_event_text = "{} shoots & scores! \U0001F6A8".format(shooter_name)
        elif shootout_event == "SHOT":
            shootout_event_text = ("{}'s shot saved by {}. \U0001F620"
                                   .format(shooter_name, goalie_name))
        else:
            shootout_event_text = "{} shoots & misses. \U0001F620".format(shooter_name)

    # Other Team is shooting
    else:
        game.shootout.other_score.append(shootout_emoji)
        if shootout_event == "GOAL":
            shootout_event_text = "{} shoots & scores. \U0001F620".format(shooter_name)
        elif shootout_event == "SHOT":
            shootout_event_text = ("{}'s shot saved by {}! \U0001F645\U0000200D\U00002642\U0000FE0F"
                                   .format(shooter_name, goalie_name))
        else:
            shootout_event_text = ("{} shoots & misses. \U0001F645\U0000200D\U00002642\U0000FE0F"
                                   .format(shooter_name))

    shootout_preferred_score = " - ".join(game.shootout.preferred_score)
    shootout_other_score = " - ".join(game.shootout.other_score)
    shootout_score_text = ("{}: {}\n{}: {}"
                           .format(game.preferred_team.short_name, shootout_preferred_score,
                                   game.other_team.short_name, shootout_other_score))
    shootout_tweet_text = ("{}\n\n{}\n\n{}"
                           .format(shootout_event_text, shootout_score_text, game.game_hashtag))
    send_tweet(shootout_tweet_text)

    # Increment Shootout Shots
    game.shootout.shots = game.shootout.shots + 1


def check_scoring_changes(previous_goals, game):
    """
    Loops through previously scored goals & determins if a scoring change has occurred.

    Args:
        previous_goals (list): A list of old goals (contains dictionary)
        game (Game): The current game instance.
    """

    preferred_goals = game.preferred_team.goals

    for idx, previous_goal in enumerate(previous_goals):
        assists = []
        for player in previous_goal["players"]:
            if player["playerType"] == "Scorer":
                goal_scorer_name = player["player"]["fullName"]

            elif player["playerType"] == "Assist":
                assists.append(player["player"]["fullName"])

        # Check for changes in existing goal array
        if goal_scorer_name != preferred_goals[idx].scorer:
            logging.info("Goal scorer change detected for goal #%s.", idx)
            # goal_tweet = preferred_goals[idx].tweet
            goal_tweet = "{}{}".format(TWITTER_URL, preferred_goals[idx].tweet)
            goal_scorechange_announce = "Scoring change on the below goal."
            if not assists:
                goal_scorechange_text = ("Now reads as an unassisted goal for {}."
                                         .format(goal_scorer_name))
            elif len(assists) == 1:
                goal_scorechange_text = ("Now reads as {} from {}."
                                         .format(goal_scorer_name, assists[0]))
            else:
                goal_scorechange_text = ("Now reads as {} from {} and {}."
                                         .format(goal_scorer_name, assists[0], assists[1]))

            # Use this to quote tweet
            goal_scorechange_tweet = ("{} {} {}\n{}"
                                      .format(goal_scorechange_announce, goal_scorechange_text,
                                              game.game_hashtag, goal_tweet))
            goal_scorechange_tweeturl = send_tweet(goal_scorechange_tweet)

            # Adjust the values of the array with the changed ones
            preferred_goals[idx].scorer = goal_scorer_name
            preferred_goals[idx].assists = assists
            preferred_goals[idx].tweet = goal_scorechange_tweeturl

        # This is used when ONLY the assists change.
        elif assists != preferred_goals[idx].assists:
            logging.info("Assists added or changed for goal #%s.", idx)
            logging.info("New assists - %s", assists)
            goal_tweet = "{}{}".format(TWITTER_URL, preferred_goals[idx].tweet)

            # Original goal has no assists, just tweet that indication.
            if not preferred_goals[idx].assists:
                if len(assists) == 1:
                    goal_assistchange_text = ("Give the lone assist on {}'s goal to {}."
                                              .format(preferred_goals[idx].scorer, assists[0]))
                elif len(assists) == 2:
                    goal_assistchange_text = ("The goal is now assisted by {} and {}."
                                              .format(assists[0], assists[1]))
                else:
                    goal_assistchange_text = "The goal is now unassisted."

                # Use this to quote tweet
                goal_assistchange_tweet = ("{} {}\n{}"
                                           .format(goal_assistchange_text,
                                                   game.game_hashtag, goal_tweet))
                goal_assistchange_url = send_tweet(goal_assistchange_tweet)

            # Assists on the original goal have changed, quote tweet that with different wording.
            else:
                goal_assistchange_announce = "The assists on the below goal have changed."
                if len(assists) == 1:
                    goal_assistchange_text = ("Give the lone assist on {}'s goal to {}."
                                              .format(preferred_goals[idx].scorer, assists[0]))
                elif len(assists) == 2:
                    goal_assistchange_text = ("The goal is now assisted by {} and {}."
                                              .format(assists[0], assists[1]))
                else:
                    goal_assistchange_text = "The goal is now unassisted."

                # Use this to quote tweet
                goal_assistchange_tweet = ("{} {} {}\n{}"
                                           .format(goal_assistchange_announce,
                                                   goal_assistchange_text, game.game_hashtag,
                                                   goal_tweet))
                goal_assistchange_url = send_tweet(goal_assistchange_tweet)

            # Then, adjust the values of the array with the changed ones
            preferred_goals[idx].scorer = goal_scorer_name
            preferred_goals[idx].assists = assists
            preferred_goals[idx].tweet = goal_assistchange_url

        else:
            logging.info("No scoring change detected for goal #%s.", idx)


def get_game_events(game):
    """
    Queries the NHL Live Feed API endpoint and returns a JSON object.

    Input:
    game - current game as a Game object

    Output:
    live_feed_json - JSON object of live feed results
    """

    try:
        live_feed_json = req_session.get(game.live_feed).json()
    except requests.exceptions.RequestException:
        logging.error("Game Events request (%s) timed out!", game.live_feed)
        return None

    if args.localdata:
        live_feed_json = json.load(open('localdata/sample-data.json'))

    # Update all object attributes (game, period & teams)
    update_object_attributes(live_feed_json, game)

    # Return a JSON object of all game events
    return live_feed_json


def loop_game_events(json_feed, game):
    """
    Takes a JSON object of game events & parses for events.

    Input:
    json - JSON object of live feed results (usually from get_game_events)
    game - current game as a Game object

    Ouput:
    None
    """

    # Logic for preferred / other team objects via if statement
    # (preferred_team, other_team) = nhl_game_events.preferred_teams(home_team, away_team)

    all_plays = json_feed["liveData"]["plays"]["allPlays"]
    linescore = json_feed["liveData"]["linescore"]
    shootout = True if linescore["currentPeriodOrdinal"] == "SO" else False
    logging.info("Game Event Shootout Loop - %s", shootout)

    # Subset all_plays dictionary by last_event_idx to shorten loop
    next_event = game.last_event_idx + 1
    new_plays = all_plays[next_event:]

    # If there are no new plays, use this loop to check for scoring changes
    if not new_plays:
        previous_goals = []
        preferred_team_name = game.preferred_team.team_name
        previous_plays = all_plays[:game.last_event_idx]
        for previous_play in previous_plays:
            prev_event_type = previous_play["result"]["eventTypeId"]
            prev_event_period = previous_play["about"]["ordinalNum"]
            if prev_event_type == "GOAL" and prev_event_period != "SO":
                prev_event_team = previous_play["team"]["name"]
                if prev_event_team == preferred_team_name:
                    previous_goals.append(previous_play)

        # This can happen if the Game Bot misses a goal - parse the last goal in all_plays
        if len(previous_goals) > len(game.preferred_team.goals):
            logging.info("Goal discrepancy detected - parsing previous goal.")
            last_goal = previous_goals[-1]
            parse_regular_goal(last_goal, game)
            return

        # Send array into scoring changes function
        logging.info("No new events detected - going to check for scoring changes.")
        check_scoring_changes(previous_goals, game)
        return

    # For completeness, print event ID & type in our detection line
    if len(new_plays) < 10:
        new_plays_shortlist = list()
        for play in new_plays:
            event_type = play["result"]["eventTypeId"]
            event_idx = play["about"]["eventIdx"]
            short_list_play = "{}: {}".format(event_idx, event_type)
            new_plays_shortlist.append(short_list_play)
        logging.info("%s new event(s) detected - looping through them now. %s", \
                    len(new_plays), new_plays_shortlist)
    else:
        logging.info("%s new event(s) detected - looping through them now.", len(new_plays))

    # Loop through any new plays to check for events
    for play in new_plays:
        event_type = play["result"]["eventTypeId"]
        event_idx = play["about"]["eventIdx"]
        event_description = play["result"]["description"]
        event_period = play["about"]["period"]
        event_period_ordinal = play["about"]["ordinalNum"]
        period_type = play["about"]["periodType"]

        # Parse each play by checking it's event_type and parsing information if needed
        # if event_type == "PERIOD_READY" and event_period == 1:
        if (event_type == "PERIOD_READY" and game.period.current == 1):
            preferred_team = game.preferred_team
            preferred_homeaway = preferred_team.home_away
            on_ice = json_feed["liveData"]["boxscore"]["teams"][preferred_homeaway]["onIce"]
            # players = json_feed["liveData"]["boxscore"]["teams"][preferred_homeaway]["players"]
            players = json_feed["gameData"]["players"]
            if recent_event(play):
                get_lineup(game, event_period, on_ice, players)

        elif event_type == "PERIOD_READY" and event_period == 4 and game.game_type in ("PR", "R"):
            preferred_team = game.preferred_team
            preferred_homeaway = preferred_team.home_away
            on_ice = json_feed["liveData"]["boxscore"]["teams"][preferred_homeaway]["onIce"]
            # players = json_feed["liveData"]["boxscore"]["teams"][preferred_homeaway]["players"]
            players = json_feed["gameData"]["players"]
            if recent_event(play):
                get_lineup(game, event_period, on_ice, players)

        elif event_type == "PERIOD_READY" and event_period == 5 and game.game_type in ("PR", "R"):
            if recent_event(play):
                tweet_text = ("The shootout is ready to begin at {}!\n\n{}"
                              .format(game.venue, game.game_hashtag))

        elif event_type == "PERIOD_START":
            if event_period == 1:
                tweet_text = ("The puck has dropped between the {} & {} at {}!\n\n{}"
                              .format(game.preferred_team.short_name, game.other_team.short_name,
                                      game.venue, game.game_hashtag))
            elif event_period in (2, 3):
                tweet_text = ("It's time for the {} period at {}.\n\n{}"
                              .format(event_period_ordinal, game.venue,
                                      game.game_hashtag))
            elif event_period == 4 and game.game_type in ("PR", "R"):
                tweet_text = ("Who will be the hero this time? 3-on-3 OT starts now at {}!\n\n{}"
                              .format(game.venue, game.game_hashtag))

            if recent_event(play):
                send_tweet(tweet_text)

        elif event_type == "PERIOD_END":
            if event_period in (1, 2):
                # Calculate win percentage when winning / trailing after period
                pref_score = game.preferred_team.score
                other_score = game.other_team.score

                if pref_score > other_score:
                    if event_period == 1:
                        pref_pd_stats, pref_pd_rank = game.preferred_team.get_stat_and_rank("winLeadFirstPer")
                    elif event_period == 2:
                        pref_pd_stats, pref_pd_rank = game.preferred_team.get_stat_and_rank("winLeadSecondPer")

                    pref_pd_stats_pct = pref_pd_stats * 100
                    win_lead_text = ("When leading after the {} period, the {} win {}% "
                                     "of their games ({} in the NHL)."
                                     .format(event_period_ordinal, game.preferred_team.short_name,
                                             pref_pd_stats_pct, pref_pd_rank))
                else:
                    win_lead_text = None

                # Build end of period tweet
                if win_lead_text is None:
                    tweet_text = ("The {} period of {} comes to an end.\n\n"
                                "{}: {} ({} shots)\n{}: {} ({} shots)"
                                .format(event_period_ordinal, game.game_hashtag,
                                        game.preferred_team.short_name, game.preferred_team.score,
                                        game.preferred_team.shots, game.other_team.short_name,
                                        game.other_team.score, game.other_team.shots))
                else:
                    tweet_text = ("The {} period of {} comes to an end. {}\n\n"
                                "{}: {} ({} shots)\n{}: {} ({} shots)"
                                .format(event_period_ordinal, game.game_hashtag, win_lead_text,
                                        game.preferred_team.short_name, game.preferred_team.score,
                                        game.preferred_team.shots, game.other_team.short_name,
                                        game.other_team.score, game.other_team.shots))
                if recent_event(play):
                    send_tweet(tweet_text)

                # 1st and 2nd intermission is 18 minutes - sleep for that long
                linescore = json_feed["liveData"]["linescore"]
                intermission_remain = linescore["intermissionInfo"]["intermissionTimeRemaining"]
                logging.info("Intermission Remaining: %s -- " \
                             "sleep for 60 seconds less.", intermission_remain)
                intermission_sleep = intermission_remain - 60
                if intermission_sleep > 60:
                    time.sleep(intermission_sleep)

            elif event_period == 3 and (game.preferred_team.score == game.other_team.score):
                tweet_text = ("60 minutes wasn't enough to decide this game. "
                              "{} and {} headed to overtime tied at {}.\n\n{}"
                              .format(game.preferred_team.short_name, game.other_team.short_name,
                                      game.preferred_team.score, game.game_hashtag))
                if recent_event(play):
                    send_tweet(tweet_text)

        elif event_type == "PENALTY":
            if recent_event(play):
                parse_penalty(play, game)

        elif event_type == "GOAL" and period_type != "SHOOTOUT":
            assists_check_done = parse_regular_goal(play, game)
            while not assists_check_done:
                # Get events from API & parse single event again
                game_events_recheck = get_game_events(game)
                assist_event = game_events_recheck["liveData"]["plays"]["allPlays"][event_idx]
                assists_check_done = parse_regular_goal(assist_event, game)

                # Sleep for 4 seconds (enough time to get assists)
                time.sleep(4)
            game.assists_check = 0
        elif event_type in ("GOAL", "SHOT", "MISSED_SHOT") and period_type == "SHOOTOUT":
            parse_shootout_event(play, game)
        else:
            logging.debug("Other event: %s - %s", event_type, event_description)

        # For each loop iteration, update the eventIdx in the game object
        game.last_event_idx = event_idx


def parse_end_of_game(json_feed, game):
    """
    Takes a JSON object of game events & parses for events.

    Input:
    json - JSON object of live feed results (usually from get_game_events)
    game - current game as a Game object

    Ouput:
    None
    """

    all_players = json_feed["gameData"]["players"]

    boxscore = json_feed["liveData"]["boxscore"]["teams"]
    decisions = json_feed["liveData"]["decisions"]

    # Once available, build the final score tweet & send it.
    boxscore_away = boxscore["away"]
    boxscore_home = boxscore["home"]
    boxscore_preferred = boxscore_home if game.home_team.preferred else boxscore_away
    boxscore_other = boxscore_away if game.home_team.preferred else boxscore_home

    preferred_home_text = "on the road" if game.preferred_team.home_away == "away" else "at home"
    preferred_hashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name)
    perferred_final_score = game.preferred_team.score
    other_final_score = game.other_team.score

    if perferred_final_score > other_final_score:
        final_score_text = ("{} win {} over the {} by a score of {} to {}! 🚨🚨🚨"
                            .format(game.preferred_team.short_name, preferred_home_text,
                                    game.other_team.short_name, game.preferred_team.score,
                                    game.other_team.score))
    else:
        final_score_text = ("{} lose {} to the {} by a score of {} to {}. \U0001F44E"
                            .format(game.preferred_team.short_name, preferred_home_text,
                                    game.other_team.short_name, game.preferred_team.score,
                                    game.other_team.score))

    # Generate Final Image
    img = final_image(game, boxscore_preferred, boxscore_other)
    final_score_tweet = ("{} {} {}"
                         .format(final_score_text, preferred_hashtag, game.game_hashtag))

    if game.finaltweets["finalscore"] is False:
        if args.notweets:
            img.show()
            logging.info("%s", final_score_tweet)
        else:
            img_filename = ('resources/images/GamedayFinal-{}.jpg'
                            .format(game.preferred_team.games + 1))
            img.save(img_filename)
            api = get_api()
            api.update_with_media(img_filename, final_score_tweet)
            game.finaltweets["finalscore"] = True

    # Once available, build the 3-stars tweet & send it.
    try:
        logging.info("Checking for the 3-stars of the game.")
        first_star_id = "ID{}".format(decisions["firstStar"]["id"])
        second_star_id = "ID{}".format(decisions["secondStar"]["id"])
        third_star_id = "ID{}".format(decisions["thirdStar"]["id"])

        first_star_name = decisions["firstStar"]["fullName"]
        second_star_name = decisions["secondStar"]["fullName"]
        third_star_name = decisions["thirdStar"]["fullName"]

        first_star_tricode = all_players[first_star_id]["currentTeam"]["triCode"]
        second_star_tricode = all_players[second_star_id]["currentTeam"]["triCode"]
        third_star_tricode = all_players[third_star_id]["currentTeam"]["triCode"]

        first_star_full = "{} ({})".format(first_star_name, first_star_tricode)
        second_star_full = "{} ({})".format(second_star_name, second_star_tricode)
        third_star_full = "{} ({})".format(third_star_name, third_star_tricode)

        stars_text = ("⭐️: {}\n⭐️⭐️: {}\n⭐️⭐️⭐️: {}"
                      .format(first_star_full, second_star_full, third_star_full))
        stars_tweet = ("The three stars for the game are - \n{}\n\n{}"
                       .format(stars_text, game.game_hashtag))
        if game.finaltweets["stars"] is False:
            if args.notweets:
                logging.info("%s", stars_tweet)
            else:
                send_tweet(stars_tweet)
                game.finaltweets["stars"] = True
    except KeyError:
        return False

    all_tweets_sent = all(value is True for value in game.finaltweets.values())
    return all_tweets_sent


def game_preview(game):
    """
    Runs when the game is in preview state and it is not yet game time.

    Input:
    game - current game as a Game object

    Output:
    None
    """

    logging.info("Game Date (UTC) - %s", game.date_time)
    logging.info("Game Date (LCL) - %s", game.game_time_local)
    logging.info("Game State is Preview - try to get preview image, "
                 "send preview tweet & sleep for %s seconds.",
                 game.game_time_countdown)

    # Get preferred & other team from Game object
    (preferred_team, other_team) = game.get_preferred_team()

    # Format & send preview tweet
    clock_emoji = nhl_game_events.clock_emoji(game.game_time_local)

    preview_text_teams = (
        "Tune in {} when the {} take on the {} at {}."
        .format(game.game_time_of_day, preferred_team.team_name, other_team.team_name, game.venue)
    )
    preview_text_emojis = (
        "{}: {}\n\U0001F4FA: {}\n\U00000023\U0000FE0F\U000020E3: {}"
        .format(clock_emoji, game.game_time_local, preferred_team.tv_channel, game.game_hashtag)
    )
    preview_tweet_text = "{}\n\n{}".format(preview_text_teams, preview_text_emojis)
    # logging.info("[TWEET] \n%s", preview_tweet_text)
    # Sleep script until game time.

    # Get Season Series
    season_series_strings = nhl_game_events.season_series(game.game_id, game.preferred_team,
                                                          game.other_team)

    season_series_str = season_series_strings[0]
    if season_series_str is None:
        season_series_tweet = ("This is the first meeting of the season between"
                               "the {} & the {}.\n\n{} {} {}"
                               .format(game.preferred_team.short_name, game.other_team.short_name,
                                       game.preferred_team.team_hashtag,
                                       game.other_team.team_hashtag, game.game_hashtag))
    else:
        points_leader_str = season_series_strings[1]
        toi_leader_str = season_series_strings[2]

        season_series_tweet = ("{}\n{}\n{}\n\n{} {} {}"
                               .format(season_series_str, points_leader_str, toi_leader_str,
                                       game.preferred_team.team_hashtag,
                                       game.other_team.team_hashtag, game.game_hashtag))

    # Get Goalie Projection
    pref_team_name = game.preferred_team.team_name
    pref_team_homeaway = game.preferred_team.home_away
    other_team_name = game.other_team.team_name
    pref_goalie, other_goalie = nhl_game_events.dailyfaceoff_goalies(
                                preferred_team, other_team, pref_team_homeaway)
    pref_goalie_tweet = ("Projected {} Goalie for {}:\n{}"
                  .format(game.game_hashtag, game.preferred_team.team_hashtag, pref_goalie))
    other_goalie_tweet = ("Projected {} Goalie for {}:\n{}"
                  .format(game.game_hashtag, game.other_team.team_hashtag, other_goalie))


    img = preview_image(game)
    if args.notweets:
        img.show()
        logging.info("%s", preview_tweet_text)
        logging.info("%s", goalie_tweet)
        logging.info("%s", season_series_tweet)
    else:
        if img is not None:
            img_filename = 'resources/images/Gameday-{}.jpg'.format(game.preferred_team.games + 1)
            img.save(img_filename)
            api = get_api()
            image_tweet = api.update_with_media(img_filename, preview_tweet_text)
            image_tweet_id = image_tweet.id_str

            pref_goalie_tweet_id = send_tweet(pref_goalie_tweet, reply=image_tweet_id)
            other_goalie_tweet_id = send_tweet(other_goalie_tweet, reply=pref_goalie_tweet_id)
            send_tweet(season_series_tweet, reply=other_goalie_tweet_id)

    time.sleep(game.game_time_countdown)


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# MAIN PROGRAM FLOW
# ------------------------------------------------------------------------------

# This line is to prevent code from being executed, if ever imported.
if __name__ == '__main__':
    args = parse_arguments()
    setup_logging()

    if args.debugtweets:
        TWITTER_ID = config['ENDPOINTS']['DEBUG_TWITTER_HANDLE']

    # If --team is specified, override TEAM_BOT constant
    if args.team is not None:
        TEAM_BOT = args.team

    # Log script start lines
    logging.info('#' * 80)
    logging.info('New instance of the Hockey Twitter Bot started...')
    logging.info('ARGS - notweets: %s, console: %s, team: %s',
                 args.notweets, args.console, args.team)
    logging.info("%s\n", "#" * 80)

    # Create a requests object to maintain session
    req_session = requests.Session()

    # Check if there is a game scheduled for today
    # If there is no game, exit the program
    game_today, game_info = is_game_today(get_team(TEAM_BOT))
    if not game_today:
        if is_linode():
            logging.info(
                "No game scheduled for today - shutting down Linode & exiting script.")
            linode_shutdown()
        else:
            logging.info("No game scheduled for today - exiting script.")
        sys.exit()

    # Create a Game Object
    gameobj_game_id = game_info["gamePk"]
    gameobj_game_type = game_info["gameType"]
    gameobj_date_time = game_info["gameDate"]
    gameobj_game_state = game_info["status"]["abstractGameState"]
    if args.localdata:
        gameobj_game_state = "Live"
    gameobj_venue = game_info["venue"]["name"]
    gameobj_live_feed = game_info["link"]

    gameobj_broadcasts = {}
    broadcasts = game_info["broadcasts"]
    for broadcast in broadcasts:
        broadcast_team = broadcast["type"]
        if broadcast_team == "national":
            gameobj_broadcasts["away"] = broadcast["name"]
            gameobj_broadcasts["home"] = broadcast["name"]
            break
        else:
            broadcast_channel = broadcast["name"]
            gameobj_broadcasts[broadcast_team] = broadcast_channel

    # Create Team Objects
    # Note: Schedule endpoint calls 3-character 'abbreviation' - not 'triCcode')
    # TODO: Review record / games played for playoffs
    awayteam_info = game_info["teams"]["away"]["team"]
    awayteam_record = game_info["teams"]["away"]["leagueRecord"]
    awayteamobj_games = awayteam_record["wins"] + awayteam_record["losses"] + awayteam_record["ot"]
    awayteamobj_name = awayteam_info["name"]
    awayteamobj_id = awayteam_info["id"]
    awayteamobj_shortname = awayteam_info["teamName"]
    awayteamobj_tri = awayteam_info["abbreviation"]
    try:
        awayteamobj_tv = gameobj_broadcasts["away"]
    except KeyError:
        awayteamobj_tv = "N/A"
    away_team_obj = nhl_game_events.Team(awayteamobj_id, awayteamobj_name, awayteamobj_shortname,
                                         awayteamobj_tri, "away", awayteamobj_tv, awayteamobj_games,
                                         awayteam_record)

    hometeam_info = game_info["teams"]["home"]["team"]
    hometeam_record = game_info["teams"]["home"]["leagueRecord"]
    hometeamobj_games = hometeam_record["wins"] + hometeam_record["losses"] + hometeam_record["ot"]
    hometeamobj_name = hometeam_info["name"]
    hometeamobj_id = hometeam_info["id"]
    hometeamobj_shortname = hometeam_info["teamName"]
    hometeamobj_tri = hometeam_info["abbreviation"]
    try:
        hometeamobj_tv = gameobj_broadcasts["home"]
    except KeyError:
        hometeamobj_tv = "N/A"
    home_team_obj = nhl_game_events.Team(hometeamobj_id, hometeamobj_name, hometeamobj_shortname,
                                         hometeamobj_tri, "home", hometeamobj_tv, hometeamobj_games,
                                         hometeam_record)

    # Set Preferred Team
    home_team_obj.preferred = bool(home_team_obj.team_name == TEAM_BOT)
    away_team_obj.preferred = bool(away_team_obj.team_name == TEAM_BOT)
    preferred_indicator = "home" if home_team_obj.preferred else "away"

    game_obj = nhl_game_events.Game(gameobj_game_id, gameobj_game_type, gameobj_date_time,
                                    gameobj_game_state, gameobj_venue, home_team_obj,
                                    away_team_obj, preferred_indicator, gameobj_live_feed)

    # print(game_obj)
    # for k, v in vars(game_obj).items():
    #     print("{}: {}".format(k, v))
    # print("------------------------------")
    # print(home_team_obj)
    # for k, v in vars(home_team_obj).items():
    #     print("{}: {}".format(k, v))
    # print("------------------------------")
    # print(away_team_obj)
    # for k, v in vars(away_team_obj).items():
    #     print("{}: {}".format(k, v))

    # sys.exit()

    # All objects are created, start the game loop
    # game_loop()
    while True:
        if game_obj.game_state == "Preview":
            if game_obj.game_time_countdown > 0:
                # show_all_objects()
                game_preview(game_obj)
            else:
                logging.info(
                    "Past game time, but game status still 'Preview' - sleep for 30 seconds.")
                get_game_events(game_obj)
                time.sleep(30)

        elif game_obj.game_state == "Live":
            logging.info('-' * 80)
            logging.info("Game is currently live - checking events after event Idx %s.",
                         game_obj.last_event_idx)
            game_events = get_game_events(game_obj)
            loop_game_events(game_events, game_obj)
            logging.info("Sleeping for 5 seconds...")
            time.sleep(5)

        elif game_obj.game_state == "Final":
            logging.info("Game is 'Final' - increase sleep time to 10 seconds.")
            game_events = get_game_events(game_obj)
            script_done = parse_end_of_game(game_events, game_obj)

            if not script_done:
                time.sleep(10)
            else:
                if is_linode():
                    logging.info("Script is done - shutting down Linode & exiting script.")
                    linode_shutdown()
                else:
                    logging.info("Script is done - exiting script.")
                sys.exit()
