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
from subprocess import Popen

import dateutil.tz
# 3rd Party Imports
import linode
import pytz
import requests
import tweepy
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

# Discord imports

import asyncio
import discord
import time
import threading
import readline

# My Local / Custom Imports
import advanced_stats
import hockey_bot_imaging
import nhl_game_events
import other_game_info

# If running via Docker, there is no secret.py file
# Config is done via ENV variables - just pass through this error
try:
    from secret import *
except ImportError:
    pass


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Congfiguration, Logging & Argument Parsing
# ------------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.realpath(__file__))
config = configparser.ConfigParser()
conf_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.ini')
config.read(conf_path)

TEAM_BOT = config['DEFAULT']['TEAM_NAME']
NHLAPI_BASEURL = config['ENDPOINTS']['NHL_BASE']
TWITTER_URL = config['ENDPOINTS']['TWITTER_URL']
TWITTER_ID = config['ENDPOINTS']['TWITTER_HANDLE']
VPS_CLOUDHOST = config['VPS']['CLOUDHOST']
VPS_HOSTNAME = config['VPS']['HOSTNAME']

# Discord Imports (Uncomment Top Line to Enable Debug Mode)
# CHANNEL_ID = config['DISCORD']['DEBUG_CHANNEL_ID']
CHANNEL_ID = config['DISCORD']['CHANNEL_ID']
message_queue = asyncio.Queue()


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
    log_file_name = datetime.now().strftime(config['SCRIPT']['LOG_FILE_NAME'] + '-%Y%m%d%H%M%s.log')
    log_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'logs', log_file_name)
    if args.console and args.debug:
        logging.basicConfig(level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S',
                            format='%(asctime)s - %(module)s.%(funcName)s (%(lineno)d) - %(levelname)s - %(message)s')
    elif args.console:
        logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                            format='%(asctime)s - %(module)s.%(funcName)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(filename=log_file, level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
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
    parser.add_argument("--overridelines", help="override lines if None are returned",
                        action="store_true")
    parser.add_argument("--yesterday", help="get yesterday game on the schedule",
                        action="store_true")
    parser.add_argument("--date", help="override game date",
                        action="store")
    parser.add_argument("--split", help="split squad game index",
                        action="store_true")
    parser.add_argument("--docker", help="running in a docker container",
                        action="store_true")
    parser.add_argument("--discord", help="Send messages to discord channel",
                        action="store_true")
    arguments = parser.parse_args()
    return arguments


def parse_env_variables(args):
    """
    For when running via Docker, parse Environment variables.
    Environment variables replace command line arguments.

    Input:
    args - argument Namespace

    Output:
    None
    """

    if "ARGS_NOTWEETS" in os.environ and os.environ['ARGS_NOTWEETS'] == "TRUE":
        args.notweets = True

    if "ARGS_DEBUG" in os.environ and os.environ['ARGS_DEBUG'] == "TRUE":
        args.debug = True

    if "ARGS_TEAM" in os.environ:
        args.team = os.environ['ARGS_TEAM']

    if "ARGS_DEBUGTWEETS" in os.environ and os.environ['ARGS_DEBUGTWEETS'] == "TRUE":
        args.debugtweets = True

    if "ARGS_DATE" in os.environ:
        args.date = os.environ['ARGS_DATE']


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
# Discord Methods
# ------------------------------------------------------------------------------
def bot_thread(loop, bot, bot_token, message_queue, channel_id):
    asyncio.set_event_loop(loop)

    @bot.event
    async def on_ready():
        while True:
            data = await message_queue.get()
            if len(data) == 3:  # No Image
                event = data[0]
                message = data[1]
                channel_id = data[2]
                message = f'▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{message}'
                try:
                    await bot.send_message(bot.get_channel(channel_id), message)
                except Exception as e:
                    logging.warning('Error sending Discord message - %s', e)

                event.set()

            elif len(data) == 4:    # Image to Send
                logging.info('Discord Image Detected - %s', data)
                event = data[0]
                message = data[1]
                image = data[2]
                channel_id = data[3]
                message = f'▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n{message}'
                try:
                    await bot.send_file(bot.get_channel(channel_id), image, content=message)
                except Exception as e:
                    logging.warning('Error sending Discord image & message - %s', e)

                event.set()

    bot.run(DISCORD_TOKEN, bot = bot_token)


def send_discord(channel_id, message, image=None):
    event = threading.Event()
    if image is None:
        logging.info('Sending Discord Message (Channel %s) - %s', channel_id, message)
        message_queue.put_nowait([event, message, channel_id])
    else:
        logging.info('Sending Discord Message w/ Image (Channel %s) - %s - %s', channel_id, message, image)
        message_queue.put_nowait([event, message, image, channel_id])
    event.wait()


def start_discord_bot():
    loop = asyncio.new_event_loop()
    bot = discord.Client()
    bot_token = True

    thread = threading.Thread(target = bot_thread, args = (loop, bot, bot_token, message_queue, CHANNEL_ID), daemon = True)
    thread.start()

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
        logging.debug("Tweet length - %s", tweet_length)
        if tweet_length < 280:
            if reply is None:
                logging.debug("Plain tweet, no reply.")
                status = api.update_status(status=tweet_text)
            else:
                tweet_text = "@{} {}".format(TWITTER_ID, tweet_text)
                logging.debug("Reply to tweet %s - \n%s", reply, tweet_text)
                status = api.update_status(tweet_text, in_reply_to_status_id=reply)
            # Return a full link to the URL in case a quote-tweet is needed
            tweet_id = status.id_str
        else:
            logging.warning("A tweet longer than 280 characters was detected.")
            logging.warning("Tweet: %s", tweet_text)
            tweet_id = TWITTER_URL
            # tweet_array = []
            # tweets_needed = math.ceil(tweet_length / 280)
            # for i in range(tweets_needed):
            #     range_start = (i * 280)
            #     range_end = ((i+1) * 280)
            #     tweet_array.append(tweet_text[range_start:range_end])

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

    # Update period related attributes
    if game.game_state != "Preview":
        game.period.current = linescore["currentPeriod"]
        game.period.current_ordinal = linescore["currentPeriodOrdinal"]
        game.period.time_remaining = linescore["currentPeriodTimeRemaining"]
        game.period.intermission = linescore["intermissionInfo"]["inIntermission"]

    # Update team related attributes
    linescore_home = linescore["teams"]["home"]
    linescore_away = linescore["teams"]["away"]

    game.home_team.score = linescore_home["goals"]
    game.home_team.shots = linescore_home["shotsOnGoal"]
    # game.home_team.goalie_pulled = linescore_home["goaliePulled"]

    game.away_team.score = linescore_away["goals"]
    game.away_team.shots = linescore_away["shotsOnGoal"]
    # game.away_team.goalie_pulled = linescore_away["goaliePulled"]

    try:
        all_plays = json_feed["liveData"]["plays"]["allPlays"]
        last_event = all_plays[game.last_event_idx]
        last_event_type = last_event["result"]["eventTypeId"]
        event_filter_list = ["GOAL", "PENALTY"]

        # Logic for tracking if a team kills a penalty
        last_power_player_strength = game.power_play_strength
        last_home_power_play = game.home_team.power_play
        last_home_skaters = game.home_team.skaters
        last_away_power_play = game.away_team.power_play
        last_away_skaters = game.away_team.skaters

        game.power_play_strength = json_feed["liveData"]["linescore"]["powerPlayStrength"]
        game.home_team.power_play = linescore_home["powerPlay"]
        game.home_team.skaters = linescore_home["numSkaters"]
        game.away_team.power_play = linescore_away["powerPlay"]
        game.away_team.skaters = linescore_away["numSkaters"]

        # TODO: Track onIce Players Array?
        preferred_homeaway = game.preferred_team.home_away
        other_homeaway = game.other_team.home_away
        on_ice_pref = json_feed["liveData"]["boxscore"]["teams"][preferred_homeaway]["onIce"]
        on_ice_other = json_feed["liveData"]["boxscore"]["teams"][other_homeaway]["onIce"]

        logging.info("Current Away Skaters: %s | Current Home Skaters: %s",
                     game.away_team.skaters, game.home_team.skaters)
        logging.info("Current Power Play Strength: %s", game.power_play_strength)
        logging.info("Preferred On Ice (%s): %s", len(on_ice_pref), on_ice_pref)
        logging.info("Other On Ice (%s): %s\n", len(on_ice_other), on_ice_other)

        # These conditions happen if one of the teams was
        # previously on a power play, but aren't anymore
        if last_home_power_play and not game.home_team.power_play:
            logging.info("PP Strength Change - Home team was on a power play, but now aren't anymore.")
            pk_team = game.home_team
            pk_linescore = linescore_home
            game.penalty_killed_flag = True
        elif last_away_power_play and not game.away_team.power_play:
            logging.info("PP Strength Change - Away team was on a power play, but now aren't anymore.")
            pk_team = game.away_team
            pk_linescore = linescore_away
            game.penalty_killed_flag = True
        elif last_home_skaters == 3 and game.home_team.skaters != 3:
            logging.info("Num Skaters Change - Home team MIGHT be coming off a 5-on-3.")
            pk_team = game.home_team
            pk_linescore = linescore_home
            game.penalty_killed_flag = True
        elif last_away_skaters == 3 and game.away_team.skaters != 3:
            logging.info("Num Skaters Change - Away team MIGHT be coming off a 5-on-3.")
            pk_team = game.away_team
            pk_linescore = linescore_away
            game.penalty_killed_flag = True

        if game.penalty_killed_flag and last_event_type not in event_filter_list:
            logging.info("Last event was not a goal or penalty and skater number changed.")
            logging.info("Previous Home Skaters: %s | Current Home Skaters: %s",
                        last_home_skaters, game.home_team.skaters)
            logging.info("Previous Away Skaters: %s | Current Away Skaters: %s",
                        last_away_skaters, game.away_team.skaters)
            logging.info('%s kill off a penalty with %s remaining in the %s period!',
                          pk_team.short_name, linescore['currentPeriodTimeRemaining'],
                          linescore['currentPeriodOrdinal'])
            game.penalty_killed_flag = False
    except Exception as e:
        game.penalty_killed_flag = False
        logging.warning("Issue checking if power play strength changed.")
        logging.warning(e)

    # Logic for keeping goalie pulled with events in between
    try:
        all_plays = json_feed["liveData"]["plays"]["allPlays"]
        last_event = all_plays[game.last_event_idx]
        last_event_type = last_event["result"]["eventTypeId"]
        event_filter_list = ["GOAL", "PENALTY"]

        # Get current values
        home_goalie_pulled = game.home_team.goalie_pulled
        away_goalie_pulled = game.away_team.goalie_pulled

        if not game.home_team.goalie_pulled:
            logging.debug("Home goalie in net - check and update attribute.")
            home_goalie_pulled = game.home_team.goalie_pulled_setter(linescore_home["goaliePulled"])
        elif game.home_team.goalie_pulled and last_event_type in event_filter_list:
            logging.info("Home goalie was pulled and an important event detected - update.")
            home_goalie_pulled = game.home_team.goalie_pulled_setter(linescore_home["goaliePulled"])
        else:
            logging.info("Home goalie is pulled and a non-important event detected, don't update.")
            return

        if not game.away_team.goalie_pulled:
            logging.debug("Away goalie in net - check and update attribute.")
            away_goalie_pulled = game.away_team.goalie_pulled_setter(linescore_away["goaliePulled"])
        elif game.away_team.goalie_pulled and last_event_type in event_filter_list:
            logging.info("Away goalie was pulled and an important event detected - update.")
            away_goalie_pulled = game.away_team.goalie_pulled_setter(linescore_away["goaliePulled"])
        else:
            logging.info("Away goalie is pulled and a non-important event detected, don't update.")
            return

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
    return bool(seconds_since_event < int(config['SCRIPT']['EVENT_TIMEOUT']))


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

