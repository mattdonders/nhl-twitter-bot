"""This module contains objects created for parsing the NHL API,
tracking game events and tweeting relevant attributes."""

# pylint: disable=too-few-public-methods

import datetime
import dateutil.tz
import requests
from bs4 import BeautifulSoup
import logging

log = logging.getLogger('root')

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
                 home, away, preferred, live_feed):

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
        self.req_session = None
        self.assists_check = 0
        self.shootout = Shootout()
        self.period = Period()

        # Initialize Final Tweets dictionary
        self.finaltweets = {"finalscore": False, "stars": False}

    # Commands used to calculate time related attributes
    localtz = dateutil.tz.tzlocal()
    localoffset = localtz.utcoffset(datetime.datetime.now(localtz))

    @property
    def game_time_local(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.datetime.strptime(
            self.date_time, '%Y-%m-%dT%H:%M:%SZ')
        game_date_local = game_date + self.localoffset
        game_date_local_ampm = game_date_local.strftime('%I:%M %p')
        return game_date_local_ampm

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

    def __init__(self, team_id, team_name, short_name, tri_code, home_away, tv_channel, games, record):
        self.team_id = team_id
        self.team_name = team_name
        self.short_name = short_name
        self.tri_code = tri_code
        self.home_away = home_away
        self.tv_channel = tv_channel
        self.games = games
        self.record = record

        # Not passed in at object creation time
        self.team_hashtag = team_hashtag(self.team_name)
        self.skaters = 5
        self.score = 0
        self.shots = 0
        self.power_play = False
        self._goalie_pulled = False
        self.preferred = False
        self.goals = []

        # Break-up the record into wins, losses, ot
        self.wins = record["wins"]
        self.losses = record["losses"]
        self.ot = record["ot"]

        # Send request to get stats
        stats_url = "https://statsapi.web.nhl.com/api/v1/teams/{}/stats".format(self.team_id)
        logging.info("Getting team stats for %s via URL - %s", self.short_name, stats_url)
        stats = requests.get(stats_url).json()
        stats = stats["stats"]
        self.team_stats = stats[0]["splits"][0]["stat"]
        self.rank_stats = stats[1]["splits"][0]["stat"]

        # Send request to get current roster
        roster_url = "https://statsapi.web.nhl.com/api/v1/teams/{}/roster".format(self.team_id)
        logging.info("Getting roster for %s via URL - %s", self.short_name, roster_url)
        roster = requests.get(roster_url).json()
        self.roster = roster["roster"]

        # If DEBUG, print all objects
        logging.debug('#' * 80)
        logging.debug("%s - Team Attributes", self.short_name)
        for k, v in vars(self).items():
            logging.debug("%s: %s", k, v)
        logging.debug('#' * 80)


    def get_new_record(self, outcome):
        """Takes a game outcome and returns the team's udpated record."""
        if outcome == "win":
            self.wins += 1
        elif outcome == "loss":
            self.losses += 1
        elif outcome == "ot":
            self.ot += 1

        new_record = "({} - {} - {})".format(self.wins, self.losses, self.ot)
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

        season_series_str = ("{} season series against the {}: {} - {} - {}."
                             .format(pref_team.short_name, other_team.short_name, pref_record["wins"],
                                     pref_record["losses"], pref_record["ot"]))

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
            toi_leader_str = ("{} leads the {} in TOI against the {} with {} / game."
                            .format(player_name, pref_team.short_name, other_team.short_name, toi_avg))

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
            points_leader_str = ("{} currently leads the {} in points against the {} with {} ({}G, {}A)."
                                 .format(player_name, pref_team.short_name, other_team.short_name,
                                         leader_points, player_goals, player_assists))
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
        points_leader_str = ("{} lead the {} in points against the {} with {} each."
                             .format(point_leaders_joined, pref_team.short_name,
                                     other_team.short_name, leader_points))

    return season_series_str, points_leader_str, toi_leader_str

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


def dailyfaceoff_goalies(pref_team, other_team, pref_homeaway):
    """Scrapes Daily Faceoff for starting goalies for the night.

    Args:
        pref_team (str): Preferred team name.
        other_team (str): Other team name.
        pref_homeaway (str): Is preferred team home or away?

    Returns:
        Tuple: preferred goalie text, other goalie text
    """
    url = 'https://www.dailyfaceoff.com/starting-goalies/'
    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'lxml')

    games = soup.find_all("div", class_="starting-goalies-card stat-card")
    for game in games:
        teams = game.find("h4", class_="top-heading-heavy")
        teams = teams.text
        if pref_team in teams:
            goalies = game.find("div", class_="stat-card-main-contents")

            away_goalie_info = goalies.find("div", class_="away-goalie")
            away_goalie_name = away_goalie_info.find("h4")
            away_goalie_confirm = away_goalie_info.find("h5", class_="news-strength")
            away_goalie_confirm = str(away_goalie_confirm.text.strip())

            away_goalie_stats = away_goalie_info.find("p", class_="goalie-record")
            away_goalie_stats_str = away_goalie_stats.text.strip()
            away_goalie_stats_str = " ".join(away_goalie_stats_str.split())
            away_goalie_str = "{} ({})\n{}".format(away_goalie_name.text.strip(),
                                                  away_goalie_confirm, away_goalie_stats_str)

            home_goalie_info = goalies.find("div", class_="home-goalie")
            home_goalie_name = home_goalie_info.find("h4")
            home_goalie_confirm = home_goalie_info.find("h5", class_="news-strength")
            home_goalie_confirm = str(home_goalie_confirm.text.strip())

            home_goalie_stats = home_goalie_info.find("p", class_="goalie-record")
            home_goalie_stats_str = home_goalie_stats.text.strip()
            home_goalie_stats_str = " ".join(home_goalie_stats_str.split())
            home_goalie_str = "{} ({})\n{}".format(home_goalie_name.text.strip(),
                                                   home_goalie_confirm, home_goalie_stats_str)

            if pref_homeaway == "home":
                pref_goalie_str = home_goalie_str
                other_goalie_str = away_goalie_str
            else:
                pref_goalie_str = away_goalie_str
                other_goalie_str = home_goalie_str

            return pref_goalie_str, other_goalie_str


