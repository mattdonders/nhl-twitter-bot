"""
The main application entrypoint in the hockeygamebot script!
"""

# pylint: disable=broad-except, too-many-statements, too-many-branches, too-many-nested-blocks

import json
import logging
import os
import sys
import time
from datetime import datetime

# If running as app.py directly, we may need to import the module manually.
try:
    import hockeygamebot  # pylint: disable=unused-import
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from hockeygamebot.core import final, live, preview
from hockeygamebot.definitions import VERSION
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.game import Game
from hockeygamebot.models.gamestate import GameState
from hockeygamebot.models.globalgame import GlobalGame
from hockeygamebot.models.team import Team
from hockeygamebot.nhlapi import livefeed, nst, roster, schedule
from hockeygamebot.social import socialhandler


def start_game_loop(game: Game):
    """ The main game loop - tracks game state & calls all relevant functions.

    Args:
        game: Current Game object

    Returns:
        None
    """

    args = arguments.get_arguments()
    config = utils.load_config()

    # ------------------------------------------------------------------------------
    # START THE MAIN LOOP
    # ------------------------------------------------------------------------------

    while True:
        if GameState(game.game_state) == GameState.PREVIEW:
            livefeed_resp = livefeed.get_livefeed(game.game_id)
            game.update_game(livefeed_resp)

            if game.game_time_countdown > 0:
                logging.info("Game is in Preview state - send out all pregame information.")
                # The core game preview function should run only once
                if not game.preview_socials.core_sent:
                    preview.generate_game_preview(game)

                # The other game preview function should run every xxx minutes
                # until all pregame tweets are sent or its too close to game time
                sleep_time = preview.game_preview_others(game)
                game.preview_socials.increment_counter()
                time.sleep(sleep_time)
            else:
                logging.info(
                    "Game is in Preview state, but past game start time - sleep for a bit "
                    "& update game attributes so we detect when game goes live."
                )
                # Starting Lineups are posted ~5 minutes before game time.
                sleep_time = config["script"]["pregame_sleep_time"] - 300
                time.sleep(sleep_time)

                # Try to get the starters from the score report
                preview.get_starters(game)


        elif GameState(game.game_state) == GameState.LIVE:
            try:
                logging.info("-" * 80)
                logging.info(
                    "Game is LIVE (loop #%s) - checking events after event Idx %s.",
                    game.live_loop_counter,
                    game.last_event_idx,
                )

                # On my development machine, this command starts the files for this game
                # python -m hockeygamebot --console --notweets --team 'Vancouver Canucks' --date '2019-09-17' --localdata
                if args.localdata:
                    logging.info(
                        "SIMULATION DETECTED - running a live game replay for Game %s (%s vs. %s).",
                        game.game_id,
                        game.home_team.team_name,
                        game.away_team.team_name,
                    )
                    directory = "/Users/mattdonders/Development/python/devils-goal-twitter-bitbucket/scratchpad/feed-samples"
                    for file in sorted(os.listdir(directory)):
                        filename = os.fsdecode(file)
                        if filename.endswith(".json"):
                            feed_json = os.path.join(directory, filename)
                            with open(feed_json) as json_file:
                                data = json.load(json_file)

                            live.live_loop(livefeed=data, game=game)
                            game.update_game(data)
                            time.sleep(0.1)

                livefeed_resp = livefeed.get_livefeed(game.game_id)
                # all_events = live.live_loop(livefeed=livefeed_resp, game=game)

                # Update all game attributes & check for goalie pulls
                game.update_game(livefeed_resp)
                game.goalie_pull_updater(livefeed_resp)

                # Logging (Temporarily) for Penalty Killed Tweets
                logging.info(
                    "Current Period Info: %s - %s",
                    game.period.current_ordinal,
                    game.period.time_remaining,
                )
                logging.info(
                    "Pref On Ice: %s - %s",
                    len(game.preferred_team.onice),
                    game.preferred_team.onice,
                )
                logging.info(
                    "Other On Ice: %s - %s", len(game.other_team.onice), game.other_team.onice
                )

                if not game.period.current_oneminute_sent:
                    live.minute_remaining_check(game)

                # Pass the live feed response to the live loop (to parse events)
                live.live_loop(livefeed=livefeed_resp, game=game)
                # game_events = get_game_events(game_obj)
                # loop_game_events(game_events, game_obj)

            except Exception as error:
                logging.error("Uncaught exception in live game loop - see below error.")
                logging.error(error)

            # Perform any intermission score changes, charts & sleep
            if game.period.intermission:
                # Uncomment this tomorrow to test the function relocation
                live_sleep_time = live.intermission_loop(game)

            else:
                live_sleep_time = config["script"]["live_sleep_time"]
                logging.info(
                    "Sleeping for configured live game time (%ss).",
                    config["script"]["live_sleep_time"],
                )

            # Now increment the counter sleep for the calculated time above
            game.live_loop_counter += 1
            time.sleep(live_sleep_time)

        elif GameState(game.game_state) == GameState.FINAL:
            logging.info(
                "Game is now over & 'Final' - run end of game functions with increased sleep time."
            )

            livefeed_resp = livefeed.get_livefeed(game.game_id)
            game.update_game(livefeed_resp)

            # If (for some reason) the bot was started after the end of the game
            # We need to re-run the live loop once to parse all of the events
            if not game.events:
                logging.info(
                    "Bot started after game ended, pass livefeed into event factory to fill events."
                )
                live.live_loop(livefeed=livefeed_resp, game=game)

            # shotmaps.generate_shotmaps(game=game)

            # Run all end of game / final functions
            if not game.final_socials.final_score_sent:
                final.final_score(livefeed=livefeed_resp, game=game)

            if not game.final_socials.three_stars_sent:
                final.three_stars(livefeed=livefeed_resp, game=game)

            if not game.final_socials.nst_linetool_sent:
                # thirdparty.nst_linetool(game=game, team=game.preferred_team)
                game.final_socials.nst_linetool_sent = True

            if not game.final_socials.hsc_sent:
                final.hockeystatcards(game=game)

            if not game.nst_charts.final_charts:
                logging.info("NST Charts not yet sent - check if it's ready for us to scrape.")
                nst_ready = (
                    nst.is_nst_ready(game.preferred_team.short_name) if not args.date else True
                )
                if nst_ready:
                    list_of_charts = nst.generate_all_charts(game=game)
                    # Chart at Position 0 is the Overview Chart & 1-4 are the existing charts
                    overview_chart = list_of_charts[0]
                    team_charts = list_of_charts[1:]

                    overview_chart_msg = (
                        f"Team Overview stat percentages - 5v5 (SVA) at the "
                        f"end of the game (via @NatStatTrick)."
                    )

                    ov_social_ids = socialhandler.send(
                        overview_chart_msg, media=overview_chart, game_hashtag=True
                    )

                    charts_msg = (
                        f"Individual, on-ice, forward lines & defensive pairs at the "
                        f"end of the game (via @NatStatTrick)."
                    )
                    social_ids = socialhandler.send(
                        charts_msg,
                        media=team_charts,
                        game_hashtag=True,
                        reply=ov_social_ids["twitter"],
                    )
                    game.nst_charts.final_charts = True

            # If we have exceeded the number of retries, stop pinging NST
            if game.final_socials.retries_exeeded:
                game.final_socials.nst_linetool_sent = True

            if game.final_socials.all_social_sent:
                logging.info("All end of game socials sent or retries were exceeded - ending game!")
                end_game_loop(game=game)

            # If all socials aren't sent or retry limit is not exceeded, sleep & check again.
            logging.info(
                "Final loop #%s done - sleep for %s seconds and check again.",
                game.final_socials.retry_count,
                config["script"]["final_sleep_time"],
            )

            game.final_socials.retry_count += 1
            time.sleep(config["script"]["final_sleep_time"])

        else:
            logging.warning(
                "Game State %s is unknown - sleep for 5 seconds and check again.", game.game_state
            )
            time.sleep(config["script"]["live_sleep_time"])


