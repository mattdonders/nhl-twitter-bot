# -*- coding: utf-8 -*-

"""
This module contains all functions pertaining to a game in Preview State.
"""

import logging

from hockeygamebot.helpers import utils
from hockeygamebot.models.gametype import GameType
from hockeygamebot.nhlapi import schedule


def generate_game_preview(game):
    """Generates and sends the game preview to social media.

    This function runs when the game is in Preview State and it is not yet
    game time. Should only run once at the morning scheduled time.

    Args:
        game: Game Object

    Returns:
        None
    """

    logging.info("Generating Game Preview images & social media posts.")
    logging.info("Game Date: Local - %s, UTC - %s", game.game_time_local, game.date_time)

    # Get the preferred team, other teams & homeaway from the Game object
    preferred_team, other_team = game.get_preferred_team()
    pref_team_homeaway = game.preferred_team.home_away

    # Get Team Hashtags
    pref_hashtag = utils.team_hashtag(preferred_team.team_name, game.game_type)
    other_hashtag = utils.team_hashtag(other_team.team_name, game.game_type)

    # Generate the propert clock emoji for the game time
    clock_emoji = utils.clock_emoji(game.game_time_local)

    # If the game is a playoff game, our preview text changes slightly
    if GameType(game.game_type) == GameType.PLAYOFFS:
        preview_text_teams = (
            f"Tune in {game.game_time_of_day} for Game #{game.game_id_playoff_game} when the "
            f"{preferred_team.team_name} take on the {other_team.team_name} at {game.venue}."
        )
    else:
        preview_text_teams = (
            f"Tune in {game.game_time_of_day} when the {preferred_team.team_name} "
            f"take on the {other_team.team_name} at {game.venue}."
        )

    # Generate clock, channel & hashtag emoji text preview
    preview_text_emojis = (
        f"{clock_emoji}: {game.game_time_local}\n"
        f"\U0001F4FA: {preferred_team.tv_channel}\n"
        f"\U00000023\U0000FE0F\U000020E3: {game.game_hashtag}"
    )

    # Generate final preview tweet text
    preview_tweet_text = f"{preview_text_teams}\n\n{preview_text_emojis}"

    # Generate Season Series Data
    season_series = schedule.season_series(game.game_id, game.preferred_team, game.other_team)
    season_series_string = season_series[0]

    if season_series_string is None:
        season_series_tweet_text = (
            f"This is the first meeting of the season between "
            f"the {game.preferred_team.short_name} & the {game.other_team.short_name}.\n\n"
            f"{pref_hashtag} {other_hashtag} {game.game_hashtag}"
        )

    logging.info(preview_tweet_text)
    logging.info(season_series_tweet_text)