def luminance(pixel):
    return (0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])


def are_colors_similar(color_a, color_b):
    return abs(luminance(color_a) - luminance(color_b)) < 18


def custom_font_size(fontName, size):
    return ImageFont.truetype(fontName, size)


def pregame_image(game):
    if not args.notweets:
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

    # Load Required Fonts
    FONT_OPENSANS_BOLD = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Bold.ttf')
    FONT_OPENSANS_SEMIBOLD = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-SemiBold.ttf')
    FONT_OPENSANS_EXTRABOLD = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-ExtraBold.ttf')
    FONT_COLOR_WHITE = (255, 255, 255)

    # Set the background / load the baseline image
    bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayPregameFinalV3-Larger.png'))
    draw = ImageDraw.Draw(bg)
    # draw.fontmode = "0"

    # Setup Colors (via functions)
    pref_colors = nhl_game_events.team_colors(game.preferred_team.team_name)
    pref_color_primary = pref_colors["primary"]["bg"]
    other_colors = nhl_game_events.team_colors(game.other_team.team_name)

    logging.debug("Pref Colors - %s // Other Colors - %s", pref_colors, other_colors)

    # Setup static coordinates / width / etc
    LOGO_WIDTH = 300

    COORDS_HOME_LOGO = (325, 270)
    COORDS_AWAY_LOGO = (0, 270)
    COORDS_RECORDS_Y = 490

    COORDS_GAME_NUM = (845, 100)
    COORDS_GAMEINFO_DAY_X = 648
    COORDS_GAMEINFO_DAY_Y = 290
    COORDS_GAMEINFO_DAY = (COORDS_GAMEINFO_DAY_X, COORDS_GAMEINFO_DAY_Y)
    COORDS_GAMEINFO_WIDTH = 520
    MAX_GAMEINFO_WIDTH = COORDS_GAMEINFO_WIDTH - 10

    COORDS_GAMEINFO_LINE2_RECT_TOPLEFT = (648, 381)
    COORDS_GAMEINFO_LINE2_RECT_BOTRIGHT = (1168, 451)
    COORDS_GAMEINFO_LINE3_RECT_TOPLEFT = (648, 451)
    COORDS_GAMEINFO_LINE3_RECT_BOTRIGHT = (1168, 521)

    # Load, resize & paste team logos
    away_logo = Image.open(os.path.join(PROJECT_ROOT,f"resources/logos/{game.away_team.team_name.replace(' ', '')}.png"))
    home_logo = Image.open(os.path.join(PROJECT_ROOT,f"resources/logos/{game.home_team.team_name.replace(' ', '')}.png"))

    resize = (300, 200)
    away_logo.thumbnail(resize, Image.ANTIALIAS)
    home_logo.thumbnail(resize, Image.ANTIALIAS)
    bg.paste(away_logo, COORDS_AWAY_LOGO, away_logo)
    bg.paste(home_logo, COORDS_HOME_LOGO, home_logo)

    # Home Points, Record & Draw
    home_pts = game.home_team.points
    home_record_str = f"{home_pts} PTS • {game.home_team.current_record}"
    home_w, _ = draw.textsize(home_record_str, custom_font_size(FONT_OPENSANS_BOLD, 35))
    coords_home_record = (((2 * LOGO_WIDTH + 325 - home_w) / 2), COORDS_RECORDS_Y)
    draw.text(coords_home_record, home_record_str, fill=FONT_COLOR_WHITE, font=custom_font_size(FONT_OPENSANS_BOLD, 35))

    away_pts = game.away_team.points
    away_record_str = f"{away_pts} PTS • {game.away_team.current_record}"
    away_w, _ = draw.textsize(away_record_str, custom_font_size(FONT_OPENSANS_BOLD, 35))
    coords_away_record = (((LOGO_WIDTH - away_w) / 2), COORDS_RECORDS_Y)
    draw.text(coords_away_record, away_record_str, fill=FONT_COLOR_WHITE, font=custom_font_size(FONT_OPENSANS_BOLD, 35))

    ## TODO: Add logic for pre-season & playoffs here.
    game_number_str = f"{game.preferred_team.games + 1} OF 82"
    draw.text(COORDS_GAME_NUM, game_number_str, fill=pref_color_primary, font=custom_font_size(FONT_OPENSANS_EXTRABOLD, 80))

    # Draw background rectangles for Game Info lines 2 & 3
    draw.rectangle([COORDS_GAMEINFO_LINE2_RECT_TOPLEFT, COORDS_GAMEINFO_LINE2_RECT_BOTRIGHT], pref_color_primary)
    draw.rectangle([COORDS_GAMEINFO_LINE3_RECT_TOPLEFT, COORDS_GAMEINFO_LINE3_RECT_BOTRIGHT], FONT_COLOR_WHITE)

    # Build Day / Date Line
    line1_chars = len(game.day_of_game_local + game.month_day_local)
    line1_fontsize = int((COORDS_GAMEINFO_WIDTH / line1_chars) + 20)

    gameinfo_day = game.day_of_game_local.upper()
    day_w, day_h = draw.textsize(gameinfo_day, font=custom_font_size(FONT_OPENSANS_EXTRABOLD, line1_fontsize))
    draw.text(COORDS_GAMEINFO_DAY, gameinfo_day, fill=pref_color_primary, font=custom_font_size(FONT_OPENSANS_EXTRABOLD, line1_fontsize))

    gameinfo_date = game.month_day_local.upper()
    date_w, date_h = draw.textsize(gameinfo_date, font=custom_font_size(FONT_OPENSANS_SEMIBOLD, line1_fontsize))
    coords_gameinfo_date = (COORDS_GAMEINFO_DAY_X + (COORDS_GAMEINFO_WIDTH - date_w), COORDS_GAMEINFO_DAY_Y)
    draw.text(coords_gameinfo_date, gameinfo_date, fill=pref_color_primary, font=custom_font_size(FONT_OPENSANS_SEMIBOLD, line1_fontsize))

    # Build Game Info Line 2 (Time & Venue)
    gameinfo_venue = game.venue
    gameinfo_time = game.game_time_local.lstrip("0")
    gameinfo_line2 = f"{gameinfo_time} • {gameinfo_venue}"
    line2_w, line2_h = draw.textsize(gameinfo_line2, font=custom_font_size(FONT_OPENSANS_BOLD, 38))
    if line2_w > MAX_GAMEINFO_WIDTH:
        logging.info("Line 2 was too long, reducing font size.")
        line2_w, line2_h = draw.textsize(gameinfo_line2, font=custom_font_size(FONT_OPENSANS_BOLD, 31))
        coords_line2 = (COORDS_GAMEINFO_DAY_X + ((COORDS_GAMEINFO_WIDTH - line2_w) / 2), 390)
        draw.text(coords_line2, gameinfo_line2, FONT_COLOR_WHITE, font=custom_font_size(FONT_OPENSANS_BOLD, 31))
    else:
        coords_line2 = (COORDS_GAMEINFO_DAY_X + ((COORDS_GAMEINFO_WIDTH - line2_w) / 2), 387)
        draw.text(coords_line2, gameinfo_line2, FONT_COLOR_WHITE, font=custom_font_size(FONT_OPENSANS_BOLD, 38))

    # Build Game Info Line 3 (Game Hashtag & Pref Team Hashtag)
    gameinfo_hashtag = game.game_hashtag
    gameinfo_teamhashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name, game.game_type)
    gameinfo_line3 = f"{gameinfo_teamhashtag} • {gameinfo_hashtag}"
    line3_w, line3_h = draw.textsize(gameinfo_line3, font=custom_font_size(FONT_OPENSANS_BOLD, 38))
    if line3_w > MAX_GAMEINFO_WIDTH:
        logging.info("Line 3 was too long, reducing font size.")
        line3_w, line3_h = draw.textsize(gameinfo_line3, font=custom_font_size(FONT_OPENSANS_BOLD, 33))
        coords_line3 = (COORDS_GAMEINFO_DAY_X + ((COORDS_GAMEINFO_WIDTH - line3_w) / 2), 460)
        draw.text(coords_line3, gameinfo_line3, pref_color_primary, font=custom_font_size(FONT_OPENSANS_BOLD, 33))
    else:
        coords_line3 = (COORDS_GAMEINFO_DAY_X + ((COORDS_GAMEINFO_WIDTH - line3_w) / 2), 457)
        draw.text(coords_line3, gameinfo_line3, pref_color_primary, font=custom_font_size(FONT_OPENSANS_BOLD, 38))

    return bg


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
    teams_font = os.path.join(PROJECT_ROOT, 'resources/fonts/Adidas.otf')
    details_font = os.path.join(PROJECT_ROOT, 'resources/fonts/Impact.ttf')
    bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayBlank.jpg'))
    font_black = (0, 0, 0)

    # Create & format text for pre-game image
    teams_text = "{} vs {}".format(game.away_team.short_name, game.home_team.short_name)

    game_date_short = game.game_date_short
    game_time = game.game_time_local.replace(" ", "")
    if game.game_type == config['GAMETYPE']['PLAYOFFS']:
        series_details = ("{} - {} / {} - {}"
                          .format(game.away_team.short_name, game.away_team.wins,
                                  game.home_team.short_name, game.home_team.wins))
        # Convert round number into text
        if game.game_id_playoff_round == "1":
            playoff_round_text = "First Round"
        elif game.game_id_playoff_round == "2":
            playoff_round_text = "Second Round"
        else:
            playoff_round_text = "Unknown Round"

        full_details = ("{} - Game #{}\n{}\n\n{} | {} | {}\n#StanleyCup {} {}"
                      .format(playoff_round_text, game.game_id_playoff_game,
                      series_details, game.venue, game_date_short, game_time,
                      nhl_game_events.team_hashtag(game.preferred_team.team_name, game.game_type),
                      game.game_hashtag))
        details_coords = (110, 110)
    elif game.game_type == config['GAMETYPE']['PRESEASON']:
        details_game = ("PRESEASON | {} | {}"
                        .format(game_date_short, game_time))
        full_details = "{}\n{}\n{}".format(details_game, game.venue, game.game_hashtag)
        details_coords = (145, 160)
    else:
        details_game = ("{} of 82 | {} | {}"
                        .format(game.preferred_team.games + 1, game_date_short, game_time))
        full_details = "{}\n{}\n{}".format(details_game, game.venue, game.game_hashtag)
        details_coords = (145, 160)

    # Calculate Font Sizes
    teams_length = len(teams_text)
    teams_font_size = math.floor(1440 / teams_length)
    longest_details = 0
    for line in iter(full_details.splitlines()):
        longest_details = len(line) if len(line) > longest_details else longest_details
    details_font_size = math.floor(1100 / longest_details)

    font_large = ImageFont.truetype(teams_font, teams_font_size)
    font_small = ImageFont.truetype(details_font, details_font_size)

    draw = ImageDraw.Draw(bg)
    team_coords = (40, 20)
    draw.text(team_coords, teams_text, font_black, font_large)
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
    teams_font = os.path.join(PROJECT_ROOT, 'resources/fonts/Adidas.otf')
    details_font = os.path.join(PROJECT_ROOT, 'resources/fonts/Impact.ttf')

    bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayFinalPrudentialBlank.jpg'))

    # Get Game Info for Updated Record
    _, schedule_json = is_game_today(get_team(TEAM_BOT))
    if game.home_team.preferred:
        pref = schedule_json["teams"]["home"]
        other = schedule_json["teams"]["away"]
    else:
        pref = schedule_json["teams"]["away"]
        other = schedule_json["teams"]["home"]

    # Load & Resize Logos
    pref_logo = Image.open(os.path.join(PROJECT_ROOT, 'resources/logos/{}.png'
                           .format(game.preferred_team.team_name.replace(" ", ""))))
    other_logo = Image.open(os.path.join(PROJECT_ROOT, 'resources/logos/{}.png'
                            .format(game.other_team.team_name.replace(" ", ""))))

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

    # Update records & get new for final image (Playoffs)
    if game.game_type == "P":
        if game.preferred_team.score > game.other_team.score:
            pref_outcome = "win"
            other_outcome = "loss"
        else:
            other_outcome = "win"
            pref_outcome = "loss"

        pref_record_str = preferred_team.get_new_playoff_series(pref_outcome)
        other_record_str = other_team.get_new_playoff_series(other_outcome)
    else:
        if game.preferred_team.score > game.other_team.score:
            pref_outcome = "win"
            other_outcome = "loss" if game.period.current < 4 else "ot"
        else:
            other_outcome = "win"
            pref_outcome = "loss" if game.period.current < 4 else "ot"

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


