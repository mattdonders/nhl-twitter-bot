from enum import Enum


class V1GameState(Enum):
    """Enum for tracking the abstractGameState attribute."""

    PREVIEW = "Preview"
    LIVE = "Live"
    FINAL = "Final"


class V1GameStateCode(Enum):
    """Enum for tracking the codedGameState attribute."""

    PREVIEW = 1
    PREGAME = 2
    LIVE = 3
    CRITICAL = 4
    GAMEOVER = 5
    NEWLYFINAL = 6
    FINAL = 7
    SCHEDULED = 8
    POSTPONED = 9


# THESE ARE THE NEW NHL API ENUMS


class GameState(Enum):
    """Enum for tracking the <TBD> Game State attribute."""

    FUTURE = "FUT"
    PREGAME = "PRE"
    SOFT_FINAL = "OVER"
    HARD_FINAL = "FINAL"
    FINAL = "FINAL"  # TDB - see if we should use hard final / soft final separately
    OFFICIAL = "OFF"
    LIVE = "LIVE"
    CRITICAL = "CRIT"

    @classmethod
    def all_finals(cls):
        return [cls.FINAL.value, cls.OFFICIAL.value, cls.SOFT_FINAL.value, cls.HARD_FINAL.value]

    @classmethod
    def all_lives(cls):
        return [cls.LIVE.value, cls.CRITICAL.value]

    @classmethod
    def all_pregames(cls):
        return [cls.FUTURE.value, cls.PREGAME.value]


class GameScheduleState(Enum):
    """Enum for tracking the <TBD / Game Scheduled> attribute."""

    SCHEDULED = "OK"
    TO_BE_DETERMINED = "TBD"
    POSTPONED = "PPD"
    SUSPENDED = "SUSP"
    CANCELLED = "CNCL"
