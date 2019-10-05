"""
This module contains object creation for all Game Events.
"""

import logging
import os
import traceback

from hockeygamebot.definitions import IMAGES_PATH
from hockeygamebot.helpers import utils
from hockeygamebot.models.game import Game
from hockeygamebot.models.gametype import GameType
from hockeygamebot.nhlapi import stats
from hockeygamebot.social import socialhandler
from hockeygamebot.core import images


def event_mapper(event: str, event_type: str) -> object:
    """ A function that maps events or event types to a GameEvent class. This is needed because
        the NHL keeps changing these fields and its easier to have one place to manage this mapping.
        We also take event & eventTypeId so we have something to fall back on.

    Args:
        event (str): The event in the livefeed response
        event_type (str): The eventTypeId field in the livefeed response

    Returns:
        object: Any object within the GameEvent module
    """

    event_map = {
        "faceoff": FaceoffEvent,
        "giveaway": GenericEvent,
        "period start": PeriodStartEvent,
        "game end": GameEndEvent,
        "goal": GoalEvent,
        "blocked shot": ShotEvent,
        "penalty": PenaltyEvent,
        "period ready": PeriodStartEvent,
        "shot": ShotEvent,
        "period official": PeriodEndEvent,
        "stoppage": StopEvent,
        "hit": HitEvent,
        "missed shot": ShotEvent,
        "period end": PeriodEndEvent,
        "takeaway": GenericEvent,
        "game scheduled": GenericEvent,
        "officlal challenge": ChallengeEvent,
        "early int start": GenericEvent,
        "early int end": GenericEvent,
        "shootout complete": GenericEvent,
        "emergency goaltender": GenericEvent,
    }

    # The NHL can't spell Period correctly, so we will have duplicates  -
    # gamecenterPeriodReady     /   gameCenterPeroidReady
    # gamecenterPeriodEnd       /   gamecenterPeroidEnd
    # gamecenterPeriodOfficial  /   gamecenterPeiodOfficial

    event_type_map = {
        "GAME_SCHEDULED": GenericEvent,
        "PERIOD_READY": PeriodStartEvent,
        "PERIOD_START": PeriodStartEvent,
        "FACEOFF": FaceoffEvent,
        "HIT": HitEvent,
        "STOP": StopEvent,
        "GOAL": GoalEvent,
        "MISSED_SHOT": ShotEvent,
        "BLOCKED_SHOT": ShotEvent,
        "GIVEAWAY": GenericEvent,
        "PENALTY": PenaltyEvent,
        "SHOT": ShotEvent,
        "CHALLENGE": ChallengeEvent,
        "TAKEAWAY": GenericEvent,
        "PERIOD_END": PeriodEndEvent,
        "PERIOD_OFFICIAL": PeriodEndEvent,
        "GAME_END": GameEndEvent,
        "gamecenterGameScheduled": GenericEvent,
        "gamecenterPeriodReady": PeriodStartEvent,
        "gamecenterPeroidReady": PeriodStartEvent,
        "gamecenterPeriodStart": PeriodStartEvent,
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
        "gamecenterPeriodEnd": PeriodEndEvent,
        "gamecenterPeroidEnd": PeriodEndEvent,
        "gamecenterPeriodOfficial": PeriodEndEvent,
        "gamecenterPeiodOfficial": PeriodEndEvent,
        "gamecenterGameEnd": GameEndEvent,
    }

    # First try to map by event
    object_type = event_map.get(event)

    # Then if we get None, try to map by eventTypeId
    if object_type is None:
        object_type = event_type_map.get(event_type, GenericEvent)

    return object_type


def event_factory(game: Game, play: dict, livefeed: dict, new_plays: bool):
    """ Factory method for creating a game event. Converts the JSON
            response into a Type-Specific Event we can parse and track.

    Args:
        play: JSON Response of a play from the NHL API (allPlays node)

    Returns:
        Type-Specific Event
    """

    event_type = play.get("result").get("eventTypeId")
    event = play.get("result").get("event")
    object_type = event_mapper(event=event, event_type=event_type)
    event_id = play.get("about").get("eventId")
    event_idx = play.get("about").get("eventIdx")

    # Check whether this event is in our Cache
    obj = object_type.cache.get(event_id)

    # Check whether this is a shootout event & re-assigned the object_type accordingly
    shootout = bool(play.get("about").get("periodType") == "SHOOTOUT")
    object_type = ShootoutEvent if shootout else object_type

    # Add the game object & livefeed to our response
    # event["game"] = game
    play["livefeed"] = livefeed

    # These methods are called when we want to act on existing objects
    # Check for scoring changes on GoalEvents
    # We also use the new_plays variable to only check for scoring changes on no new events
    if object_type == GoalEvent and obj is not None and not new_plays:
        score_change_msg = obj.check_for_scoring_changes(play)
        if score_change_msg is not None:
            social_ids = socialhandler.send(msg=score_change_msg, reply=obj.tweet, force_send=True)
            obj.tweet = social_ids.get("twitter")

    # If object doesn't exist, create it & add to Cache
    if obj is None:
        try:
            logging.info("Creating %s event for Id %s / IdX %s.", object_type.__name__, event_id, event_idx)
            obj = object_type(data=play, game=game)
            object_type.cache.add(obj)
        except Exception as error:
            logging.error("Error creating %s event for Id %s. / IdX %s.", object_type, event_id, event_idx)
            # logging.error(response)
            logging.error(error)
            logging.error(traceback.format_exc())

    # Update our Game EventIDX for Tracking
    game.last_event_idx = event_idx

    return obj


