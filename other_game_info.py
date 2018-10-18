"""This module contains functions related to gathering
   information from non NHL APIs & websites."""

# pylint: disable=too-few-public-methods

import configparser
import logging
import os
import re
from datetime import datetime, timedelta

import dateutil.tz
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse

import nhl_game_events

log = logging.getLogger('root')
config = configparser.ConfigParser()
conf_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.ini')
config.read(conf_path)

TEAM_BOT = config['DEFAULT']['TEAM_NAME']
NHLAPI_BASEURL = config['ENDPOINTS']['NHL_BASE']
NHLRPT_BASEURL = config['ENDPOINTS']['NHL_RPT_BASE']
TWITTER_URL = config['ENDPOINTS']['TWITTER_URL']
TWITTER_ID = config['ENDPOINTS']['TWITTER_HANDLE']
VPS_CLOUDHOST = config['VPS']['CLOUDHOST']
VPS_HOSTNAME = config['VPS']['HOSTNAME']


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Advanced Stats Functions
# ------------------------------------------------------------------------------

def scouting_the_refs(game, team):
    # Initialize return dictionary
    return_dict = {}
    refposts = requests.get('http://scoutingtherefs.com/wp-json/wp/v2/posts').json()
    for post in refposts:
        categories = post.get('categories')
        post_date = parse(post.get('date'))
        posted_today = bool(post_date.date() == datetime.today().date())
        post_title = post.get('title').get('rendered')
        if (921 in categories and posted_today) or (posted_today and 'NHL' in post_title):
            content = post.get('content').get('rendered')
            soup = BeautifulSoup(content, 'html.parser')

    try:
        officials_games = soup.find_all("h1")
        for official_game in officials_games:
            if team.team_name in official_game.text:
                game_details = official_game.find_next('table')

                referees = []
                linesmen = []

                soup_referees = game_details.find_all("tr")[1].find_all("td")
                soup_referees_gms = game_details.find_all("tr")[4].find_all("td")
                for i, ref in enumerate(soup_referees):
                    ref_name = ref.text
                    ref_gms = soup_referees_gms[i].text
                    if ref_name:
                        ref_string = f'{ref_name} ({ref_gms} games)'
                        referees.append(ref_string)

                soup_linesmen = game_details.find_all("tr")[23].find_all("td")
                soup_linesman_gms = game_details.find_all("tr")[26].find_all("td")
                for i, linesman in enumerate(soup_linesmen):
                    linesman_name = linesman.text
                    linesman_gms = soup_linesman_gms[i].text
                    if linesman_name:
                        linesman_string = f'{linesman_name} ({linesman_gms} games)'
                        linesmen.append(linesman_string)

                return_dict['referees'] = referees
                return_dict['linesmen'] = linesmen

                # Add 'tweet strings' to dictionary
                tweet_string = f'The officials for {game.game_hashtag} are - \n'
                for official, attrs in return_dict.items():
                    tweet_string += f'\n{official.title()}:\n'
                    for individual in attrs:
                        tweet_string += f'* {individual.strip()}\n'

                tweet_string += '\n(via @ScoutingTheRefs)'
                return_dict['tweet'] = tweet_string
    except NameError:
        print("Ref information is not posted for today - check again later!")

    return_dict['confirmed'] = False if not bool(return_dict) else True
    logging.debug('Scouting the Refs - %s', return_dict)
    return(return_dict)
