"""
This module contains functions related to gathering information
from non NHL APIs & websites (ex - lineups, officials, etc).
"""

import logging
from bs4 import BeautifulSoup

import requests
from datetime import datetime, timedelta
from dateutil.parser import parse
from requests.adapters import HTTPAdapter
from fake_useragent import UserAgent

from hockeygamebot.helpers import utils
from hockeygamebot.models.sessions import SessionFactory


def thirdparty_request(url, headers=None):
    """Handles all third-party requests / URL calls.

    Args:
        url: URL of the website to call
        headers: Optional headers (ex - fake User Agent)

    Returns:
        response: response from the website (requests.get)
    """

    sf = SessionFactory()
    session = sf.get()

    retries = HTTPAdapter(max_retries=3)
    session.mount("https://", retries)
    session.mount("http://", retries)

    try:
        logging.info("Sending Third Party URL Request - %s", url)
        response = session.get(url, headers=headers)
        return response
    except requests.ConnectionError as ce:
        logging.error(ce)
        return None
    except requests.RequestException as re:
        logging.error(re)
        return None


def bs4_parse(content):
    """ Instead of speficying lxml every time, we define this function and pass
        any content that requires scraping to it.

    Args:
        content: A response from the requests library

    Returns:
        A souped response
    """
    try:
        return BeautifulSoup(content, "lxml")
    except TypeError as e:
        logging.error(e)
        return None


def hockeyref_goalie_against_team(goalie, opponent):
    """Scrapes Hockey Reference for starting goalies for the night.

    Args:
        goalie: The name of the goalie we want to look up.
        opponent: The team we want to check the above goalie's stats for

    Returns:
        goalie_stats_split: A string of goalie stats split versus opponent
    """

    config = utils.load_config()
    hockeyref_base = config["endpoints"]["hockeyref_base"]

    # Form the Hockey Reference specific player name format
    goalie_name_orig = goalie
    goalie_name = goalie.lower()
    goalie_first_name = goalie_name.split()[0]
    goalie_last_name = goalie_name.split()[1]
    goalie_hockeyref_name = f"{goalie_last_name[0:5]}{goalie_first_name[0:2]}01"

    logging.info("Trying to get goalie split information for %s against the %s.", goalie, opponent)
    hockeyref_url = f"{hockeyref_base}/{goalie_last_name[0]}/{goalie_hockeyref_name}/splits"
    resp = thirdparty_request(hockeyref_url)

    # If we get a bad response from the function above, return False
    if resp is None:
        return False

    soup = bs4_parse(resp.content)
    if soup is None:
        return False

    hr_player_info = soup.find("div", attrs={"itemtype": "https://schema.org/Person"})
    hr_player_info_attr = hr_player_info.find_all("p")
    hr_name = soup.find("h1", attrs={"itemprop": "name"}).text

    for attr in hr_player_info_attr:
        if "Position:" in attr.text:
            hr_position_goalie = bool("Position: G" in attr.text.rstrip())
            break

    # If the goalie name doesn't match exactly or the player position is not goalie, try Player 02
    if hr_name.lower() != goalie_name_orig.lower() or not hr_position_goalie:
        logging.warning("%s is not who we are looking for, or is not a goalie - trying 02.")
        goalie_hockeyref_name = f"{goalie_last_name[0:5]}{goalie_first_name[0:2]}02"
        hockeyref_url = f"{hockeyref_base}/{goalie_last_name[0]}/{goalie_hockeyref_name}/splits"
        resp = thirdparty_request(hockeyref_url)
        soup = bs4_parse(resp.content)

    split_rows = soup.find("table", {"id": "splits"}).find("tbody").find_all("tr")
    for row in split_rows:
        cells = row.find_all("td")
        team_row = row.find("td", attrs={"data-stat": "split_value"})
        team_name = team_row.text if team_row is not None else "None"

        if team_name == opponent:
            wins = cells[2].text
            loss = cells[3].text
            ot = cells[4].text
            sv_percent = cells[8].text
            gaa = cells[9].text
            shutout = cells[10].text

            goalie_stats_split = "{}-{}-{} W-L | {} GAA | 0{} SV% | {} SO".format(
                wins, loss, ot, gaa, sv_percent, shutout
            )
            return goalie_stats_split

    return True


def fantasy_lab_lines(game, preferred_team):
    return True


def dailyfaceoff_lines_parser(lines, soup):
    """ A sub-function of the dailyfaceoff_lines(...) that takes a BS4 Soup
        and parses it to break it down by individual player & position.

    Args:
        lines: Existing lines dictionary (append)
        soup: A valid souped response

    Return:
        lines: Modified lines dictionary
    """

    for player in soup:
        try:
            soup_position = player['id']
            line = soup_position[-1]
            position = soup_position[0:-1]
            player_position = f"{line}{position}"
            name = player.find("a").text

            # Add player & position to existing lines dictionary
            lines[player_position] = name
        except KeyError:
            pass    # This is a valid exception - not a player.

    return lines