def stats_image_bar_generator(draw, stat, pref_stat_value, other_stat_value,
                              pref_colors, other_colors):
    logging.debug("Stats Bar Generator: stat - %s, pref_value - %s, other_value - %s, pref_colors - %s, other_colors - %s",
                  stat, pref_stat_value, other_stat_value, pref_colors, other_colors)

    # Load all fonts to be used within the image generator
    font_opensans_regular = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Regular.ttf')
    font_opensans_italic = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Italic.ttf')
    font_opensans_bold = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Bold.ttf')
    font_opensans_bolditalic = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-BoldItalic.ttf')

    # Static Font Sizes
    font_opensans_regular_large = ImageFont.truetype(font_opensans_regular, 80)
    font_opensans_regular_small = ImageFont.truetype(font_opensans_regular, 40)
    font_opensans_regular_smaller = ImageFont.truetype(font_opensans_regular, 30)
    font_opensans_regular_xxs = ImageFont.truetype(font_opensans_regular, 20)

    font_opensans_italic_xs = ImageFont.truetype(font_opensans_italic, 25)
    font_opensans_italic_xxs = ImageFont.truetype(font_opensans_italic, 20)

    font_opensans_bold_large = ImageFont.truetype(font_opensans_bold, 90)
    font_opensans_bold_small = ImageFont.truetype(font_opensans_bold, 40)
    font_opensans_bold_smaller = ImageFont.truetype(font_opensans_bold, 30)
    font_opensans_bold_xs = ImageFont.truetype(font_opensans_bold, 27)

    font_opensans_boldit_small = ImageFont.truetype(font_opensans_bolditalic, 40)
    font_opensans_boldit_smallish = ImageFont.truetype(font_opensans_bolditalic, 35)
    font_opensans_boldit_smaller = ImageFont.truetype(font_opensans_bolditalic, 30)
    font_opensans_boldit_xs = ImageFont.truetype(font_opensans_bolditalic, 25)
    font_opensans_boldit_xxs = ImageFont.truetype(font_opensans_bolditalic, 20)

    # Define static values, text strings & coordinates
    STATS_RECT_WIDTH = 437
    STATS_RECT_TOPLEFT_X = 279
    STATS_RECT_HEIGHT = 49
    FONT_BLACK = (0, 0, 0)
    FONT_WHITE = (255, 255, 255)

    # Check stat type and set specific parameters here
    if stat == "shots":
        stat_total = pref_stat_value + other_stat_value
        stat_total_text = f"SHOTS: {stat_total}"
        stat_total_text_coords = (50, 243)
        stat_total_text_font = font_opensans_boldit_smaller
        stat_rect_pref_topleft_y = 241
    elif stat == "blocked shots":
        stat_total = pref_stat_value + other_stat_value
        stat_total_text = f"BLOCKED SHOTS: {stat_total}"
        stat_total_text_font = custom_font_size(font_opensans_bolditalic, 23)
        stat_total_text_coords = (50, 335)
        stat_rect_pref_topleft_y = 328
    elif stat == "hits":
        stat_total = pref_stat_value + other_stat_value
        stat_total_text = f"HITS: {stat_total}"
        stat_total_text_font = font_opensans_boldit_smaller
        stat_total_text_coords = (50, 510)
        stat_rect_pref_topleft_y = 505
    elif stat == "power play":
        pref_powerplays, pref_ppg = pref_stat_value
        other_powerplays, other_ppg = other_stat_value
        power_play_pref = f"{int(pref_ppg)} / {int(pref_powerplays)}"
        power_play_other = f"{int(other_ppg)} / {int(other_powerplays)}"

        # Re-assign values
        pref_stat_value = pref_powerplays
        other_stat_value = other_powerplays

        stat_total = pref_powerplays + other_powerplays
        stat_total_text = f"POWER PLAYS: {int(stat_total)}"
        stat_total_text_font = custom_font_size(font_opensans_bolditalic, 23)
        stat_total_text_coords = (50, 423)
        stat_rect_pref_topleft_y = 416
    elif stat == "penalty minutes":
        stat_total = pref_stat_value + other_stat_value
        stat_total_text = f"PENALTY MINUTES: {stat_total}"
        stat_total_text_font = custom_font_size(font_opensans_bolditalic, 20)
        stat_total_text_coords = (50, 603)
        stat_rect_pref_topleft_y = 592


    # Calculate the remainder of the coordinates
    stat_rect_width_pref = STATS_RECT_WIDTH * (pref_stat_value / stat_total)
    stat_rect_width_other = STATS_RECT_WIDTH * (other_stat_value / stat_total)

    stat_rect_pref_topleft_x = STATS_RECT_TOPLEFT_X
    stat_rect_pref_bottomright_x = stat_rect_pref_topleft_x + stat_rect_width_pref
    stat_rect_pref_bottomright_y = stat_rect_pref_topleft_y + STATS_RECT_HEIGHT
    stat_text_pref_coords = (stat_rect_pref_topleft_x + 10, stat_rect_pref_topleft_y + 6)

    stat_rect_other_topleft_x = stat_rect_pref_bottomright_x
    stat_rect_other_topleft_y = stat_rect_pref_topleft_y
    stat_rect_other_bottomright_x = stat_rect_other_topleft_x + stat_rect_width_other
    stat_rect_other_bottomright_y = stat_rect_pref_bottomright_y
    stat_text_other_coords = (stat_rect_other_topleft_x + 10, stat_rect_other_topleft_y + 6)

    # Draw the text fields & bars
    if stat == "power play":
        draw.rectangle([stat_rect_pref_topleft_x, stat_rect_pref_topleft_y, stat_rect_pref_bottomright_x,
                        stat_rect_pref_bottomright_y], outline=None, fill=pref_colors["bg"])
        draw.rectangle([stat_rect_other_topleft_x, stat_rect_other_topleft_y, stat_rect_other_bottomright_x,
                        stat_rect_other_bottomright_y], outline=None, fill=other_colors["bg"])
        if pref_powerplays != 0:
            draw.text(stat_text_pref_coords, power_play_pref, pref_colors["text"], font_opensans_bold_xs)
        if other_powerplays != 0:
            draw.text(stat_text_other_coords, power_play_other, other_colors["text"], font_opensans_bold_xs)
        draw.text(stat_total_text_coords, stat_total_text, FONT_WHITE, stat_total_text_font)
    else:
        draw.rectangle([stat_rect_pref_topleft_x, stat_rect_pref_topleft_y, stat_rect_pref_bottomright_x,
                        stat_rect_pref_bottomright_y], outline=None, fill=pref_colors["bg"])
        draw.rectangle([stat_rect_other_topleft_x, stat_rect_other_topleft_y, stat_rect_other_bottomright_x,
                        stat_rect_other_bottomright_y], outline=None, fill=other_colors["bg"])
        draw.text(stat_text_pref_coords, str(pref_stat_value), pref_colors["text"], font_opensans_bold_xs)
        draw.text(stat_text_other_coords, str(other_stat_value), other_colors["text"], font_opensans_bold_xs)
        draw.text(stat_total_text_coords, stat_total_text, FONT_WHITE, stat_total_text_font)


