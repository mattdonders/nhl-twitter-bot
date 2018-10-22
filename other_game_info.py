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


def fantasy_lab_alt_names(player_name):
    fantasy_lab_alts = {
        "Steve Santini": "Steven Santini"
    }

    return fantasy_lab_alts.get(player_name, player_name)

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Other Game Information
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
            soup = BeautifulSoup(content, 'lxml')

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
                        tweet_string += f'- {individual.strip()}\n'

                tweet_string += '\n(via @ScoutingTheRefs)'
                return_dict['tweet'] = tweet_string
    except NameError:
        pass

    return_dict['confirmed'] = False if not bool(return_dict) else True
    logging.debug('Scouting the Refs - %s', return_dict)
    return(return_dict)


def dailyfaceoff_goalies(pref_team, other_team, pref_homeaway):
    """Scrapes Daily Faceoff for starting goalies for the night.

    Args:
        pref_team (Team): Preferred team object.
        other_team (Team): Other team object.
        pref_homeaway (str): Is preferred team home or away?

    Returns:
        Tuple: dictionary {goalie string, goalie confirmed}
    """
    return_dict = {}
    pref_team_name = pref_team.team_name
    home_team_short = pref_team.short_name if pref_homeaway == "home" else other_team.short_name
    away_team_short = pref_team.short_name if pref_homeaway == "away" else other_team.short_name

    url = 'https://www.dailyfaceoff.com/starting-goalies/'
    logging.info('Getting goalies on Daily Faceoff via URL - %s', url)
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'lxml')
    logging.info('Souping the Daily Faceoff goalies page.')

    games = soup.find_all("div", class_="starting-goalies-card stat-card")
    team_playing_today = any(pref_team_name in game.text for game in games)
    if len(games) > 0 and team_playing_today:
        for game in games:
            teams = game.find("h4", class_="top-heading-heavy")
            teams = teams.text
            if pref_team_name in teams:
                teams_split = teams.split(" at ")
                home_team = teams_split[1]
                away_team = teams_split[0]
                goalies = game.find("div", class_="stat-card-main-contents")

                away_goalie_info = goalies.find("div", class_="away-goalie")
                away_goalie_name = away_goalie_info.find("h4")
                away_goalie_name = away_goalie_name.text.strip()
                away_goalie_confirm = away_goalie_info.find("h5", class_="news-strength")
                away_goalie_confirm = str(away_goalie_confirm.text.strip())

                away_goalie_stats = away_goalie_info.find("p", class_="goalie-record")
                away_goalie_stats_str = away_goalie_stats.text.strip()
                away_goalie_stats_str = " ".join(away_goalie_stats_str.split())
                away_goalie_stats_split = nhl_game_events.hockey_ref_goalie_against_team(away_goalie_name, home_team)
                away_goalie_str = "{} ({})\nSeason Stats: {}\n\nCareer (vs {}): {}".format(away_goalie_name,
                                                    away_goalie_confirm, away_goalie_stats_str,
                                                    home_team_short, away_goalie_stats_split)

                home_goalie_info = goalies.find("div", class_="home-goalie")
                home_goalie_name = home_goalie_info.find("h4")
                home_goalie_name = home_goalie_name.text.strip()
                home_goalie_confirm = home_goalie_info.find("h5", class_="news-strength")
                home_goalie_confirm = str(home_goalie_confirm.text.strip())

                home_goalie_stats = home_goalie_info.find("p", class_="goalie-record")
                home_goalie_stats_str = home_goalie_stats.text.strip()
                home_goalie_stats_str = " ".join(home_goalie_stats_str.split())
                home_goalie_stats_split = nhl_game_events.hockey_ref_goalie_against_team(home_goalie_name, away_team)
                home_goalie_str = "{} ({})\nSeason Stats: {}\n\nCareer (vs {}): {}".format(home_goalie_name,
                                                    home_goalie_confirm, home_goalie_stats_str,
                                                    away_team_short, home_goalie_stats_split)

                if pref_homeaway == "home":
                    pref_goalie_str = home_goalie_str
                    pref_goalie_confirm = home_goalie_confirm
                    other_goalie_str = away_goalie_str
                    other_goalie_confirm = away_goalie_confirm
                else:
                    pref_goalie_str = away_goalie_str
                    pref_goalie_confirm = away_goalie_confirm
                    other_goalie_str = home_goalie_str
                    other_goalie_confirm = home_goalie_confirm

                return_dict['pref_goalie'] = pref_goalie_str
                return_dict['pref_goalie_confirm'] = pref_goalie_confirm.replace('(', '')
                return_dict['other_goalie'] = other_goalie_str
                return_dict['other_goalie_confirm'] = other_goalie_confirm

                return return_dict
    else:
        # Get one goalie from each team
        url_team_name_pref = pref_team.team_name.replace(" ","-").replace("é","e").lower()
        url_team_name_other = other_team.team_name.replace(" ", "-").replace("é","e").lower()
        faceoff_url_pref = "https://www.dailyfaceoff.com/teams/{}/line-combinations".format(url_team_name_pref)
        faceoff_url_other = "https://www.dailyfaceoff.com/teams/{}/line-combinations".format(url_team_name_other)

        r = requests.get(faceoff_url_pref)
        soup = BeautifulSoup(r.content, 'lxml')
        goalie_table = soup.find("table", attrs={"summary":"Goalies"}).find("tbody").find_all("tr")
        pref_goalie_name = goalie_table[0].find_all("td")[0].find("a").text

        r = requests.get(faceoff_url_other)
        soup = BeautifulSoup(r.content, 'lxml')
        goalie_table = soup.find("table", attrs={"summary":"Goalies"}).find("tbody").find_all("tr")
        other_goalie_name = goalie_table[0].find_all("td")[0].find("a").text

        return_dict['pref_goalie'] = pref_goalie_name
        return_dict['pref_goalie_confirm'] = "Not Found"
        return_dict['other_goalie'] = other_goalie_name
        return_dict['other_goalie_confirm'] = "Not Found"

        return return_dict