def game_event_total(object_type: object, player: str, attribute: str):
    """ Calculates the number of events a person has for a single game.
        Mostly used for penalties and goals (hat trick, etc).

    Args:
        object_type: the type of object to help determine the cache
        player: player name to filter on
        attribute: attribute to match on

    Return:
        event_count: number of events
    """

    items = object_type.cache.entries.items()
    events = [getattr(v, attribute) for k, v in items if getattr(v, attribute) == player]
    return len(events)


def game_scoring_totals(player: str):
    """ Calculates the number of goals, assists, points a person has for a single game.

    Args:
        player: player name to filter on

    Return:
        event_count: dictionary of event counts
    """

    items = GoalEvent.cache.entries.items()

    goals = len(
        [getattr(v, "scorer_name") for k, v in items if getattr(v, "scorer_name") == player]
    )
    primary = len(
        [getattr(v, "primary_name") for k, v in items if getattr(v, "primary_name") == player]
    )
    secondary = len(
        [getattr(v, "secondary_name") for k, v in items if getattr(v, "secondary_name") == player]
    )

    assists = primary + secondary
    points = goals + assists

    game_totals = {"goals": goals, "assists": assists, "points": points}
    return game_totals


class Cache:
    """ A cache that holds GameEvents by type. """

    def __init__(self, object_type: object, duration: int = 60):
        self.contains = object_type
        self.duration = duration
        self.entries = {}

    def add(self, entry: object):
        """ Adds an object to this Cache. """
        self.entries[entry.event_id] = entry

    def get(self, id: int):
        """ Gets an entry from the cache / checks if exists via None return. """
        entry = self.entries.get(id)
        return entry


class GenericEvent:
    """ A Generic Game event where we just store the attributes and don't
        do anything with the object except store it.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        self.data = data
        self.game = game
        self.livefeed = data.get("livefeed")
        self.social_msg = None
        self.game.events.append(self)

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
        self.period_time_remain_str = utils.time_remain_converter(self.period_time_remain)
        # self.date_time = dateutil.parser.parse(about.get("dateTime"))
        self.date_time = about.get("dateTime")
        self.away_goals = about.get("goals").get("away")
        self.home_goals = about.get("goals").get("home")
        self.pref_goals = about.get("goals").get(self.game.preferred_team.home_away)
        self.other_goals = about.get("goals").get(self.game.other_team.home_away)

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


class PeriodStartEvent(GenericEvent):
    """ A Period Start object contains all start of period-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Now call any functions that should be called when creating a new object
        self.generate_social_msg()
        ids = socialhandler.send(msg=self.social_msg, event=self)

    def generate_social_msg(self):
        """ Used for generating the message that will be logged or sent to social media. """

        # Logic for Period Ready Events (used for lineups)
        if "ready" in self.event_type.lower():
            preferred_homeaway = self.game.preferred_team.home_away
            players = self.livefeed.get("gameData").get("players")
            on_ice = (
                self.livefeed.get("liveData")
                .get("boxscore")
                .get("teams")
                .get(preferred_homeaway)
                .get("onIce")
            )
            self.social_msg = self.get_lineup(on_ice, players)

        # Logic for Period Start Events
        elif "start" in self.event_type.lower():
            # First period start event
            if self.period == 1:
                self.social_msg = (
                    f"The puck has dropped between the "
                    f"{self.game.preferred_team.short_name} & "
                    f"{self.game.other_team.short_name} at {self.game.venue}!"
                )
            # Second & Third period start events are same for all game types
            elif self.period in (2, 3):
                self.social_msg = (
                    f"It's time for the {self.period_ordinal} period at " f"{self.game.venue}."
                )
            # Non-Playoff Game Period Start (3-on-3 OT)
            elif self.period == 4 and self.game.game_type in ("PR", "R"):
                self.social_msg = (
                    f"Who will be the hero this time? "
                    f"3-on-3 OT starts now at {self.game.venue}."
                )
            # Playoff Game Period Start (5-on-5 OT)
            elif self.period > 3 and self.game.game_type == "P":
                ot_period = self.period - 3
                self.social_msg = (
                    f"Who will be the hero this time? "
                    f"OT{ot_period} starts now at {self.game.venue}."
                )
            # Start of the Shootout (Period 5 of Non-Playoff Game)
            elif self.period == 5 and self.game.game_type in ("PR", "R"):
                self.social_msg = f"The shootout is underway at {self.game.venue}!"

    def get_lineup(self, on_ice, players):
        """ Generates a lineup message for a given team.

        Args:
            game (Game): The current game instance.
            period (Period): The current period instance.
            on_ice (list): A list of players on the ice for the preferred team.
            players (dict): A dictionary of all players of the preferred team.
        """

        logging.info("On Ice Players - %s", on_ice)

        forwards = []
        defense = []
        goalies = []

        for player in on_ice:
            key_id = "ID{}".format(player)
            player_obj = players[key_id]
            logging.debug("Getting information for %s -- %s", key_id, player_obj)

            player_last_name = player_obj["lastName"]
            player_type = player_obj["primaryPosition"]["type"]
            if player_type == "Forward":
                forwards.append(player_last_name)
            elif player_type == "Defenseman":
                defense.append(player_last_name)
            elif player_type == "Goalie":
                goalies.append(player_last_name)

        # Get Linenup for Periods 1-3 (applies to all games)
        if self.period <= 3:
            text_forwards = " - ".join(forwards)
            text_defense = " - ".join(defense)
            text_goalie = goalies[0] if goalies else ''

            social_msg = (
                f"On the ice to start the {self.period_ordinal} period for your "
                f"{self.game.preferred_team.team_name} -\n\n"
                f"{text_forwards}\n{text_defense}\n{text_goalie}"
            )

        # Get Lineup for pre-season or regular season overtime game (3-on-3)
        elif self.period == 4 and self.game.game_type in ("PR", "R"):
            all_players = forwards + defense
            text_players = " - ".join(all_players)
            try:
                text_goalie = goalies[0]
                social_msg = (
                    f"On the ice to start overtime for your "
                    f"{self.game.preferred_team.team_name} "
                    f"are:\n\n{text_players} & {text_goalie}."
                )
            except IndexError:
                # If for some reason a goalie isn't detected on ice
                social_msg = (
                    f"On the ice to start overtime for your "
                    f"{self.game.preferred_team.team_name} "
                    f"are:\n\n{text_players}."
                )

        elif self.period > 3 and self.game.game_type == "P":
            ot_number = self.period - 3
            text_forwards = "-".join(forwards)
            text_defense = "-".join(defense)
            text_goalie = goalies[0]

            social_msg = (
                f"On the ice to start OT{ot_number} for your "
                f"{self.game.preferred_team.team_name} -\n\n"
                f"{text_forwards}\n{text_defense}\n{text_goalie}"
            )

        return social_msg