def stats_image_generator(game, bg_type, boxscore_preferred, boxscore_other):

    logging.debug("Stats Image Generator Game: %s", game)
    logging.debug("Stats Image Generator BG: %s", bg_type)
    # logging.debug("Stats Image Generator BOXPREF: %s", boxscore_preferred)
    # logging.debug("Stats Image Generator BOXOTHER: %s", boxscore_other)

    # Define static values, text strings & coordinates
    STATS_RECT_WIDTH = 437
    STATS_RECT_TOPLEFT_X = 279
    STATS_RECT_HEIGHT = 49
    FONT_BLACK = (0, 0, 0)
    FONT_WHITE = (255, 255, 255)

    COORDS_PREF_LOGO = (840, 120)
    COORDS_OTHER_LOGO = (1015, 120)
    COORDS_PREF_RECORD = (910, 135)
    COORDS_OTHER_RECORD = (1110, 135)
    COORDS_LOGO_VS = (960, 130)
    COORDS_TEAMS_VS_Y = 198
    COORDS_TEAMS_VS_X = 275
    WIDTH_TEAMS_VS = 447
    COORDS_TEAMS_VS = (335, 198)
    TEAMS_VS_W, TEAMS_VS_H = (447, 39)

    # Load & Resize Logos
    pref_logo = Image.open(os.path.join(PROJECT_ROOT, 'resources/logos/{}.png'
                           .format(game.preferred_team.team_name.replace(" ", ""))))
    other_logo = Image.open(os.path.join(PROJECT_ROOT, 'resources/logos/{}.png'
                            .format(game.other_team.team_name.replace(" ", ""))))
    resize = (120, 120)
    pref_logo.thumbnail(resize, Image.ANTIALIAS)
    other_logo.thumbnail(resize, Image.ANTIALIAS)

    # Change background image based on intermission or game final
    # Also change the "losing team" image to grayscale for final
    if bg_type == "intermission":
        bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayIntermissionFinal-V3Larger.png'))
        bg.paste(pref_logo, COORDS_PREF_LOGO, pref_logo)
        bg.paste(other_logo, COORDS_OTHER_LOGO, other_logo)
    else:
        bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayRecapFinalV3-Larger.png'))
        COORDS_PREF_LOGO = (780, 120)
        COORDS_OTHER_LOGO = (985, 120)
        COORDS_LOGO_VS = (-100, -100)

        if game.preferred_team.score > game.other_team.score:
            bg.paste(pref_logo, COORDS_PREF_LOGO, pref_logo)
            bg.paste(other_logo.convert('LA'), COORDS_OTHER_LOGO, other_logo)
        else:
            bg.paste(pref_logo.convert('LA'), COORDS_PREF_LOGO, pref_logo)
            bg.paste(other_logo, COORDS_OTHER_LOGO, other_logo)

    # Load all fonts to be used within the image generator
    teams_font = os.path.join(PROJECT_ROOT, 'resources/fonts/Adidas.otf')
    details_font = os.path.join(PROJECT_ROOT, 'resources/fonts/Impact.ttf')
    font_opensans_regular = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Regular.ttf')
    font_opensans_italic = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Italic.ttf')
    font_opensans_bold = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Bold.ttf')
    font_opensans_bolditalic = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-BoldItalic.ttf')

    # Static Font Sizes
    font_opensans_regular_large = ImageFont.truetype(font_opensans_regular, 80)
    font_opensans_regular_small = ImageFont.truetype(font_opensans_regular, 40)
    font_opensans_regular_smaller = ImageFont.truetype(font_opensans_regular, 30)
    font_opensans_regular_xxs = ImageFont.truetype(font_opensans_regular, 20)

    font_opensans_italic_xs = ImageFont.truetype(font_opensans_italic, 25)
    font_opensans_italic_xxs = ImageFont.truetype(font_opensans_italic, 20)

    font_opensans_bold_large = ImageFont.truetype(font_opensans_bold, 90)
    font_opensans_bold_small = ImageFont.truetype(font_opensans_bold, 40)
    font_opensans_bold_smaller = ImageFont.truetype(font_opensans_bold, 30)
    font_opensans_bold_xs = ImageFont.truetype(font_opensans_bold, 27)

    font_opensans_boldit_small = ImageFont.truetype(font_opensans_bolditalic, 40)
    font_opensans_boldit_smallish = ImageFont.truetype(font_opensans_bolditalic, 35)
    font_opensans_boldit_smaller = ImageFont.truetype(font_opensans_bolditalic, 30)
    font_opensans_boldit_xs = ImageFont.truetype(font_opensans_bolditalic, 25)
    font_opensans_boldit_xxs = ImageFont.truetype(font_opensans_bolditalic, 20)

    # Setup Colors (via functions)
    pref_colors = nhl_game_events.team_colors(game.preferred_team.team_name)
    other_colors = nhl_game_events.team_colors(game.other_team.team_name)

    logging.debug("Pref Colors - %s // Other Colors - %s", pref_colors, other_colors)

    if are_colors_similar(pref_colors["primary"]["bg"], other_colors["primary"]["bg"]):
        logging.debug("Primary Colors are Similar!")
        pref_colors_all = pref_colors["primary"]
        pref_colors_bg = pref_colors["primary"]["bg"]
        pref_colors_text = pref_colors["primary"]["text"]
        other_colors_all = other_colors["secondary"]
        other_colors_bg = other_colors["secondary"]["bg"]
        other_colors_text = other_colors["secondary"]["text"]
    else:
        pref_colors_all = pref_colors["primary"]
        pref_colors_bg = pref_colors["primary"]["bg"]
        pref_colors_text = pref_colors["primary"]["text"]
        other_colors_all = other_colors["primary"]
        other_colors_bg = other_colors["primary"]["bg"]
        other_colors_text = other_colors["primary"]["text"]

    logging.debug("(After Similar) -- Pref Colors - %s // Other Colors - %s", pref_colors, other_colors)

    # Draw the rest of the image
    draw = ImageDraw.Draw(bg)
    draw.fontmode = "0"

    # Draw "VS" or Updated Record
    if bg_type == "intermission":
        draw.text(COORDS_LOGO_VS, "vs", FONT_WHITE, font_opensans_bold_small)
    else:
        # Update records & get new for final image (Playoffs)
        if game.game_type == "P":
            if game.preferred_team.score > game.other_team.score:
                pref_outcome = "win"
                other_outcome = "loss"
            else:
                other_outcome = "win"
                pref_outcome = "loss"

            pref_str = game.preferred_team.get_new_playoff_series(pref_outcome)
            other_str = game.other_team.get_new_playoff_series(other_outcome)
        else:
            if game.preferred_team.score > game.other_team.score:
                pref_outcome = "win"
                other_outcome = "loss" if game.period.current < 4 else "ot"
            else:
                other_outcome = "win"
                pref_outcome = "loss" if game.period.current < 4 else "ot"

            pref_points_str = game.preferred_team.get_new_points(pref_outcome)
            pref_record_str = game.preferred_team.get_new_record(pref_outcome)
            other_points_str = game.other_team.get_new_points(other_outcome)
            other_record_str = game.other_team.get_new_record(other_outcome)

            pref_str = f"{pref_points_str} PTS\n{pref_record_str}"
            other_str = f"{other_points_str} PTS\n{other_record_str}"

        draw.text(COORDS_PREF_RECORD, pref_str, FONT_WHITE, custom_font_size(font_opensans_bold, 16), align="center")
        draw.text(COORDS_OTHER_RECORD, other_str, FONT_WHITE, custom_font_size(font_opensans_bold, 16), align="center")

    # Create Team Name String & Calculate Center
    teams_vs_text = f"{game.preferred_team.short_name} vs. {game.other_team.short_name}".upper()
    w, h = draw.textsize(teams_vs_text, font_opensans_bold_smaller)
    if w < WIDTH_TEAMS_VS:
        coords_teams_vs_calc = (COORDS_TEAMS_VS_X + ((TEAMS_VS_W - w) / 2), COORDS_TEAMS_VS_Y)
        draw.text(coords_teams_vs_calc, teams_vs_text, FONT_BLACK, font_opensans_bold_smaller)
    else:
        w, h = draw.textsize(teams_vs_text, font_opensans_bold_xs)
        coords_teams_vs_calc = (COORDS_TEAMS_VS_X + ((TEAMS_VS_W - w) / 2), COORDS_TEAMS_VS_Y)
        draw.text(coords_teams_vs_calc, teams_vs_text, FONT_BLACK, font_opensans_bold_smaller)

    # Draw the stats bars
    preferred_stats = boxscore_preferred["teamStats"]["teamSkaterStats"]
    other_stats = boxscore_other["teamStats"]["teamSkaterStats"]
    stats_image_bar_generator(draw, "shots", preferred_stats["shots"],
                              other_stats["shots"], pref_colors_all, other_colors_all)
    stats_image_bar_generator(draw, "blocked shots", preferred_stats["blocked"],
                              other_stats["blocked"], pref_colors_all, other_colors_all)
    stats_image_bar_generator(draw, "hits", preferred_stats["hits"],
                              other_stats["hits"], pref_colors_all, other_colors_all)

    # Some games go through multiple periods without a single penalty being called.
    # Checking here removes the `Divide by Zero` errors.
    if (
            preferred_stats["pim"] != 0 and
            other_stats["pim"] != 0 and
            preferred_stats["powerPlayOpportunities"] != 0 and
            other_stats["powerPlayOpportunities"] !=0
       ):
        stats_image_bar_generator(draw, "penalty minutes", preferred_stats["pim"],
                                other_stats["pim"], pref_colors_all, other_colors_all)

        # Power Play requires a Tuple to be passed in (instead of a integer)
        pref_powerplay = (preferred_stats["powerPlayOpportunities"], preferred_stats["powerPlayGoals"])
        other_powerplay = (other_stats["powerPlayOpportunities"], other_stats["powerPlayGoals"])
        logging.debug("Calling Stats Bar: pref_pp - %s, other_pp - %s, pref_colors - %s, other_colors - %s",
                    pref_powerplay, other_powerplay, pref_colors_all, other_colors_all)
        stats_image_bar_generator(draw, "power play", pref_powerplay, other_powerplay,
                                pref_colors_all, other_colors_all)

    else:
        # If PIM & PP == 0, draw only the labels
        penalty_total_text = "PENALTY MINUTES: 0"
        penalty_total_text_font = custom_font_size(font_opensans_bolditalic, 20)
        penalty_total_text_coords = (50, 603)
        draw.text(penalty_total_text_coords, penalty_total_text, FONT_WHITE, penalty_total_text_font)

        pp_total_text = "POWER PLAYS: 0"
        pp_total_text_font = custom_font_size(font_opensans_bolditalic, 23)
        pp_total_text_coords = (50, 423)
        draw.text(pp_total_text_coords, pp_total_text, FONT_WHITE, pp_total_text_font)


    # Setup & Draw Faceoff Graph (including inner / outer circles)
    logging.debug("Generating Faceoff Stats for Image.")
    text_title_faceoff = "FACEOFF %"
    coords_faceoff_title = (950, 500)
    coords_faceoff_pref = (950, 550)
    coords_faceoff_other = (950, 575)
    coords_faceoff_box = [780, 475, 920, 615]
    coords_faceoff_box_inner_black = [810, 505, 890, 585]
    coords_faceoff_box_inner_white = [809, 504, 891, 586]

    pref_faceoff = float(preferred_stats["faceOffWinPercentage"])
    text_faceoff_pref = f"{game.preferred_team.short_name}: {pref_faceoff}%".upper()
    other_faceoff = float(other_stats["faceOffWinPercentage"])
    text_faceoff_other = f"{game.other_team.short_name}: {other_faceoff}%".upper()
    faceoff_angle = (pref_faceoff / 100) * 360

    logging.debug("Preferred Faceoff: %s", pref_faceoff)
    logging.debug("Faceoff Angle: %s", faceoff_angle)

    text_title_faceoff = "FACEOFF %"
    draw.text(coords_faceoff_title, text_title_faceoff, FONT_WHITE, font_opensans_boldit_small)
    draw.text(coords_faceoff_pref, text_faceoff_pref, FONT_WHITE, font_opensans_regular_xxs)
    draw.text(coords_faceoff_other, text_faceoff_other, FONT_WHITE, font_opensans_regular_xxs)
    draw.pieslice(coords_faceoff_box, 0, faceoff_angle, fill=pref_colors_bg)
    draw.pieslice(coords_faceoff_box, faceoff_angle, 360, fill=other_colors_bg)

    # Draw outlines & inner circles
    # draw.pieslice(coords_faceoff_box_inner_white, 0, 360, fill=(255, 255, 255))
    draw.pieslice(coords_faceoff_box_inner_black, 0, 360, fill=(0, 0, 0))

    # Draw Goals & Score Text
    coords_pref_score = (1095, 198)
    coords_pref_score_goals_box = [760, 210, 873, 246]
    coords_pref_score_goals_text = (764, 215)
    coords_goals_pref = (775, 256)
    coords_other_score = (1095, 328)
    coords_other_score_goals_box = [760, 336, 873, 372]
    coords_other_score_goals_text = (764, 341)
    coords_goals_other = (775, 378)

    text_pref_score = game.preferred_team.score
    text_other_score = game.other_team.score
    text_pref_goal_title = f"{game.preferred_team.tri_code} GOALS".upper()
    text_other_goal_title = f"{game.other_team.tri_code} GOALS".upper()
    pref_goals_array = []
    other_goals_array = []

    logging.debug("Looping through preferred goals for stat box.")
    preferred_boxscore_players = boxscore_preferred["players"]
    for id, player in preferred_boxscore_players.items():
        try:
            if player["stats"]["skaterStats"]["goals"] == 1:
                player_name = player["person"]["fullName"]
                player_first_name = player_name.split()[0]
                player_first_letter = player_first_name[0]
                player_last_name = player_name.split()[1]
                player_abbrev_name = f"{player_first_letter}. {player_last_name}"
                pref_goals_array.append(player_abbrev_name)
            elif player["stats"]["skaterStats"]["goals"] > 1:
                player_goals = player["stats"]["skaterStats"]["goals"]
                player_name = player["person"]["fullName"]
                player_first_name = player_name.split()[0]
                player_first_letter = player_first_name[0]
                player_last_name = player_name.split()[1]
                player_abbrev_name = f"{player_first_letter}. {player_last_name} [{player_goals}]"
                pref_goals_array.append(player_abbrev_name)
        except KeyError:
            logging.debug("Stats for %s not available.", player["person"]["fullName"])

    logging.debug("Looping through preferred goals for stat box.")
    other_boxscore_players = boxscore_other["players"]
    for id, player in other_boxscore_players.items():
        try:
            if player["stats"]["skaterStats"]["goals"] == 1:
                player_name = player["person"]["fullName"]
                player_first_name = player_name.split()[0]
                player_first_letter = player_first_name[0]
                player_last_name = player_name.split()[1]
                player_abbrev_name = f"{player_first_letter}. {player_last_name}"
                other_goals_array.append(player_abbrev_name)
            elif player["stats"]["skaterStats"]["goals"] > 1:
                player_goals = player["stats"]["skaterStats"]["goals"]
                player_name = player["person"]["fullName"]
                player_first_name = player_name.split()[0]
                player_first_letter = player_first_name[0]
                player_last_name = player_name.split()[1]
                player_abbrev_name = f"{player_first_letter}. {player_last_name} [{player_goals}]"
                other_goals_array.append(player_abbrev_name)
        except KeyError:
            logging.debug("Stats for %s not available.", player["person"]["fullName"])

    logging.debug("Pref Goals: %s // Other Goals: %s", pref_goals_array, other_goals_array)
    if len(pref_goals_array) < 4:
        text_goals_pref = ", ".join(pref_goals_array)
        logging.debug("Length: %s // String: %s", len(pref_goals_array), text_goals_pref)
    else:
        for idx, scorer in enumerate(pref_goals_array):
            logging.debug("%s: %s", idx, scorer)
        text_goals_pref = ", ".join(pref_goals_array[0:3])
        text_goals_pref = text_goals_pref + "\n" + ", ".join(pref_goals_array[3:])
        logging.debug("Length: %s // String: %s", len(pref_goals_array), text_goals_pref)

    if len(other_goals_array) < 4:
        text_goals_other = ", ".join(other_goals_array)
    else:
        text_goals_other = ", ".join(other_goals_array[0:3])
        text_goals_other = text_goals_other + "\n" +  ", ".join(other_goals_array[3:])

    logging.debug("Drawing team score text.")
    draw.text(coords_pref_score, str(text_pref_score), pref_colors_bg, font_opensans_bold_large)
    draw.text(coords_other_score, str(text_other_score), other_colors_bg, font_opensans_bold_large)

    logging.debug("Drawing team goal rects & title.")
    draw.rectangle(coords_pref_score_goals_box, outline=None, fill=pref_colors_bg)
    draw.rectangle(coords_other_score_goals_box, outline=None, fill=other_colors_bg)
    draw.text(coords_pref_score_goals_text, text_pref_goal_title, FONT_WHITE, custom_font_size(font_opensans_bold, 18))
    draw.text(coords_other_score_goals_text, text_other_goal_title, FONT_WHITE, custom_font_size(font_opensans_bold, 18))

    logging.debug("Drawing goal scorer text.")
    draw.multiline_text(coords_goals_pref, text_goals_pref, FONT_WHITE, custom_font_size(font_opensans_bold, 16))
    draw.multiline_text(coords_goals_other, text_goals_other, FONT_WHITE, custom_font_size(font_opensans_bold, 16))

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
    elif args.date is not None:
        try:
            now = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError as e:
            logging.error("Invalid override date - exiting.")
            logging.error(e)
            sys.exit()

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
    elif games_total == 2:
        dirname = os.path.dirname(os.path.realpath(__file__))
        if args.split is False:
            logging.info("Split squad detected, spawning a second process to pick up second game.")
            game_index = 0
            if args.date is not None:
                spawn_args = ' '.join(sys.argv[1:])
                logging.debug("Spawning Process: python3 %s/hockey_twitter_bot.py --split %s", dirname, spawn_args)
                Popen(['python3 ' + dirname + '/hockey_twitter_bot.py --split ' + spawn_args], shell=True)
            else:
                Popen(['nohup python3 ' + dirname + '/hockey_twitter_bot.py --split &'], shell=True)
        else:
            logging.info("Split squad detected, this is the second spawned process to pick up second game (sleep for 5 seconds).")
            time.sleep(5)
            game_index = 1
        games_info = schedule["dates"][0]["games"][game_index]
        return True, games_info
    return False, None


