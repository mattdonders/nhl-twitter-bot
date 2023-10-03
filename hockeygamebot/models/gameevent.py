"""
This module contains object creation for all Game Events.
"""

from enum import Enum
import logging
import os
import traceback

from hockeygamebot.definitions import IMAGES_PATH
from hockeygamebot.helpers import utils
from hockeygamebot.models.game import Game, PenaltySituation
from hockeygamebot.models.gametype import GameType
from hockeygamebot.nhlapi import contentfeed, stats, livefeed
from hockeygamebot.social import socialhandler
from hockeygamebot.core import images


class GameEventTypeCode(Enum):
    """Enum for tracking the <TBD / Game Event Type Code> attribute."""

    FACEOFF = 502
    HIT = 503
    GIVEAWAY = 504
    GOAL = 505
    SHOT_ON_GOAL = 506
    MISSED_SHOT = 507
    BLOCKED_SHOT = 508
    PENALTY = 509
    STOPPAGE = 516
    PERIOD_START = 520
    PERIOD_END = 521
    SHOOTOUT_COMPLETE = 523
    GAME_END = 524
    TAKEAWAY = 525
    DELAYED_PENALTY = 535
    FAILED_SHOT_ATTEMPT = 537


def strength_mapper(strength_code):
    mapper = {"pp": "Power Play", "ev": "Even"}
    return mapper.get(strength_code, strength_code)


def event_mapper(event_type: str, event_type_code: str) -> object:
    """A function that maps events or event types to a GameEvent class. This is needed because
        the NHL keeps changing these fields and its easier to have one place to manage this mapping.
        We also take event & eventTypeId so we have something to fall back on.

    Args:
        event (str): The typeDescKey in the livefeed response
        event_type_code (str): The typeCode field in the livefeed response

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
        "period ready": PeriodReadyEvent,
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
        "PERIOD_READY": PeriodReadyEvent,
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
        "gamecenterPeriodReady": PeriodReadyEvent,
        "gamecenterPeroidReady": PeriodReadyEvent,
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

    event_code_map = {
        502: FaceoffEvent,
        503: HitEvent,
        504: GenericEvent,
        505: GoalEvent,
        506: ShotEvent,
        507: ShotEvent,
        508: ShotEvent,
        509: PenaltyEvent,
        516: StopEvent,
        520: PeriodStartEvent,
        521: PeriodEndEvent,
        523: ShootoutEvent,
        524: GameEndEvent,
        525: GenericEvent,
        # 535:DelayedPenaltyEvent,    #TBD
        535: GenericEvent,  # TBD
        537: ShotEvent,
    }

    # First try to map by event
    object_type = event_map.get(event_type)

    # Then if we get None, try to map by eventTypeId
    if object_type is None:
        object_type = event_code_map.get(event_type_code, GenericEvent)

    return object_type


def generate_custom_event_id(play: dict):
    # In the NHL V2 API (at least in pre-season) it seems that the old iDX (running tally) is not present anymore.
    # Instead we will generate our own custom ID per event based on the current game time.
    # Custom ID = currentPeriod * timeInPeriod (in seconds)

    current_period = play.get("period")
    current_period_time = play.get("timeInPeriod")
    current_period_time_ss = utils.from_mmss(current_period_time)
    custom_id = current_period * current_period_time_ss
    return custom_id


def event_factory(game: Game, play: dict, livefeed: dict, new_plays: bool):
    """Factory method for creating a game event. Converts the JSON
            response into a Type-Specific Event we can parse and track.

    Args:
        play: JSON Response of a play from the NHL API (allPlays node)

    Returns:
        Type-Specific Event
    """

    event_type = play.get("typeDescKey")
    event_type_code = play.get("typeCode")
    event_reason = play.get("details", {}).get("reason")
    event_2nd_reason = play.get("details", {}).get("secondaryReason")  # Secondary Reason has TV Timeouts
    object_type = event_mapper(event_type=event_type, event_type_code=event_type_code)

    event_id = play.get("eventId")
    event_idx = play.get("sortOrder")
    custom_event_id = generate_custom_event_id(play)
    sort_order = play.get("sortOrder")

    # Check whether this is a shootout event & re-assigned the object_type accordingly
    # TODO: NEW API: GameType != PlayOffs & Period == 5
    shootout = bool(game.game_type != 3 and play.get("period") == 5 and object_type != GameEndEvent)
    object_type = ShootoutEvent if shootout else object_type

    # Check whether this event is in our Cache
    obj = object_type.cache.get(event_id)

    # Add the game object & livefeed to our response
    # event["game"] = game
    play["livefeed"] = livefeed

    # These methods are called when we want to act on existing objects
    # Check for scoring changes and NHL Video IDs on GoalEvents
    # We also use the new_plays variable to only check for scoring changes on no new events

    if object_type == GoalEvent and obj is not None and not new_plays:
        # TODO / TBD: Disabling Scoring Changes b/c of 24-hour Twitter Limit

        # score_change_msg = obj.check_for_scoring_changes(play)
        # if score_change_msg is not None:
        #     social_ids = socialhandler.send(
        #         msg=score_change_msg, reply=obj.tweet, force_send=True, game_hashtag=True
        #     )
        #     obj.tweet = social_ids.get("twitter")

        # Content Feed Checks
        # all_goals_have_content = all(goal.video_url is not None for idx, goal in GoalEvent.cache.entries.items())
        should_check_content = True if game.live_loop_counter % 10 == 0 else False

        # TODO: Fix this for the V2 API (Need Regular Season Data for Video / Content Data)
        # If the object has no video_url, all goals don't have content and we should be checking content (via counter)
        # if not obj.video_url and should_check_content:
        #     logging.info("A Goal without a video has been found - check the content feed for it.")
        #     milestones = contentfeed.get_content_feed(game_id=game.game_id, milestones=True)
        #     content_exists, highlight, video_url, mp4_url = contentfeed.search_milestones_for_id(
        #         milestones, event_id
        #     )
        #     if content_exists:
        #         # blurb = highlight.get('blurb')
        #         description = highlight.get("description")
        #         video_path = utils.download_file(mp4_url)
        #         content_msg = f"NHL Video Highlight - {description}. \n\n{video_url}"
        #         discord_msg = f"🎥 **NHL Video Highlight**\n{description}.\n{mp4_url}"
        #         social_ids = socialhandler.send(
        #             msg=content_msg,
        #             reply=obj.tweet,
        #             force_send=True,
        #             game_hashtag=True,
        #             discord_msg=discord_msg,
        #             video=video_path,
        #         )
        #         obj.tweet = social_ids.get("twitter")
        #         obj.video_url = video_url

    # If object doesn't exist, create it & add to Cache
    if obj is None:
        try:
            logging.info(
                "Creating %s event for Id %s / IdX %s / Custom eventId: %s.",
                object_type.__name__,
                event_id,
                event_idx,
                custom_event_id,
            )
            obj = object_type(data=play, game=game)
            object_type.cache.add(obj)
        except Exception as error:
            logging.error("Error creating %s event for Id %s. / IdX %s.", object_type, event_id, event_idx)
            # logging.error(response)
            logging.error(error)
            logging.error(traceback.format_exc())

    # Update our Game EventIDX for Tracking
    game.last_event_idx = custom_event_id

    return obj


def game_event_total(object_type: object, player: str, attribute: str):
    """Calculates the number of events a person has for a single game.
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
    """Calculates the number of goals, assists, points a person has for a single game.

    Args:
        player: player name to filter on

    Return:
        event_count: dictionary of event counts
    """

    items = GoalEvent.cache.entries.items()

    goals = len([getattr(v, "scorer_name") for k, v in items if getattr(v, "scorer_name") == player])
    primary = len([getattr(v, "primary_name") for k, v in items if getattr(v, "primary_name") == player])
    secondary = len(
        [getattr(v, "secondary_name") for k, v in items if getattr(v, "secondary_name") == player]
    )

    assists = primary + secondary
    points = goals + assists

    game_totals = {"goals": goals, "assists": assists, "points": points}
    return game_totals