def team_hashtag(team):
    """Accepts a team name and returns the corresponding team hashtag."""

    team_hashtags = {
        "Anaheim Ducks": "#LetsGoDucks",
        "Arizona Coyotes": "#Yotes",
        "Boston Bruins": "#NHLBruins",
        "Buffalo Sabres": "#Sabres",
        "Calgary Flames": "#CofRed",
        "Carolina Hurricanes": "#Redvolution",
        "Chicago Blackhawks": "#Blackhawks",
        "Colorado Avalanche": "#GoAvsGo",
        "Columbus Blue Jackets": "#CBJ",
        "Dallas Stars": "#GoStars",
        "Detroit Red Wings": "#LGRW",
        "Edmonton Oilers": "#LetsGoOilers",
        "Florida Panthers": "#FlaPanthers",
        "Los Angeles Kings": "#GoKingsGo",
        "Minnesota Wild": "#mnwild",
        "Montreal Canadiens": "#GoHabsGo",
        "Nashville Predators": "#Preds",
        "New Jersey Devils": "#NJDevils",
        "New York Islanders": "#Isles",
        "New York Rangers": "#NYR",
        "Ottawa Senators": "#Sens",
        "Philadelphia Flyers": "#LetsGoFlyers",
        "Pittsburgh Penguins": "#LetsGoPens",
        "San Jose Sharks": "#SJSharks",
        "St. Louis Blues": "#AllTogetherNowSTL",
        "Tampa Bay Lightning": "#GoBolts",
        "Toronto Maple Leafs": "#TMLtalk",
        "Vancouver Canucks": "#Canucks",
        "Vegas Golden Knights": "#VegasGoesGold",
        "Washington Capitals": "#ALLCAPS",
        "Winnipeg Jets": "#GoJetsGo"
    }

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
