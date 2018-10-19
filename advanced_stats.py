"""This module contains functions related to gathering
   advanced post-game stats to tweet."""

# pylint: disable=too-few-public-methods

import configparser
import datetime
import logging
import os
import re

import dateutil.tz
import requests
from bs4 import BeautifulSoup

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

def nss_abbreviation(team):
    # Fix Montreal Canadiens
    team_name = team.team_name.replace('é', 'e')
    nss_teams = {'Anaheim Ducks': 'ANA', 'Arizona Coyotes': 'ARI', 'Boston Bruins': 'BOS',
                 'Buffalo Sabres': 'BUF', 'Carolina Hurricanes': 'CAR', 'Columbus Blue Jackets': 'CBJ',
                 'Calgary Flames': 'CGY', 'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL',
                 'Dallas Stars': 'DAL', 'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM',
                 'Florida Panthers': 'FLA', 'Los Angeles Kings': 'L.A', 'Minnesota Wild': 'MIN',
                 'Montreal Canadiens': 'MTL', 'New Jersey Devils': 'N.J', 'Nashville Predators': 'NSH',
                 'New York Islanders': 'NYI', 'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT',
                 'Philadelphia Flyers': 'PHI', 'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'S.J',
                 'St Louis Blues': 'STL', 'Tampa Bay Lightning': 'T.B', 'Toronto Maple Leafs': 'TOR',
                 'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK', 'Winnipeg Jets': 'WPG',
                 'Washington Capitals': 'WSH'}
    return nss_teams[team_name]


def nss_foward_url(game, team, LW, C, RW):
    team_name = nss_abbreviation(team)
    url = (f'https://www.naturalstattrick.com/linestats.php?season={game.season}'
           f'&stype={game.game_id_gametype_id}&sit=5v5&score=all&rate=n&team={team_name}'
           f'&view=log&loc=B&gpfilt=none&fd={game.game_date_local}&td={game.game_date_local}'
           f'&tgp=82&strict=incl&p1={LW}&p2={C}&p3={RW}&p4=0&p5=0')
    return url


def nss_defense_url(game, team, LD, RD):
    team_name = nss_abbreviation(team)
    url = (f'https://www.naturalstattrick.com/linestats.php?season={game.season}'
           f'&stype={game.game_id_gametype_id}&sit=5v5&score=all&rate=n&team={team_name}'
           f'&view=log&loc=B&gpfilt=none&fd={game.game_date_local}&td={game.game_date_local}'
           f'&tgp=82&strict=incl&p1={LD}&p2={RD}&p3=0&p4=0&p5=0')
    return url


def get_nss_stat(array, index):
    try:
        return float(array[index].text)
    except ValueError:
        return 'N/A'