class PeriodEndEvent(GenericEvent):
    """ A Period End object contains all end of period-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)
        self.tied_score = bool(self.pref_goals == self.other_goals)

        # Now call any functions that should be called when creating a new object
        # Only do these for Period Official event type
        if self.event_type == "PERIOD_END":
            self.period_end_text = self.get_period_end_text()
            self.lead_trail_text = self.get_lead_trail()
            self.social_msg = self.generate_social_msg()

            # Generate Stats Image
            boxscore = self.livefeed.get("liveData").get("boxscore")
            stats_image = images.stats_image(game=self.game, game_end=False, boxscore=boxscore)
            img_filename = os.path.join(IMAGES_PATH, "temp", f"Intermission-{self.}-{game.game_id}.png")
            stats_image.save(img_filename)

            ids = socialhandler.send(msg=self.social_msg, media=img_filename, event=self)

    def get_period_end_text(self):
        """ Formats the main period end text with some logic based on score & period. """

        # Normal intermission message
        if self.period in (1, 2):
            period_end_text = (
                f"The {self.period_ordinal} period of " f"{self.game.game_hashtag} comes to an end."
            )

        # If the game needs (at least) 1 OT period
        elif self.period == 3 and self.tied_score:
            period_end_text = (
                f"60 minutes wasn't enough to decide this game. "
                f"{self.game.preferred_team.short_name} and {self.game.other_team.short_name} "
                f"are headed to overtime tied at {self.pref_goals}!"
            )

        # Non-Playoff game tied after OT - Heads to a Shootout
        elif (
            self.period > 3
            and self.tied_score
            and GameType(self.game.game_type) != GameType.PLAYOFFS
        ):
            period_end_text = (
                f"60 minutes and some overtime weren't enough to decide this game. "
                f"{self.game.preferred_team.short_name} and {self.game.other_team.short_name} "
                f"are headed to a shootout!"
            )

        # Playoff game still tied - heads to extra OT!
        elif (
            self.period > 3
            and self.tied_score
            and GameType(self.game.game_type) == GameType.PLAYOFFS
        ):
            ot_period = self.period - 3
            next_ot_period = ot_period + 1
            ot_text = "overtime wasn't" if ot_period == 1 else "overtimes weren't"
            period_end_text = (
                f"{ot_period} {ot_text} to decide this game. "
                f"{self.game.preferred_team.short_name} and {self.game.other_team.short_name} "
                f"headed to OT{next_ot_period} tied at {self.pref_goals}!"
            )

        else:
            period_end_text = None

        return period_end_text

    def get_lead_trail(self):
        """ Formats the leading / trailing stat text based on score & period. """

        # Lead / Trailing stat is only valid for 1st and 2nd periods
        if self.period > 2:
            return None

        if self.pref_goals > self.other_goals:
            if self.period == 1:
                lead_trail_stat = self.game.preferred_team.lead_trail_lead1P
            elif self.period == 2:
                lead_trail_stat = self.game.preferred_team.lead_trail_lead2P
            lead_trail_text = (
                f"When leading after the {self.period_ordinal} period the "
                f"{self.game.preferred_team.short_name} are {lead_trail_stat}."
            )

        elif self.pref_goals < self.other_goals:
            if self.period == 1:
                lead_trail_stat = self.game.preferred_team.lead_trail_trail1P
            elif self.period == 2:
                lead_trail_stat = self.game.preferred_team.lead_trail_trail2P
            lead_trail_text = (
                f"When trailing after the {self.period_ordinal} period the "
                f"{self.game.preferred_team.short_name} are {lead_trail_stat}."
            )
        else:
            lead_trail_text = None

        return lead_trail_text

    def generate_social_msg(self):
        """ Used for generating the message that will be logged or sent to social media. """

        if self.period_end_text is None and self.lead_trail_text is None:
            social_msg = None
        elif self.lead_trail_text is None:
            social_msg = f"{self.period_end_text}"
        else:
            social_msg = f"{self.period_end_text}\n\n{self.lead_trail_text}"

        return social_msg


class FaceoffEvent(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

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
            self.generate_social_msg()
            ids = socialhandler.send(msg=self.social_msg, event=self)

    def generate_social_msg(self):
        """ Used for generating the message that will be logged or sent to social media. """
        msg = (
            f"{self.winner_name} wins the opening faceoff of the {self.period_ordinal} "
            f"period against {self.loser_name}!"
        )
        self.social_msg = msg


class HitEvent(GenericEvent):
    """ A Hit object contains all hit-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

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

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)
        # TODO: Determine what stoppage tweets we want to send out