def calculate_shot_distance(play):
    """Parses a play and returns the distance from the net.

    Args:
        play (dict): A dictionary of a penalty play attributes.

    Note:
        dist_string (String): distance with unit (foot / feet)
    """

    event_x = abs(play['coordinates']['x'])
    event_y = play['coordinates']['y']
    approx_goal_x = 89
    approx_goal_y = 0
    shot_dist = math.ceil(math.hypot(event_x - approx_goal_x, event_y - approx_goal_y))
    # shot_dist = abs(math.ceil(approx_goal_x - shot_x))

    if shot_dist == 1:
        shot_dist_unit = 'foot'
    else:
        shot_dist_unit = 'feet'

    dist_string = f'{shot_dist} {shot_dist_unit}'
    return dist_string


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
        if args.discord:
            send_discord(CHANNEL_ID, tweet_text)

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
        if args.discord:
            send_discord(CHANNEL_ID, tweet_text)

    elif period > 3 and game.game_type == "P":
        ot_number = period - 3
        tweet_forwards = "-".join(forwards)
        tweet_defense = "-".join(defense)
        tweet_goalie = goalies[0]

        tweet_text = ("On the ice to start OT{} for your {} -\n\n{}\n{}\n{}"
                      .format(ot_number, game.preferred_team.team_name,
                              tweet_forwards, tweet_defense, tweet_goalie))
        send_tweet(tweet_text)
        if args.discord:
            send_discord(CHANNEL_ID, tweet_text)


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
    if args.discord:
        send_discord(CHANNEL_ID, goalie_pull_text)


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
        elif game.preferred_team.skaters == 4 and game.other_team.skaters == 3:
            penalty_text_skaters = ("{} are headed to a 4-on-3 power play."
                                    .format(preferred_shortname))
        elif game.preferred_team.skaters == 3 and game.other_team.skaters == 5:
            penalty_text_skaters = ("{} will have to kill off a two-man advantage."
                                    .format(preferred_shortname))
        elif game.preferred_team.skaters == 3 and game.other_team.skaters == 4:
            penalty_text_skaters = ("{} will have a 4-on-3 PK to contend with."
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

    if power_play_strength != "Even":
        penalty_tweet = ("{} {}\n\n{}\n{}\n\n{}"
                         .format(penalty_text_players, penalty_text_skaters,
                                 penalty_on_rankstat_str, penalty_draw_rankstat_str,
                                 game.game_hashtag))
    else:
        penalty_tweet = ("{} {}\n\n{}"
                         .format(penalty_text_players, penalty_text_skaters, game.game_hashtag))
    penalty_tweet_id = send_tweet(penalty_tweet)
    if args.discord:
        send_discord(CHANNEL_ID, penalty_tweet)

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
            player_name = player["player"]["fullName"]
            assist_total = player["seasonTotal"]
            assists.append(f'{player_name} ({assist_total})')

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
    try:
        goal_distance = calculate_shot_distance(play)
    except:
        goal_distance = None

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
            if goal_score_preferred == 7:
                goal_announce = "{} TOUCHDOWN!".format(goal_team)
            else:
                goal_announce = "{} GOAL!".format(goal_team)
    # Overtime goal announcements should be more exciting
    else:
        goal_announce = "{} OVERTIME GOAL!!".format(goal_team)

    # Change some wording around to make it a bit more unique
    # TODO: Add some randomness to this section
    if goal_type == "deflected":
        goal_scorer_text = ("{} ({}) deflects a shot past {} with {} left in the {} period!"
                            .format(goal_scorer_name, ordinal(goal_scorer_total), goalie_name,
                                    goal_period_remain, goal_period_ord))
    else:
        if goal_distance is not None:
            goal_scorer_text = ("{} scores ({}) on a {} from {} away "
                                "with {} left in the {} period!"
                                .format(goal_scorer_name, ordinal(goal_scorer_total), goal_type,
                                        goal_distance, goal_period_remain, goal_period_ord))
        else:
            goal_scorer_text = ("{} scores ({}) on a {} "
                                "with {} left in the {} period!"
                                .format(goal_scorer_name, ordinal(goal_scorer_total), goal_type,
                                        goal_period_remain, goal_period_ord))

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
        if len(game.preferred_team.goals) == goal_score_preferred:
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
        team_hashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name, game.game_type)

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
        goal_tweet = send_tweet(goal_text_full) if recent_event(play) else None
        if args.discord:
            send_discord(CHANNEL_ID, goal_text_full)
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
        goal_text_player = ("{} ({}) - {} left in the {} period."
                            .format(goal_scorer_name, ordinal(goal_scorer_total),
                                    goal_period_remain, goal_period_ord))
        goal_text_score = ("Score - {}: {} / {}: {}"
                           .format(game.preferred_team.short_name, goal_score_preferred,
                                   game.other_team.short_name, goal_score_other))
        goal_other_tweet = ("{}\n\n{}\n\n{}\n\n{}"
                            .format(goal_announce, goal_text_player,
                                    goal_text_score, game.game_hashtag))
        goal_tweet = send_tweet(goal_other_tweet) if recent_event(play) else None
        if args.discord:
            send_discord(CHANNEL_ID, goal_other_tweet)
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
    if args.discord:
        send_discord(CHANNEL_ID, shootout_tweet_text)
    # Increment Shootout Shots
    game.shootout.shots = game.shootout.shots + 1