class Cache:
    """A cache that holds GameEvents by type."""

    def __init__(self, object_type: object, duration: int = 60):
        self.contains = object_type
        self.duration = duration
        self.entries = {}

    def add(self, entry: object):
        """Adds an object to this Cache."""
        self.entries[entry.event_id] = entry

    def get(self, id: int):
        """Gets an entry from the cache / checks if exists via None return."""
        entry = self.entries.get(id)
        return entry

    def remove(self, entry: object):
        """Removes an entry from its Object cache."""
        del self.entries[entry.event_id]


class GenericEvent:
    """A Generic Game event where we just store the attributes and don't
    do anything with the object except store it.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        self.data = data
        self.game = game
        self.livefeed = data.get("livefeed")
        self.social_msg = None
        self.game.events.append(self)
        self.event_removal_counter = 0

        self.event_type = data.get("typeDescKey")
        self.event_type_code = data.get("typeCode")

        details = data.get("details")
        self.event_reason = data.get("details", {}).get("reason")
        self.event_2nd_reason = data.get("details", {}).get("secondaryReason")

        self.event_idx = data.get("sortOrder")
        self.event_id = data.get("eventId")
        self.custom_event_id = generate_custom_event_id(data)
        self.period = data.get("period")
        self.period_type = data.get("periodType")
        self.period_ordinal = utils.ordinal(self.period)
        self.period_time = data.get("timeInPeriod")
        self.period_time_remain = data.get("timeRemaining")
        self.period_time_remain_str = utils.time_remain_converter(self.period_time_remain)
        self.period_time_remain_ss = utils.from_mmss(self.period_time_remain)

        self.game_duration = self.period * 1200 - self.period_time_remain_ss

        self.away_goals = self.livefeed.get("awayTeam").get("score")
        self.home_goals = self.livefeed.get("homeTeam").get("score")
        self.pref_goals = self.livefeed.get(f"{self.game.preferred_team.home_away}Team").get("score")
        self.other_goals = self.livefeed.get(f"{self.game.other_team.home_away}Team").get("score")

        # Get On-Ice Players
        self.home_onice = self.livefeed.get("homeTeam").get("onIce")
        self.home_onice_num = len(self.home_onice)
        self.away_onice = self.livefeed.get("awayTeam").get("onIce")
        self.away_onice_num = len(self.away_onice)
        self.strength = f"{self.home_onice_num}v{self.away_onice_num}"

    def asdict(self, withsource=False):
        """Returns the object as a dictionary with the option of excluding the original
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
        dict_obj_nosource.pop("livefeed")

        return dict_obj if withsource else dict_obj_nosource


class PeriodReadyEvent(GenericEvent):
    """A Period Ready object contains all of period-ready-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Now call any functions that should be called when creating a new object
        self.generate_social_msg()
        if self.social_msg:
            ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True)

    def generate_social_msg(self):
        """Used for generating the message that will be logged or sent to social media."""
        preferred_homeaway = self.game.preferred_team.home_away
        players = self.livefeed.get("gameData").get("players")
        on_ice = (
            self.livefeed.get("liveData").get("boxscore").get("teams").get(preferred_homeaway).get("onIce")
        )
        self.social_msg = self.get_lineup(on_ice, players) if on_ice else None

    def get_lineup(self, on_ice, players):
        """Generates a lineup message for a given team.

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
            text_goalie = goalies[0] if goalies else ""

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