class GoalEvent(GenericEvent):
    """ A Goal object contains all goal-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Goals have a few extra results attributes
        results = data.get("result")
        self.secondary_type = results.get("secondaryType", "shot").lower()
        self.strength_code = results.get("strength").get("code")
        self.strength_name = results.get("strength").get("name")
        self.game_winning_goal = results.get("gameWinningGoal")
        self.empty_net = results.get("emptyNet")
        self.event_team = data.get("team").get("name")
        self.tweet = None

        # Add this event to the goals list in the game
        goals_list = self.game.pref_goals if self.event_team == self.game.preferred_team.team_name \
            else self.game.other_goals
        goals_list.append(self)

        # Get the Coordinates Section
        coordinates = data.get("coordinates")
        self.x = coordinates.get("x", 0.0)
        self.y = coordinates.get("y", 0.0)
        self.goal_distnace = utils.calculate_shot_distance(self.x, self.y)

        # Get the Players Section
        players = data.get("players")
        scorer = [x for x in players if x.get("playerType").lower() == "scorer"]
        assist = [x for x in players if x.get("playerType").lower() == "assist"]
        goalie = [x for x in players if x.get("playerType").lower() == "goalie"]

        # Handle Scorer name, id & totals
        self.scorer_name = scorer[0].get("player").get("fullName")
        self.scorer_id = scorer[0].get("player").get("id")
        self.scorer_game_total = game_scoring_totals(self.scorer_name)["goals"] + 1
        self.scorer_game_total_ordinal = utils.ordinal(self.scorer_game_total)
        self.scorer_game_total_points = game_scoring_totals(self.scorer_name)["points"] + 1
        self.scorer_game_total_point_ordinal = utils.ordinal(self.scorer_game_total_points)
        self.scorer_season_ttl = scorer[0].get("seasonTotal")

        # Get Scorer Career Stats
        self.scorer_career_stats = stats.get_player_career_stats(self.scorer_id)
        self.scorer_career_goals = self.scorer_career_stats["goals"] + self.scorer_game_total
        self.scorer_career_points = (
            self.scorer_career_stats["points"] + self.scorer_game_total_points
        )
        print("==================== POINT TOALS SECTION ====================")
        print(f"Goal Scorer ({self.scorer_name}) Goals - {self.scorer_game_total}")
        print(f"Goal Scorer ({self.scorer_name}) Career Goals - {self.scorer_career_goals}")
        print(f"Goal Scorer ({self.scorer_name}) Points - {self.scorer_game_total_points}")
        print(f"Goal Scorer ({self.scorer_name}) Career Points - {self.scorer_career_points}")

        # Goalie isn't recorded for empty net goals
        if not self.empty_net:
            self.goalie_name = goalie[0].get("player").get("fullName")
            self.goalie_id = goalie[0].get("player").get("id")
        else:
            self.goalie_name = None
            self.goalie_id = None

        # Assist parsing is contained within a function
        self.parse_assists(assist=assist)

        # Now call any functions that should be called when creating a new object
        self.goal_title_text = self.get_goal_title_text()
        self.goal_main_text = self.get_goal_main_text()
        self.social_msg = f"{self.goal_title_text}\n\n{self.goal_main_text}"
        social_ids = socialhandler.send(msg=self.social_msg, event=self)

        # Set any social media IDs
        self.tweet = social_ids.get("twitter")

        # Now that the main goal text is sent, check for milestones
        if hasattr(self, 'scorer_career_points') and  self.scorer_career_points % 100 == 0:
            logging.info("Goal Scorer - Career Point Milestone - %s", self.scorer_career_points)

        if hasattr(self, 'primary_career_assists') and self.primary_career_assists % 100 == 0:
            logging.info("Primary - Career Assist Milestone - %s", self.primary_career_assists)

        if hasattr(self, 'primary_career_points') and self.primary_career_points % 100 == 0:
            logging.info("Primary - Career Point Milestone - %s", self.scorer_career_points)

        if hasattr(self, 'secondary_career_assists') and self.secondary_career_assists % 100 == 0:
            logging.info("Secondary - Career Assist Milestone - %s", self.secondary_career_assists)

        if hasattr(self, 'secondary_career_points') and self.secondary_career_points % 100 == 0:
            logging.info("Secondary - Career Point Milestone - %s", self.secondary_career_points)


    def parse_assists(self, assist: list):
        """ Since we have to parse assists initially & for scoring changes, move this to a function. """

        self.assists = assist
        self.num_assists = len(assist)

        if len(assist) == 2:
            self.primary_name = assist[0].get("player").get("fullName")
            self.primary_id = assist[0].get("player").get("id")
            self.primary_season_ttl = assist[0].get("seasonTotal")

            # Get Primary Game & Career Stats
            self.primary_game_stats = game_scoring_totals(self.primary_name)
            self.primary_game_assists = self.primary_game_stats["assists"] + 1
            self.primary_game_points = self.primary_game_stats["points"] + 1
            self.primary_career_stats = stats.get_player_career_stats(self.primary_id)
            self.primary_career_assists = (
                self.primary_career_stats["assists"] + self.primary_game_assists
            )
            self.primary_career_points = (
                self.primary_career_stats["points"] + self.primary_game_points
            )
            print(f"Primary Assist ({self.primary_name}) Assists - {self.primary_game_assists}")
            print(
                f"Primary Assist ({self.primary_name}) Career Assists - {self.primary_career_assists}"
            )
            print(f"Primary Assist ({self.primary_name}) Points - {self.primary_game_points}")
            print(
                f"Primary Assist ({self.primary_name}) Career Points - {self.primary_career_points}"
            )

            self.secondary_name = assist[1].get("player").get("fullName")
            self.secondary_id = assist[1].get("player").get("id")
            self.secondary_season_ttl = assist[1].get("seasonTotal")

            # Get Secondary Game & Career Stats
            self.secondary_game_stats = game_scoring_totals(self.secondary_name)
            self.secondary_game_assists = self.secondary_game_stats["assists"] + 1
            self.secondary_game_points = self.secondary_game_stats["points"] + 1
            self.secondary_career_stats = stats.get_player_career_stats(self.secondary_id)
            self.secondary_career_assists = (
                self.secondary_career_stats["assists"] + self.secondary_game_assists
            )
            self.secondary_career_points = (
                self.secondary_career_stats["points"] + self.secondary_game_points
            )
            print(
                f"Secondary Assist ({self.secondary_name}) Assists - {self.secondary_game_assists}"
            )
            print(
                f"Secondary Assist ({self.secondary_name}) Career Assists - {self.secondary_career_assists}"
            )
            print(f"Secondary Assist ({self.secondary_name}) Points - {self.secondary_game_points}")
            print(
                f"Secondary Assist ({self.secondary_name}) Career Points - {self.secondary_career_points}"
            )

            self.unassisted = False
        elif len(assist) == 1:
            self.primary_name = assist[0].get("player").get("fullName")
            self.primary_id = assist[0].get("player").get("id")
            self.primary_season_ttl = assist[0].get("seasonTotal")

            # Get Primary Game & Career Stats
            self.primary_game_stats = game_scoring_totals(self.primary_name)
            self.primary_game_assists = self.primary_game_stats["assists"] + 1
            self.primary_game_points = self.primary_game_stats["points"] + 1
            self.primary_career_stats = stats.get_player_career_stats(self.primary_id)
            self.primary_career_assists = (
                self.primary_career_stats["assists"] + self.primary_game_assists
            )
            self.primary_career_points = (
                self.primary_career_stats["points"] + self.primary_game_points
            )
            print(f"Primary Assist ({self.primary_name}) Assists - {self.primary_game_assists}")
            print(
                f"Primary Assist ({self.primary_name}) Career Assists - {self.primary_career_assists}"
            )
            print(f"Primary Assist ({self.primary_name}) Points - {self.primary_game_points}")
            print(
                f"Primary Assist ({self.primary_name}) Career Points - {self.primary_career_points}"
            )

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

    def get_goal_title_text(self):
        """ Gets the main goal text / header. """

        if self.event_team == self.game.preferred_team.team_name:
            goal_emoji = "🚨" * self.pref_goals

            if self.scorer_career_goals == 1:
                goal_milestone_text = "🚨 FIRST GOAL ALERT! 🚨\n\n"
            elif self.scorer_career_goals % 100 == 0:
                goal_ordinal = utils.ordinal(self.scorer_career_goals)
                goal_milestone_text = f"🚨 {goal_ordinal} CAREER GOALS! 🚨\n\n"
            else:
                goal_milestone_text = ""

            if self.period_type == "OVERTIME":
                goal_title_text = f"{self.event_team} OVERTIME GOAL!!"
            elif self.strength_name != "Even":
                goal_title_text = f"{self.event_team} {self.strength_name} GOAL!"
            elif self.empty_net:
                goal_title_text = f"{self.event_team} empty net GOAL!"
            elif self.pref_goals == 7:
                goal_title_text = f"{self.event_team} TOUCHDOWN!"
            else:
                goal_title_text = f"{self.event_team} GOAL!"
        else:
            goal_title_text = f"{self.event_team} score."
            goal_emoji = "👎🏻" * self.other_goals
            goal_milestone_text = ""

        goal_title_text = f"{goal_milestone_text}{goal_title_text} {goal_emoji}"
        return goal_title_text

    def get_goal_main_text(self):
        """ Gets the main goal description (players, shots, etc). """
        # TODO: Add randomness to this section of code.

        # This section is for goals per game (only add for 2+ goals)
        if self.scorer_game_total == 2:
            goal_count_text = f"With his {self.scorer_game_total_ordinal} goal of the game,"
        elif self.scorer_game_total == 3:
            goal_count_text = "🎩🎩🎩 HAT TRICK!"
        elif self.scorer_game_total == 4:
            goal_count_text = f"{self.scorer_game_total} GOALS!!"
        else:
            goal_count_text = None

        # Main goal scorere text (per season, shot type, etc)
        if self.secondary_type == "deflected":
            goal_scoring_text = (
                f"{self.scorer_name} ({self.scorer_season_ttl}) deflects a shot past "
                f"{self.goalie_name} with {self.period_time_remain_str} left "
                f"in the {self.period_ordinal} period."
            )
        else:
            goal_scoring_text = (
                f"{self.scorer_name} ({self.scorer_season_ttl}) scores on a "
                f"{self.secondary_type} from {self.goal_distnace} away with "
                f"{self.period_time_remain_str} left in the "
                f"{self.period_ordinal} period."
            )

        # Assists Section
        if self.num_assists == 1:
            goal_assist_text = (
                f"Give the assist to {self.primary_name} ({self.primary_season_ttl})."
            )
        elif self.num_assists == 2:
            goal_assist_text = (
                f"The goal was assisted by {self.primary_name} ({self.primary_season_ttl}) "
                f"and {self.secondary_name} ({self.secondary_season_ttl})."
            )
        else:
            goal_assist_text = None

        # FIXME: Can I fix this weird if / else - come back to it.
        if goal_count_text is None and goal_assist_text is None:
            goal_main_text = goal_scoring_text
        elif goal_count_text is None:
            goal_main_text = f"{goal_scoring_text} {goal_assist_text}"
        elif goal_assist_text is None:
            goal_main_text = f"{goal_count_text} {goal_scoring_text}"
        else:
            goal_main_text = f"{goal_count_text} {goal_scoring_text} {goal_assist_text}"

        return goal_main_text

    def check_for_scoring_changes(self, data: dict):
        """ Checks for scoring changes or changes in assists (or even number of assists).

        Args:
            data: Dictionary of a Goal Event from the Live Feed allPlays endpoint

        Returns:
            None if no goal change / new social media string if goal change.
        """

        logging.info(
            "Checking for scoring changes (team : %s / event ID %s / IDX %s).", self.event_team, self.event_id, self.event_idx
        )
        players = data.get("players")
        scorer = [x for x in players if x.get("playerType").lower() == "scorer"]
        assist = [x for x in players if x.get("playerType").lower() == "assist"]

        # Check for Changes in Player IDs
        scorer_change = bool(scorer[0].get("player").get("id") != self.scorer_id)
        assist_change = bool(assist != self.assists)
        logging.info("Scoring Change - %s / Assists Change - %s", scorer_change, assist_change)

        if scorer_change:
            print("Old Scorer -", self.scorer_name)
            goal_scorechange_title = "The scoring on this goal has changed."
            logging.info(
                "Scoring change detected for event ID %s / IDX %s.", self.event_id, self.event_idx
            )
            self.scorer_name = scorer[0].get("player").get("fullName")
            self.scorer_id = scorer[0].get("player").get("id")
            self.scorer_season_ttl = scorer[0].get("seasonTotal")
            logging.info("New Scorer - %s", self.scorer_name)

            # Re-parse assists too (a goal scoring change usually means assist changes too)
            self.parse_assists(assist=assist)

            if not assist:
                goal_scorechange_text = (
                    f"Now reads as an unassisted goal for {self.scorer_name} "
                    f"({self.scorer_season_ttl})."
                )
            elif self.num_assists == 1:
                goal_scorechange_text = (
                    f"Now reads as {self.scorer_name} ({self.scorer_season_ttl}) "
                    f"from {self.primary_name} ({self.primary_season_ttl})."
                )
            else:
                goal_scorechange_text = (
                    f"Now reads as {self.scorer_name} ({self.scorer_season_ttl}) "
                    f"from {self.primary_name} ({self.primary_season_ttl}) "
                    f"and {self.secondary_name} ({self.secondary_season_ttl})."
                )

        elif assist_change:
            # A change in assists could be a change or addition of a previously unassisted goal.
            # To check which scenario this is, check previous num_assists before re-parsing.
            goal_scorechange_title = (
                "The assists on this goal have changed." if self.num_assists != 0 else None
            )

            # Re-parse assists too (a goal scoring change usually means assist changes too)
            self.parse_assists(assist=assist)
            if self.num_assists == 1:
                goal_scorechange_text = (
                    f"Give the lone assist on the {self.scorer_name} goal to "
                    f"{self.primary_name} ({self.primary_season_ttl})."
                )
            elif self.num_assists == 2:
                goal_scorechange_text = (
                    f"The {self.scorer_name} goal is now assisted by "
                    f"{self.primary_name} ({self.primary_season_ttl}) "
                    f"and {self.secondary_name} ({self.secondary_season_ttl})."
                )
            else:
                goal_scorechange_text = f"The {self.scorer_name} goal is now uniassisted!"
        else:
            goal_scorechange_text = None
            return None

        # Return a string based on
        if goal_scorechange_title is None:
            return goal_scorechange_text
        else:
            return f"{goal_scorechange_title}\n\n{goal_scorechange_text}"


class ShotEvent(GenericEvent):
    """ A Shot object contains all shot-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Shots have a secondary type & a team name
        self.secondary_type = data.get("result").get("secondaryType")
        self.event_team = data.get("team").get("name")

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
        self.shot_distance = utils.calculate_shot_distance(self.x, self.y)

        # Now call any functions that should be called when creating a new object
        # (FOR NOW) we only checked for missed shots that hit the post.
        if self.crossbar_or_post():
            self.generate_social_msg()
            ids = socialhandler.send(msg=self.social_msg, event=self)

    def crossbar_or_post(self):
        """ Checks shot text to determine if the shot was by the preferred
            team and hit the crossbar or post. """

        # This checks if the shot was taken by the preferred team
        if self.event_team != self.game.preferred_team.team_name:
            return False

        # Check to see if the post hit the crossbar or the goal post
        hit_keywords = ["crossbar", "goalpost"]
        if any(x in self.description.lower() for x in hit_keywords):
            logging.info("The preferred team hit a post or crossbar - social media message.")
            return True
        else:
            logging.debug("The preferred team missed a shot, but didn't hit the post.")
            return False

    def generate_social_msg(self):
        """ Used for generating the message that will be logged or sent to social media. """
        if "crossbar" in self.description.lower():
            shot_hit = "crossbar"
        elif "goalpost" in self.description.lower():
            shot_hit = "post"
        else:
            shot_hit = None

        self.social_msg = (
            f"DING! 🛎\n\n{self.player_name} hits the {shot_hit} from {self.shot_distance} "
            f"away with {self.period_time_remain} remaining in the {self.period_ordinal} period."
        )