def parse_missed_shot(play, game):
    """Parses attributes of a missed shot (post / crossbar) and tweets out the result.

    Args:
        play (dict): A dictionary of a penalty play attributes.
        game (Game): The current game instance.
    """

    shot_team = play["team"]["name"]
    if shot_team != game.preferred_team.team_name:
        return False

    shot_description = play["result"]["description"].lower()
    if "crossbar" in shot_description:
        shot_hit = "crossbar"
    elif "goalpost" in shot_description:
        shot_hit = "post"
    else:
        logging.info("The preferred team missed a shot, but didn't hit the post.")
        return False

    logging.info("The preferred team hit a post or crossbar - find distance & tweet it.")
    shooter = play['players'][0]['player']['fullName']
    shot_period_ord = play["about"]["ordinalNum"]
    shot_period_remain = play["about"]["periodTimeRemaining"]
    shot_x = abs(play['coordinates']['x'])
    shot_y = play['coordinates']['y']
    approx_goal_x = 89
    approx_goal_y = 0
    shot_dist = math.ceil(math.hypot(shot_x - approx_goal_x, shot_y - approx_goal_y))
    # shot_dist = abs(math.ceil(approx_goal_x - shot_x))

    if shot_dist == 1:
        shot_dist_unit = 'foot'
    else:
        shot_dist_unit = 'feet'

    game_hashtag = game.game_hashtag
    preferred_hashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name, game.game_type)
    shot_tweet_text = (f'DING! 🛎\n\n{shooter} hits the {shot_hit} from {shot_dist} {shot_dist_unit} '
                       f'away with {shot_period_remain} remaining in the {shot_period_ord} period.'
                       f'\n\n{preferred_hashtag} {game_hashtag}')
    send_tweet(shot_tweet_text)
    if args.discord:
        send_discord(CHANNEL_ID, shot_tweet_text)

def check_tvtimeout(play, game):
    logging.info("Recent stoppage detected - wait 10 seconds & check if this is a TV Timeout.")
    time.sleep(10)
    # Check if a Stoppage is a TV Timeout
    html_plays = get_html_report(game)
    last_play = html_plays[-1]

    last_play_details = last_play.find_all('td', class_='bborder')
    event_description = last_play_details[5].text
    logging.info('Last HTML Event Description - %s', event_description)
    if "tv timeout" in event_description.lower():
        period_ordinal = play["about"]["ordinalNum"]
        period_remaining = play["about"]["periodTimeRemaining"]
        game_hashtag = game.game_hashtag

        tv_timeout_tweet = (f'Heading to a TV Timeout with {period_remaining} '
                            f'remaining in the {period_ordinal} period.'
                            f'\n\n{game_hashtag}')
        send_tweet(tv_timeout_tweet)
        if args.discord:
            send_discord(CHANNEL_ID, tv_timeout_tweet)

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
                player_name = player["player"]["fullName"]
                assist_total = player["seasonTotal"]
                assists.append(f'{player_name} ({assist_total})')

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
            if args.discord:
                send_discord(CHANNEL_ID, goal_scorechange_tweet)
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
                if args.discord:
                    send_discord(CHANNEL_ID, goal_assistchange_tweet)

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
                if args.discord:
                    send_discord(CHANNEL_ID, goal_assistchange_tweet)
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

        elif event_type == "PERIOD_READY" and event_period > 3 and game.game_type == "P":
            logging.info("Playoff overtime detected.")
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

            elif event_period > 3 and game.game_type == "P":
                ot_period = event_period - 3
                tweet_text = ("Who will be the hero this time? OT{} starts now at {}!\n\n{}"
                              .format(ot_period, game.venue, game.game_hashtag))

            if recent_event(play):
                send_tweet(tweet_text)
                if args.discord:
                    send_discord(CHANNEL_ID, tweet_text)

        elif event_type == "PERIOD_END":
            if event_period in (1, 2):
                # Calculate win percentage when winning / trailing after period
                pref_score = game.preferred_team.score
                other_score = game.other_team.score

                if pref_score > other_score:
                    if event_period == 1:
                        lead_trail_stat = game.preferred_team.lead_trail_lead1P
                    elif event_period == 2:
                        lead_trail_stat = game.preferred_team.lead_trail_lead2P

                    lead_trail_text = ("When leading after the {} period, the {} are {}."
                                     .format(event_period_ordinal, game.preferred_team.short_name,
                                             lead_trail_stat))
                elif pref_score < other_score:
                    if event_period == 1:
                        lead_trail_stat = game.preferred_team.lead_trail_trail1P
                    elif event_period == 2:
                        lead_trail_stat = game.preferred_team.lead_trail_trail2P

                    lead_trail_text = ("When trailing after the {} period, the {} are {}."
                                     .format(event_period_ordinal, game.preferred_team.short_name,
                                             lead_trail_stat))
                else:
                    lead_trail_text = None

                # Build end of period tweet & image
                boxscore = json_feed["liveData"]["boxscore"]["teams"]
                boxscore_away = boxscore["away"]
                boxscore_home = boxscore["home"]
                boxscore_preferred = boxscore_home if game.home_team.preferred else boxscore_away
                boxscore_other = boxscore_away if game.home_team.preferred else boxscore_home
                img = stats_image_generator(game, "intermission", boxscore_preferred, boxscore_other)

                img_shotmap = hockey_bot_imaging.image_generator_shotmap(game, all_plays)
                shotmap_tweet_text = f'Shot map after the {event_period_ordinal} period.'
                if args.notweets:
                    img.show()
                    img_shotmap.show()
                else:
                    img_filename = (os.path.join(PROJECT_ROOT, 'resources/images/GamedayIntermission-{}-{}.png'
                                    .format(event_period, game.preferred_team.games + 1)))
                    img.save(img_filename)

                    img_shotmap_filename = (os.path.join(PROJECT_ROOT, 'resources/images/RinkShotmap-{}-{}.png'
                                            .format(event_period, game.preferred_team.games + 1)))
                    img_shotmap.save(img_shotmap_filename)


                if lead_trail_text is None:
                    # tweet_text = ("The {} period of {} comes to an end.\n\n"
                    #             "{}: {} ({} shots)\n{}: {} ({} shots)"
                    #             .format(event_period_ordinal, game.game_hashtag,
                    #                     game.preferred_team.short_name, game.preferred_team.score,
                    #                     game.preferred_team.shots, game.other_team.short_name,
                    #                     game.other_team.score, game.other_team.shots))
                    tweet_text = ("The {} period of {} comes to an end."
                                  .format(event_period_ordinal, game.game_hashtag))
                else:
                    tweet_text = ("The {} period of {} comes to an end. {}"
                                .format(event_period_ordinal, game.game_hashtag, lead_trail_text))

                if recent_event(play):
                    api = get_api()
                    api.update_with_media(img_filename, tweet_text)
                    api.update_with_media(img_shotmap_filename, shotmap_tweet_text)

                    if args.discord:
                        send_discord(CHANNEL_ID, tweet_text, img_filename)
                        send_discord(CHANNEL_ID, shotmap_tweet_text, img_shotmap_filename)


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
                    if args.discord:
                        send_discord(CHANNEL_ID, tweet_text)

            elif event_period > 3 and (game.preferred_team.score == game.other_team.score) and game.game_type == "P":
                ot_period = event_period - 3
                next_ot = ot_period + 1
                ot_string = "overtime wasn't" if ot_period == 1 else "overtimes weren't"
                tweet_text = ("{} {} to decide this game. "
                              "{} and {} headed to OT{} tied at {}.\n\n{}"
                              .format(ot_period, ot_string, game.preferred_team.short_name, game.other_team.short_name,
                                      next_ot, game.preferred_team.score, game.game_hashtag))
                if recent_event(play):
                    send_tweet(tweet_text)
                    if args.discord:
                        send_discord(CHANNEL_ID, tweet_text)

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

        elif event_type == "MISSED_SHOT" and period_type != "SHOOTOUT":
            if recent_event(play):
                parse_missed_shot(play, game)

        # This code is not reliable enough - commenting out for now
        # elif event_type == "STOP":
        #     if recent_event(play):
        #         check_tvtimeout(play, game)

        else:
            logging.debug("Other event: %s - %s", event_type, event_description)

        # For each loop iteration, update the eventIdx in the game object
        game.last_event_idx = event_idx


def get_html_report(game):
    game_id = game.game_id_html
    pbp_url = f'http://www.nhl.com/scores/htmlreports/20182019/PL{game_id}.HTM'
    logging.info('Going to get HTML Report - %s', pbp_url)

    pbp = requests.get(pbp_url)
    pbp_soup = BeautifulSoup(pbp.content, 'lxml')

    all_plays = pbp_soup.find_all('tr', class_='evenColor')
    return all_plays


