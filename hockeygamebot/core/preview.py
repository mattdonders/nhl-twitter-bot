# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Preview State.
"""

import logging

from hockeygamebot.helpers import utils
from hockeygamebot.models.gametype import GameType
from hockeygamebot.nhlapi import schedule, thirdparty


def generate_game_preview(game):
    """Generates and sends the game preview to social media.

    This function runs when the game is in Preview State and it is not yet
    game time. Should only run once at the morning scheduled time.

    Args:
        game: Game Object

    Returns:
        sleep_time: Seconds to sleep until next action
    """

    logging.info("Generating Game Preview images & social media posts.")
    logging.info("Game Date: Local - %s, UTC - %s", game.game_time_local, game.date_time)

    # Load our Config
    config = utils.load_config()
    preview_sleep_time = config["script"]["preview_sleep_time"]
    preview_sleep_mins = preview_sleep_time / 60

    # Get the preferred team, other teams & homeaway from the Game object
    pref_team, other_team = game.get_preferred_team()
    pref_team_homeaway = game.preferred_team.home_away

    # Get Team Hashtags
    pref_hashtag = utils.team_hashtag(pref_team.team_name, game.game_type)
    other_hashtag = utils.team_hashtag(other_team.team_name, game.game_type)

    # Generate the propert clock emoji for the game time
    clock_emoji = utils.clock_emoji(game.game_time_local)

    # If the game is a playoff game, our preview text changes slightly
    if GameType(game.game_type) == GameType.PLAYOFFS:
        preview_text_teams = (
            f"Tune in {game.game_time_of_day} for Game #{game.game_id_playoff_game} when the "
            f"{pref_team.team_name} take on the {other_team.team_name} at {game.venue}."
        )
    else:
        preview_text_teams = (
            f"Tune in {game.game_time_of_day} when the {pref_team.team_name} "
            f"take on the {other_team.team_name} at {game.venue}."
        )

    # Generate clock, channel & hashtag emoji text preview
    preview_text_emojis = (
        f"{clock_emoji}: {game.game_time_local}\n"
        f"\U0001F4FA: {pref_team.tv_channel}\n"
        f"\U00000023\U0000FE0F\U000020E3: {game.game_hashtag}"
    )

    # Generate final preview tweet text
    preview_tweet_text = f"{preview_text_teams}\n\n{preview_text_emojis}"

    # Generate Season Series Data
    season_series = schedule.season_series(game.game_id, pref_team, other_team)
    season_series_string = season_series[0]

    if season_series_string is None:
        season_series_tweet_text = (
            f"This is the first meeting of the season between "
            f"the {pref_team.short_name} & the {other_team.short_name}.\n\n"
            f"{pref_hashtag} {other_hashtag} {game.game_hashtag}"
        )

    logging.info(preview_tweet_text)
    logging.info(season_series_tweet_text)
    game.pregametweets["core"] = True


def game_preview_others(game):
    """ Other game preview information (excluding our core game preview).
        This includes things like goalies, lines, referees, etc.

    This function runs when the game is in Preview State and it is not yet
    game time. Runs every xxx minutes (configured in config.yaml file).

    Args:
        game: Game Object

    Returns:
        sleep_time: Seconds to sleep until next action
    """
    # All of the below functions containg information from non-NHL API sites
    # Each one is wrapped in a try / except just in case.

    # Load our Config
    config = utils.load_config()
    preview_sleep_time = config["script"]["preview_sleep_time"]
    preview_sleep_mins = preview_sleep_time / 60

    # Get the preferred team, other teams & homeaway from the Game object
    pref_team, other_team = game.get_preferred_team()
    pref_team_homeaway = game.preferred_team.home_away

    if not game.pregametweets["goalies_pref"] or not game.pregametweets["goalies_other"]:
        # goalies_confirmed_values = ("Confirmed", "Likely")
        try:
            goalies_df = thirdparty.dailyfaceoff_goalies(pref_team, other_team, pref_team_homeaway)
            logging.info(goalies_df)
        except Exception as e:
            logging.error("Exception getting Daily Faceoff goalies - try again next loop.")
            logging.error(e)

        try:
            goalie_away = goalies_df.get("away").get("name")
            goalie_home = goalies_df.get("home").get("name")
            goalie_hr_home = thirdparty.hockeyref_goalie_against_team(
                goalie_home, game.away_team.team_name
            )
            logging.info(goalie_hr_home)
            goalie_hr_away = thirdparty.hockeyref_goalie_against_team(
                goalie_away, game.home_team.team_name
            )
            logging.info(goalie_hr_away)
        except Exception as e:
            logging.error("Exception getting Hockey Reference splits - try again next loop.")
            logging.error(e)

    if not game.pregametweets["lines"]:
        try:
            lines = thirdparty.dailyfaceoff_lines(game, pref_team)
            logging.info(lines)
        except Exception as e:
            logging.error("Exception getting lines from Daily Faceoff - try again next loop.")
            logging.error(e)

    if not game.pregametweets["refs"]:
        try:
            officials = thirdparty.scouting_the_refs(game, pref_team)
            logging.info(officials)
        except Exception as e:
            logging.error("Exception getting Scouting the Refs information - try again next loop.")
            logging.error(e)

    # Check if all pre-game tweets are sent
    # And return time to sleep
    all_pregametweets = all(value is True for value in game.pregametweets.values())

    if not all_pregametweets and game.game_time_countdown > preview_sleep_time:
        logging.info(
            "Game State is Preview & all pre-game tweets are not sent. "
            "Sleep for 30 minutes & check again."
        )
        return preview_sleep_time
    elif not all_pregametweets and game.game_time_countdown < preview_sleep_time:
        logging.warning(
            "Game State is Preview & all pre-game tweets are not sent. "
            "Less than %s minutes until game time so we skip these today."
            "If needed, we try to get lines at the end of the game for advanced stats.",
            preview_sleep_mins,
        )
        return game.game_time_countdown
    else:
        logging.info(
            "Game State is Preview & all tweets are sent. Sleep for %s seconds until game time.",
            game.game_time_countdown,
        )
        return game.game_time_countdown