class PenaltyEvent(GenericEvent):
    """ A Faceoff object contains all faceoff-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Penalties have some extra result attributes
        results = data.get("result")
        self.secondary_type = self.penalty_type_fixer(results.get("secondaryType")).lower()
        self.severity = results.get("penaltySeverity").lower()
        self.minutes = results.get("penaltyMinutes")
        self.penalty_team = data.get("team").get("name")

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
        self.penalty_on_game_ttl = (
            game_event_total(__class__, self.penalty_on_name, "penalty_on_name") + 1
        )

        # Get the Coordinates Section
        coordinates = data.get("coordinates")
        self.x = coordinates.get("x", 0.0)
        self.y = coordinates.get("y", 0.0)

        # Now call any functions that should be called when creating a new object
        # TODO: Figure out if theres a way to check for offsetting penalties
        self.penalty_main_text = self.get_skaters()
        self.penalty_rankstat_text = self.get_penalty_stats()
        self.generate_social_msg()
        ids = socialhandler.send(msg=self.social_msg, event=self)

    def penalty_type_fixer(self, original_type):
        """ A function that converts some poorly named penalty types. """
        secondarty_types = {
            "delaying game - puck over glass": "delay of game (puck over glass)",
            "interference - goalkeeper": "goalie interference"
        }
        return secondarty_types.get(original_type, original_type)

    def get_skaters(self):
        """ Used for determining how many skaters were on the ice at the time of event. """

        # Get penalty team & skater attributes / numbers
        if self.penalty_team == self.game.home_team.team_name:
            self.penalty_on_team = self.game.home_team
            self.penalty_draw_team = self.game.away_team
        else:
            self.penalty_on_team = self.game.away_team
            self.penalty_draw_team = self.game.home_team

        power_play_strength = self.game.power_play_strength
        penalty_on_skaters = self.penalty_on_team.skaters
        penalty_draw_skaters = self.penalty_draw_team.skaters

        pref_short_name = self.game.preferred_team.short_name
        pref_skaters = self.game.preferred_team.skaters
        other_skaters = self.game.other_team.skaters

        logging.info(
            "PP Strength - %s | PenaltyOn Skaters - %s | PenaltyDraw Skaters - %s",
            power_play_strength,
            penalty_on_skaters,
            penalty_draw_skaters,
        )

        # TODO: Get periodTimeRemaining for some of these strings
        if power_play_strength == "Even" and penalty_on_skaters == penalty_draw_skaters == 4:
            penalty_text_skaters = "Teams will skate 4 on 4."
        elif power_play_strength == "Even" and penalty_on_skaters == penalty_draw_skaters == 3:
            penalty_text_skaters = "Teams will skate 3 on 3."
        elif power_play_strength != "Even":
            # Preferred Team Advantages
            if pref_skaters == 5 and other_skaters == 4:
                penalty_text_skaters = f"{pref_short_name} are headed to the power play!"
            elif pref_skaters == 5 and other_skaters == 3:
                penalty_text_skaters = f"{pref_short_name} will have a two-man advantage!"
            elif pref_skaters == 4 and other_skaters == 3:
                penalty_text_skaters = f"{pref_short_name} are headed a 4-on-3 power play!"

            # Other Team Advantages
            elif pref_skaters == 4 and other_skaters == 5:
                penalty_text_skaters = f"{pref_short_name} are headed to the penalty kill!"
            elif pref_skaters == 3 and other_skaters == 5:
                penalty_text_skaters = (
                    f"{pref_short_name} will have to kill off a two-man advantage!"
                )
            elif pref_skaters == 3 and other_skaters == 5:
                penalty_text_skaters = f"{pref_short_name} will have a 4-on-3 penalty to kill!"
        else:
            logging.info("Unkown penalty skater combination")
            penalty_text_skaters = ""

        penalty_text_players = (
            f"{self.penalty_on_name} takes a {self.minutes}-minute {self.severity} "
            f"penalty for {self.secondary_type} and heads to the penalty box with "
            f"{self.period_time_remain} remaining in the {self.period_ordinal} period. "
            # f"That's his {utils.ordinal(self.penalty_on_game_ttl)} penalty of the game. "
            f"{penalty_text_skaters}"
        )

        return penalty_text_players

    def get_penalty_stats(self):
        """ Used for determining penalty kill / power play stats. """
        penalty_on_stats = self.penalty_on_team.get_stat_and_rank("penaltyKillPercentage")
        penalty_on_short_name = self.penalty_on_team.short_name
        penalty_on_stat = penalty_on_stats[0]
        penalty_on_rank = penalty_on_stats[1]
        penalty_on_rankstat_text = (
            f"{penalty_on_short_name} PK: {penalty_on_stat}% ({penalty_on_rank})"
        )

        penalty_draw_stats = self.penalty_draw_team.get_stat_and_rank("powerPlayPercentage")
        penalty_draw_short_name = self.penalty_draw_team.short_name
        penalty_draw_stat = penalty_draw_stats[0]
        penalty_draw_rank = penalty_draw_stats[1]
        penalty_draw_rankstat_text = (
            f"{penalty_draw_short_name} PP: {penalty_draw_stat} ({penalty_draw_rank})"
        )

        penalty_rankstat_text = f"{penalty_on_rankstat_text}\n{penalty_draw_rankstat_text}"
        return penalty_rankstat_text

    def generate_social_msg(self):
        """ Used for generating the message that will be logged or sent to social media. """
        if self.game.power_play_strength != "Even":
            self.social_msg = f"{self.penalty_main_text}\n\n{self.penalty_rankstat_text}"
        else:
            self.social_msg = f"{self.penalty_main_text}"


class ChallengeEvent(GenericEvent):
    """ A Challenge object contains all challenge-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
        This event needs to be aware of events around it so it can understand reversals.
    """

    cache = Cache(__name__)


class ShootoutEvent(GenericEvent):
    """ A Shootout object contains all shootout-related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)


class GameEndEvent(GenericEvent):
    """ A Game End object contains all game end related attributes and extra methods.
        It is a subclass of the GenericEvent class with the most basic attributes.
        # TODO: Determine if we need this or if the game goes FINAL as this event is posted
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)
        self.winner = "home" if self.home_goals > self.away_goals else "away"
        logging.info("Game End Event detected before game state is Final - manually setting!")
        self.game.game_state = "Final"