def nss_linetool(game, team):
    logging.info("Running NSS Line Tool - advanced stats.")
    # Setup a Dictionary to Return
    return_dict_strings = {}
    return_dict_attrs = {}

    # Get the team roster & lines dictionaries
    roster_dict = team.roster_dict_by_name

    if bool(team.lines) is False:
        logging.info('Somehow the lines dictionary is empty - rebuild it.')
        nhl_game_events.fantasy_lab_lines(game, team)
    lines = team.lines

    # Get Team Totals (NSS Opposition Tool gets game log)
    logging.info('Getting team totals via the NSS Game Log.')
    gamelog_soup = team.nss_gamelog
    overviewlb = gamelog_soup.find("label", {"id": "overviewlb"})
    overview = overviewlb.parent.find("div", class_="t5v5 datadiv")
    team_stats = overview.find("tbody").find_all("tr")
    if team.short_name in team_stats[0].find_all("td")[0].text:
        pref_team_stats = team_stats[0].find_all("td")
    else:
        pref_team_stats = team_stats[1].find_all("td")

    pref_team_toi = list(filter(None, pref_team_stats[2].text.split("\n")))[-1]
    pref_team_cf = list(filter(None, pref_team_stats[5].text.split("\n")))[-1]
    pref_team_scf = list(filter(None, pref_team_stats[14].text.split("\n")))[-1]
    pref_team_hdcf = list(filter(None, pref_team_stats[17].text.split("\n")))[-1]
    pref_team_gf = list(filter(None, pref_team_stats[20].text.split("\n")))[-1]
    return_dict_attrs['team'] = {}
    return_dict_attrs['team']['CF'] = pref_team_cf
    return_dict_attrs['team']['SCF'] = pref_team_scf
    return_dict_attrs['team']['HDCF'] = pref_team_hdcf
    return_dict_attrs['team']['GF'] = pref_team_gf
    return_dict_attrs['team']['TOI'] = pref_team_toi


    # Loop through the forwards lines
    for i in range(1, 5):
        CENTER = lines.get(str(i) + 'C', 'N/A')
        LW = lines.get(str(i) + 'LW', 'N/A')
        RW = lines.get(str(i) + 'RW', 'N/A')
        CENTER_ID = roster_dict.get(CENTER).get('id')
        LW_ID = roster_dict.get(LW).get('id')
        RW_ID = roster_dict.get(RW).get('id')
        nss_url = nss_foward_url(game, team, LW_ID, CENTER_ID, RW_ID)
        logging.info("NSS Line Tool URL (Line #%s) - %s", i, nss_url)

        stats = requests.get(nss_url)
        soup = BeautifulSoup(stats.content, 'lxml')
        games = soup.find("table", {"id": "players"}).find("tbody").find_all("tr")
        last_game = games[-1]
        game_info = last_game.find("td").text

        if game.game_date_local not in game_info:
            logging.warning("Line tool not yet updated - return Fals & check again shortly.")
            return False

        last_game_stats = last_game.find_all("td")
        TOI = float(last_game_stats[1].text)
        TOI_MM = int(TOI)
        TOI_SS = (TOI * 60) % 60
        TOI_MMSS = "%02d:%02d" % (TOI_MM, TOI_SS)
        CF_PERCENT = get_nss_stat(last_game_stats, 4)
        GF_PERCENT = get_nss_stat(last_game_stats, 13)
        SCF_PERCENT = get_nss_stat(last_game_stats, 16)
        HDCF_PERCENT = get_nss_stat(last_game_stats, 19)

        line_key = f'F{str(i)}'
        line_players = f'{LW} - {CENTER} - {RW}'
        line_stats = (f'CF%: {CF_PERCENT} | SCF%: {SCF_PERCENT} | GF%: {GF_PERCENT} | '
                      f'HDCF%: {HDCF_PERCENT} | TOI: {TOI_MMSS}')
        line_full = f'{line_players}\n{line_stats}'

        # Set the Attribute Split return dictionary
        lw_lastname = LW.split()[1]
        center_lastname = CENTER.split()[1]
        rw_lastname = RW.split()[1]
        line_players_lastname = f'{lw_lastname} - {center_lastname} - {rw_lastname}'
        return_dict_attrs[line_key] = {}
        return_dict_attrs[line_key]['name'] = line_players_lastname
        return_dict_attrs[line_key]['CF'] = CF_PERCENT
        return_dict_attrs[line_key]['GF'] = GF_PERCENT
        return_dict_attrs[line_key]['SCF'] = SCF_PERCENT
        return_dict_attrs[line_key]['HDCF'] = HDCF_PERCENT
        return_dict_attrs[line_key]['TOI'] = TOI_MMSS

        return_dict_strings[line_key] = line_full
        logging.debug(line_full)

    # Loop through defense pairings
    for i in range(1, 4):
        LD = lines.get(str(i) + 'LD', 'N/A')
        RD = lines.get(str(i) + 'RD', 'N/A')
        LD_ID = roster_dict.get(LD).get('id')
        RD_ID = roster_dict.get(RD).get('id')
        nss_url = nss_defense_url(game, team, LD_ID, RD_ID)
        logging.info("NSS Line Tool URL (Pairing #%s) - %s", i, nss_url)

        stats = requests.get(nss_url)
        soup = BeautifulSoup(stats.content, 'lxml')
        games = soup.find("table", {"id": "players"}).find("tbody").find_all("tr")
        last_game = games[-1]

        last_game_stats = last_game.find_all("td")
        TOI = float(last_game_stats[1].text)
        TOI_MM = int(TOI)
        TOI_SS = (TOI * 60) % 60
        TOI_MMSS = "%02d:%02d" % (TOI_MM, TOI_SS)
        CF_PERCENT = get_nss_stat(last_game_stats, 4)
        GF_PERCENT = get_nss_stat(last_game_stats, 13)
        SCF_PERCENT = get_nss_stat(last_game_stats, 16)
        HDCF_PERCENT = get_nss_stat(last_game_stats, 19)

        line_key = f'D{str(i)}'
        line_players = f'{LD} - {RD}'
        line_stats = (f'CF%: {CF_PERCENT} | SCF%: {SCF_PERCENT} | GF%: {GF_PERCENT} | '
                      f'HDCF%: {HDCF_PERCENT} | TOI: {TOI_MMSS}')
        line_full = f'{line_players}\n{line_stats}'

        # Set the Attribute Split return dictionary
        ld_lastname = LD.split()[1]
        rd_lastname = RD.split()[1]
        line_players_lastname = f'{ld_lastname} - {rd_lastname}'
        return_dict_attrs[line_key] = {}
        return_dict_attrs[line_key]['name'] = line_players_lastname
        return_dict_attrs[line_key]['CF'] = CF_PERCENT
        return_dict_attrs[line_key]['GF'] = GF_PERCENT
        return_dict_attrs[line_key]['SCF'] = SCF_PERCENT
        return_dict_attrs[line_key]['HDCF'] = HDCF_PERCENT
        return_dict_attrs[line_key]['TOI'] = TOI_MMSS

        return_dict_strings[line_key] = line_full
        logging.debug(line_full)

    logging.debug('NSS Line Tool Return Dictionary: %s', return_dict_strings)
    return return_dict_strings, return_dict_attrs


