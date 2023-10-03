from enum import Enum


class V1GameType(Enum):
    PREASEASON = "PR"
    REGSEASON = "R"
    PLAYOFFS = "P"


class GameType(Enum):
    PRESEASON = 1
    REGSEASON = 2
    PLAYOFFS = 3
