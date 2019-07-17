import logging
from datetime import datetime

import dateutil.tz

from hockeygamebot.helpers import utils
from hockeygamebot.models.period import Period
from hockeygamebot.models.shootout import Shootout
from hockeygamebot.models.team import Team


class Game:
    """Holds all game related attributes - usually one instance created per game."""

    # pylint: disable=too-many-instance-attributes, too-many-locals, too-many-arguments
    # pylint: disable=too-many-locals, bad-continuation

    # A Game has a lot of attributes that cannot be subclassed.

    def __init__(
        self,
        game_id,
        game_type,
        date_time,
        game_state,
        venue,
        home: Team,
        away: Team,
        preferred,
        live_feed,
        season,
    ):

        self.game_id = game_id
        self.game_type = game_type
        self.date_time = date_time
        self.game_state = game_state
        self.venue = venue
        self.live_feed_endpoint = live_feed
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

        # Attributes holding other models / objects
        self.shootout = Shootout()
        self.period = Period()
        self.events = []

        # Initialize Pregame Tweets dictionary
        self.pregame_lasttweet = None
        self.pregametweets = {
            "core": False,
            "lines": False,
            "refs": False,
            "goalies_pref": False,
            "goalies_other": False,
        }

        # Initialize Final Tweets dictionary
        self.finaltweets = {
            "finalscore": False,
            "stars": False,
            "opposition": False,
            "advstats": False,
            "shotmap": False,
        }
        self.finaltweets_retry = 0

        # Parse Game ID to get attributes
        game_id_string = str(self.game_id)
        self.game_id_season = game_id_string[0:4]
        self.game_id_gametype_id = game_id_string[4:6]
        self.game_id_gametype_shortid = game_id_string[5:6]
        self.game_id_shortid = game_id_string[6:]
        self.game_id_html = game_id_string[4:]

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

    @classmethod
    def from_json_and_teams(cls, resp, home_team, away_team):
        # The venue is not always a 'cherry-pick' from the dictionary
        try:
            venue = resp["venue"]["name"]
        except KeyError:
            venue = resp["teams"]["home"]["team"]["venue"]["name"]

        # Get the preferred team flag from the Team objects attribute
        preferred = "home" if home_team.preferred else "away"

        return Game(
            game_id=resp["gamePk"],
            season=resp["season"],
            game_type=resp["gameType"],
            date_time=resp["gameDate"],
            game_state=resp["status"]["abstractGameState"],
            live_feed=resp["link"],
            venue=venue,
            home=home_team,
            away=away_team,
            preferred=preferred,
        )

    # Instance Functions
    def update_game(self, response):
        """ Use the livefeed to update game attributes.
            Including: game state, period attributes, etc.
        """

        logging.info("Updating all Game object attributes.")
        linescore = response.get("liveData").get("linescore")

        # Update Game State & Period related attributes
        self.game_state = response.get("gameData").get("status").get("abstractGameState")
        self.period.current = linescore["currentPeriod"]
        self.period.current_ordinal = linescore["currentPeriodOrdinal"]
        self.period.time_remaining = linescore["currentPeriodTimeRemaining"]
        self.period.intermission = linescore["intermissionInfo"]["inIntermission"]

        linescore_home = linescore.get("teams").get("home")
        self.home_team.score = linescore_home.get("goals")
        self.home_team.shots = linescore_home.get("shots")

        linescore_away = linescore.get("teams").get("away")
        self.away_team.score = linescore_away.get("goals")
        self.away_team.shots = linescore_away.get("shots")

    # Commands used to calculate time related attributes
    localtz = dateutil.tz.tzlocal()
    localoffset = localtz.utcoffset(datetime.now(localtz))

    @property
    def day_of_game_local(self):
        """Returns the day of date_time in local server time."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        game_day_local = game_date_local.strftime("%A")
        return game_day_local

    @property
    def month_day_local(self):
        """Returns the month & date of date_time in local server time."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        game_abbr_month = game_date_local.strftime("%b %d").lstrip("0")
        return game_abbr_month

    @property
    def game_time_local(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        game_date_local_ampm = game_date_local.strftime("%I:%M %p")
        return game_date_local_ampm

    @property
    def game_date_local(self):
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        game_date_local_api = game_date_local.strftime("%Y-%m-%d")
        return game_date_local_api

    @property
    def game_date_short(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        game_date_local_short = game_date_local.strftime("%b %d").replace(" 0", " ").upper()
        return game_date_local_short

    @property
    def game_time_of_day(self):
        """Returns the time of the day of the game (later today or tonight)."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        game_date_hour = game_date_local.strftime("%H")
        return "tonight" if int(game_date_hour) > 17 else "later today"

    @property
    def game_time_countdown(self):
        """Returns a countdown (in seconds) to the game start time."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.localoffset
        countdown = (game_date_local - datetime.now()).total_seconds()
        # value_when_true if condition else value_when_false
        return 0 if countdown < 0 else countdown

    @property
    def live_feed(self):
        """Returns a full URL to the livefeed API endpoint."""
        base_url = utils.load_config()["endpoints"]["nhl_base"]
        full_url = "{}{}".format(base_url, self.live_feed_endpoint)
        return full_url

    @property
    def game_hashtag(self):
        """Returns the game specific hashtag (usually #AWAYvsHOME tri-codes)."""
        hashtag = "#{}vs{}".format(self.away_team.tri_code, self.home_team.tri_code)
        return hashtag

    def get_preferred_team(self):
        """Returns a Tuple of team objects of the preferred & other teams."""
        if self.home_team.preferred is True:
            return (self.home_team, self.away_team)

        return (self.away_team, self.home_team)