def parse_end_of_game(json_feed, game):
    """
    Takes a JSON object of game events & parses for events.

    Input:
    json - JSON object of live feed results (usually from get_game_events)
    game - current game as a Game object

    Ouput:
    None
    """

    all_plays = json_feed["liveData"]["plays"]["allPlays"]
    all_players = json_feed["gameData"]["players"]

    boxscore = json_feed["liveData"]["boxscore"]["teams"]
    decisions = json_feed["liveData"]["decisions"]

    # Once available, build the final score tweet & send it.
    boxscore_away = boxscore["away"]
    boxscore_home = boxscore["home"]
    boxscore_preferred = boxscore_home if game.home_team.preferred else boxscore_away
    boxscore_other = boxscore_away if game.home_team.preferred else boxscore_home

    preferred_home_text = "on the road" if game.preferred_team.home_away == "away" else "at home"
    preferred_hashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name, game.game_type)
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


    # Get next game on the schedule (bottom of the final tweet)
    try:
        pref_team_id = game.preferred_team.team_id
        next_game_url = f'{NHLAPI_BASEURL}/api/v1/teams/{pref_team_id}?expand=team.schedule.next'
        logging.info(f"Going to get next game information via URL - {next_game_url}")
        next_game_json = req_session.get(next_game_url).json()
        next_game_sched = next_game_json.get('teams')[0].get('nextGameSchedule')
        next_game = next_game_sched.get('dates')[0].get('games')[0]

        # Commands used to calculate time related attributes
        localtz = dateutil.tz.tzlocal()
        localoffset = localtz.utcoffset(datetime.now(localtz))
        next_game_date = next_game.get('gameDate')
        next_game_datetime = datetime.strptime(next_game_date, '%Y-%m-%dT%H:%M:%SZ')
        next_game_datetime_local = next_game_datetime + localoffset
        next_game_date_string = datetime.strftime(next_game_datetime_local, '%A %B %d @ %I:%M%p')

        # Get the Opponent for Next Game
        next_game_teams = next_game.get('teams')
        next_game_home = next_game_teams.get('home')
        next_game_away = next_game_teams.get('away')
        if next_game_home.get('team').get('id') == pref_team_id:
            next_game_opponent = next_game_away.get('team').get('name')
        else:
            next_game_opponent = next_game_home.get('team').get('name')

        next_game_venue = next_game.get('venue').get('name')
        next_game_text = (f'Next Game: {next_game_date_string} vs. {next_game_opponent}'
                        f' (at {next_game_venue})!')
    except:
        logging.warning('NHL API returned an incorrect response.')
        next_game_text = ''

    # Generate Final Image
    # img = final_image(game, boxscore_preferred, boxscore_other)
    img = stats_image_generator(game, "final", boxscore_preferred, boxscore_other)
    final_score_tweet = ("{} {} {}\n\n{}"
                         .format(final_score_text, preferred_hashtag, game.game_hashtag,
                                 next_game_text))

    if game.finaltweets["finalscore"] is False:
        # Set the Image Filename & Save it
        img_filename = (os.path.join(PROJECT_ROOT, 'resources/images/GamedayFinal-{}.png'
                            .format(game.preferred_team.games + 1)))
        img.save(img_filename)

        if args.notweets:
            img.show()
            logging.info("%s", final_score_tweet)
        else:
            api = get_api()
            api.update_with_media(img_filename, final_score_tweet)

        if args.discord:
            logging.info("Sending Image & Message to Discord: %s", final_score_tweet)
            send_discord(CHANNEL_ID, final_score_tweet, img_filename)
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

            if args.discord:
                    send_discord(CHANNEL_ID, stars_tweet)
            game.finaltweets["stars"] = True
    except KeyError:
        logging.info("3-stars have not yet posted - try again in next iteration.")

    # Generate Shotmap & Send Tweet
    if game.finaltweets["shotmap"] is False:
        img_shotmap = hockey_bot_imaging.image_generator_shotmap(game, all_plays)
        shotmap_tweet_text = f'Final shot map of the game.'

        img_shotmap_filename = (os.path.join(PROJECT_ROOT, 'resources/images/RinkShotmap-Final-{}.png'
                                            .format(game.preferred_team.games + 1)))
        img_shotmap.save(img_shotmap_filename)

        if args.notweets:
            img_shotmap.show()
            logging.info("%s", shotmap_tweet_text)
        else:
            api = get_api()
            api.update_with_media(img_shotmap_filename, shotmap_tweet_text)

        if args.discord:
            send_discord(CHANNEL_ID, shotmap_tweet_text, img_shotmap_filename)

        game.finaltweets["shotmap"] = True


    # Perform Opposition Stats
    if game.finaltweets["opposition"] is False:
        try:
            nss_opposition, nss_opposition_byline = advanced_stats.nss_opposition(game, game.preferred_team)

            # If both return values are False, it means the lines aren't confirmed
            if nss_opposition is False and nss_opposition_byline is False:
                tweet_text = (f'The bot could not programatically find the confirmed lines for tonight.'
                              f'Due to this no advanced stats will be posted.'
                              f'\n\n{preferred_hashtag} {game.game_hashtag}')
                send_tweet(tweet_text)
                if args.discord:
                    send_discord(CHANNEL_ID, tweet_text)

                # Skip the remainder of the functions by setting retries & tweet array values
                # Then raise an Exception to skip the rest of the below
                game.finaltweets["advstats"] = True
                game.finaltweets["opposition"] = True
                game.finaltweets_retry == 3
                raise ValueError('Advanced stats cannot be performed with no lines!')

            # If the above criteria is not met, the bot can do the rest of the advanced stats
            opposition_tweet_text = (f'{game.preferred_team.team_name} Primary Opposition\n'
                                    f'(via @NatStatTrick)')
            img = hockey_bot_imaging.image_generator_nss_opposition(nss_opposition_byline)
            img_filename = os.path.join(PROJECT_ROOT,
                            'resources/images/GamedayAdvStats-{}.png'
                            .format(game.preferred_team.games + 1))
            img.save(img_filename)

            if args.notweets:
                img.show()
                logging.info("%s", opposition_tweet_text)
            else:
                api = get_api()
                api.update_with_media(img_filename, opposition_tweet_text)

            if args.discord:
                send_discord(CHANNEL_ID, opposition_tweet_text, img_filename)
            game.finaltweets["opposition"] = True
        except Exception as e:
            logging.error(e)
            if game.finaltweets_retry == 3:
                logging.warning('Maximum of 3 retries exceeded - setting opposition to True.')
                game.finaltweets["opposition"] = True



    # Perform Line-By-Line Advanced Stats
    if game.finaltweets["advstats"] is False:
        try:
            # Run the Advanced Stats Function
            nss_linetool, nss_linetool_dict = advanced_stats.nss_linetool(game, game.preferred_team)
            # nss_linetool = advanced_stats.nss_linetool(game, game.preferred_team)

            if nss_linetool is False or nss_linetool_dict is False:
                raise IndexError('Line tool not yet available for this game - try again shortly.')


            adv_stats_tweet_text = (f'{game.preferred_team.team_name} Advanced Stats\n'
                                    f'(via @NatStatTrick)')
            img = hockey_bot_imaging.image_generator_nss_linetool(nss_linetool_dict)
            img_filename = os.path.join(PROJECT_ROOT,
                                        'resources/images/GamedayAdvStats-{}.png'
                                        .format(game.preferred_team.games + 1))
            img.save(img_filename)

            if args.notweets:
                img.show()
                logging.info("%s", adv_stats_tweet_text)
            else:
                api = get_api()
                api.update_with_media(img_filename, adv_stats_tweet_text)

            if args.discord:
                send_discord(CHANNEL_ID, adv_stats_tweet_text, img_filename)
            game.finaltweets["advstats"] = True
        except Exception as e:
            logging.error(e)
            if game.finaltweets_retry == 3:
                logging.warning('Maximum of 5 retries exceeded - setting advstats to True.')
                game.finaltweets["advstats"] = True

    all_tweets_sent = all(value is True for value in game.finaltweets.values())
    logging.info("All Tweets Info: %s", game.finaltweets)

    # Increment Final Tweets Retry Counter
    game.finaltweets_retry += 1
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

    # Get preferred & other team from Game object
    (preferred_team, other_team) = game.get_preferred_team()
    pref_team_homeaway = game.preferred_team.home_away

    # Format & send preview tweet
    clock_emoji = nhl_game_events.clock_emoji(game.game_time_local)

    if game.game_type == "P":
        preview_text_teams = (
            "Tune in {} for Game #{} when the {} take on the {} at {}."
            .format(game.game_time_of_day, game.game_id_playoff_game ,preferred_team.team_name, other_team.team_name, game.venue)
        )
    else:
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

    # Get Team Hashtags
    pref_hashtag = nhl_game_events.team_hashtag(game.preferred_team.team_name, game.game_type)
    other_hashtag = nhl_game_events.team_hashtag(game.other_team.team_name, game.game_type)

    # Get Season Series
    season_series_strings = nhl_game_events.season_series(game.game_id, game.preferred_team,
                                                          game.other_team)

    season_series_str = season_series_strings[0]
    if season_series_str is None:
        season_series_tweet = ("This is the first meeting of the season between "
                               "the {} & the {}.\n\n{} {} {}"
                               .format(game.preferred_team.short_name, game.other_team.short_name,
                                       pref_hashtag, other_hashtag, game.game_hashtag))
    else:
        points_leader_str = season_series_strings[1]
        toi_leader_str = season_series_strings[2]
        if game.game_type == "P":
            # season_series_str = season_series_str.replace("season series", "regular season series")
            season_series_str = "Regular Season Stats -\n\n{}".format(season_series_str)

        season_series_tweet = ("{}\n{}\n{}\n\n{} {} {}"
                               .format(season_series_str, points_leader_str, toi_leader_str,
                                       pref_hashtag, other_hashtag, game.game_hashtag))

    # img = preview_image(game)
    img = pregame_image(game)

    if args.discord:
        if img is not None:
            img_filename = os.path.join(PROJECT_ROOT, 'resources/images/Gameday-{}.png'.format(game.preferred_team.games + 1))
            img.save(img_filename)
            send_discord(CHANNEL_ID, preview_tweet_text, img_filename)
        else:
            send_discord(CHANNEL_ID, preview_tweet_text)

    if args.notweets:
        lineups = nhl_game_events.fantasy_lab_lines(game, game.preferred_team)
        lineups_confirmed = lineups.get('confirmed')
        officials = other_game_info.scouting_the_refs(game, game.preferred_team)
        officials_confirmed = officials.get('confirmed')
        goalies = other_game_info.dailyfaceoff_goalies(
                  preferred_team, other_team, pref_team_homeaway)

        img.show()
        logging.info("%s", preview_tweet_text)
        if lineups_confirmed:
            fwd_def_lines_tweet = lineups.get('fwd_def_lines_tweet')
            power_play_lines_tweet = lineups.get('power_play_lines_tweet', 'N/A')
            logging.info("%s", fwd_def_lines_tweet)
            logging.info("%s", power_play_lines_tweet)
            if args.discord:
                send_discord(CHANNEL_ID, fwd_def_lines_tweet)
                send_discord(CHANNEL_ID, power_play_lines_tweet)
        if officials_confirmed:
            logging.info("%s", officials.get('tweet'))
            if args.discord:
                send_discord(CHANNEL_ID, officials.get('tweet'))
        pref_goalie_tweet_text = goalies.get('pref_goalie')
        other_goalie_tweet_text = goalies.get('other_goalie')
        pref_goalie_tweet = (f'Projected {game.game_hashtag} Goalie '
                             f'for {pref_hashtag}:\n{pref_goalie_tweet_text}')
        other_goalie_tweet = (f'Projected {game.game_hashtag} Goalie '
                              f'for {other_hashtag}:\n{other_goalie_tweet_text}')
        logging.info("%s", pref_goalie_tweet)
        logging.info("%s", other_goalie_tweet)
        logging.info("%s", season_series_tweet)
        if args.discord:
            send_discord(CHANNEL_ID, pref_goalie_tweet)
            send_discord(CHANNEL_ID, other_goalie_tweet)
            send_discord(CHANNEL_ID, season_series_tweet)

        logging.info("Since we are not sending tweets, just sleep until game time.")
        time.sleep(game.game_time_countdown)
    else:
        if img is not None:
            img_filename = os.path.join(PROJECT_ROOT, 'resources/images/Gameday-{}.png'.format(game.preferred_team.games + 1))
            img.save(img_filename)
            api = get_api()
            image_tweet = api.update_with_media(img_filename, preview_tweet_text)
            image_tweet_id = image_tweet.id_str
            game.pregame_lasttweet = image_tweet_id

        else:
            image_tweet_id = send_tweet(preview_tweet_text)
            if args.discord:
                send_discord(CHANNEL_ID, preview_tweet_text)

        # Send Season Series tweet (only tweet not waiting on confirmation)
        game.pregame_lasttweet = send_tweet(season_series_tweet, reply=game.pregame_lasttweet)
        if args.discord:
            send_discord(CHANNEL_ID, season_series_tweet)

        while True:
            if not game.pregametweets['goalies_pref'] or not game.pregametweets['goalies_other']:
                goalie_confirm_list = ('Confirmed', 'Likely')

                # Get Goalies from Daily Faceoff
                goalies = other_game_info.dailyfaceoff_goalies(
                        preferred_team, other_team, pref_team_homeaway)
                pref_goalie_tweet_text = goalies.get('pref_goalie')
                other_goalie_tweet_text = goalies.get('other_goalie')
                pref_goalie_confirm_text = goalies.get('pref_goalie_confirm')
                other_goalie_confirm_text = goalies.get('other_goalie_confirm')

                # Convert confirmations into True / False
                pref_goalie_confirm = bool(pref_goalie_confirm_text in goalie_confirm_list)
                other_goalie_confirm = bool(other_goalie_confirm_text in goalie_confirm_list)

                if pref_goalie_confirm and not game.pregametweets['goalies_pref']:
                    pref_goalie_tweet = (f'Projected {game.game_hashtag} Goalie '
                                         f'for {pref_hashtag}:\n{pref_goalie_tweet_text}')
                    game.pregame_lasttweet = send_tweet(pref_goalie_tweet, reply=game.pregame_lasttweet)
                    if args.discord:
                        send_discord(CHANNEL_ID, pref_goalie_tweet)
                    game.pregametweets['goalies_pref'] = True
                else:
                    logging.info('Preferred team goalie not yet likely or confirmed.')

                if other_goalie_confirm and not game.pregametweets['goalies_other']:
                    other_goalie_tweet = (f'Projected {game.game_hashtag} Goalie '
                                          f'for {other_hashtag}:\n{other_goalie_tweet_text}')
                    game.pregame_lasttweet = send_tweet(other_goalie_tweet, reply=game.pregame_lasttweet)
                    if args.discord:
                        send_discord(CHANNEL_ID, other_goalie_tweet)
                    game.pregametweets['goalies_other'] = True
                else:
                    logging.info('Other team goalie not yet likely or confirmed.')

            # Get Fantasy Labs lineups (only if tweet not sent)
            if not game.pregametweets['lines']:
                lineups = nhl_game_events.fantasy_lab_lines(game, game.preferred_team)
                lineups_confirmed = lineups['confirmed']

                # Only send lineups tweet if confirmed
                if lineups_confirmed:
                    fwd_def_lines_tweet = lineups.get('fwd_def_lines_tweet')
                    power_play_lines_tweet = lineups.get('power_play_lines_tweet')
                    game.pregame_lasttweet = send_tweet(fwd_def_lines_tweet, reply=game.pregame_lasttweet)
                    if args.discord:
                        send_discord(CHANNEL_ID, fwd_def_lines_tweet)
                    game.pregame_lasttweet = send_tweet(power_play_lines_tweet, reply=game.pregame_lasttweet)
                    if args.discord:
                        send_discord(CHANNEL_ID, power_play_lines_tweet)
                    game.pregametweets['lines'] = True
                else:
                    logging.info('Lineup information not yet confirmed.')

            # Get Officials via Scouting the Refs (if tweet not sent)
            if not game.pregametweets['refs']:
                officials = other_game_info.scouting_the_refs(game, game.preferred_team)
                officials_confirmed = officials.get('confirmed')

                # Only send officials tweet if confirmed
                if officials_confirmed:
                    officials_tweet = officials.get('tweet')
                    game.pregame_lasttweet = send_tweet(officials_tweet, reply=game.pregame_lasttweet)
                    if args.discord:
                        send_discord(CHANNEL_ID, officials_tweet)
                    game.pregametweets['refs'] = True
                else:
                    logging.info('Referee information not yet posted.')


            # Check if all tweets are sent
            all_pregametweets_sent = all(value is True for value in game.pregametweets.values())
            logging.info("Pre-Game Tweets: %s", game.pregametweets)
            logging.info("Pre-Game Tweets Flag: %s", all_pregametweets_sent)

            if not all_pregametweets_sent and game.game_time_countdown > 1800:
                logging.info("Game State is Preview & all pre-game tweets are not sent. "
                             "Sleep for 30 minutes & check again.")
                time.sleep(1800)
            elif not all_pregametweets_sent and game.game_time_countdown < 1800:
                logging.warning("Game State is Preview & all pre-game tweets are not sent. "
                                "Less than 30 minutes until game time so we skip these today."
                                "If needed, we try to get lines at the end of the game for advanced stats.")
                time.sleep(game.game_time_countdown)
                break
            else:
                logging.info("Game State is Preview & all tweets are sent. "
                             "Sleep for %s seconds until game time.", game.game_time_countdown)
                time.sleep(game.game_time_countdown)
                break


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# MAIN PROGRAM FLOW
# ------------------------------------------------------------------------------

