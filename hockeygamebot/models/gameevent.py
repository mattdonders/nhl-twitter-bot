"""
This module contains object creation for all Game Events.
"""

import logging
import traceback

from hockeygamebot.models.game import Game
from hockeygamebot.helpers import utils
from hockeygamebot.social import socialhandler


def event_factory(game: Game, response: dict):
    """ Factory method for creating a game event. Converts the JSON
            response into a Type-Specific Event we can parse and track.

    Args:
        response": JSON Response from the NHL API (allPlays node)

    Returns:
        Type-Specific Event
    """

    # The NHL can't spell Period correctly, so we will have duplicates  -
    # gamecenterPeriodReady     /   gameCenterPeroidReady
    # gamecenterPeriodEnd       /   gamecenterPeroidEnd
    # gamecenterPeriodOfficial  /   gamecenterPeiodOfficial

    event_map = {
        "gamecenterGameScheduled": GenericEvent,
        "gamecenterPeriodReady": PeriodEvent,
        "gamecenterPeroidReady": PeriodEvent,
        "gamecenterPeriodStart": PeriodEvent,
        "gamecenterFaceoff": FaceoffEvent,
        "gamecenterHit": HitEvent,
        "gamecenterStop": StopEvent,
        "gamecenterGoal": GoalEvent,
        "gamecenterMissedShot": ShotEvent,
        "gamecenterBlockedShot": ShotEvent,
        "gamecenterGiveaway": GenericEvent,
        "gamecenterPenalty": PenaltyEvent,
        "gamecenterShot": ShotEvent,
        "gamecenterOfficialChallenge": ChallengeEvent,
        "gamecenterTakeaway": GenericEvent,
        "gamecenterPeriodEnd": PeriodEvent,
        "gamecenterPeroidEnd": PeriodEvent,
        "gamecenterPeriodOfficial": PeriodEvent,
        "gamecenterPeiodOfficial": PeriodEvent,
        "gamecenterGameEnd": GameEndEvent,
    }

    event_type = response.get("result").get("eventTypeId")
    object_type = event_map.get(event_type, GenericEvent)
    event_idx = response.get("about").get("eventIdx")

    # Check whether this event is in our Cache
    obj = object_type.cache.get(event_idx)

    # Add the game object to our response
    response["game"] = game

    # These methods are called when we want to act on existing objects
    # Check for scoring changes on GoalEvents
    # TODO: Compare eventIdx and only check for scoring changes on no new events
    if object_type == GoalEvent and obj is not None:
        obj.check_for_scoring_changes(response)

    # If object doesn't exist, create it & add to Cache
    if obj is None:
        try:
            obj = object_type(response)
            object_type.cache.add(obj)
        except Exception as error:
            logging.error("Error creating %s event for Idx %s.", object_type, event_idx)
            logging.error(response)
            logging.error(error)
            logging.error(traceback.format_exc())

    return obj


def game_event_total(object_type, player, attribute):
    """ Calculates the number of events a person has for a single game.
        Mostly used for penalties and goals (hat trick, etc).

    Args:
        object_type: the type of object to help determine the cache
        player: player name to filter on
        attribute: attribute to match on

    Return:
        event_count: number of events
    """

    events = [getattr(v, attribute) for k,v in object_type.cache.entries.items() if getattr(v, attribute) == player]
    return len(events)


class Cache:
    """ A cache that holds GameEvents by type. """

    def __init__(self, object_type, duration=60):
        self.contains = object_type
        self.duration = duration
        self.entries = {}

    def add(self, entry):
        """ Adds an object to this Cache. """
        self.entries[entry.event_idx] = entry

    def get(self, idx):
        """ Gets an entry from the cache / checks if exists via None return. """
        entry = self.entries.get(idx)
        return entry


class GenericEvent:
    """ A Generic Game event where we just store the attributes and don't
        do anything with the object except store it.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        self.data = data
        self.game = data.get("game")

        # Get the Result Section
        results = data.get("result")
        self.event = results.get("event")
        self.event_code = results.get("eventCode")
        self.event_type = results.get("eventTypeId")
        self.description = results.get("description")

        # Get the About Section
        about = data.get("about")
        self.event_idx = about.get("eventIdx")
        self.event_id = about.get("eventId")
        self.period = about.get("period")
        self.period_type = about.get("periodType")
        self.period_ordinal = about.get("ordinalNum")
        self.period_time = about.get("periodTime")
        self.period_time_remain = about.get("periodTimeRemaining")
        # self.date_time = dateutil.parser.parse(about.get("dateTime"))
        self.date_time = about.get("dateTime")
        self.away_goals = about.get("goals").get("away")
        self.home_goals = about.get("goals").get("home")

    def asdict(self, withsource=False):
        """ Returns the object as a dictionary with the option of excluding the original
            dictionary used to create the objet.

        Args:
            withsource: True / False to include or exclude original dict

        Returns:
            Dictionary representation of object
        """
        # Generate the full dictionary
        dict_obj = self.__dict__

        # Copy the dictionary & pop the data key if needed
        dict_obj_nosource = dict(dict_obj)
        dict_obj_nosource.pop("data")

        return dict_obj if withsource else dict_obj_nosource


class PeriodEvent(GenericEvent):
    """ A Period object contains all period-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)
        # Now call any functions that should be called when creating a new object
        self.send_socials()

    @utils.check_social_timeout
    def send_socials(self):
        if self.event_type == "gamecenterPeriodStart":
            msg = f"The {self.period_ordinal} period is underway at {self.game.venue}!"
            socialhandler.send(msg)