class PeriodStartEvent(GenericEvent):
    """A Period Start object contains all start of period-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Reset the 1-minute remaining property for this period
        self.game.period.shotmap_retweet = False
        self.game.period.current_oneminute_sent = False

        # Now call any functions that should be called when creating a new object
        self.generate_social_msg()
        ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True)

    def generate_social_msg(self):
        """Used for generating the message that will be logged or sent to social media."""

        # First period start event
        if self.period == 1:
            self.social_msg = (
                f"The puck has dropped between the "
                f"{self.game.preferred_team.short_name} & "
                f"{self.game.other_team.short_name} at {self.game.venue}!"
            )
        # Second & Third period start events are same for all game types
        elif self.period in (2, 3):
            self.social_msg = f"It's time for the {self.period_ordinal} period at " f"{self.game.venue}."
        # Non-Playoff Game Period Start (3-on-3 OT)
        elif self.period == 4 and self.game.game_type in ("PR", "R"):
            self.social_msg = (
                f"Who will be the hero this time? " f"3-on-3 OT starts now at {self.game.venue}."
            )
        # Playoff Game Period Start (5-on-5 OT)
        elif self.period > 3 and self.game.game_type == "P":
            ot_period = self.period - 3
            self.social_msg = (
                f"Who will be the hero this time? " f"OT{ot_period} starts now at {self.game.venue}."
            )
        # Start of the Shootout (Period 5 of Non-Playoff Game)
        elif self.period == 5 and self.game.game_type in ("PR", "R"):
            self.social_msg = f"The shootout is underway at {self.game.venue}!"


class PeriodEndEvent(GenericEvent):
    """A Period End object contains all end of period-related attributes and extra methods.
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
            # Sometimes (???) the boxscore is empty...?
            if not boxscore:
                raise AttributeError("Cannot generate images with an empty boxscore, try again later.")

            stats_image = images.stats_image(game=self.game, game_end=False, boxscore=boxscore)
            img_filename = os.path.join(IMAGES_PATH, "temp", f"Intermission-{self.period}-{game.game_id}.png")
            stats_image.save(img_filename)

            social_ids = socialhandler.send(
                msg=self.social_msg, media=img_filename, event=self, game_hashtag=True
            )
            last_tweet = social_ids.get("twitter") if social_ids else None

            stat_leaders_social = self.get_stat_leaders()
            social_ids = socialhandler.send(
                msg=stat_leaders_social, reply=last_tweet, event=self, game_hashtag=True
            )

    def get_period_end_text(self):
        """Formats the main period end text with some logic based on score & period."""

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
        elif self.period > 3 and self.tied_score and GameType(self.game.game_type) != GameType.PLAYOFFS:
            period_end_text = (
                f"60 minutes and some overtime weren't enough to decide this game. "
                f"{self.game.preferred_team.short_name} and {self.game.other_team.short_name} "
                f"are headed to a shootout!"
            )

        # Playoff game still tied - heads to extra OT!
        elif self.period > 3 and self.tied_score and GameType(self.game.game_type) == GameType.PLAYOFFS:
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
        """Formats the leading / trailing stat text based on score & period."""

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
        """Used for generating the message that will be logged or sent to social media."""

        if self.period_end_text is None and self.lead_trail_text is None:
            social_msg = None
        elif self.lead_trail_text is None:
            social_msg = f"{self.period_end_text}"
        else:
            social_msg = f"{self.period_end_text}\n\n{self.lead_trail_text}"

        return social_msg

    # The two below functions are used for end of period stat leaders.
    def check_and_update_leader(self, stat_leaders, stat, value, last_name):
        """Checks if a stat needs to be updated with a new player value (greater than before)."""
        current_leader_value = stat_leaders.get(stat)
        if value > current_leader_value:
            stat_leaders[stat] = value
            value = utils.to_mmss(value) if stat == "timeOnIce" else value
            stat_leaders[f"{stat}_str"] = f"{value} ({last_name})"

        # Return updated stat_leaders dictionary
        return stat_leaders

    def get_stat_leaders(self):
        """Gets stat leaders in a number of important categories."""

        # Setup Stat Leaders Dictionary
        # Add / remove values here to automatically calculate them
        stat_leaders = {
            "timeOnIce": 0,
            "timeOnIce_desc": "Time On Ice",
            "shots": 0,
            "shots_desc": "Shots",
            "hits": 0,
            "hits_desc": "Hits",
            "faceOffWins": 0,
            "faceOffWins_desc": "Faceoff Wins",
            "giveaways": 0,
            "giveaways_desc": "Giveaways",
            "takeaways": 0,
            "takeaways_desc": "Takeaways",
            "blocked": 0,
            "blocked_desc": "Blocked",
        }

        # Create a list of stats to check (converts dict keys into iterable list)
        stats_to_check = [k for k in stat_leaders if "_" not in k]

        preferred_homeaway = self.game.preferred_team.home_away
        player_stats = (
            self.livefeed.get("liveData").get("boxscore").get("teams").get(preferred_homeaway).get("players")
        )

        for _, player in player_stats.items():
            name = player.get("person").get("fullName")
            last_name = " ".join(name.split()[1:])
            stats = player.get("stats").get("skaterStats")
            if not stats:
                continue
            for i in stats_to_check:
                stat_value = stats.get(i)
                if i == "timeOnIce":
                    stat_value = utils.from_mmss(stat_value)
                stat_leaders = self.check_and_update_leader(stat_leaders, i, stat_value, last_name)

        stat_leaders_final = list()
        for i in stats_to_check:
            desc = stat_leaders.get(f"{i}_desc")
            value = stat_leaders.get(f"{i}_str")
            stat_value_string = f"{desc}: {value}"
            stat_leaders_final.append(stat_value_string)

        stat_leaders_final_string = "\n".join(stat_leaders_final)
        stat_leaders_final_string = f"End of Period Stat Leaders - \n\n{stat_leaders_final_string}"
        return stat_leaders_final_string


class FaceoffEvent(GenericEvent):
    """A Faceoff object contains all faceoff-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Get the Players Section
        details = data.get("details")
        self.winner_id = details.get("winningPlayerId")
        self.loser_id = details.get("losingPlayerId")
        self.winner_name = game.full_roster.get(self.winner_id, {}).get("fullName", "N/A")
        self.loser_name = game.full_roster.get(self.loser_id, {}).get("fullName", "N/A")

        # Get the Coordinates Section
        self.x = details.get("xCoord", 0)
        self.y = details.get("yCoord", 0)

        self.opening_faceoff = bool(self.period_time == "00:00")

        # Now call any functions that should be called when creating a new object
        if self.opening_faceoff:
            self.generate_social_msg()
            ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True)

    def generate_social_msg(self):
        """Used for generating the message that will be logged or sent to social media."""
        msg = (
            f"{self.winner_name} wins the opening faceoff of the {self.period_ordinal} "
            f"period against {self.loser_name}!"
        )
        self.social_msg = msg


class HitEvent(GenericEvent):
    """A Hit object contains all hit-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Get the Players Section
        details = data.get("details")

        self.hitter_id = details.get("hittingPlayerId")
        self.hittee_id = details.get("hitteePlayerId")
        self.hitter_name = game.full_roster.get(self.hitter_id, {}).get("fullName", "N/A")
        self.hittee_name = game.full_roster.get(self.hittee_id, {}).get("fullName", "N/A")

        # Get the Coordinates Section
        self.x = details.get("xCoord", 0)
        self.y = details.get("yCoord", 0)