# This line is to prevent code from being executed, if ever imported.
if __name__ == '__main__':
    args = parse_arguments()

    # If running in Docker, parse environment variables (instead of arguments)
    # And set args.console to True to make `docker logs` easier to use
    if args.docker:
        # Check to see if Time Zone is set
        if "TZ" not in os.environ:
            print("[ERROR] Timezone environment variable not set, please add to `docker run` commmand.")
            sys.exit()

        if os.environ["TZ"] not in pytz.all_timezones:
            print(f"[ERROR] {os.environ['TZ']} is not a valid time zone, please fix in `docker run` commmand.")
            sys.exit()

        # Force console argument & parse the remainder of the environment variables
        args.console = True
        parse_env_variables(args)

        # Standardize Twitter Tokens (if being used via Docker)
        if not args.notweets:
            try:
                if args.debugtweets:
                    debug_consumer_key = os.environ["TWTR_CONSUMER_KEY"]
                    debug_consumer_secret = os.environ["TWTR_CONSUMER_SECRET"]
                    debug_access_token = os.environ["TWTR_ACCESS_TOKEN"]
                    debug_access_secret = os.environ["TWTR_ACCESS_SECRET"]
                else:
                    consumer_key = os.environ["TWTR_CONSUMER_KEY"]
                    consumer_secret = os.environ["TWTR_CONSUMER_SECRET"]
                    access_token = os.environ["TWTR_ACCESS_TOKEN"]
                    access_secret = os.environ["TWTR_ACCESS_SECRET"]
            except KeyError:
                print("[ERROR] Twitter API keys are not set, please add to `docker run` command.")
                sys.exit()


    # Setup Logging for this script
    setup_logging()

    if args.docker and not args.notweets:
        try:
            TWITTER_ID = os.environ["TWTR_HANDLE"]
        except KeyError:
            print("[ERROR] Twitter handle is not set, please add to `docker run` command.")
            sys.exit()
    else:
        if args.debugtweets:
            TWITTER_ID = config['ENDPOINTS']['DEBUG_TWITTER_HANDLE']

    # If --team is specified, override TEAM_BOT constant
    if args.docker:
        try:
            TEAM_BOT = args.team
        except KeyError:
            print("[ERROR] NHL Team is not set, please add to `docker run` command.")
            sys.exit()
    else:
        if args.team is not None:
            TEAM_BOT = args.team

    # ------------------------------------------------------------------------------
    # SCRIPT STARTS PROCESSING BELOW
    # ------------------------------------------------------------------------------

    # Log script start lines
    logging.info('#' * 80)
    logging.info('New instance of the Hockey Twitter Bot started.')
    if args.docker:
        logging.info('Running in a Docker container - environment variables parsed.')
    logging.info('TIME: %s', datetime.now())
    logging.info('ARGS - notweets: %s, console: %s, teamoverride: %s',
                 args.notweets, args.console, args.team)
    logging.info('ARGS - debug: %s, debugtweets: %s, overridelines: %s',
                 args.debug, args.debugtweets, args.overridelines)
    logging.info('ARGS - date: %s, split: %s, localdata: %s, discord: %s',
                 args.date, args.split, args.localdata, args.discord)
    logging.info("%s\n", "#" * 80)

    # Create a requests object to maintain session
    req_session = requests.Session()

    # Starting Discord thread
    logging.info('Starting Discord Thread')
    start_discord_bot()
    # send_discord(CHANNEL_ID, 'TEST')
    logging.info('Discord Thread started')

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


    # For debugging purposes, print all game_info
    logging.debug("Game Information: %s", game_info)

    # Create a Game Object
    gameobj_game_id = game_info["gamePk"]
    gameobj_game_season = game_info["season"]
    gameobj_game_type = game_info["gameType"]
    gameobj_date_time = game_info["gameDate"]
    gameobj_game_state = game_info["status"]["abstractGameState"]
    if args.localdata or args.yesterday:
        gameobj_game_state = "Live"

    # If venue is null for some reason, extract from home_team
    try:
        gameobj_venue = game_info["venue"]["name"]
    except KeyError:
        gameobj_venue = game_info["teams"]["home"]["team"]["venue"]["name"]
    gameobj_live_feed = game_info["link"]

    gameobj_broadcasts = {}
    try:
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
    except KeyError:
        logging.warning("Broadcasts not available - setting them to TBD.")
        gameobj_broadcasts["home"] = "TBD"
        gameobj_broadcasts["home"] = "TBD"

    # Create Team Objects
    # Note: Schedule endpoint calls 3-character 'abbreviation' - not 'triCode')
    # TODO: Review record / games played for playoffs
    team_objs_season_id = str(gameobj_game_id)[0:4]
    team_objs_season = "{}{}".format(team_objs_season_id, int(team_objs_season_id) + 1)
    awayteam_info = game_info["teams"]["away"]["team"]
    awayteam_record = game_info["teams"]["away"]["leagueRecord"]
    if gameobj_game_type == config['GAMETYPE']['PLAYOFFS'] or gameobj_game_type == config['GAMETYPE']['PRESEASON']:
        awayteamobj_games = awayteam_record["wins"] + awayteam_record["losses"]
    else:
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
                                         awayteam_record, team_objs_season)

    hometeam_info = game_info["teams"]["home"]["team"]
    hometeam_record = game_info["teams"]["home"]["leagueRecord"]
    if gameobj_game_type == config['GAMETYPE']['PLAYOFFS'] or gameobj_game_type == config['GAMETYPE']['PRESEASON']:
        hometeamobj_games = hometeam_record["wins"] + hometeam_record["losses"]
    else:
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
                                         hometeam_record, team_objs_season)

    # Check for Line Overrides
    if args.overridelines:
        home_team_obj.overridelines = True
        away_team_obj.overridelines = True

    # Set Preferred Team
    home_team_obj.preferred = bool(home_team_obj.team_name == TEAM_BOT)
    away_team_obj.preferred = bool(away_team_obj.team_name == TEAM_BOT)
    preferred_indicator = "home" if home_team_obj.preferred else "away"

    game_obj = nhl_game_events.Game(gameobj_game_id, gameobj_game_type, gameobj_date_time,
                                    gameobj_game_state, gameobj_venue, home_team_obj,
                                    away_team_obj, preferred_indicator, gameobj_live_feed,
                                    gameobj_game_season)

    # Get the gameday rosters (from the Live Feed)
    # This is needed because in some instances a player is not included
    # on the /teams/{id}/roster page for some reason
    preferred_homeaway = game_obj.preferred_team.home_away
    preferred_team = game_obj.preferred_team
    other_team = game_obj.other_team
    try:
        logging.info("Getting Gameday Roster via API - %s", game_obj.live_feed)
        all_players = req_session.get(game_obj.live_feed).json()
        all_players = all_players.get('gameData').get('players')
        for id, player in all_players.items():
            team = player.get('currentTeam').get('name')
            if team == preferred_team.team_name:
                preferred_team.gameday_roster[id] = player
            else:
                other_team.gameday_roster[id] = player
    except requests.exceptions.RequestException as e:
        logging.error("Unable to get all players.")
        logging.error(e)


    # All objects are created, start the game loop
    while True:
        if game_obj.game_state == "Preview":
            if game_obj.game_time_countdown > 0:
                if args.debug:
                    show_all_objects()
                game_preview(game_obj)
            else:
                logging.info(
                    "Past game time, but game status still 'Preview' - sleep for 30 seconds.")
                get_game_events(game_obj)
                time.sleep(30)

        elif game_obj.game_state == "Live":
            # Add try / except to avoid exits
            try:
                logging.info('-' * 80)
                logging.info("Game is currently live - checking events after event Idx %s.",
                            game_obj.last_event_idx)
                game_events = get_game_events(game_obj)
                loop_game_events(game_events, game_obj)
                logging.info("Sleeping for 5 seconds...")
                time.sleep(5)
            except Exception as e:
                logging.error("Uncaught exception in live game loop - still sleep for 5 seconds.")
                logging.error(e)
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