def dailyfaceoff_lines(game, team):
    """Parse Daily Faceoff lines page to get lines dictionary.
       Used for pre-game tweets & advanced stats.

    Args:
        game (game): An NHL Game Event game object.
        team (Team): A NHL Game Event team object.

    Returns:
        Dictionary: confirmed, forwards, defense, powerplay
    """

    # Instantiate blank dictionaries
    return_dict = dict()
    lines = dict()

    config = utils.load_config()
    df_linecombos_url = config["endpoints"]["df_line_combos"]

    # Setup a Fake User Agent (simulates a real visit)
    ua = UserAgent()
    ua_header = {'User-Agent':str(ua.chrome)}

    df_team_encoded = team.team_name.replace(" ", "-").replace("é", "e").lower()
    df_lines_url = df_linecombos_url.replace("TEAMNAME", df_team_encoded)

    logging.info("Requesting & souping the Daily Faceoff lines page.")
    resp = thirdparty_request(df_lines_url, headers=ua_header)
    soup = bs4_parse(resp.content)

    # Grab the last update line from Daily Faceoff
    # If Update Time != Game Date, return not confirmed
    soup_update = soup.find('div', class_="team-lineup-last-updated")
    last_update = soup_update.text.replace('\n', '').strip().split(': ')[1]
    last_update_date = parse(last_update)
    game_day = parse(game.game_date_local)
    confirmed = bool(last_update_date.date() == game_day.date())
    return_dict['confirmed'] = confirmed
    # if not confirmed:
    #     return return_dict

    # If the lines are confirmed (updated today) then parse & return
    combos = soup.find("div", class_="team-line-combination-wrap")
    soup_forwards = combos.find('table', {"id":"forwards"}).find('tbody').find_all('td')
    soup_defense = combos.find('table', {"id":"defense"}).find('tbody').find_all('td')

    lines = dailyfaceoff_lines_parser(lines, soup_forwards)
    lines = dailyfaceoff_lines_parser(lines, soup_defense)

    # Put the lines in the return dictionary
    # And set the property on the team object
    return_dict['lines'] = lines
    team.lines = lines

    return return_dict



