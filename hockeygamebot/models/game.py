"""
This module contains the Class definition for the single Game object created during a game.
"""

import logging
from datetime import datetime

import dateutil.tz

from hockeygamebot import models
from hockeygamebot.helpers import utils
from hockeygamebot.models.period import Period
from hockeygamebot.models.shootout import Shootout
from hockeygamebot.models.team import Team
from hockeygamebot.models.hashtag import Hashtag
from hockeygamebot.social import socialhandler

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

        self.tz_id = dateutil.tz.gettz(self.preferred_team.tz_id)
        self.tz_offset = self.tz_id.utcoffset(datetime.now(self.tz_id))
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
        self.pref_goals = []
        self.other_goals = []

        # Initialize Pregame Tweets dictionary
        self.pregame_lasttweet = None
        self.pregametweets = {
            "core": False,
            "lines": False,
            "officials": False,
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

        self.preview_socials = StartOfGameSocial()
        self.final_socials = EndOfGameSocial()
        self.nst_charts = NSTChartSocial()
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

        # Set the hashtags in the Hashtag class
        Hashtag.game_hashtag = f"#{self.away_team.tri_code}vs{self.home_team.tri_code}"
        Hashtag.pref_hashtag = utils.team_hashtag(self.preferred_team.team_name, self.game_type)
        Hashtag.other_hashtag = utils.team_hashtag(self.other_team.team_name, self.game_type)
        Hashtag.home_hashtag = utils.team_hashtag(self.home_team.team_name, self.game_type)
        Hashtag.away_hashtag = utils.team_hashtag(self.away_team.team_name, self.game_type)

    @classmethod
    def from_json_and_teams(cls, resp: dict, home_team: Team, away_team: Team) -> "Game":
        """ A class method that creates a Game object from a combination of the argument fields
            including a JSON livefeed response & the two Team objects (home & away).

        Args:
            resp: livefeed JSON response (dictionary)
            home_team: Team object of home team
            away_team: Team object of away team

        Returns:
            Game: single Game object
        """

        # The venue is not always a 'cherry-pick' from the dictionary
        try:
            venue = resp.get("venue").get("name")
        except KeyError:
            venue = resp.get("teams").get("home").get("team").get("venue").get("name")

        # Get the preferred team flag from the Team objects attribute
        preferred = "home" if home_team.preferred else "away"

        return Game(
            game_id=resp.get("gamePk"),
            season=resp.get("season"),
            game_type=resp.get("gameType"),
            date_time=resp.get("gameDate"),
            game_state=resp.get("status").get("abstractGameState"),
            live_feed=resp.get("link"),
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
        self.period.current = linescore.get("currentPeriod")
        self.period.current_ordinal = linescore.get("currentPeriodOrdinal")
        self.period.time_remaining = linescore.get("currentPeriodTimeRemaining")

        intermission = linescore.get("intermissionInfo")
        self.period.intermission = intermission.get("inIntermission")
        self.period.intermission_remaining = intermission.get("intermissionTimeRemaining")

        linescore_home = linescore.get("teams").get("home")
        self.home_team.score = linescore_home.get("goals")
        self.home_team.shots = linescore_home.get("shots")

        linescore_away = linescore.get("teams").get("away")
        self.away_team.score = linescore_away.get("goals")
        self.away_team.shots = linescore_away.get("shots")

        self.power_play_strength = linescore.get("powerPlayStrength")
        self.home_team.power_play = linescore_home.get("powerPlay")
        self.home_team.skaters = linescore_home.get("numSkaters")
        self.away_team.power_play = linescore_away.get("powerPlay")
        self.away_team.skaters = linescore_away.get("numSkaters")

        # self.last_event_idx = (
        #     response.get("liveData").get("plays").get("currentPlay").get("about").get("eventIdx")
        # )

    def goalie_pull_updater(self, response):
        """ Use the livefeed to determine if the goalie of either team has been pulled.
            And keep the attribute updated in each team object.
        """
        try:
            linescore = response.get("liveData").get("linescore")
            linescore_home = linescore.get("teams").get("home")
            linescore_away = linescore.get("teams").get("away")

            # Goalie Pulled Updater
            last_tracked_event = self.events[-1]
            event_filter_list = (models.gameevent.GoalEvent, models.gameevent.PenaltyEvent)

            # Get current values from the linescore
            home_goalie_current = linescore_home.get("goaliePulled")
            away_goalie_current = linescore_away.get("goaliePulled")

            # Logic to determine previous & current goalie state
            # If the goalie was in net last update, update with new value & check the change.
            # If the goalie was pulled in last update & an important event happened - update & check change.
            # If the goalie was pulled in last update & nothing important happened, don't update or check.
            if not self.home_team.goalie_pulled:
                logging.debug("Home goalie in net - check & update goalie attribute.")
                home_goalie_pulled = self.home_team.goalie_pulled_setter(home_goalie_current)
            elif self.home_team.goalie_pulled and isinstance(last_tracked_event, event_filter_list):
                logging.info(
                    "Home goalie previously pulled, but important event detected - update & check."
                )
                home_goalie_pulled = self.home_team.goalie_pulled_setter(home_goalie_current)
            else:
                logging.info(
                    "Home goalie is pulled and either no event or a non-important event happened - do nothing."
                )
                return

            if not self.away_team.goalie_pulled:
                logging.debug("Home goalie in net - check & update goalie attribute.")
                away_goalie_pulled = self.away_team.goalie_pulled_setter(away_goalie_current)
            elif self.away_team.goalie_pulled and isinstance(last_tracked_event, event_filter_list):
                logging.info(
                    "Away goalie previously pulled, but important event detected - update & check."
                )
                away_goalie_pulled = self.home_team.goalie_pulled_setter(away_goalie_current)
            else:
                logging.info(
                    "Away goalie is pulled and either no event or a non-important event happened - do nothing."
                )
                return

            if home_goalie_pulled:
                trailing_score = self.away_team.score - self.home_team.score
                self.goalie_pull_social(self.home_team.short_name, trailing_score)
            elif away_goalie_pulled:
                trailing_score = self.home_team.score - self.away_team.score
                self.goalie_pull_social(self.away_team.short_name, trailing_score)
        except IndexError as e:
            logging.warning(
                "Tried to update goalie pulled status, but got an error - try again next loop."
            )
            logging.warning(e)

    def goalie_pull_social(self, team_name, trailing_score):
        """ Sends a message to social media about the goalie for a team being pulled.

        Args:
            self: current game instance
            team_name: team short name (from the team's object)
            trailing_score: the amount of goals the pulled team is trailing by

        Returns:
            None
        """

        goalie_pull_text = (
            f"The {team_name} have pulled their goalie trailing by {trailing_score} with "
            f"{self.period.time_remaining} left in the {self.period.current_ordinal} period."
        )

        socialhandler.send(msg=goalie_pull_text, force_send=True)


    @property
    def day_of_game_local(self):
        """Returns the day of date_time in local server time."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_day_local = game_date_local.strftime("%A")
        return game_day_local

    @property
    def month_day_local(self):
        """Returns the month & date of date_time in local server time."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_abbr_month = game_date_local.strftime("%b %d").lstrip("0")
        return game_abbr_month

    @property
    def game_time_local(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_date_local_ampm = game_date_local.strftime("%I:%M %p")
        return game_date_local_ampm

    @property
    def game_date_local(self):
        """ Returns the game as Y-m-d format in local time zone. """
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_date_local_api = game_date_local.strftime("%Y-%m-%d")
        return game_date_local_api

    @property
    def game_date_mmddyyyy(self):
        """ Returns the game as Y-m-d format in local time zone. """
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_date_local_mmddyyyy = game_date_local.strftime("%m/%d/%Y")
        return game_date_local_mmddyyyy

    @property
    def game_date_short(self):
        """Returns the game date_time in local server time in AM / PM format."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_date_local_short = game_date_local.strftime("%B %d").replace(" 0", " ").upper()
        return game_date_local_short

    @property
    def game_time_of_day(self):
        """Returns the time of the day of the game (later today or tonight)."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        game_date_hour = game_date_local.strftime("%H")
        return "tonight" if int(game_date_hour) > 17 else "later today"

    @property
    def game_time_countdown(self):
        """Returns a countdown (in seconds) to the game start time."""
        game_date = datetime.strptime(self.date_time, "%Y-%m-%dT%H:%M:%SZ")
        game_date_local = game_date + self.tz_offset
        countdown = (game_date_local - datetime.now()).total_seconds()
        # value_when_true if condition else value_when_false
        return 0 if countdown < 0 else countdown

    @property
    def live_feed(self):
        """Returns a full URL to the livefeed API endpoint."""
        base_url = utils.load_config().get("endpoints").get("nhl_base")
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


class StartOfGameSocial:
    """ A class that holds all end of game social media messages & statuses."""

    def __init__(self):
        self.retry_count = 0
        self.lasttweet = None

        self.core_msg = None
        self.core_sent = False
        self.season_series_msg = None
        self.season_series_sent = None
        self.goalies_pref_msg = None
        self.goalies_pref_sent = False
        self.goalies_other_msg = None
        self.goalies_other_sent = False
        self.officials_msg = None
        self.officials_sent = False
        self.pref_lines_msg = None
        self.pref_lines_sent = False
        self.other_lines_msg = None
        self.other_lines_sent = False

    @property
    def all_social_sent(self):
        """ Returns True / False depending on if all final socials were sent. """

        all_final_social = [v for k, v in self.__dict__.items() if "sent" in k]
        all_final_social_sent = all(all_final_social)
        return all_final_social_sent

    @property
    def retries_exeeded(self):
        """ Returns True if the number of retires (3 = default) has been exceeded. """
        return bool(self.retry_count >= 3)


class NSTChartSocial:
    """ A class that holds the state of all NST chart social media messages & statuses."""

    def __init__(self):
        pass


class EndOfGameSocial:
    """ A class that holds all end of game social media messages & statuses."""

    def __init__(self):
        self.retry_count = 0

        # These attributes hold scraped values to avoid having to scrape multiple times
        self.hsc_homegs = None
        self.hsc_awaygs = None

        # These attributes hold messages and message sent boolean values
        self.final_score_msg = None
        self.final_score_sent = False
        self.three_stars_msg = None
        self.three_stars_sent = False
        self.nst_linetool_msg = None
        self.nst_linetool_sent = False
        self.hsc_msg = None
        self.hsc_sent = False

    @property
    def all_social_sent(self):
        """ Returns True / False depending on if all final socials were sent. """

        all_final_social = [v for k, v in self.__dict__.items() if "sent" in k]
        all_final_social_sent = all(all_final_social)
        return all_final_social_sent

    @property
    def retries_exeeded(self):
        """ Returns True if the number of retires (3 = default) has been exceeded. """
        return bool(self.retry_count >= 3)