def end_game_loop(game: Game):
    """ A function that is run once the game is finally over. Nothing fancy - just denotes a logical place
        to end the game, log one last section & end the script."""
    pref_team = game.preferred_team
    other_team = game.other_team

    # Empty the temporary (in-game) images directory.
    try:
        utils.empty_images_temp()
    except Exception as e:
        logging.warning("Unable to empty temporary images directory. %s", e)

    logging.info("#" * 80)
    logging.info("End of the %s Hockey Twitter Bot game.", pref_team.short_name)
    logging.info(
        "Final Score: %s: %s / %s: %s",
        pref_team.short_name,
        pref_team.score,
        other_team.short_name,
        other_team.score,
    )
    logging.info("TIME: %s", datetime.now())
    logging.info("%s\n", "#" * 80)
    sys.exit()


def run():
    """ The main script runner - everything starts here! """
    config = utils.load_config()
    args = arguments.get_arguments()

    # Setup the logging for this script run (console, file, etc)
    utils.setup_logging()

    # Get the team name the bot is running as
    team_name = args.team if args.team else config["default"]["team_name"]

    # ------------------------------------------------------------------------------
    # PRE-SCRIPT STARTS PROCESSING BELOW
    # ------------------------------------------------------------------------------

    # Log script start lines
    logging.info("#" * 80)
    logging.info("New instance of the Hockey Twitter Bot (V%s) started.", VERSION)
    if args.docker:
        logging.info("Running in a Docker container - environment variables parsed.")
    logging.info("TIME: %s", datetime.now())
    logging.info(
        "ARGS - notweets: %s, console: %s, teamoverride: %s", args.notweets, args.console, args.team
    )
    logging.info(
        "ARGS - debug: %s, debugsocial: %s, overridelines: %s",
        args.debug,
        args.debugsocial,
        args.overridelines,
    )
    logging.info("ARGS - date: %s, split: %s, localdata: %s", args.date, args.split, args.localdata)
    logging.info(
        "SOCIAL - twitter: %s, discord: %s, slack: %s",
        config["socials"]["twitter"],
        config["socials"]["discord"],
        config["socials"]["slack"],
    )
    logging.info("%s\n", "#" * 80)

    # Check if there is a game scheduled for today -
    # If there is no game, exit the script.
    date = utils.date_parser(args.date) if args.date else datetime.now()
    team_id = schedule.get_team_id(team_name)
    game_today, game_info = schedule.is_game_today(team_id, date)
    if not game_today:
        game_yesterday, prev_game = schedule.was_game_yesterday(team_id, date)
        if game_yesterday:
            logging.info(
                "There was a game yesterday - generate new season overview stats chart, tweet it & exit."
            )
            home_team = prev_game["teams"]["home"]
            away_team = prev_game["teams"]["away"]

            pref_team = home_team if home_team["team"]["name"] == team_name else away_team
            other_team = away_team if home_team["team"]["name"] == team_name else home_team

            pref_team_name = pref_team["team"]["name"]
            pref_score = pref_team["score"]
            pref_hashtag = utils.team_hashtag(pref_team_name)
            other_team_name = other_team["team"]["name"]
            other_score = other_team["score"]

            game_result_str = "defeat" if pref_score > other_score else "lose to"

            team_season_msg = (
                f"Updated season overview & last 10 game stats after the {pref_team_name} "
                f"{game_result_str} the {other_team_name} by a score of {pref_score} to {other_score}."
                f"\n\n{pref_hashtag}"
            )

            team_season_fig = nst.generate_team_season_charts(team_name)
            team_season_fig_last10 = nst.generate_team_season_charts(team_name, lastgames=10)
            team_season_charts = [team_season_fig, team_season_fig_last10]
            socialhandler.send(team_season_msg, media=team_season_charts)

        sys.exit()

    # For debugging purposes, print all game_info
    logging.debug("%s", game_info)

    # Create the Home & Away Team objects
    away_team = Team.from_json(game_info, "away")
    home_team = Team.from_json(game_info, "home")

    # If lines are being overriden by a local lineup file,
    # set the overrlide lines property to True
    if args.overridelines:
        home_team.overridelines = True
        away_team.overridelines = True

    # The preferred team is the team the bot is running as
    # This allows us to track if the preferred team is home / away
    home_team.preferred = bool(home_team.team_name == team_name)
    away_team.preferred = bool(away_team.team_name == team_name)

    # Create the Game Object!
    game = Game.from_json_and_teams(game_info, home_team, away_team)
    GlobalGame.game = game

    # Override Game State for localdata testing
    game.game_state = "Live" if args.localdata else game.game_state

    # Update the Team Objects with the gameday rosters
    roster.gameday_roster_update(game)

    # print(vars(game))
    # print(vars(away_team))
    # print(vars(home_team))

    # Return the game object to use in the game loop function
    return game


if __name__ == "__main__":
    # Run the application (creates main objects)
    game = run()

    # All necessary Objects are created, start the game loop!
    logging.info("Starting main game loop now!")
    start_game_loop(game)