def scouting_the_refs(game, pref_team):
    """Scrapes Scouting the Refs for referee information for the night.

    Args:
        game: Game Object
        pref_team (Team): Preferred team object.

    Returns:
        Tuple: dictionary {goalie string, goalie confirmed}
    """
    # Initialized return dictionary
    return_dict = dict()

    config = utils.load_config()
    refs_url = config["endpoints"]["scouting_refs"]
    logging.info('Getting officials information from Scouting the Refs!')
    response = thirdparty_request(refs_url).json()

    # If we get a bad response from the function above, return False
    if response is None:
        return False

    for post in response:
        categories = post.get('categories')
        post_date = parse(post.get('date'))
        posted_today = bool(post_date.date() == datetime.today().date())
        post_title = post.get('title').get('rendered')
        # if (921 in categories and posted_today) or (posted_today and 'NHL' in post_title):
        if 921 in categories:
            content = post.get('content').get('rendered')
            soup = bs4_parse(content)
            break

    # TESTING
    soup = BeautifulSoup(requests.get('https://scoutingtherefs.com/2019/04/25706/tonights-nhl-referees-and-linesmen-4-6-19/').content, 'lxml')

    # If we get some bad soup, return False
    if soup is None:
        return False

    games = soup.find_all("h1")
    for game in games:
        if pref_team.team_name in game.text:
            game_details = game.find_next('table')
            break

    return_referees = list()
    return_linesmen = list()

    refs = game_details.find_all("tr")[1].find_all("td")
    refs_season_games = game_details.find_all("tr")[3].find_all("td")
    refs_career_games = game_details.find_all("tr")[4].find_all("td")
    for i, ref in enumerate(refs):
        ref_name = ref.text
        ref_season_games = refs_season_games[i].text
        ref_career_games = refs_career_games[i].text
        if ref_name:
            ref_dict = dict()
            ref_dict['name'] = ref_name
            ref_dict['seasongames'] = ref_season_games
            ref_dict['careergames'] = ref_career_games
            return_referees.append(ref_dict)

    linesmen = game_details.find_all("tr")[22].find_all("td")
    linesmen_season_games = game_details.find_all("tr")[24].find_all("td")
    linesmen_career_games = game_details.find_all("tr")[25].find_all("td")
    for i, linesman in enumerate(linesmen):
        linesman_name = linesman.text
        linesman_season_games = linesmen_season_games[i].text
        linesman_career_games = linesmen_career_games[i].text
        if linesman_name:
            linesman_dict = dict()
            linesman_dict['name'] = linesman_name
            linesman_dict['seasongames'] = linesman_season_games
            linesman_dict['careergames'] = linesman_career_games
            return_linesmen.append(linesman_dict)

    return_dict['referees'] = return_referees
    return_dict['linesmen'] = return_linesmen
    return_dict['confirmed'] = False if not bool(return_dict) else True
    logging.debug('Scouting the Refs - %s', return_dict)
    return return_dict


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
    config = utils.load_config()
    df_goalies_url = config["endpoints"]["df_starting_goalies"]
    df_linecombos_url = config["endpoints"]["df_line_combos"]

    logging.info("Trying to get starting goalie information via Daily Faceoff.")
    resp = thirdparty_request(df_goalies_url)

    # If we get a bad response from the function above, return False
    if resp is None:
        return False

    soup = bs4_parse(resp.content)
    if soup is None:
        return False

    logging.info("Valid response received & souped - parse the Daily Faceoff page!")
    pref_team_name = pref_team.team_name

    games = soup.find_all("div", class_="starting-goalies-card stat-card")
    team_playing_today = any(pref_team_name in game.text for game in games)
    if games and team_playing_today:
        for game in games:
            teams = game.find("h4", class_="top-heading-heavy").text
            # If the preferred team is not in this matchup, skip this loop iteration
            if pref_team_name not in teams:
                continue

            teams_split = teams.split(" at ")
            home_team = teams_split[1]
            away_team = teams_split[0]
            goalies = game.find("div", class_="stat-card-main-contents")

            away_goalie_info = goalies.find("div", class_="away-goalie")
            away_goalie_name = away_goalie_info.find("h4").text.strip()
            away_goalie_confirm = away_goalie_info.find("h5", class_="news-strength")
            away_goalie_confirm = str(away_goalie_confirm.text.strip())
            away_goalie_stats = away_goalie_info.find("p", class_="goalie-record")
            away_goalie_stats_str = " ".join(away_goalie_stats.text.strip().split())

            away_goalie = dict()
            away_goalie["name"] = away_goalie_name
            away_goalie["confirm"] = away_goalie_confirm
            away_goalie["season"] = away_goalie_stats_str

            home_goalie_info = goalies.find("div", class_="home-goalie")
            home_goalie_name = home_goalie_info.find("h4").text.strip()
            home_goalie_confirm = home_goalie_info.find("h5", class_="news-strength")
            home_goalie_confirm = str(home_goalie_confirm.text.strip())
            home_goalie_stats = home_goalie_info.find("p", class_="goalie-record")
            home_goalie_stats_str = " ".join(home_goalie_stats.text.strip().split())

            home_goalie = dict()
            home_goalie["name"] = home_goalie_name
            home_goalie["confirm"] = home_goalie_confirm
            home_goalie["season"] = home_goalie_stats_str

            if pref_homeaway == "home":
                return_dict["pref"] = home_goalie
                return_dict["other"] = away_goalie
            else:
                return_dict["pref"] = away_goalie
                return_dict["pref"]["homeaway"] = "away"
                return_dict["other"] = home_goalie
                return_dict["other"]["homeaway"] = "home"

            return_dict["home"] = home_goalie
            return_dict["away"] = away_goalie
            return return_dict

    # If there is any issue parsing the Daily Faceoff page, grab a goalie from each team
    else:
        logging.info(
            "There was an issue parsing the Daily Faceoff page, "
            "grabbing a goalie from each individual team's line combinations page."
        )
        pref_team_encoded = pref_team.team_name.replace(" ", "-").replace("é", "e").lower()
        other_team_encoded = other_team.team_name.replace(" ", "-").replace("é", "e").lower()
        df_url_pref = df_linecombos_url.replace("TEAMNAME", pref_team_encoded)
        df_url_other = df_linecombos_url.replace("TEAMNAME", other_team_encoded)

        logging.info("Getting a fallback goalie for the preferred team.")
        resp = thirdparty_request(df_url_pref)
        soup = bs4_parse(resp.content)
        goalie_table = soup.find("table", attrs={"summary": "Goalies"}).find("tbody").find_all("tr")
        pref_goalie_name = goalie_table[0].find_all("td")[0].find("a").text

        logging.info("Getting a fallback goalie for the other team.")
        resp = thirdparty_request(df_url_other)
        soup = bs4_parse(resp.content)
        goalie_table = soup.find("table", attrs={"summary": "Goalies"}).find("tbody").find_all("tr")
        other_goalie_name = goalie_table[0].find_all("td")[0].find("a").text

        return_dict["pref_goalie"] = pref_goalie_name
        return_dict["pref_goalie_confirm"] = "Not Found"
        return_dict["other_goalie"] = other_goalie_name
        return_dict["other_goalie_confirm"] = "Not Found"

        return return_dict

    return True
