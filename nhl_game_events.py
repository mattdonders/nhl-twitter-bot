"""This module contains objects created for parsing the NHL API,
tracking game events and tweeting relevant attributes."""

# pylint: disable=too-few-public-methods

import configparser
import datetime
import logging
import os

import dateutil.tz
import requests
from bs4 import BeautifulSoup

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
# Classes & Objects
# ------------------------------------------------------------------------------

class Game(object):
    """Holds all game related attributes - usually one instance created per game."""

    # pylint: disable=too-many-instance-attributes
    # pyline: disable-msg=too-many-locals
    # A Game has a lot of attributes that cannot be subclassed.

    def __init__(self, game_id, game_type, date_time, game_state, venue,
                 home, away, preferred, live_feed, season):

        # pylint: disable-msg=too-many-arguments
        # pylint: disable-msg=too-many-locals

        self.game_id = game_id
        self.game_type = game_type
        self.date_time = date_time
        self.game_state = game_state
        self.venue = venue
        self._live_feed = live_feed
        self.home_team = home
        self.away_team = away
        self.season = season

        # Not passed in at object creation time
        if preferred == "home":
            self.preferred_team = home
            self.other_team = away
        else:
            self.preferred_team = away
            self.other_team = home

        self.past_start_time = False
        self.last_event_idx = 0
        self.power_play_strength = "Even"
        self.penalty_killed_flag = False
        self.req_session = None
        self.assists_check = 0
        self.shootout = Shootout()
        self.period = Period()

        # Initialize Pregame Tweets dictionary
        self.pregame_lasttweet = None
        self.pregametweets = {"lineups": False, "refs": False,
                              "goalies_pref": False, "goalies_other": False}

        # Initialize Final Tweets dictionary
        self.finaltweets = {"finalscore": False, "stars": False,
                            "opposition": False, "advstats": False}

        # Parse Game ID to get attributes
        game_id_string = str(self.game_id)
        self.game_id_season = game_id_string[0:4]
        self.game_id_gametype_id = game_id_string[4:6]
        self.game_id_gametype_shortid = game_id_string[5:6]
        self.game_id_shortid = game_id_string[6:]

        if self.game_id_gametype_id == "01":
            self.game_id_gametype = "Preseason"
        elif self.game_id_gametype_id == "02":
            self.game_id_gametype = "Regular"
        elif self.game_id_gametype_id == "03":
            self.game_id_gametype = "Playoff"
            self.game_id_playoff_round = self.game_id_shortid[1]
            self.game_id_playoff_matchup = self.game_id_shortid[2]
            self.game_id_playoff_game = self.game_id_shortid[3]
        elif self.game_id_gametype_id == "04":
            self.game_id_gametype = "All-Star"
        else:
            self.game_id_gametype = "Unknown"


    # Commands used to calculate time related attributes
    localtz = dateutil.tz.tzlocal()
    localoffset = localtz.utcoffset(datetime.datetime.now(localtz))

    @property
    def day_of_game_local(self):
        """Returns the day of date_time in local server time."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_day_local = game_date_local.strftime('%A')
        return game_day_local

    @property
    def month_day_local(self):
        """Returns the month & date of date_time in local server time."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_abbr_month = game_date_local.strftime('%b %d').lstrip("0")
        return game_abbr_month

    @property
    def game_time_local(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_date_local_ampm = game_date_local.strftime('%I:%M %p')
        return game_date_local_ampm

    @property
    def game_date_local(self):
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_date_local_api = game_date_local.strftime('%Y-%m-%d')
        return game_date_local_api

    @property
    def game_date_short(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_date_local_short = game_date_local.strftime('%b %d').replace(' 0', ' ').upper()
        return game_date_local_short

    @property
    def game_time_of_day(self):
        """Returns the time of the day of the game (later today or tonight)."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_date_hour = game_date_local.strftime('%H')
        return "tonight" if int(game_date_hour) > 17 else "later today"

    @property
    def game_time_countdown(self):
        """Returns a countdown (in seconds) to the game start time."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        countdown = (game_date_local - datetime.datetime.now()).total_seconds()
        # value_when_true if condition else value_when_false
        return 0 if countdown < 0 else countdown

    @property
    def live_feed(self):
        """Returns a full URL to the livefeed API endpoint."""
        base_url = 'http://statsapi.web.nhl.com'
        full_url = '{}{}'.format(base_url, self._live_feed)
        return full_url

    @property
    def game_hashtag(self):
        """Returns the game specific hashtag (usually #AWAYvsHOME tri-codes)."""
        hashtag = "#{}vs{}".format(
            self.away_team.tri_code, self.home_team.tri_code)
        return hashtag


    def get_preferred_team(self):
        """Returns a Tuple of team objects of the preferred & other teams."""
        if self.home_team.preferred is True:
            return (self.home_team, self.away_team)

        return (self.away_team, self.home_team)


class Period(object):
    """Holds attributes related to the current period & time remaining."""

    def __init__(self):
        self.current = 1
        self.current_ordinal = "1st"
        self.time_remaining = "20:00"
        self.intermission = False


class Team(object):
    """Holds attributes related to a team - usually two created per game."""

    def __init__(self, team_id, team_name, short_name, tri_code, home_away, tv_channel, games, record, season):
        self.team_id = team_id
        self.team_name = team_name
        self.short_name = short_name
        self.tri_code = tri_code
        self.home_away = home_away
        self.tv_channel = tv_channel
        self.games = games
        self.record = record
        self.season = season

        # Not passed in at object creation time
        # self.team_hashtag = team_hashtag(self.team_name)
        self.skaters = 5
        self.score = 0
        self.shots = 0
        self.power_play = False
        self._goalie_pulled = False
        self.preferred = False
        self.goals = []
        self.lines = {}
        self.nss_gamelog = None

        # Break-up the record into wins, losses, ot
        self.wins = record["wins"]
        self.losses = record["losses"]
        try:
            self.ot = record["ot"]
        except KeyError:
            self.ot = None

        # Calculate Points
        self.points = (2 * self.wins) + self.ot


        # Send request for leading / trailing stats (via other API)
        try:
            lead_trail_stats_url = ("{}?isAggregate=false"
                                    "&reportType=basic&isGame=false&reportName=leadingtrailing"
                                    "&cayenneExp=seasonId={}%20and%20teamId={}"
                                    .format(NHLRPT_BASEURL, self.season, self.team_id))
            logging.info("Getting leading / trailing stats for %s via URL - %s", self.short_name, lead_trail_stats_url)
            lead_trail_stats = requests.get(lead_trail_stats_url).json()
            lead_trail_stats = lead_trail_stats['data'][0]
            self.lead_trail_lead1P = ("{}-{}-{}"
                                    .format(lead_trail_stats["winsAfterLead1p"],
                                            lead_trail_stats["lossAfterLead1p"],
                                            lead_trail_stats["otLossAfterLead1p"]))
            self.lead_trail_lead2P = ("{}-{}-{}"
                                    .format(lead_trail_stats["winsAfterLead2p"],
                                            lead_trail_stats["lossAfterLead2p"],
                                            lead_trail_stats["otLossAfterLead2p"]))
            self.lead_trail_trail1P = ("{}-{}-{}"
                                    .format(lead_trail_stats["winsAfterTrail1p"],
                                            lead_trail_stats["lossAfterTrail1p"],
                                            lead_trail_stats["otLossAfterTrail1p"]))
            self.lead_trail_trail2P = ("{}-{}-{}"
                                    .format(lead_trail_stats["winsAfterTrail2p"],
                                            lead_trail_stats["lossAfterTrail2p"],
                                            lead_trail_stats["otLossAfterTrail2p"]))
        except (IndexError, KeyError) as e:
            # Stats not available (for this team or page timeout)
            logging.warning("Error getting Lead / Trail Stats - %s", e)
            self.lead_trail_lead1P = "N/A-N/A-N/A"
            self.lead_trail_lead2P = "N/A-N/A-N/A"
            self.lead_trail_trail1P = "N/A-N/A-N/A"
            self.lead_trail_trail2P = "N/A-N/A-N/A"

        # Send request to get stats
        try:
            stats_url = "https://statsapi.web.nhl.com/api/v1/teams/{}/stats".format(self.team_id)
            logging.info("Getting team stats for %s via URL - %s", self.short_name, stats_url)
            stats = requests.get(stats_url).json()
            stats = stats["stats"]
            self.team_stats = stats[0]["splits"][0]["stat"]
            self.rank_stats = stats[1]["splits"][0]["stat"]
        except (IndexError, KeyError) as e:
            logging.warning("Error getting team stats - %s", e)
            self.team_stats = "N/A"
            self.rank_stats = "N/A"

        # Send request to get current roster
        try:
            roster_url = "https://statsapi.web.nhl.com/api/v1/teams/{}/roster".format(self.team_id)
            logging.info("Getting roster for %s via URL - %s", self.short_name, roster_url)
            roster = requests.get(roster_url).json()
            self.roster = roster["roster"]
        except (IndexError, KeyError) as e:
            logging.warning("Error getting team roster - %s", e)
            self.roster = "N/A"

        # If DEBUG, print all objects
        logging.debug('#' * 80)
        logging.debug("%s - Team Attributes", self.short_name)
        for k, v in vars(self).items():
            logging.debug("%s: %s", k, v)
        logging.debug('#' * 80)


    @property
    def current_record(self):
        return f"{self.wins}-{self.losses}-{self.ot}"


    def get_new_points(self, outcome):
        """Takes a game outcome and returns the team's udpated points."""
        current_points = self.points
        if outcome == "win":
            current_points += 2
        elif outcome == "loss":
            current_points += 0
        elif outcome == "ot":
            current_points += 1

        return current_points


    def get_new_record(self, outcome):
        """Takes a game outcome and returns the team's udpated record."""
        logging.debug("%s Current Record - %s", self.short_name, self.current_record)
        logging.debug("Outcome - %s", outcome)
        if outcome == "win":
            self.wins += 1
        elif outcome == "loss":
            self.losses += 1
        elif outcome == "ot":
            self.ot += 1

        new_record = "{} - {} - {}".format(self.wins, self.losses, self.ot)
        logging.debug("New Record - %s", new_record)
        return new_record


    def get_new_playoff_series(self, outcome):
        """Takes a game outcome and returns the team's udpated record."""
        if outcome == "win":
            self.wins += 1
        elif outcome == "loss":
            self.losses += 1
        new_record = "({} - {})".format(self.wins, self.losses)
        return new_record


    def get_stat_and_rank(self, attr):
        """Returns a teams statistic and rank in the NHL.

        Args:
            attr (str): Stat to retrieve (gamesPlayed, wins, losses, ot, pts, ptPctg, goalsPerGame,
                        goalsAgainstPerGame, evGGARatio, powerPlayPercentage, powerPlayGoals,
                        powerPlayGoalsAgainst, powerPlayOpportunities, penaltyKillPercentage,
                        shotsPerGame, shotsAllowed, winScoreFirst, winOppScoreFirst, winLeadFirstPer,
                        winLeadSecondPer, winOutshootOpp, winOutshotByOpp, faceOffsTaken, faceOffsWon,
                        faceOffsLost, faceOffWinPercentage, shootingPctg, savePctg)

        Returns:
            tuple: 0 - Stat, 1 - NHL Rank
        """
        stat = self.team_stats[attr]
        rank = self.rank_stats[attr]
        return stat, rank


    @property
    def roster_dict_by_name(self):
        roster_dict = {}
        for player in self.roster:
            person = player.get('person')
            id = person.get('id')
            name = person.get('fullName')
            number = player.get('jerseyNumber')
            roster_dict[name] = {}
            roster_dict[name]['id'] = id
            roster_dict[name]['jerseyNumber'] = number
        return roster_dict

    @property
    def roster_dict_by_number(self):
        roster_dict = {}
        for player in self.roster:
            person = player.get('person')
            id = person.get('id')
            name = person.get('fullName')
            number = player.get('jerseyNumber')
            roster_dict[number] = {}
            roster_dict[number]['id'] = id
            roster_dict[number]['name'] = name
        return roster_dict


    @property
    def goalie_pulled(self):
        """Returns the goalie_pulled attribute of a team."""
        return self._goalie_pulled


    @goalie_pulled.setter
    def goalie_pulled(self, new_value):
        """Allows the goalie_pulled attribute to be set externally and checks for changes."""
        old_value = self.goalie_pulled
        self._goalie_pulled = new_value
        return bool(new_value is True and old_value is False)


    def goalie_pulled_setter(self, new_value):
        """Allows the goalie_pulled attribute to be set externally and checks for changes."""
        old_value = self.goalie_pulled
        self._goalie_pulled = new_value
        return bool(new_value is True and old_value is False)


class GameEvent(object):
    """Attributes related to a single event. Abstract class - never create instance."""

    # pylint: disable=too-many-instance-attributes
    # A GameEvent is an abstract class to avoid code replication.

    def __init__(self, event_type, description, idx, period, period_type,
                 period_ordinal, period_remaining, score_home, score_away):
        self.event_type = event_type
        self.description = description
        self.idx = idx
        self.period = period
        self.period_type = period_type
        self.period_ordinal = period_ordinal
        self.period_remaining = period_remaining
        self.score_home = score_home
        self.score_away = score_away


class Goal(GameEvent):
    """Attributes related to a goal (subclass of GameEvent)."""

    def __init__(self, description, idx, period, period_type, period_ordinal,
                 period_remaining, score_home, score_away, team, secondary_type,
                 strength, empty_net, scorer, assists, tweet):

        # pylint: disable-msg=too-many-locals
        # Parent class GameEvent has many variables.

        GameEvent.__init__(self, "Goal", description, idx, period, period_type,
                           period_ordinal, period_remaining, score_home, score_away)
        self.team = team
        self.secondary_type = secondary_type
        self.strength = strength
        self.empty_net = empty_net
        self.scorer = scorer
        self.assists = assists
        self.tweet = tweet


class Shootout(object):
    """Attributes to track a shootout."""

    def __init__(self):
        self.preferred_score = []
        self.other_score = []
        self.shots = 0
        self.round = 1

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# NHL API Functions
# ------------------------------------------------------------------------------

def player_attr_by_id(roster, player_id, attribute):
    """[summary]

    Args:
        roster (dict): Team roster (returned from API)
        player_id (str): Player unique identifier (IDXXXXXXX)
        attribute (str): Attribute from roster dictionary.

    Returns:
        string: Attribute of the person requested.
    """
    new_player_id = player_id.replace("ID", "")
    for roster_item in roster:
        person_id = str(roster_item["person"]["id"])
        person_attr = roster_item["person"][attribute]
        if person_id == new_player_id:
            return person_attr


def nonroster_player_attr_by_id(player_id, attribute):
    api_player_url = "https://statsapi.web.nhl.com/api/v1/people/{}".format(player_id)
    api_player = requests.get(api_player_url).json()
    player_attr = api_player["people"][0][attribute]
    return player_attr


def season_series(game_id, pref_team, other_team):
    # Init empty dictionaries and lists
    games_against = list()
    pref_toi = dict()
    pref_goals = dict()
    pref_assists = dict()
    pref_points = dict()
    pref_record = {"wins": 0, "losses": 0, "ot": 0}
    roster_player = True

    season_start = str(game_id)[0:4]
    season_end = str(int(season_start) + 1)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    schedule_url = ("http://statsapi.web.nhl.com/api/v1/schedule?teamId={}"
                    "&expand=schedule.broadcasts,schedule.teams&startDate={}-08-01&endDate={:%Y-%m-%d}"
                    .format(pref_team.team_id, season_start, yesterday))

    schedule = requests.get(schedule_url).json()
    dates = schedule["dates"]

    # Loop through scheduled to get previously played games against
    for idx, date in enumerate(dates):
        game = date["games"][0]
        game_type = game["gameType"]
        game_id = game["gamePk"]
        game_date = game["gameDate"]
        game_team_home = game["teams"]["home"]["team"]["name"]
        game_team_away = game["teams"]["away"]["team"]["name"]
        teams = [game_team_away, game_team_home]
        if game_type == "R" and other_team.team_name in teams:
            game_feed = "http://statsapi.web.nhl.com/api/v1/game/{}/feed/live".format(game_id)
            games_against.append(game_feed)

    # If the two teams haven't played yet, just exit this function
    if not games_against:
        return None, None, None

    # Loop through newly created games_against list to get each stats
    for feed in games_against:
        game = requests.get(feed).json()
        game_data = game["gameData"]
        pref_homeaway = "home" if game_data["teams"]["home"]["name"] == pref_team.team_name else "away"
        other_homeaway = "away" if game_data["teams"]["home"]["name"] == pref_team.team_name else "home"

        # Get season series
        end_period = game["liveData"]["linescore"]["currentPeriod"]
        extra_time = True if end_period > 3 else False
        pref_score = game["liveData"]["linescore"]["teams"][pref_homeaway]["goals"]
        other_score = game["liveData"]["linescore"]["teams"][other_homeaway]["goals"]
        if pref_score > other_score:
            pref_record["wins"] += 1
        elif other_score > pref_score and extra_time:
            pref_record["ot"] += 1
        else:
            pref_record["losses"] +=1

        season_series_str = ("Season Series: {}-{}-{}."
                             .format(pref_record["wins"], pref_record["losses"], pref_record["ot"]))

        # Get stats leaders
        # pref_teamstats = game["liveData"]["boxscore"]["teams"][pref_homeaway]["teamStats"]
        pref_playerstats = game["liveData"]["boxscore"]["teams"][pref_homeaway]["players"]
        for id, player in pref_playerstats.items():
            try:
                # Calculate TOI
                player_toi_str = player["stats"]["skaterStats"]["timeOnIce"]
                player_toi_minutes = int(player_toi_str.split(":")[0])
                player_toi_seconds = int(player_toi_str.split(":")[1])
                player_toi = (player_toi_minutes * 60) + player_toi_seconds
                pref_toi[id] = pref_toi.get(id, 0) + player_toi

                # Point Totals
                player_goal_str = player["stats"]["skaterStats"]["goals"]
                pref_goals[id] = pref_goals.get(id, 0) + int(player_goal_str)
                player_assist_str = player["stats"]["skaterStats"]["assists"]
                pref_assists[id] = pref_assists.get(id, 0) + int(player_assist_str)
                player_points = int(player_goal_str) + int(player_assist_str)
                pref_points[id] = pref_points.get(id, 0) + int(player_points)

            except KeyError:
                pass

    # Calculate Stats Leaders
    sorted_toi = sorted(pref_toi.values(), reverse=True)
    leader_toi = sorted_toi[0]

    sorted_points = sorted(pref_points.values(), reverse=True)
    leader_points = sorted_points[0]

    # Get TOI leader
    for id in pref_toi.keys():
        if pref_toi[id] == leader_toi:
            player_name = player_attr_by_id(pref_team.roster, id, "fullName")
            if player_name is None:
                roster_player = False
                player_id_only = id.replace("ID", "")
                player_name = nonroster_player_attr_by_id(player_id_only, "fullName")
            leader_toi_avg = leader_toi / len(games_against)
            m, s = divmod(leader_toi_avg, 60)
            toi_m = int(m)
            toi_s = int(s)
            toi_s = "0{}".format(toi_s) if toi_s < 10 else toi_s
            toi_avg = "{}:{}".format(toi_m, toi_s)
            toi_leader_str = ("TOI Leader - {} with {} / game."
                            .format(player_name, toi_avg))

    # Handle tied points leaders
    point_leaders = list()
    for id in pref_points.keys():
        if pref_points[id] == leader_points:
            point_leaders.append(id)

    if len(point_leaders) == 1:
        leader = point_leaders[0]
        player_name = player_attr_by_id(pref_team.roster, leader, "fullName")
        # If the player is no longer on the team, get their information (change string here?)
        if player_name is None:
            roster_player = False
            player_id_only = leader.replace("ID", "")
            player_name = nonroster_player_attr_by_id(player_id_only, "fullName")
        player_goals = pref_goals[leader]
        player_assists = pref_assists[leader]
        if not roster_player:
            points_leader_str = ("{} lead the {} with {} points ({}G, {}A) against the {} this season."
                                 .format(player_name, pref_team.short_name, leader_points,
                                         player_goals, player_assists, other_team.short_name))
        else:
            points_leader_str = ("Points Leader - {} with {} ({}G, {}A)."
                                 .format(player_name, leader_points, player_goals, player_assists))
    else:
        point_leaders_with_attrs = list()
        for leader in point_leaders:
            player_name = player_attr_by_id(pref_team.roster, leader, "fullName")
            if player_name is None:
                player_id_only = leader.replace("ID", "")
                player_name = nonroster_player_attr_by_id(player_id_only, "fullName")
            player_goals = pref_goals[leader]
            player_assists = pref_assists[leader]
            player_str = "{} ({}G, {}A)".format(player_name, player_goals, player_assists)
            point_leaders_with_attrs.append(player_str)

        point_leaders_joined = " & ".join(point_leaders_with_attrs)
        points_leader_str = ("Points Leaders - {} with {} each."
                             .format(point_leaders_joined, leader_points))

    return season_series_str, points_leader_str, toi_leader_str


def playoff_series(game_id, pref_team, other_team):
    # Init empty dictionaries and lists
    games_against = list()
    pref_toi = dict()
    pref_goals = dict()
    pref_assists = dict()
    pref_points = dict()
    pref_record = {"wins": 0, "losses": 0, "ot": 0}
    roster_player = True

    season_start = str(game_id)[0:4]
    season_end = str(int(season_start) + 1)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    schedule_url = ("http://statsapi.web.nhl.com/api/v1/schedule?teamId={}"
                    "&expand=schedule.broadcasts,schedule.teams&startDate={}-08-01&endDate={:%Y-%m-%d}"
                    .format(pref_team.team_id, season_start, yesterday))

    schedule = requests.get(schedule_url).json()
    dates = schedule["dates"]

    # Loop through scheduled to get previously played games against
    for idx, date in enumerate(dates):
        game = date["games"][0]
        game_type = game["gameType"]
        game_id = game["gamePk"]
        game_date = game["gameDate"]
        game_team_home = game["teams"]["home"]["team"]["name"]
        game_team_away = game["teams"]["away"]["team"]["name"]
        teams = [game_team_away, game_team_home]
        if game_type == "P" and other_team.team_name in teams:
            game_feed = "http://statsapi.web.nhl.com/api/v1/game/{}/feed/live".format(game_id)
            games_against.append(game_feed)

    # If the two teams haven't played yet, just exit this function
    if not games_against:
        return None, None, None

    # Loop through newly created games_against list to get each stats
    for feed in games_against:
        game = requests.get(feed).json()
        game_data = game["gameData"]
        pref_homeaway = "home" if game_data["teams"]["home"]["name"] == pref_team.team_name else "away"
        other_homeaway = "away" if game_data["teams"]["home"]["name"] == pref_team.team_name else "home"

        # Get stats leaders
        # pref_teamstats = game["liveData"]["boxscore"]["teams"][pref_homeaway]["teamStats"]
        pref_playerstats = game["liveData"]["boxscore"]["teams"][pref_homeaway]["players"]
        for id, player in pref_playerstats.items():
            try:
                # Calculate TOI
                player_toi_str = player["stats"]["skaterStats"]["timeOnIce"]
                player_toi_minutes = int(player_toi_str.split(":")[0])
                player_toi_seconds = int(player_toi_str.split(":")[1])
                player_toi = (player_toi_minutes * 60) + player_toi_seconds
                pref_toi[id] = pref_toi.get(id, 0) + player_toi

                # Point Totals
                player_goal_str = player["stats"]["skaterStats"]["goals"]
                pref_goals[id] = pref_goals.get(id, 0) + int(player_goal_str)
                player_assist_str = player["stats"]["skaterStats"]["assists"]
                pref_assists[id] = pref_assists.get(id, 0) + int(player_assist_str)
                player_points = int(player_goal_str) + int(player_assist_str)
                pref_points[id] = pref_points.get(id, 0) + int(player_points)

            except KeyError:
                pass

    # Calculate Stats Leaders
    sorted_toi = sorted(pref_toi.values(), reverse=True)
    leader_toi = sorted_toi[0]

    sorted_points = sorted(pref_points.values(), reverse=True)
    leader_points = sorted_points[0]

    # Get TOI leader
    for id in pref_toi.keys():
        if pref_toi[id] == leader_toi:
            player_name = player_attr_by_id(pref_team.roster, id, "fullName")
            if player_name is None:
                roster_player = False
                player_id_only = id.replace("ID", "")
                player_name = nonroster_player_attr_by_id(player_id_only, "fullName")
            leader_toi_avg = leader_toi / len(games_against)
            m, s = divmod(leader_toi_avg, 60)
            toi_m = int(m)
            toi_s = int(s)
            toi_s = "0{}".format(toi_s) if toi_s < 10 else toi_s
            toi_avg = "{}:{}".format(toi_m, toi_s)
            toi_leader_str = ("TOI Leader - {} with {} / game."
                            .format(player_name, toi_avg))

    # Handle tied points leaders
    point_leaders = list()
    for id in pref_points.keys():
        if pref_points[id] == leader_points:
            point_leaders.append(id)

    if len(point_leaders) == 1:
        leader = point_leaders[0]
        player_name = player_attr_by_id(pref_team.roster, leader, "fullName")
        # If the player is no longer on the team, get their information (change string here?)
        if player_name is None:
            roster_player = False
            player_id_only = leader.replace("ID", "")
            player_name = nonroster_player_attr_by_id(player_id_only, "fullName")
        player_goals = pref_goals[leader]
        player_assists = pref_assists[leader]
        if not roster_player:
            points_leader_str = ("{} lead the {} with {} points ({}G, {}A) against the {} this season."
                                 .format(player_name, pref_team.short_name, leader_points,
                                         player_goals, player_assists, other_team.short_name))
        else:
            points_leader_str = ("Points Leader - {} with {} ({}G, {}A)."
                                 .format(player_name, leader_points, player_goals, player_assists))
    else:
        point_leaders_with_attrs = list()
        for leader in point_leaders:
            player_name = player_attr_by_id(pref_team.roster, leader, "fullName")
            if player_name is None:
                player_id_only = leader.replace("ID", "")
                player_name = nonroster_player_attr_by_id(player_id_only, "fullName")
            player_goals = pref_goals[leader]
            player_assists = pref_assists[leader]
            player_str = "{} ({}G, {}A)".format(player_name, player_goals, player_assists)
            point_leaders_with_attrs.append(player_str)

        point_leaders_joined = " & ".join(point_leaders_with_attrs)
        points_leader_str = ("Points Leaders - {} with {} each."
                             .format(point_leaders_joined, leader_points))

    return points_leader_str, toi_leader_str


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Independent functions
# ------------------------------------------------------------------------------

def preferred_teams(home_team, away_team):
    """Logic for preferred / other team objects via if statement

    Args:
        home_team (Team): The home team object.
        away_team (Team): The away team object.

    Returns:
        (preferred_team, other_team) - Tuple of Team objects
    """

    if home_team.preferred:
        # Home Team is preferred
        return (home_team, away_team)

    # Away Team is preferred
    return (away_team, home_team)


def hockey_ref_goalie_against_team(goalie, opponent):
    logging.info("HR - Goalie: %s, Opponent: %s", goalie, opponent)
    hockey_ref_url_base = 'https://www.hockey-reference.com/players'

    goalie_name_camel = goalie
    goalie_name = goalie_name_camel.lower()
    goalie_name = hockey_ref_alt_names(goalie_name)

    goalie_name_split = goalie_name.split(" ")
    goalie_first_name = goalie_name_split[0]
    goalie_last_name = goalie_name_split[1]
    goalie_hockey_ref_name = "{}{}01".format(goalie_last_name[0:5], goalie_first_name[0:2])
    hockey_ref_url = ("{}/{}/{}/splits"
                     .format(hockey_ref_url_base, goalie_last_name[0:1], goalie_hockey_ref_name))
    logging.info("HR URL - %s", hockey_ref_url)

    r = requests.get(hockey_ref_url)
    soup = BeautifulSoup(r.content, 'lxml')

    hr_player_info = soup.find("div", attrs={"itemtype":"https://schema.org/Person"})
    hr_player_info_attr = hr_player_info.find_all("p")
    hr_name = soup.find("h1", attrs={"itemprop":"name"}).text
    for attr in hr_player_info_attr:
        if "Position:" in attr.text:
            hr_position_goalie = bool("Position: G" in attr.text.rstrip())
            break

    if hr_name != goalie_name_camel or not hr_position_goalie:
        logging.warning("Wrong player retrieved from HR, trying 02.")
        goalie_hockey_ref_name = "{}{}02".format(goalie_last_name[0:5], goalie_first_name[0:2])
        hockey_ref_url = ("{}/{}/{}/splits"
                     .format(hockey_ref_url_base, goalie_last_name[0:1], goalie_hockey_ref_name))
        logging.info("HR URL - %s", hockey_ref_url)
        r = requests.get(hockey_ref_url)
        soup = BeautifulSoup(r.content, 'lxml')

    split_rows = soup.find("table", { "id" : "splits" }).find("tbody").find_all("tr")
    for row in split_rows:
        cells = row.find_all("td")
        team_row = row.find("td", attrs={"data-stat":"split_value"})
        team_name = team_row.text if team_row is not None else "None"

        if team_name == opponent:
            wins = cells[2].text
            loss = cells[3].text
            ot = cells[4].text
            sv_percent = cells[8].text
            gaa = cells[9].text
            shutout = cells[10].text

            goalie_stats_split = ("{}-{}-{} W-L | {} GAA | 0{} SV% | {} SO"
                                  .format(wins, loss, ot, gaa, sv_percent, shutout))
            return goalie_stats_split


def hockey_ref_alt_names(goalie_name):
    hockey_ref_alts = {
        "jimmy howard": "james howard"
    }

    return hockey_ref_alts.get(goalie_name, goalie_name)


def fantasy_lab_lines(game, team):
    """Use the Fantasy Labs API to get confirmed lineup.

    Args:
        game (game): An NHL Game Event game object.
        team (Team): A NHL Game Event team object.

    Returns:
        Dictionary: confirmed, forwards, defense, powerplay
    """

    # Instantiate blank return dictionary
    return_dict = {}
    return_dict['forwards'] = ""
    return_dict['defense'] = ""
    return_dict['powerplay1'] = ""
    return_dict['powerplay2'] = ""


    FANTASY_LABS_BASE_URL = 'https://www.fantasylabs.com/api/lines/4'
    lineup_date = game.game_date_local
    lineup_team = team.team_name

    logging.info("Checking Fantasy Labs for today's lineup for %s", lineup_team)
    fantasy_labs_url = f"{FANTASY_LABS_BASE_URL}/{lineup_team}/{lineup_date}"
    r = requests.get(fantasy_labs_url).json()

    # Check if lineup is confirmed (return false if not)
    confirmed = r.get('NextMatchupData')[0].get('Properties').get('LineupConfirmed', False)
    confirmed_datetime = r.get('NextMatchupData')[0].get('Properties').get('LineupConfirmedDateTime', 'N/A')
    return_dict['confirmed'] = confirmed
    return_dict['confirmed_datetime'] = confirmed_datetime
    if not confirmed:
        return return_dict

    # Create a dictionary of players and their positions
    lines_dict = {}
    players = r['PlayerLines']
    for player in players:
        properties = player['Properties']
        position = properties['Position']
        full_name = properties['FullName']
        last_name = full_name.split()[1]
        lines_dict[position] = full_name

    for i in range(1, 5):
        C = lines_dict.get(str(i) + 'C', 'N/A').split()[1]
        LW = lines_dict.get(str(i) + 'LW', 'N/A').split()[1]
        RW = lines_dict.get(str(i) + 'RW', 'N/A').split()[1]
        line = f"{LW} - {C} - {RW}\n"

        line_key = 'F' + str(i)
        return_dict[line_key] = line
        return_dict['forwards'] += line

    for i in range(1, 4):
        LD = lines_dict.get(str(i) + 'LD', 'N/A').split()[1]
        RD = lines_dict.get(str(i) + 'RD', 'N/A').split()[1]
        pairing = f"{LD} - {RD}\n"

        pair_key = 'D' + str(i)
        return_dict[pair_key] = pairing
        return_dict['defense'] += pairing

    for i in range(1, 3):
        F1 = lines_dict.get('PP' + str(i) + 'F1', 'N/A').split()[1]
        F2 = lines_dict.get('PP' + str(i) + 'F2', 'N/A').split()[1]
        F3 = lines_dict.get('PP' + str(i) + 'F3', 'N/A').split()[1]
        D1 = lines_dict.get('PP' + str(i) + 'D1', 'N/A').split()[1]
        D2 = lines_dict.get('PP' + str(i) + 'D2', 'N/A').split()[1]
        pp_line = f"{F1} - {F2} - {F3}\n{D1} - {D2}\n"
        return_dict[f'powerplay{i}'] = pp_line

    # Generate Tweet Strings
    pref_hashtag = team_hashtag(team.team_name, game.game_type)
    fwd_def_lines_tweet = (f"{pref_hashtag} Forwards:\n{return_dict.get('forwards')}\n\n"
                                f"{pref_hashtag} Defense:\n{return_dict.get('defense')}")
    power_play_lines_tweet = (f"{pref_hashtag} Power Play 1:\n{return_dict.get('powerplay1')}\n\n"
                                f"{pref_hashtag} Power Play 2:\n{return_dict.get('powerplay2')}")

    return_dict['lines'] = lines_dict
    return_dict['fwd_def_lines_tweet'] = fwd_def_lines_tweet
    return_dict['power_play_lines_tweet'] = power_play_lines_tweet

    team.lines = lines_dict
    return return_dict


def team_hashtag(team, game_type):
    """Accepts a team name and returns the corresponding team hashtag."""

    team_hashtags = {
        "Anaheim Ducks": "#LetsGoDucks",
        "Arizona Coyotes": "#OurPack",
        "Boston Bruins": "#NHLBruins",
        "Buffalo Sabres": "#Sabres",
        "Calgary Flames": "#Flames",
        "Carolina Hurricanes": "#TakeWarning",
        "Chicago Blackhawks": "#Blackhawks",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Dallas Stars": "#GoStars",
        "Detroit Red Wings": "#LGRW",
        "Edmonton Oilers": "#LetsGoOilers",
        "Florida Panthers": "#FlaPanthers",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#mnwild",
        "Montréal Canadiens": "#GoHabsGo",
        "Nashville Predators": "#Preds",
        "New Jersey Devils": "#NJDevils",
        "New York Islanders": "#Isles",
        "New York Rangers": "#NYR",
        "Ottawa Senators": "#Sens",
        "Philadelphia Flyers": "#LetsGoFlyers",
        "Pittsburgh Penguins": "#LetsGoPens",
        "San Jose Sharks": "#SJSharks",
        "St. Louis Blues": "#stlblues",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#LeafsForever",
        "Vancouver Canucks": "#Canucks",
        "Vegas Golden Knights": "#VegasBorn",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#GoJetsGo"
    }

    team_hashtags_playoffs = {
        "Anaheim Ducks": "#LetsGoDucks",
        "Boston Bruins": "#GoBruins",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#mnwild",
        "Nashville Predators": "#standwithus",
        "New Jersey Devils": "#NowWeRise",
        "Philadelphia Flyers": "#EarnTomorrow",
        "Pittsburgh Penguins": "#3elieve",
        "San Jose Sharks": "#SJSharks",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#TMLTalk",
        "Vegas Golden Knights": "#VegasBorn",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#WPGWhiteout"
    }

    if game_type == "P":
        hashtag = team_hashtags_playoffs[team]
    else:
        hashtag = team_hashtags[team]
    return hashtag


def clock_emoji(time):
    '''
    Accepts an hour (in 12 or 24 hour format) and returns the correct clock emoji.

    Input:
    time - 12 or 24 hour format time (:00 or :30)

    Output:
    clock - corresponding clock emoji.
    '''

    hour_emojis = {
        "0": "🕛",
        "1": "🕐",
        "2": "🕑",
        "3": "🕒",
        "4": "🕓",
        "5": "🕔",
        "6": "🕕",
        "7": "🕖",
        "8": "🕗",
        "9": "🕘",
        "10": "🕙",
        "11": "🕚"
    }

    half_hour_emojis = {
        "0": "🕧",
        "1": "🕜",
        "2": "🕝",
        "3": "🕞",
        "4": "🕟",
        "5": "🕠",
        "6": "🕡",
        "7": "🕢",
        "8": "🕣",
        "9": "🕤",
        "10": "🕥",
        "11": "🕦"
    }

    time_split = time.split(':')
    hour = int(time_split[0])
    minutes = time_split[1].split(' ')[0]

    if hour > 11:
        hour = 12 - hour

    if int(minutes) == 30:
        clock = half_hour_emojis[str(hour)]
    else:
        clock = hour_emojis[str(hour)]

    return clock


# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Imaging Functions
# ------------------------------------------------------------------------------

def team_colors(team):
    """Accepts a team name and returns the background color & text color."""

    team_colors_array = {
        "Anaheim Ducks": {
            "primary": {"bg": (252, 76, 2), "text": (255, 255, 255)},
            "secondary": {"bg": (162, 170, 173), "text": (0, 0, 0)}},
        "Arizona Coyotes": {
            "primary": {"bg": (134, 38, 51), "text": (255, 255, 255)},
            "secondary": {"bg": (221, 203, 164), "text": (0, 0, 0)}},
        "Boston Bruins": {
            "primary": {"bg": (255, 184, 28), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "Buffalo Sabres": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (162, 170, 173), "text": (0, 0, 0)}},
        "Calgary Flames": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (241, 190, 72), "text": (0, 0, 0)}},
        "Carolina Hurricanes": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (162, 170, 173), "text": (0, 0, 0)}},
        "Chicago Blackhawks": {
            "primary": {"bg": (204, 138, 0), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 209, 0), "text": (0, 0, 0)}},
        "Colorado Avalanche": {
            "primary": {"bg": (111, 38, 61), "text": (255, 255, 255)},
            "secondary": {"bg": (35, 97, 146), "text": (0, 0, 0)}},
        "Columbus Blue Jackets": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (0, 0, 0)}},
        "Dallas Stars": {
            "primary": {"bg": (0, 99, 65), "text": (255, 255, 255)},
            "secondary": {"bg": (138, 141, 143), "text": (0, 0, 0)}},
        "Detroit Red Wings": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "Edmonton Oilers": {
            "primary": {"bg": (207, 69, 32), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 32, 91), "text": (0, 0, 0)}},
        "Florida Panthers": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (185, 151, 91), "text": (0, 0, 0)}},
        "Los Angeles Kings": {
            "primary": {"bg": (162, 170, 173), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "Minnesota Wild": {
            "primary": {"bg": (21, 71, 52), "text": (255, 255, 255)},
            "secondary": {"bg": (166, 25, 46), "text": (0, 0, 0)}},
        "Montréal Canadiens": {
            "primary": {"bg": (166, 25, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 30, 98), "text": (0, 0, 0)}},
        "Nashville Predators": {
            "primary": {"bg": (255, 184, 28), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (0, 0, 0)}},
        "New Jersey Devils": {
            "primary": {"bg": (200, 16, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "New York Islanders": {
            "primary": {"bg": (252, 76, 2), "text": (255, 255, 255)},
            "secondary": {"bg": (0, 48, 135), "text": (0, 0, 0)}},
        "New York Rangers": {
            "primary": {"bg": (0, 51, 160), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (0, 0, 0)}},
        "Ottawa Senators": {
            "primary": {"bg": (198, 146, 20), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (0, 0, 0)}},
        "Philadelphia Flyers": {
            "primary": {"bg": (250, 70, 22), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "Pittsburgh Penguins": {
            "primary": {"bg": (255, 184, 28), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "San Jose Sharks": {
            "primary": {"bg": (0, 98, 114), "text": (255, 255, 255)},
            "secondary": {"bg": (229, 114, 0), "text": (0, 0, 0)}},
        "St. Louis Blues": {
            "primary": {"bg": (0, 48, 135), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (0, 0, 0)}},
        "Tampa Bay Lightning": {
            "primary": {"bg": (0, 32, 91), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "Toronto Maple Leafs": {
            "primary": {"bg": (0, 32, 91), "text": (255, 255, 255)},
            "secondary": {"bg": (255, 255, 255), "text": (0, 0, 0)}},
        "Vancouver Canucks": {
            "primary": {"bg": (0, 32, 91), "text": (255, 255, 255)},
            "secondary": {"bg": (151, 153, 155), "text": (0, 0, 0)}},
        "Vegas Golden Knights": {
            "primary": {"bg": (180, 151, 90), "text": (255, 255, 255)},
            "secondary": {"bg": (51, 63, 66), "text": (0, 0, 0)}},
        "Washington Capitals": {
            "primary": {"bg": (166, 25, 46), "text": (255, 255, 255)},
            "secondary": {"bg": (4, 30, 66), "text": (255, 255, 255)}},
        "Winnipeg Jets": {
            "primary": {"bg": (4, 30, 66), "text": (255, 255, 255)},
            "secondary": {"bg": (200, 16, 46), "text": (0, 0, 0)}},
    }

    return team_colors_array[team]