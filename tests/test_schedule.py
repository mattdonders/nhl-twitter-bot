""" Tests for 'nhlapi.schedule' module. """

import responses
import requests

from hockeygamebot.helpers import utils
from hockeygamebot.nhlapi import schedule


@responses.activate
def test_schedule_no_game():
    config = utils.load_config()
    date = utils.date_parser("2019-06-27")
    json_response = {
        "copyright": "NHL and the NHL Shield are registered trademarks of the National Hockey League. NHL and NHL team marks are the property of the NHL and its teams. © NHL 2019. All Rights Reserved.",
        "totalItems": 0,
        "totalEvents": 0,
        "totalGames": 0,
        "totalMatches": 0,
        "wait": 10,
        "dates": [],
    }
    url = (
        "{api}/schedule?teamId={id}&expand="
        "schedule.broadcasts,schedule.teams&date={date:%Y-%m-%d}".format(
            api=config["endpoints"]["nhl_endpoint"], id=1, date=date
        )
    )
    responses.add(responses.GET, url, json=json_response, content_type="application/json")

    game_today, game_info = schedule.is_game_today(1, date)

    assert not game_today
    assert game_info == json_response


@responses.activate
def test_schedule_one_game():
    config = utils.load_config()
    date = utils.date_parser("2019-10-04")
    json_response = {
        "copyright": "NHL and the NHL Shield are registered trademarks of the National Hockey League. NHL and NHL team marks are the property of the NHL and its teams. © NHL 2019. All Rights Reserved.",
        "totalItems": 1,
        "totalEvents": 0,
        "totalGames": 1,
        "totalMatches": 0,
        "wait": 10,
        "dates": [
            {
                "date": "2019-10-04",
                "totalItems": 1,
                "totalEvents": 0,
                "totalGames": 1,
                "totalMatches": 0,
                "games": [
                    {
                        "gamePk": 2019020013,
                        "link": "/api/v1/game/2019020013/feed/live",
                        "gameType": "R",
                        "season": "20192020",
                        "gameDate": "2019-10-04T23:00:00Z",
                        "status": {
                            "abstractGameState": "Preview",
                            "codedGameState": "1",
                            "detailedState": "Scheduled",
                            "statusCode": "1",
                            "startTimeTBD": False,
                        },
                        "teams": {
                            "away": {
                                "leagueRecord": {"wins": 0, "losses": 0, "ot": 0, "type": "league"},
                                "score": 0,
                                "team": {
                                    "id": 52,
                                    "name": "Winnipeg Jets",
                                    "link": "/api/v1/teams/52",
                                    "venue": {
                                        "id": 5058,
                                        "name": "Bell MTS Place",
                                        "link": "/api/v1/venues/5058",
                                        "city": "Winnipeg",
                                        "timeZone": {
                                            "id": "America/Winnipeg",
                                            "offset": -5,
                                            "tz": "CDT",
                                        },
                                    },
                                    "abbreviation": "WPG",
                                    "teamName": "Jets",
                                    "locationName": "Winnipeg",
                                    "firstYearOfPlay": "2011",
                                    "division": {
                                        "id": 16,
                                        "name": "Central",
                                        "nameShort": "CEN",
                                        "link": "/api/v1/divisions/16",
                                        "abbreviation": "C",
                                    },
                                    "conference": {
                                        "id": 5,
                                        "name": "Western",
                                        "link": "/api/v1/conferences/5",
                                    },
                                    "franchise": {
                                        "franchiseId": 35,
                                        "teamName": "Jets",
                                        "link": "/api/v1/franchises/35",
                                    },
                                    "shortName": "Winnipeg",
                                    "officialSiteUrl": "http://winnipegjets.com/",
                                    "franchiseId": 35,
                                    "active": True,
                                },
                            },
                            "home": {
                                "leagueRecord": {"wins": 0, "losses": 0, "ot": 0, "type": "league"},
                                "score": 0,
                                "team": {
                                    "id": 1,
                                    "name": "New Jersey Devils",
                                    "link": "/api/v1/teams/1",
                                    "venue": {
                                        "name": "Prudential Center",
                                        "link": "/api/v1/venues/null",
                                        "city": "Newark",
                                        "timeZone": {
                                            "id": "America/New_York",
                                            "offset": -4,
                                            "tz": "EDT",
                                        },
                                    },
                                    "abbreviation": "NJD",
                                    "teamName": "Devils",
                                    "locationName": "New Jersey",
                                    "firstYearOfPlay": "1982",
                                    "division": {
                                        "id": 18,
                                        "name": "Metropolitan",
                                        "nameShort": "Metro",
                                        "link": "/api/v1/divisions/18",
                                        "abbreviation": "M",
                                    },
                                    "conference": {
                                        "id": 6,
                                        "name": "Eastern",
                                        "link": "/api/v1/conferences/6",
                                    },
                                    "franchise": {
                                        "franchiseId": 23,
                                        "teamName": "Devils",
                                        "link": "/api/v1/franchises/23",
                                    },
                                    "shortName": "New Jersey",
                                    "officialSiteUrl": "http://www.newjerseydevils.com/",
                                    "franchiseId": 23,
                                    "active": True,
                                },
                            },
                        },
                        "venue": {"name": "Prudential Center", "link": "/api/v1/venues/null"},
                        "content": {"link": "/api/v1/game/2019020013/content"},
                    }
                ],
                "events": [],
                "matches": [],
            }
        ],
    }
    url = (
        "{api}/schedule?teamId={id}&expand="
        "schedule.broadcasts,schedule.teams&date={date:%Y-%m-%d}".format(
            api=config["endpoints"]["nhl_endpoint"], id=1, date=date
        )
    )
    responses.add(responses.GET, url, json=json_response, content_type="application/json")

    game_today, game_info = schedule.is_game_today(1, date)
    assert game_today
    assert game_info == json_response["dates"][0]["games"][0]