def nss_opposition(game, team):
    stats_url = (f'https://www.naturalstattrick.com/game.php?season={game.season}'
                 f'&game={game.game_id_gametype_shortid}{game.game_id_shortid}')
    logging.info(f'Running NSS Opposition Tool via URL - {stats_url}')

    # Wrap this in a retry / timeout loop (just in case)
    nss_session = requests.Session()
    nss_http_adapter = requests.adapters.HTTPAdapter(max_retries=3)
    nss_https_adapter = requests.adapters.HTTPAdapter(max_retries=3)
    nss_session.mount('http://', nss_http_adapter)
    nss_session.mount('https://', nss_https_adapter)
    try:
        stats = nss_session.get(stats_url, timeout=5)
    except requests.exceptions.RequestException as e:
        logging.error('NSS Request Exception: %s', e)
        return False

    # Parse the response via BeautifulSoup
    logging.info(f'Souping the NSS Opposition Content.')
    soup = BeautifulSoup(stats.content, 'lxml')
    logging.info('Storing the Game Log Soup in the Team Object (for possible later use).')
    team.nss_gamelog = soup

    search_string = f'{team.short_name} - Opposition'
    wyoplb = soup.find(text=search_string)
    opposition = wyoplb.parent.parent
    opposition5v5 = opposition.find("div", class_="t5v5").find_all("div", class_="datadiv")

    # Get the team roster & lines dictionaries
    roster_dict = team.roster_dict_by_number
    if bool(team.lines) is False:
        logging.info('Somehow the lines dictionary is empty - rebuild it.')
        nhl_game_events.fantasy_lab_lines(game, team)
    lines = team.lines

    # Loop through each preferred player & their opposition
    opposition_dict = {}
    for player in opposition5v5:
        teamnumber = player['class'][0]
        number = re.sub('[A-Za-z]', '', teamnumber)
        pref_player_name = roster_dict.get(number).get('name')
        opps = player.find("tbody").find_all("tr")

        highestopp_forward_toi = 0
        highestopp_forward_name = ""
        highestopp_defense_toi = 0
        highestopp_defense_name = ""

        for opp in opps:
            stats = opp.find_all("td")
            name = stats[0].text.replace('\xa0',' ')
            position = stats[1].text
            TOI = float(stats[2].text)
            if position in ('L', 'R', 'C'):
                if TOI > highestopp_forward_toi:
                    highestopp_forward_toi = TOI
                    highestopp_forward_name = name
            elif position == 'D':
                if TOI > highestopp_defense_toi:
                    highestopp_defense_toi = TOI
                    highestopp_defense_name = name
            opposition_dict[pref_player_name] = {}
            opposition_dict[pref_player_name]['FWDNAME'] = highestopp_forward_name
            opposition_dict[pref_player_name]['FWDTOI'] = highestopp_forward_toi
            opposition_dict[pref_player_name]['DEFNAME'] = highestopp_defense_name
            opposition_dict[pref_player_name]['DEFTOI'] = highestopp_defense_toi

    opposition_dict_byline = {}
    # Loop through forward lines & get highest TOI opponent
    for i in range(1, 5):
        CENTER = lines.get(str(i) + 'C', 'N/A')
        LW = lines.get(str(i) + 'LW', 'N/A')
        RW = lines.get(str(i) + 'RW', 'N/A')

        line_key = f'F{str(i)}'
        opposition_dict_byline[line_key] = {}
        opposition_dict_byline[line_key]['line'] = f'{LW} - {CENTER} - {RW}'
        opposition_dict_byline[line_key]['FWD'] = []
        opposition_dict_byline[line_key]['DEF'] = []
        opposition_dict_byline[line_key]['FWD'].append(opposition_dict.get(CENTER).get('FWDNAME'))
        opposition_dict_byline[line_key]['DEF'].append(opposition_dict.get(CENTER).get('DEFNAME'))

        if opposition_dict.get(LW).get('FWDNAME') not in opposition_dict_byline[line_key]['FWD']:
            opposition_dict_byline[line_key]['FWD'].append(opposition_dict.get(LW).get('FWDNAME'))
        if opposition_dict.get(LW).get('DEFNAME') not in opposition_dict_byline[line_key]['DEF']:
            opposition_dict_byline[line_key]['DEF'].append(opposition_dict.get(LW).get('DEFNAME'))

        if opposition_dict.get(RW).get('FWDNAME') not in opposition_dict_byline[line_key]['FWD']:
            opposition_dict_byline[line_key]['FWD'].append(opposition_dict.get(RW).get('FWDNAME'))
        if opposition_dict.get(RW).get('DEFNAME') not in opposition_dict_byline[line_key]['DEF']:
            opposition_dict_byline[line_key]['DEF'].append(opposition_dict.get(RW).get('DEFNAME'))

    # Loop through defense pairings & get highest TOI opponent
    for i in range(1, 4):
        LD = lines.get(str(i) + 'LD', 'N/A')
        RD = lines.get(str(i) + 'RD', 'N/A')
        line_key = f'D{str(i)}'

        opposition_dict_byline[line_key] = {}
        opposition_dict_byline[line_key]['line'] = f'{LD} - {RD}'
        opposition_dict_byline[line_key]['FWD'] = []
        opposition_dict_byline[line_key]['DEF'] = []
        opposition_dict_byline[line_key]['FWD'].append(opposition_dict.get(LD).get('FWDNAME'))
        opposition_dict_byline[line_key]['DEF'].append(opposition_dict.get(LD).get('DEFNAME'))

        if opposition_dict.get(RD).get('FWDNAME') not in opposition_dict_byline[line_key]['FWD']:
            opposition_dict_byline[line_key]['FWD'].append(opposition_dict.get(RD).get('FWDNAME'))
        if opposition_dict.get(RD).get('DEFNAME') not in opposition_dict_byline[line_key]['DEF']:
            opposition_dict_byline[line_key]['DEF'].append(opposition_dict.get(RD).get('DEFNAME'))

    logging.debug('NSS Opposition Return Dictionary: %s', opposition_dict)
    logging.debug('NSS Opposition Return Dictionary (by line): %s', opposition_dict_byline)
    return (opposition_dict, opposition_dict_byline)