class StopEvent(GenericEvent):
    """A Stop object contains all stoppage-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)
        # TODO: Determine what stoppage tweets we want to send out

        # Consider Sending TV Timeout Tweets
        if self.event_2nd_reason == "tv-timeout":
            logging.info(
                "TV Timeout detected @ %s left in the %s period.",
                self.period_time_remain,
                self.period_ordinal,
            )


class GoalEvent(GenericEvent):
    """A Goal object contains all goal-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Goals have a few extra results attributes
        details = data.get("details")

        # The GameCenter Landing Page Contains Extra Data the Play by Play API Does Not
        self.unique_key = f"{self.period}-{self.period_time}"
        gclanding_all_goals = self.get_goals_gclanding()
        gc_details = gclanding_all_goals.get(self.unique_key)

        shot_type = details.get("shotType", "shot").lower()
        self.secondary_type = f"{shot_type} shot"
        self.goal_modifier = gc_details.get("goalModifier")
        self.situation_code = data.get("situationCode")
        self.strength_code = gc_details.get("strength")
        self.strength_name = strength_mapper(self.strength_code)
        # self.game_winning_goal = results.get("gameWinningGoal")
        self.empty_net = True if self.goal_modifier == "empty-net" else False
        self.team_id = details.get("eventOwnerTeamId")
        self.team_name = self.game.team_lookup[self.team_id].team_name
        self.tweet = None
        self.video_url = None

        # Determine if we need to reset the Penalty Situation (PP Team Scores)
        penalty_situation = self.game.penalty_situation
        if penalty_situation.in_situation and penalty_situation.pp_team.team_name == self.team_name:
            self.game.penalty_situation = PenaltySituation()

        # Get the Coordinates Section
        self.x = details.get("xCoord", 0)
        self.y = details.get("yCoord", 0)
        self.goal_distnace = utils.calculate_shot_distance(self.x, self.y)

        # Handle Scorer name, id & totals
        self.scorer_id = details.get("scoringPlayerId")
        self.scorer_name = game.full_roster.get(self.scorer_id, {}).get("fullName", "N/A")
        self.scorer_game_total = game_scoring_totals(self.scorer_name)["goals"] + 1
        self.scorer_game_total_ordinal = utils.ordinal(self.scorer_game_total)
        self.scorer_game_total_points = game_scoring_totals(self.scorer_name)["points"] + 1
        self.scorer_game_total_point_ordinal = utils.ordinal(self.scorer_game_total_points)
        self.scorer_season_ttl = gc_details.get("goalsToDate")

        # Get Scorer Career Stats (Only Regular Season)
        # TODO: Maybe Playoffs
        self.scorer_career_stats = stats.get_player_career_stats(self.scorer_id)
        self.scorer_career_goals = self.scorer_career_stats.get("goals", 0) + self.scorer_game_total
        self.scorer_career_points = self.scorer_career_stats.get("points", 0) + self.scorer_game_total_points
        print("==================== POINT TOALS SECTION ====================")
        print(f"Goal Scorer ({self.scorer_name}) Goals - {self.scorer_game_total}")
        print(f"Goal Scorer ({self.scorer_name}) Career Goals - {self.scorer_career_goals}")
        print(f"Goal Scorer ({self.scorer_name}) Points - {self.scorer_game_total_points}")
        print(f"Goal Scorer ({self.scorer_name}) Career Points - {self.scorer_career_points}")

        # Goalie isn't recorded for empty net goals
        try:
            self.goalie_id = details.get("goalieInNetId")
            self.goalie_name = game.full_roster.get(self.goalie_id, {}).get("fullName", "N/A")
        except IndexError as e:
            logging.warning("No goalie was recorded - not needed so just setting to None. %s", e)
            self.goalie_name = None
            self.goalie_id = None

        # Assist parsing is contained within a function
        self.assists_data = {key: value for key, value in details.items() if "assist" in key}
        gc_assists = gc_details.get("assists")
        self.parse_assists(self.assists_data, gc_assists)
        # print(self.asdict())

        # Add this event to the goals list in the game
        goals_list = (
            self.game.pref_goals
            if self.team_name == self.game.preferred_team.team_name
            else self.game.other_goals
        )
        goals_list.append(self)
        self.game.all_goals.append(self)

        # Now call any functions that should be called when creating a new object
        self.goal_title_text = self.get_goal_title_text()
        self.goal_main_text = self.get_goal_main_text()
        self.social_msg = (
            f"{self.goal_title_text}\n\n{self.goal_main_text}\n\n"
            f"{game.preferred_team.short_name}: {game.preferred_team.score}\n"
            f"{game.other_team.short_name}: {game.other_team.score}"
        )

        # Generate the Discord Embed
        self.discord_embed = self.generate_discord_embed()
        social_ids = socialhandler.send(
            msg=self.social_msg, event=self, game_hashtag=True, discord_embed=self.discord_embed
        )

        # Set any social media IDs
        self.tweet = social_ids.get("twitter")

        # Now that the main goal text is sent, check for milestones
        # TODO: Maybe Playoffs
        if GameType(self.game.game_type) == GameType.REGSEASON:
            if hasattr(self, "scorer_career_points") and (
                self.scorer_career_points % 100 == 0 or self.scorer_career_points == 1
            ):
                logging.info("Goal Scorer - Career Point Milestone - %s", self.scorer_career_points)
                self.milestone_tweet_sender(self.scorer_name, "point", self.scorer_career_points)

            if hasattr(self, "primary_career_assists") and (
                self.primary_career_assists % 100 == 0 or self.primary_career_assists == 1
            ):
                logging.info("Primary - Career Assist Milestone - %s", self.primary_career_assists)
                self.milestone_tweet_sender(self.primary_name, "assist", self.primary_career_assists)

            if hasattr(self, "primary_career_points") and (
                self.primary_career_points % 100 == 0 or self.primary_career_points == 1
            ):
                logging.info("Primary - Career Point Milestone - %s", self.scorer_career_points)
                self.milestone_tweet_sender(self.primary_name, "point", self.primary_career_points)

            if hasattr(self, "secondary_career_assists") and (
                self.secondary_career_assists % 100 == 0 or self.secondary_career_assists == 1
            ):
                logging.info("Secondary - Career Assist Milestone - %s", self.secondary_career_assists)
                self.milestone_tweet_sender(self.secondary_name, "assist", self.secondary_career_assists)

            if hasattr(self, "secondary_career_points") and (
                self.secondary_career_points % 100 == 0 or self.secondary_career_points == 1
            ):
                logging.info("Secondary - Career Point Milestone - %s", self.secondary_career_points)
                self.milestone_tweet_sender(self.secondary_name, "point", self.secondary_career_points)

    def get_goals_gclanding(self):
        gc_landing = livefeed.get_gamecenter_landing(self.game.game_id)
        all_goals = {}
        scoring = gc_landing.get("summary").get("scoring")
        for k in scoring:
            period = k["period"]
            goals = k["goals"]
            for goal in goals:
                time_in_period = goal["timeInPeriod"]
                goal["period"] = period
                unique_key = f"{period}-{time_in_period}"
                all_goals[unique_key] = goal

        return all_goals

    def parse_assists(self, assists_data: dict, gc_assists: list):
        """Since we have to parse assists initially & for scoring changes, move this to a function."""

        self.assists = assists_data
        self.num_assists = len(assists_data)

        if self.num_assists == 2:
            self.primary_id = assists_data.get("assist1PlayerId")
            self.primary_name = self.game.full_roster.get(self.primary_id, {}).get("fullName", "N/A")
            self.primary_season_ttl = [
                x["assistsToDate"] for x in gc_assists if x["playerId"] == self.primary_id
            ][0]

            # Get Primary Game & Career Stats
            self.primary_game_stats = game_scoring_totals(self.primary_name)
            self.primary_game_assists = self.primary_game_stats["assists"] + 1
            self.primary_game_points = self.primary_game_stats["points"] + 1
            self.primary_career_stats = stats.get_player_career_stats(self.primary_id)
            self.primary_career_assists = (
                self.primary_career_stats.get("assists", 0) + self.primary_game_assists
            )
            self.primary_career_points = self.primary_career_stats.get("points", 0) + self.primary_game_points
            print(f"Primary Assist ({self.primary_name}) Assists - {self.primary_game_assists}")
            print(f"Primary Assist ({self.primary_name}) Career Assists - {self.primary_career_assists}")
            print(f"Primary Assist ({self.primary_name}) Points - {self.primary_game_points}")
            print(f"Primary Assist ({self.primary_name}) Career Points - {self.primary_career_points}")

            self.secondary_id = assists_data.get("assist2PlayerId")
            self.secondary_name = self.game.full_roster.get(self.secondary_id, {}).get("fullName", "N/A")
            self.secondary_season_ttl = [
                x["assistsToDate"] for x in gc_assists if x["playerId"] == self.secondary_id
            ][0]

            # Get Secondary Game & Career Stats
            self.secondary_game_stats = game_scoring_totals(self.secondary_name)
            self.secondary_game_assists = self.secondary_game_stats["assists"] + 1
            self.secondary_game_points = self.secondary_game_stats["points"] + 1
            self.secondary_career_stats = stats.get_player_career_stats(self.secondary_id)
            self.secondary_career_assists = (
                self.secondary_career_stats.get("assists", 0) + self.secondary_game_assists
            )
            self.secondary_career_points = (
                self.secondary_career_stats.get("points", 0) + self.secondary_game_points
            )
            print(f"Secondary Assist ({self.secondary_name}) Assists - {self.secondary_game_assists}")
            print(
                f"Secondary Assist ({self.secondary_name}) Career Assists - {self.secondary_career_assists}"
            )
            print(f"Secondary Assist ({self.secondary_name}) Points - {self.secondary_game_points}")
            print(f"Secondary Assist ({self.secondary_name}) Career Points - {self.secondary_career_points}")

            # self.unassisted = False
        elif self.num_assists == 1:
            self.primary_id = assists_data.get("assist1PlayerId")
            self.primary_name = self.game.full_roster.get(self.primary_id, {}).get("fullName", "N/A")
            self.primary_season_ttl = [
                x["assistsToDate"] for x in gc_assists if x["playerId"] == self.primary_id
            ][0]

            # Get Primary Game & Career Stats
            self.primary_game_stats = game_scoring_totals(self.primary_name)
            self.primary_game_assists = self.primary_game_stats["assists"] + 1
            self.primary_game_points = self.primary_game_stats["points"] + 1
            self.primary_career_stats = stats.get_player_career_stats(self.primary_id)
            self.primary_career_assists = self.primary_career_stats["assists"] + self.primary_game_assists
            self.primary_career_points = self.primary_career_stats["points"] + self.primary_game_points
            print(f"Primary Assist ({self.primary_name}) Assists - {self.primary_game_assists}")
            print(f"Primary Assist ({self.primary_name}) Career Assists - {self.primary_career_assists}")
            print(f"Primary Assist ({self.primary_name}) Points - {self.primary_game_points}")
            print(f"Primary Assist ({self.primary_name}) Career Points - {self.primary_career_points}")

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
        """Gets the main goal text / header."""

        if self.team_name == self.game.preferred_team.team_name:
            goal_emoji = "🚨" * self.pref_goals

            if GameType(self.game.game_type) != GameType.REGSEASON:
                goal_milestone_text = ""
            elif self.scorer_career_goals == 1:
                goal_milestone_text = "🎉 FIRST GOAL ALERT!\n\n"
            elif self.scorer_career_goals % 100 == 0:
                goal_ordinal = utils.ordinal(self.scorer_career_goals)
                goal_milestone_text = f"🎉 {goal_ordinal} CAREER GOAL!\n\n"
            else:
                goal_milestone_text = ""

            if self.period_type == "OT":
                goal_title_text = f"{self.team_name} OVERTIME GOAL!!"
            elif self.strength_name != "Even":
                goal_title_text = f"{self.team_name} {self.strength_name} GOAL!"
            elif self.empty_net:
                goal_title_text = f"{self.team_name} empty net GOAL!"
            elif self.pref_goals == 7:
                goal_title_text = f"{self.team_name} TOUCHDOWN!"
            else:
                goal_title_text = f"{self.team_name} GOAL!"
        else:
            goal_title_text = f"{self.team_name} score."
            goal_emoji = "👎🏻" * self.other_goals
            goal_milestone_text = ""

        goal_title_text = f"{goal_milestone_text}{goal_title_text} {goal_emoji}"
        return goal_title_text

    def get_goal_main_text(self, discordfmt=False):
        """Gets the main goal description (players, shots, etc)."""
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
        if self.period_type == "OT":
            goal_scoring_text = (
                f"{self.scorer_name} ({self.scorer_season_ttl}) deflects a shot past "
                f"{self.goalie_name} with {self.period_time_remain_str} left in overtime!"
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
            goal_assist_text = f"🍎 {self.primary_name} ({self.primary_season_ttl})"
            goal_assist_discord = f"🍎 {self.primary_name} ({self.primary_season_ttl})"
        elif self.num_assists == 2:
            goal_assist_text = (
                f"🍎 {self.primary_name} ({self.primary_season_ttl})\n"
                f"🍏 {self.secondary_name} ({self.secondary_season_ttl})"
            )
            goal_assist_discord = (
                f"🍎 {self.primary_name} ({self.primary_season_ttl})\n"
                f"🍏 {self.secondary_name} ({self.secondary_season_ttl})"
            )
        else:
            goal_assist_text = None
            goal_assist_discord = None

        # FIXME: Can I fix this weird if / else - come back to it.
        if goal_count_text is None and goal_assist_text is None:
            goal_main_text = goal_scoring_text
            goal_main_discord = goal_scoring_text
        elif goal_count_text is None:
            goal_main_text = f"{goal_scoring_text}\n\n{goal_assist_text}"
            goal_main_discord = f"{goal_scoring_text}\n\n{goal_assist_discord}"
        elif goal_assist_text is None:
            goal_main_text = f"{goal_count_text} {goal_scoring_text}"
            goal_main_discord = f"{goal_count_text} {goal_scoring_text}"
        else:
            goal_main_text = f"{goal_count_text} {goal_scoring_text}\n\n{goal_assist_text}"
            goal_main_discord = f"{goal_count_text} {goal_scoring_text}\n\n{goal_assist_text}"

        if discordfmt:
            return goal_main_discord

        return goal_main_text

    def generate_discord_embed(self):
        """Generates the custom Discord embed used for Goals."""

        discord_embed = {
            "embeds": [
                {
                    "title": f"**{self.get_goal_title_text()}**",
                    "description": self.get_goal_main_text(discordfmt=True),
                    "color": 13111342,
                    # "timestamp": self.date_time,
                    "footer": {
                        "text": f"Period: {self.period} / Time Remaining: {self.period_time_remain_str}"
                    },
                    # "thumbnail": {"url": "https://i.imgur.com/lCBug3D.png"},
                    # "image": {"url": "attachment://NewJerseyDevils.png"},
                    # "author": {"name": "Hockey Game Bot"},
                    "fields": [
                        {
                            "name": f"**{self.game.preferred_team.team_name}**",
                            "value": f"Score: {self.pref_goals}",
                            "inline": True,
                        },
                        {
                            "name": f"**{self.game.other_team.team_name}**",
                            "value": f"Score: {self.other_goals}",
                            "inline": True,
                        },
                    ],
                }
            ]
        }

        return discord_embed

    def check_for_scoring_changes(self, data: dict):
        """Checks for scoring changes or changes in assists (or even number of assists).

        Args:
            data: Dictionary of a Goal Event from the Live Feed allPlays endpoint

        Returns:
            None if no goal change / new social media string if goal change.
        """

        logging.info(
            "Checking for scoring changes (Team: %s / Event ID: %s / CustomEventId (IDX): %s).",
            self.team_name,
            self.event_id,
            self.custom_event_id,
        )

        details = data.get("details")
        current_scorer_id = details.get("scoringPlayerId")
        current_assists = {key: value for key, value in details.items() if "assist" in key}

        # Check for Changes in Player IDs
        scorer_change = bool(current_scorer_id != self.scorer_id)
        assist_change = bool(current_assists != self.assists_data)

        # Drop Out of This Function if No Scorer Change (Since we Need GC Details Now)
        if not (scorer_change or assist_change):
            return None

        if scorer_change or assist_change:
            logging.info("Scoring Change - %s / Assists Change - %s", scorer_change, assist_change)

        # The GameCenter Landing Page Contains Extra Data the Play by Play API Does Not
        gclanding_all_goals = self.get_goals_gclanding()
        gc_details = gclanding_all_goals.get(self.unique_key)

        if scorer_change:
            old_scorer = self.scorer_name
            goal_scorechange_title = "The scoring on this goal has changed."
            logging.info("Scoring change detected for event ID %s / IDX %s.", self.event_id, self.event_idx)
            self.scorer_name = self.game.full_roster.get(self.scorer_id, {}).get("fullName", "N/A")
            self.scorer_id = current_scorer_id
            self.scorer_season_ttl = gc_details.get("goalsToDate")
            logging.info("Old Scorer: %s / New Scorer: %s", old_scorer, self.scorer_name)

            # Re-parse assists too (a goal scoring change usually means assist changes too)
            gc_assists = gc_details.get("assists")
            self.assists_data = current_assists
            self.parse_assists(self.assists_data, gc_assists)

            if self.num_assists == 0:
                goal_scorechange_text = (
                    f"Now reads as an unassisted goal for {self.scorer_name} " f"({self.scorer_season_ttl})."
                )
            elif self.num_assists == 1:
                goal_scorechange_text = (
                    f"🚨 {self.scorer_name} ({self.scorer_season_ttl})\n"
                    f"🍎 {self.primary_name} ({self.primary_season_ttl})"
                )
            else:
                goal_scorechange_text = (
                    f"🚨 {self.scorer_name} ({self.scorer_season_ttl})\n"
                    f"🍎 {self.primary_name} ({self.primary_season_ttl})\n"
                    f"🍏 {self.secondary_name} ({self.secondary_season_ttl})"
                )

        elif assist_change:
            # A change in assists could be a change or addition of a previously unassisted goal.
            # To check which scenario this is, check previous num_assists before re-parsing.
            goal_scorechange_title = (
                "The assists on this goal have changed." if self.num_assists != 0 else None
            )

            # Re-parse assists too (a goal scoring change usually means assist changes too)
            gc_assists = gc_details.get("assists")
            self.assists_data = current_assists
            self.parse_assists(self.assists_data, gc_assists)

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
                goal_scorechange_text = f"The {self.scorer_name} goal is now unassisted!"
        else:
            goal_scorechange_text = None
            return None

        # Return a string based on
        if goal_scorechange_title is None:
            return goal_scorechange_text
        else:
            return f"{goal_scorechange_title}\n\n{goal_scorechange_text}"

    def milestone_tweet_sender(self, player_name, pointassist, number):
        """A function that generates / sends tweet if a player has hit some type of milestone."""
        number_ordinal = utils.ordinal(number)
        tweet_msg = f"🎉 Congratulations to {player_name} on their {number_ordinal} career {pointassist}!"

        # Checking if self.tweet is None allows us to still use force_send only if the original tweet was sent
        if not self.tweet:
            social_ids = socialhandler.send(tweet_msg, reply=self.tweet, force_send=True, game_hashtag=True)
            self.tweet = social_ids.get("twitter")

    def was_goal_removed(self, all_plays: dict):
        """This function checks if the goal was removed from the livefeed (usually for a Challenge)."""
        goal_still_exists = next((play for play in all_plays if play.get("eventId") == self.event_id), None)

        # If the goal doesn't exist, check the event removal counter & then delete the event
        if not goal_still_exists and self.event_removal_counter < 5:
            logging.warning(
                "A GoalEvent (event ID: %s) is missing (loop #%s) - will check again.",
                self.event_id,
                self.event_removal_counter,
            )
            self.event_removal_counter += 1
            return False
        elif not goal_still_exists and self.event_removal_counter == 5:
            logging.warning(
                "A GoalEvent (event ID: %s) has been missing for 5 checks - deleting.", self.event_id
            )
            return True
        else:
            return False


class ShotEvent(GenericEvent):
    """A Shot object contains all shot-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Shots have a secondary type & a team name
        self.shot_type = data.get("details").get("shotType")
        self.event_team_id = data.get("details").get("eventOwnerTeamId")

        # Mark Shots as Corsi or Fenwick
        corsi_events = ["missed-shot", "blocked-shot", "shot-on-goal"]
        fenwick_events = ["missed-shot", "shot-on-goal"]
        self.corsi = True if self.event_type in corsi_events else False
        self.fenwick = True if self.event_type in fenwick_events else False

        # Get the Players Section
        details = data.get("details")
        self.shooter_id = details.get("shootingPlayerId")
        self.goalie_id = details.get("goalieInNetId")
        self.shooter_name = game.full_roster.get(self.shooter_id, {}).get("fullName", "N/A")
        self.goalie_name = game.full_roster.get(self.goalie_id, {}).get("fullName", None)

        # Get the Coordinates Section
        self.x = details.get("xCoord", 0)
        self.y = details.get("yCoord", 0)
        self.shot_distance = utils.calculate_shot_distance(self.x, self.y)

        # Now call any functions that should be called when creating a new object
        # (FOR NOW) we only checked for missed shots that hit the post.
        # TODO - Check a few games to see if they still record crossbars / posts.
        if self.crossbar_or_post():
            self.generate_social_msg()
            ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True)

    def crossbar_or_post(self):
        """Checks shot text to determine if the shot was by the preferred
        team and hit the crossbar or post."""

        return False

        # This checks if the shot was taken by the preferred team
        if self.event_team_id != self.game.preferred_team.team_id:
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
        """Used for generating the message that will be logged or sent to social media."""
        if "crossbar" in self.description.lower():
            shot_hit = "crossbar"
        elif "goalpost" in self.description.lower():
            shot_hit = "post"
        else:
            shot_hit = None

        self.social_msg = (
            f"DING! 🛎\n\n{self.shooter_name} hits the {shot_hit} from {self.shot_distance} "
            f"away with {self.period_time_remain} remaining in the {self.period_ordinal} period."
        )


class PenaltyEvent(GenericEvent):
    """A Faceoff object contains all faceoff-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Penalties have some extra result attributes
        details = data.get("details")
        self.secondary_type = details.get("descKey")
        # self.secondary_type = self.penalty_type_fixer(details.get("descKey").lower())
        self.severity_code = details.get("typeCode")
        self.severity = self.penalty_severity_code_mapper(self.severity_code).lower()
        self.minutes = details.get("duration")
        self.penalty_length_ss = 60 * self.minutes

        # If penalty secondaryType is 'minor' (seems to be a recent bug) - skip, dump & try again next loop
        if self.secondary_type == "minor":
            logging.warning("BAD Secondary Type Found: %s", details)
            raise ValueError("A penalty can not have a secondary type of 'minor' - skip & try again.")

        # Assign Penalty Team
        home_team = self.game.home_team
        away_team = self.game.away_team
        preferred_team = self.game.preferred_team
        other_team = self.game.other_team

        self.penalty_team_id = details.get("eventOwnerTeamId")
        self.penalty_team = home_team if self.penalty_team_id == home_team.team_id else away_team
        self.penalty_team_name = self.penalty_team.short_name
        if self.penalty_team_name == preferred_team.team_name:
            self.penalty_team_obj = preferred_team
            self.powerplay_team_obj = other_team
            print("Penalty Team:", self.penalty_team_obj.team_name)
            print("PP Team:", self.powerplay_team_obj.team_name)
        else:
            self.penalty_team_obj = other_team
            self.powerplay_team_obj = preferred_team
            print("Penalty Team:", self.penalty_team_obj.team_name)
            print("PP Team:", self.powerplay_team_obj.team_name)

        # Setup the Penalty Situation Object
        penalty_situation = self.game.penalty_situation
        penalty_situation.new_penalty(
            penalty_ss=self.period_time_remain_ss,
            penalty_length=self.penalty_length_ss,
            pp_team=self.powerplay_team_obj,
        )

        # Get the Players
        self.committed_by_id = details.get("committedByPlayerId")
        self.committed_by_name = game.full_roster.get(self.committed_by_id, {}).get("fullName", "N/A")
        self.committed_by_game_ttl = (
            game_event_total(PenaltyEvent, self.committed_by_name, "committed_by_name") + 1
        )

        self.drawn_by_id = details.get("drawnByPlayerId")
        self.drawn_by_name = game.full_roster.get(self.drawn_by_id, {}).get("fullName", "N/A")

        self.served_by_id = details.get("")
        self.served_by_name = game.full_roster.get(self.served_by_id, {}).get("fullName", "N/A")

        # If penalty is a bench minor & served_by is empty, try again next loop
        if self.severity == "bench minor" and not self.served_by_id:
            raise ValueError("A bench-minor penalty should have a servedBy player.")

        # Penalty Shot Fixes
        if self.minutes == 0 and not self.drew_by_name:
            raise ValueError(
                "A 0-minute penalty (usually a penalty shot) requires a drewBy attribute for the shooter."
            )
        elif self.minutes == 0 and self.drew_by_name:
            self.secondary_type = self.secondary_type.replace("ps - ", "")
            self.penalty_shot = True
        else:
            self.penalty_shot = False

        # Get the Coordinates Section
        self.x = details.get("xCoord", 0)
        self.y = details.get("yCoord", 0)

        # Determine the Penalty Zone
        penalty_zone_code = details.get("zoneCode")
        penalty_zone = self.penalty_zone_code_mapper(penalty_zone_code)
        self.penalty_zone_text = f" in the {penalty_zone} zone" if penalty_zone else ""

        # Now call any functions that should be called when creating a new object
        # TODO: Figure out if theres a way to check for offsetting penalties
        self.penalty_main_text = self.get_skaters()
        self.penalty_rankstat_text = self.get_penalty_stats()
        self.generate_social_msg(self.penalty_shot)

        # Twitter API V2 - Do Not Send Penalty Events
        # ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True)

    def penalty_type_fixer(self, original_type):
        """A function that converts some poorly named penalty types."""
        secondarty_types = {
            "delaying game - puck over glass": "delay of game (puck over glass)",
            "interference - goalkeeper": "goalie interference",
            "missing key [pd_151]": "delay of game (unsuccessful challenge)",
            "hi-sticking": "high sticking",
        }
        return secondarty_types.get(original_type, original_type)

    def penalty_severity_code_mapper(self, code):
        """A function that maps typeCodes to actual penalty strings."""
        code_mapping = {"MIN": "minor"}

        return code_mapping.get(code, code)

    def penalty_zone_code_mapper(self, code):
        """A function that maps typeCodes to actual penalty strings."""
        code_mapping = {"D": "defensive", "O": "offensive", "N": "neutral"}

        return code_mapping.get(code, code)

    def get_skaters(self):
        """Used for determining how many skaters were on the ice at the time of event."""

        power_play_strength = self.game.power_play_strength
        penalty_on_skaters = self.penalty_team_obj.skaters
        penalty_draw_skaters = self.powerplay_team_obj.skaters

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
        penalty_text_skaters = ""

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
                penalty_text_skaters = f"{pref_short_name} will have to kill off a two-man advantage!"
            elif pref_skaters == 3 and other_skaters == 5:
                penalty_text_skaters = f"{pref_short_name} will have a 4-on-3 penalty to kill!"
        else:
            logging.info("Unkown penalty skater combination - use default skater logic.")

        if self.served_by_name is not None:
            penalty_text_players = (
                f"{self.committed_by_name} takes a {self.minutes}-minute {self.severity} "
                f"penalty for {self.secondary_type} (served by {self.served_by_name}) with "
                f"{self.period_time_remain} remaining in the {self.period_ordinal} period. "
                # f"That's his {utils.ordinal(self.penalty_on_game_ttl)} penalty of the game. "
                f"{penalty_text_skaters}"
            )
        elif self.severity == "game misconduct":
            penalty_text_players = (
                f"{self.committed_by_name} takes a {self.minutes}-minute {self.severity} "
                f"penalty and won't return to the game. The penalty occurred with "
                f"{self.period_time_remain} remaining in the {self.period_ordinal} period. "
                # f"That's his {utils.ordinal(self.penalty_on_game_ttl)} penalty of the game. "
                f"{penalty_text_skaters}"
            )
        else:
            penalty_text_players = (
                f"{self.committed_by_name} takes a {self.minutes}-minute {self.severity} penalty"
                f"{self.penalty_zone_text} for {self.secondary_type} and heads to the "
                f"penalty box with {self.period_time_remain} remaining in the {self.period_ordinal} period. "
                # f"That's his {utils.ordinal(self.penalty_on_game_ttl)} penalty of the game. "
                f"{penalty_text_skaters}"
            )

        return penalty_text_players

    def get_penalty_stats(self):
        """Used for determining penalty kill / power play stats."""
        # penalty_on_stats = self.penalty_team_obj.get_stat_and_rank("penaltyKillPercentage")
        penalty_on_short_name = self.penalty_team_obj.short_name
        penalty_on_stat = self.penalty_team_obj.pk_pct
        penalty_on_rank = self.penalty_team_obj.pk_rank
        penalty_on_rankstat_text = f"{penalty_on_short_name} PK: {penalty_on_stat} ({penalty_on_rank})"

        # penalty_draw_stats = self.powerplay_team_obj.get_stat_and_rank("powerPlayPercentage")
        penalty_draw_short_name = self.powerplay_team_obj.short_name
        penalty_draw_stat = self.powerplay_team_obj.pp_pct
        penalty_draw_rank = self.powerplay_team_obj.pp_rank
        penalty_draw_rankstat_text = (
            f"{penalty_draw_short_name} PP: {penalty_draw_stat} ({penalty_draw_rank})"
        )

        penalty_rankstat_text = f"{penalty_on_rankstat_text}\n{penalty_draw_rankstat_text}"
        return penalty_rankstat_text

    def generate_social_msg(self, penaltyshot=False):
        """Used for generating the message that will be logged or sent to social media."""
        if penaltyshot:
            self.social_msg = (
                f"⚠️ PENALTY SHOT!\n\n{self.penalty_on_name} is called for {self.secondary_type} with "
                f"{self.period_time_remain} remaining in the {self.period_ordinal} period. "
                f"{self.drew_by_name} has been awarded a penalty shot!"
            )
        elif self.game.power_play_strength != "Even":
            self.social_msg = f"{self.penalty_main_text}\n\n{self.penalty_rankstat_text}"
        else:
            self.social_msg = f"{self.penalty_main_text}"


class ChallengeEvent(GenericEvent):
    """A Challenge object contains all challenge-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    This event needs to be aware of events around it so it can understand reversals.
    """

    cache = Cache(__name__)


class ShootoutEvent(GenericEvent):
    """A Shootout object contains all shootout-related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)

        # Check if the event is actual shootout event
        non_shootout_events = [
            "PERIOD_START",
            "SHOOTOUT_COMPLETE",
            "PERIOD_END",
            "PERIOD_OFFICIAL",
            "GAME_OFFICIAL",
        ]
        if self.event_type in non_shootout_events:
            logging.info(
                "A non-tracking shootout event (%s) detected - just return & skip this.", self.event_type
            )
            return

        if self.event_type == "PERIOD_READY":
            self.social_msg = f"The shootout is underway at {self.game.venue}!"
            social_ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True)
            self.game.shootout.last_tweet = social_ids.get("twitter")
            return

        # Grab the event team from the Results section
        results = data.get("result")
        self.event_team = data.get("team").get("name")

        # Get the Players Section
        players = data.get("players")
        shooter = [x for x in players if x.get("playerType").lower() in ("scorer", "shooter")]
        goalie = [x for x in players if x.get("playerType").lower() == "goalie"]

        # Handle Scorer name, id & totals
        self.shooter_name = shooter[0].get("player").get("fullName")
        self.shooter_id = shooter[0].get("player").get("id")
        self.goalie_name = goalie[0].get("player").get("fullName") if goalie else None
        self.goalie_id = goalie[0].get("player").get("id") if goalie else None

        shootout_tracking_emoji = "✅" if self.event_type == "GOAL" else "❌"
        logging.info("Shootout event (%s) detected for %s.", self.event_type, self.event_team)

        # Preferred Team Shoots
        if self.event_team == game.preferred_team.team_name:
            game.shootout.preferred_score.append(shootout_tracking_emoji)
            hit_crossbar_post = self.crossbar_or_post()
            if self.event_type == "GOAL":
                self.shootout_event_text = f"{self.shooter_name} shoots & scores! 🚨"
            elif self.event_type == "SHOT":
                goalie_string = f" by {self.goalie_name}." if self.goalie_name else "."
                self.shootout_event_text = f"{self.shooter_name}'s shot saved{goalie_string} 😠"
            elif hit_crossbar_post:
                self.shootout_event_text = f"{self.shooter_name} shoots & hits the {hit_crossbar_post}. 😠"
            else:
                self.shootout_event_text = f"{self.shooter_name} shoots & misses the net. 😠"

        # Other Team Shoots
        if self.event_team == game.other_team.team_name:
            game.shootout.other_score.append(shootout_tracking_emoji)
            hit_crossbar_post = self.crossbar_or_post()
            if self.event_type == "GOAL":
                self.shootout_event_text = f"{self.shooter_name} shoots & scores. 👎🏻"
            elif self.event_type == "SHOT":
                goalie_string = f" by {self.goalie_name}!" if self.goalie_name else "!"
                self.shootout_event_text = f"{self.shooter_name}'s shot saved{goalie_string} 🛑"
            elif hit_crossbar_post:
                self.shootout_event_text = f"{self.shooter_name} shoots & hits the {hit_crossbar_post}! 🛎"
            else:
                self.shootout_event_text = f"{self.shooter_name} shoots & misses the net! 🛑"

        # Now that all parsing is done, generate the social media message
        self.generate_social_msg()
        last_tweet = self.game.shootout.last_tweet
        social_ids = socialhandler.send(msg=self.social_msg, event=self, game_hashtag=True, reply=last_tweet)
        self.game.shootout.last_tweet = social_ids.get("twitter")
        self.game.shootout.shots += 1

    def crossbar_or_post(self):
        """Checks shot text to determine if the shootout shot hit the crossbar or post."""
        hit_keywords = ["crossbar", "goalpost"]

        # If any of the hit keywords appear in the description of the event
        if any(x in self.description.lower() for x in hit_keywords):
            if "crossbar" in self.description.lower():
                return "crossbar"
            elif "goalpost" in self.description.lower():
                return "post"
            else:
                return False
        else:
            return False

    def generate_social_msg(self):
        shootout_preferred_score = " - ".join(self.game.shootout.preferred_score)
        shootout_other_score = " - ".join(self.game.shootout.other_score)
        self.social_msg = (
            f"{self.shootout_event_text}\n\n"
            f"{self.game.preferred_team.short_name}: {shootout_preferred_score}\n"
            f"{self.game.other_team.short_name}: {shootout_other_score}"
        )


class GameEndEvent(GenericEvent):
    """A Game End object contains all game end related attributes and extra methods.
    It is a subclass of the GenericEvent class with the most basic attributes.
    # TODO: Determine if we need this or if the game goes FINAL as this event is posted
    """

    cache = Cache(__name__)

    def __init__(self, data: dict, game: Game):
        super().__init__(data, game)
        self.winner = "home" if self.home_goals > self.away_goals else "away"
        logging.info("Game End Event detected before game state is Final - manually setting!")
        self.game.game_state = "Final"
