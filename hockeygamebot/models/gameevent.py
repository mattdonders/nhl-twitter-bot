"""
This module contains object creation for all Game Events.
"""
import weakref

import dateutil.parser

from hockeygamebot.helpers import utils

allobjects = list()


def event_factory(response: dict):
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
        "gamecenterPeriodReady": Period,
        "gamecenterPeroidReady": Period,
        "gamecenterPeriodStart": Period,
        "gamecenterFaceoff": Faceoff,
        "gamecenterHit": Hit,
        "gamecenterStop": Stop,
        "gamecenterGoal": Goal,
        "gamecenterMissedShot": Shot,
        "gamecenterBlockedShot": Shot,
        "gamecenterGiveaway": GenericEvent,
        "gamecenterPenalty": Penalty,
        "gamecenterShot": Shot,
        "gamecenterOfficialChallenge": Challenge,
        "gamecenterTakeaway": GenericEvent,
        "gamecenterPeriodEnd": Period,
        "gamecenterPeroidEnd": Period,
        "gamecenterPeriodOfficial": Period,
        "gamecenterPeiodOfficial": Period,
        "gamecenterGameEnd": GameEnd,
    }

    event_type = response.get("result").get("eventTypeId")
    object_type = event_map.get(event_type, GenericEvent)
    event_idx = response.get("about").get("eventIdx")

    # Check whether this event is in our Cache
    obj = object_type.cache.get(event_idx)

    # Update attributes only for existing Goal objects
    if object_type == Goal and obj is not None:
        obj.check_for_scoring_changes()

    # If object doesn't exist, create it & add to Cache
    if obj is None:
        obj = object_type(response)
        object_type.cache.add(obj)

    return obj


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
        self.date_time = dateutil.parser.parse(about.get("dateTime"))
        self.away_goals = about.get("goals").get("away")
        self.home_goals = about.get("goals").get("home")

    # @classmethod
    # def idx_exists(cls, idx):
    #     for obj in cls.allobjects:
    #         if obj.event_idx == idx:
    #             return obj


class Period(GenericEvent):
    """ A Period object contains all period-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    def __init__(self, data: dict):
        super().__init__(data)
        self.call_socials()

    @utils.check_social_timeout
    def call_socials(self):
        print("This a PERIOD object!")
        print(self.data)
        pass


class Faceoff(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass


class Hit(GenericEvent):
    """ A Hit object contains all hit-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass


class Stop(GenericEvent):
    """ A Stop object contains all stoppage-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass


class Goal(GenericEvent):
    """ A Goal object contains all goal-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    def check_for_scoring_changes(self):
        print("Checking for scoring changes!")


class Shot(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass


class Penalty(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass


class Challenge(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass


class GameEnd(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    pass