class FaceoffEvent(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)

        # Get the Players Section
        players = data.get("players")
        winner = [x for x in players if x.get("playerType").lower() == "winner"]
        loser = [x for x in players if x.get("playerType").lower() == "loser"]
        self.winner_name = winner[0].get("player").get("fullName")
        self.winner_id = winner[0].get("player").get("id")
        self.loser_name = loser[0].get("player").get("fullName")
        self.loser_id = loser[0].get("player").get("id")

        # Get the Coordinates Section
        coordinates = data.get("coordinates")
        self.x = coordinates.get("x", 0.0)
        self.y = coordinates.get("y", 0.0)

        self.opening_faceoff = bool(self.period_time == "00:00")

        # Now call any functions that should be called when creating a new object
        if self.opening_faceoff:
            self.opening_faceoff_socials()

    @utils.check_social_timeout
    def opening_faceoff_socials(self):
        msg = (f"{self.winner_name} wins the opening faceoff of the {self.period_ordinal} "
               f"period against {self.loser_name}!")
        socialhandler.send(msg)


class HitEvent(GenericEvent):
    """ A Hit object contains all hit-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)

        # Get the Players Section
        players = data.get("players")
        hitter = [x for x in players if x.get("playerType").lower() == "hitter"]
        hittee = [x for x in players if x.get("playerType").lower() == "hittee"]
        self.hitter_name = hitter[0].get("player").get("fullName")
        self.hitter_id = hitter[0].get("player").get("id")
        self.hittee_id = hittee[0].get("player").get("fullName")
        self.hittee_id = hittee[0].get("player").get("id")

        # Get the Coordinates Section
        coordinates = data.get("coordinates")
        self.x = coordinates.get("x", 0.0)
        self.y = coordinates.get("y", 0.0)


class StopEvent(GenericEvent):
    """ A Stop object contains all stoppage-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)
        # TODO: Determine what stoppage tweets we want to send out
        pass


