"""This module contains objects created for parsing the NHL API,
tracking game events and tweeting relevant attributes."""

# pylint: disable=too-few-public-methods

import datetime
import dateutil.tz

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

    def __init__(self, team_name, short_name, tri_code, home_away, tv_channel, games):
        self.team_name = team_name
        self.short_name = short_name
        self.tri_code = tri_code
        self.home_away = home_away
        self.tv_channel = tv_channel
        self.games = games

        # Not passed in at object creation time
        self.skaters = 5
        self.score = 0
        self.shots = 0
        self.power_play = False
        self._goalie_pulled = False
        self.preferred = False
        self.goals = []


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