class GoalEvent(GenericEvent):
    """ A Goal object contains all goal-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)

        # Shots have a few extra results attributes
        results = data.get("result")
        self.secondary_type = results.get("secondaryType")
        self.strength_code = results.get("strength").get("code")
        self.strength_name = results.get("strength").get("name")
        self.game_winning_goal = results.get("gameWinningGoal")
        self.empty_net = results.get("emptyNet")

        # Get the Players Section
        players = data.get("players")
        scorer = [x for x in players if x.get("playerType").lower() == "scorer"]
        assist = [x for x in players if x.get("playerType").lower() == "assist"]
        goalie = [x for x in players if x.get("playerType").lower() == "goalie"]
        self.scorer_name = scorer[0].get("player").get("fullName")
        self.scorer_id = scorer[0].get("player").get("id")
        self.scorer_game_total = game_event_total(__class__, self.scorer_name, "scorer_name") + 1
        self.scorer_season_ttl = scorer[0].get("seasonTotal")
        # Goalie isn't recorded for empty net goals
        if not self.empty_net:
            self.goalie_name = goalie[0].get("player").get("fullName")
            self.goalie_id = goalie[0].get("player").get("id")
        else:
            self.goalie_name = None
            self.goalie_id = None
        self.assists = assist
        self.num_assists = len(assist)
        if len(assist) == 2:
            self.primary_name = assist[0].get("player").get("fullName")
            self.primary_id = assist[0].get("player").get("id")
            self.primary_season_ttl = assist[0].get("seasonTotal")
            self.secondary_name = assist[1].get("player").get("fullName")
            self.secondry_id = assist[1].get("player").get("id")
            self.secondary_season_ttl = assist[1].get("seasonTotal")
            self.unassisted = False
        elif len(assist) == 1:
            self.primary_name = assist[0].get("player").get("fullName")
            self.primary_id = assist[0].get("player").get("id")
            self.primary_season_ttl = assist[0].get("seasonTotal")
            self.secondary_name = None
            self.secondry_id = None
            self.secondary_season_ttl = None
            self.unassisted = False
        else:
            self.primary_name = None
            self.primary_id = None
            self.primary_season_ttl = None
            self.secondary_name = None
            self.secondry_id = None
            self.secondary_season_ttl = None
            self.unassisted = True

        # Call social media functions
        self.call_socials()

    @utils.check_social_timeout
    def call_socials(self):
        if self.unassisted:
            msg = (f"GOAL - {self.scorer_name} ({self.scorer_season_ttl}) scores his {utils.ordinal(self.scorer_game_total)} of the game unassisted at "
                   f"{self.period_time} of the {self.period_ordinal} period.")
        if self.num_assists == 1:
            msg = (f"GOAL - {self.scorer_name} ({self.scorer_season_ttl}) scores his {utils.ordinal(self.scorer_game_total)} of the game from {self.primary_name} "
                   f"({self.primary_season_ttl}) at {self.period_time} of the {self.period_ordinal} period.")
        else:
            msg = (f"GOAL - {self.scorer_name} ({self.scorer_season_ttl}) scores his {utils.ordinal(self.scorer_game_total)} of the game from {self.primary_name} "
                   f"({self.primary_season_ttl}) & {self.secondary_name} ({self.secondary_season_ttl}) "
                   f"at {self.period_time} of the {self.period_ordinal} period.")

        socialhandler.send(msg)


    def check_for_scoring_changes(self, data: dict):
        """ Checks for scoring changes or changes in assists (or even number of assists).

        Args:
            data: Dictionary of a Goal Event from the Live Feed allPlays endpoint

        Returns:
            None
        """

        print("Checking for scoring changes!")
        players = data.get("players")
        scorer = [x for x in players if x.get("playerType").lower() == "scorer"]
        assist = [x for x in players if x.get("playerType").lower() == "assist"]
        num_assists = len(assist)

        # Check for Changes in Player IDs
        scorer_change = bool(scorer[0].get("player").get("id") != self.scorer_id)
        assist_change = bool(assist != self.assists)
        print("Scoring Change -", scorer_change)
        print("Assists Change -", assist_change)

        if scorer_change:
            logging.info(
                "Scoring change detected for event ID %s / IDX %s.", self.event_id, self.event_idx
            )
            new_scorer_name = scorer[0].get("player").get("fullName")
            new_scorer_id = scorer[0].get("player").get("id")
            new_scorer_season_ttl = scorer[0].get("seasonTotal")
            print("Old Scorer -", self.scorer_name)
            print("New Scorer -", new_scorer_name)

            if not assist:
                logging.info("New goal is scored as unassisted.")
            if num_assists == 1:
                logging.info("Now reads as XXX from XXX.")
            else:
                logging.info("Now reads as XXX from XXX.")

        elif assist_change:
            if not assist:
                logging.info("The goal is now unassisted.")
            if num_assists == 1:
                logging.info("Give the lone assist on XXXX's goal to YYYYY.")
            else:
                logging.info("The goal is now assisted by XXXXX and YYYYY.")


class ShotEvent(GenericEvent):
    """ A Shot object contains all shot-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)

        # Shots have a secondary type
        self.secondary_type = data.get("result").get("secondaryType")

        # Get the Players Section
        players = data.get("players")
        player = [x for x in players if x.get("playerType").lower() == "shooter"]
        goalie = [x for x in players if x.get("playerType").lower() == "goalie"]
        self.player_name = player[0].get("player").get("fullName")
        self.player_id = player[0].get("player").get("id")

        # Missed Shots & Blocked Shots don't have goalie attributes
        if goalie:
            self.goalie_name = goalie[0].get("player").get("fullName")
            self.goalie_id = goalie[0].get("player").get("id")
        else:
            self.goalie_name = None
            self.goalie_id = None

        # Get the Coordinates Section
        coordinates = data.get("coordinates")
        self.x = coordinates.get("x", 0.0)
        self.y = coordinates.get("y", 0.0)


class PenaltyEvent(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)

        # Penalties have some extra result attributes
        results = data.get("result")
        self.secondary_type = results.get("secondaryType")
        self.severity = results.get("penaltySeverity")
        self.minutes = results.get("penaltyMinutes")

        # Get the Players Section
        players = data.get("players")
        drew_by = [x for x in players if x.get("playerType").lower() == "drewby"]
        penalty_on = [x for x in players if x.get("playerType").lower() == "penaltyon"]
        # Sometimes the drew_by fields are not populated immediately
        if drew_by:
            self.drew_by_name = drew_by[0].get("player").get("fullName")
            self.drew_by_id = drew_by[0].get("player").get("id")
        else:
            self.drew_by_name = None
            self.drew_by_id = None
        self.penalty_on_name = penalty_on[0].get("player").get("fullName")
        self.penalty_on_id = penalty_on[0].get("player").get("id")
        self.penalty_on_game_ttl = game_event_total(__class__, self.penalty_on_name, "penalty_on_name") + 1

        # Get the Coordinates Section
        coordinates = data.get("coordinates")
        self.x = coordinates.get("x", 0.0)
        self.y = coordinates.get("y", 0.0)

        self.call_socials()

    @utils.check_social_timeout
    def call_socials(self):
        msg = (f"{self.penalty_on_name} takes a {self.minutes}-minute {self.severity.lower()} "
               f"penalty for {self.secondary_type.lower()}. That's his {utils.ordinal(self.penalty_on_game_ttl)} "
               f"penalty of the game.")
        socialhandler.send(msg)



class ChallengeEvent(GenericEvent):
    """ A Challenge object contains all challenge-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
        This event needs to be aware of events around it so it can understand reversals.
    """

    cache = Cache(__name__)

    pass


class GameEndEvent(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict):
        super().__init__(data)
        self.winner = "home" if self.home_goals > self.away_goals else "away"
