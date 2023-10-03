"""
The main application entrypoint in the hockeygamebot script!
"""

# pylint: disable=broad-except, too-many-statements, too-many-branches, too-many-nested-blocks

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime

# If running as app.py directly, we may need to import the module manually.
try:
    import hockeygamebot  # pylint: disable=unused-import
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

from hockeygamebot.core import common, final, live, preview, images
from hockeygamebot.definitions import VERSION
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.game import Game, PenaltySituation
from hockeygamebot.models.gamestate import GameScheduleState, GameState, V1GameStateCode
from hockeygamebot.models.globalgame import GlobalGame
from hockeygamebot.models.team import Team
from hockeygamebot.nhlapi import contentfeed, livefeed, nst, roster, schedule, standings, youtube
from hockeygamebot.social import socialhandler


def start_game_loop(game: Game):
    """The main game loop - tracks game state & calls all relevant functions.

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
        if game.game_state in GameState.all_pregames():
            livefeed_resp = livefeed.get_livefeed(game.game_id)
            game.update_game(livefeed_resp)

            # If the Game Roster is still empty, try setting it again
            if not game.full_roster:
                logging.info("Game Roster is still not set, try getting it again.")
                roster.gameday_roster_update(game)

            # If after the update_game() function runs, we have a Postponed Game
            # We should tweet it - this means it happened after the game was scheduled
            if game.game_schedule_state == GameScheduleState.POSTPONED.value:
                logging.warning("This game was originally scheduled, but is now postponed.")
                social_msg = (
                    f"⚠️ The {game.preferred_team.team_name} game scheduled for today has been postponed."
                )
                socialhandler.send(social_msg)
                end_game_loop(game)

            if game.game_time_countdown > 0:
                logging.info("Game is in Preview state - send out all pregame information.")
                # The core game preview function should run only once
                if not game.preview_socials.core_sent:
                    preview.generate_game_preview(game)

                # The other game preview function should run every xxx minutes
                # until all pregame tweets are sent or its too close to game time
                sleep_time, last_sleep_before_live = preview.game_preview_others(game)
                game.preview_socials.increment_counter()

                # If this is the last sleep before the game goes live, cut it by 5 minutes for starters function.
                if last_sleep_before_live:
                    logging.info(
                        "This is the last sleep before the game goes live - 5 minutes less & starters."
                    )
                    sleep_time = 0 if (sleep_time - 300) < 0 else sleep_time
                    time.sleep(sleep_time)
                    preview.get_starters(game)
                else:
                    time.sleep(sleep_time)

            else:
                logging.info(
                    "Game is in Preview state, but past game start time - sleep for a bit "
                    "& update game attributes so we detect when game goes live."
                )

                # If the Game Roster is still empty, try setting it again
                if not game.full_roster:
                    logging.info("Game Roster is <STILL> not set, try getting it again.")
                    roster.gameday_roster_update(game)

                # Somehow we got here without the starting lineup - try again
                if not game.preview_socials.starters_sent:
                    preview.get_starters(game)

                sleep_time = config["script"]["pregame_sleep_time"]
                time.sleep(sleep_time)

        elif game.game_state in GameState.all_lives():
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
                                "Other On Ice: %s - %s",
                                len(game.other_team.onice),
                                game.other_team.onice,
                            )

                            # Penalty Killed Status
                            penalty_situation = game.penalty_situation
                            if penalty_situation.penalty_killed:
                                logging.info("***** PENALTY KILLED NOTIFICATION *****")
                                shots_taken = (
                                    penalty_situation.pp_team.shots - penalty_situation.pp_team_shots_start
                                )
                                logging.info("PP Shots Taken: %s", shots_taken)
                                game.penalty_situation = PenaltySituation()

                            if game.penalty_situation.in_situation:
                                logging.info(
                                    "Current Penalty (In Situation): %s",
                                    vars(game.penalty_situation),
                                )

                            if not game.period.current_oneminute_sent:
                                live.minute_remaining_check(game)

                            live.live_loop(livefeed=data, game=game)
                            game.update_game(data)

                            time.sleep(0.1)

                # Non-Local Data
                livefeed_resp = livefeed.get_livefeed(game.game_id)
                # all_events = live.live_loop(livefeed=livefeed_resp, game=game)

                # Update all game attributes & check for goalie pulls
                game.update_game(livefeed_resp)
                # game.goalie_pull_updater(livefeed_resp)

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
                logging.info("Other On Ice: %s - %s", len(game.other_team.onice), game.other_team.onice)

                # Penalty Killed Status
                penalty_situation = game.penalty_situation
                if penalty_situation.penalty_killed:
                    logging.info("***** PENALTY KILLED NOTIFICATION *****")
                    shots_taken = penalty_situation.pp_team.shots - penalty_situation.pp_team_shots_start
                    logging.info("PP Shots Taken: %s", shots_taken)
                    game.penalty_situation = PenaltySituation()

                if game.penalty_situation.in_situation:
                    logging.info("Current Penalty (In Situation): %s", vars(game.penalty_situation))

                if not game.period.current_oneminute_sent:
                    live.minute_remaining_check(game)

                # Pass the live feed response to the live loop (to parse events)
                live.live_loop(livefeed=livefeed_resp, game=game)
                # game_events = get_game_events(game_obj)
                # loop_game_events(game_events, game_obj)

            except Exception as error:
                logging.error("Uncaught exception in live game loop - see below error.")
                logging.error(error)
                traceback.print_exc()

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

        elif game.game_state in GameState.all_finals():
            logging.info("Game is now over & 'Final' - run end of game functions with increased sleep time.")

            livefeed_resp = livefeed.get_livefeed(game.game_id)
            game.update_game(livefeed_resp)

            # If (for some reason) the bot was started after the end of the game
            # We need to re-run the live loop once to parse all of the events
            if not game.events:
                logging.info("Bot started after game ended, pass livefeed into event factory to fill events.")
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

            # Twitter API V2 is too Expensive to Send Shotmaps
            # if not game.final_socials.shotmap_retweet:
            #     game.final_socials.shotmap_retweet = common.search_send_shotmap(game=game)

            if not game.final_socials.hsc_sent:
                try:
                    final.hockeystatcards(game=game)
                except Exception as e:
                    logging.error("Error generating Hockey Stat Cards - setting HSC finals to true.")
                    traceback.print_exc()
                    # Set the end of game social attributes
                    game.final_socials.hsc_msg = None
                    game.final_socials.hsc_sent = True

            if not game.nst_charts.final_charts:
                logging.info("NST Charts not yet sent - check if it's ready for us to scrape.")
                nst_ready = nst.is_nst_ready(game.preferred_team.short_name) if not args.date else True
                if nst_ready:
                    all_charts = nst.generate_all_charts(game=game)
                    # Chart at Position 0 is the Overview Chart & 1-4 are the existing charts
                    overview_chart = all_charts["overview"]
                    team_charts = all_charts["barcharts"]
                    scatter_charts = all_charts["scatters"]
                    shift_chart = all_charts["shift"]
                    heatmap_charts = all_charts["heatmaps"]

                    last_chart_socials = None

                    if overview_chart:
                        overview_chart_msg = (
                            f"Team Overview stat percentages - 5v5 (SVA) at the "
                            f"end of the game (via @NatStatTrick)."
                        )

                        last_chart_socials = socialhandler.send(
                            overview_chart_msg, media=overview_chart, game_hashtag=True
                        )

                    if team_charts:
                        charts_msg = (
                            f"Individual, on-ice, forward lines & defensive pairs at the "
                            f"end of the game (via @NatStatTrick)."
                        )
                        last_chart_socials = socialhandler.send(
                            charts_msg,
                            media=team_charts,
                            game_hashtag=True,
                            reply=last_chart_socials["twitter"],
                        )

                    if heatmap_charts:
                        charts_msg = (
                            f"Linemate & Opposition Data (TOI, CF% and xGF%) at the "
                            f"end of the game (via @NatStatTrick)."
                        )
                        last_chart_socials = socialhandler.send(
                            charts_msg,
                            media=heatmap_charts,
                            game_hashtag=True,
                            reply=last_chart_socials["twitter"],
                        )

                    if shift_chart:
                        charts_msg = f"Shift length breakdown at the end of the game (via @NatStatTrick)."
                        last_chart_socials = socialhandler.send(
                            charts_msg,
                            media=shift_chart,
                            game_hashtag=True,
                            reply=last_chart_socials["twitter"],
                        )

                    if scatter_charts:
                        charts_msg = (
                            f"Quality vs. Quantity & Expected Goals Rate / 60 at the"
                            " end of the game (via @NatStatTrick)."
                        )
                        last_chart_socials = socialhandler.send(
                            charts_msg,
                            media=scatter_charts,
                            game_hashtag=True,
                            reply=last_chart_socials["twitter"],
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
    """A function that is run once the game is finally over. Nothing fancy - just denotes a logical place
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
    """The main script runner - everything starts here!"""
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
    logging.info("ARGS - notweets: %s, console: %s, teamoverride: %s", args.notweets, args.console, args.team)
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
    team_id, team_tri_code = schedule.get_team_id(team_name)
    logging.info("[NEWAPI] Team ID: %s / Team TriCode: %s", team_id, team_tri_code)

    game_today, game_info = schedule.is_game_today(team_tri_code, date)

    if not game_today:
        game_yesterday, prev_game = schedule.was_game_yesterday(team_tri_code, date)
        if game_yesterday:
            logging.info(
                "There was a game yesterday - send recap, condensed game "
                "and generate new season overview stats chart, tweet it & exit."
            )

            # Get Team Information
            game_id = prev_game["id"]
            gamecenter = livefeed.get_gamecenter_landing(game_id)

            home_team_place = gamecenter["homeTeam"]["placeName"]
            home_team_short_name = gamecenter["homeTeam"]["name"]
            home_team_name = f"{home_team_place} {home_team_short_name}"

            away_team_place = gamecenter["awayTeam"]["placeName"]
            away_team_short_name = gamecenter["awayTeam"]["name"]
            away_team_name = f"{away_team_place} {away_team_short_name}"

            pref_team = gamecenter["homeTeam"] if home_team_name == team_name else gamecenter["awayTeam"]
            other_team = gamecenter["awayTeam"] if home_team_name == team_name else gamecenter["homeTeam"]

            pref_team_name = home_team_name if home_team_name == team_name else away_team_name
            pref_score = pref_team["score"]
            pref_hashtag = utils.team_hashtag(pref_team_name)

            other_team_name = away_team_name if home_team_name == team_name else home_team_name
            other_score = other_team["score"]

            # # TODO: Content Feed Re-Write
            # game_summary = gamecenter.get("summary", {})
            # game_video = game_summary.get("gameVideo", {})
            # three_min_recap_id = game_video.get("threeMinRecap")
            # three_min_recap_url = f"https://www.nhl.com/video/c-{three_min_recap_id}?tcid=tw_video_content_id"
            # condensed_game_id = game_video.get("condensedGame")
            # condensed_game_url = f"https://www.nhl.com/video/c-{condensed_game_id}?tcid=tw_video_content_id"
            # print(three_min_recap_url, condensed_game_url)

            # # Get the Recap & Condensed Game
            # content_feed = contentfeed.get_content_feed(game_id)

            # # Send Recap Tweet
            # try:
            #     recap, recap_video_url = contentfeed.get_game_recap(content_feed)
            #     recap_description = recap["items"][0]["description"]
            #     recap_msg = f"📺 {recap_description}.\n\n{recap_video_url}"
            #     socialhandler.send(recap_msg)
            # except Exception as e:
            #     logging.error("Error getting Game Recap. %s", e)

            # # Send Condensed Game / Extended Highlights Tweet
            # try:
            #     condensed_game, condensed_video_url = contentfeed.get_condensed_game(content_feed)
            #     condensed_blurb = condensed_game["items"][0]["blurb"]
            #     condensed_msg = f"📺 {condensed_blurb}.\n\n{condensed_video_url}"
            #     socialhandler.send(condensed_msg)
            # except Exception as e:
            #     logging.error("Error getting Condensed Game from NHL - trying YouTube. %s", e)
            #     try:
            #         condensed_game = youtube.youtube_condensed(away_team_name, home_team_name)
            #         condensed_blurb = condensed_game["title"]
            #         condensed_video_url = condensed_game["yt_link"]
            #         condensed_msg = f"📺 {condensed_blurb}.\n\n{condensed_video_url}"
            #         socialhandler.send(condensed_msg)
            #     except Exception as e:
            #         logging.error("Error getting Condensed Game from NHL & YouTube - skip this today. %s", e)

            # Generate the Season Overview charts
            game_result_str = "defeat" if pref_score > other_score else "lose to"

            team_season_msg = (
                f"Updated season overview & last 10 game stats after the {pref_team_name} "
                f"{game_result_str} the {other_team_name} by a score of {pref_score} to {other_score}."
                f"\n\n{pref_hashtag}"
            )

            team_season_fig = nst.generate_team_season_charts(team_name, "sva")
            team_season_fig_last10 = nst.generate_team_season_charts(team_name, "sva", lastgames=10)
            team_season_fig_all = nst.generate_team_season_charts(team_name, "all")
            team_season_fig_last10_all = nst.generate_team_season_charts(team_name, "all", lastgames=10)
            team_season_charts = [
                team_season_fig,
                team_season_fig_last10,
                team_season_fig_all,
                team_season_fig_last10_all,
            ]
            socialhandler.send(team_season_msg, media=team_season_charts)
        else:
            logging.info("There was no game yesterday - exiting!")

        sys.exit()

        game_id = game_info["id"]

    logging.info("[NEWAPI] Game Today: %s", game_today)
    logging.info("[NEWAPI] Game Info: %s", game_info)

    # Get Game ID from Game Info
    game_id = game_info["id"]

    # Get Broadcast Information
    gamecenter = livefeed.get_gamecenter_landing(game_id)
    broadcasts = schedule.get_broadcasts_from_gamecenter(gamecenter)

    home_team_abbreviation = game_info["homeTeam"]["abbrev"]
    home_team_logo = game_info["homeTeam"]["logo"]
    home_standings = standings.get_standings(home_team_abbreviation)
    home_team_name = home_standings["teamName"]["default"]
    # home_team_name = home_standings["teamName"].get("en", home_standings["teamName"]["default"])
    home_team_short_name = gamecenter["homeTeam"]["name"]
    home_team_record = standings.get_record(home_standings)
    home_team_numgames = home_standings["gamesPlayed"]

    away_team_abbreviation = game_info["awayTeam"]["abbrev"]
    away_team_logo = game_info["awayTeam"]["logo"]
    away_standings = standings.get_standings(away_team_abbreviation)
    away_team_name = away_standings["teamName"]["default"]
    # away_team_name = away_standings["teamName"].get("en", away_standings["teamName"]["default"])
    away_team_short_name = gamecenter["awayTeam"]["name"]
    away_team_record = standings.get_record(away_standings)
    away_team_numgames = away_standings["gamesPlayed"]

    # Get Home & Away Team Names
    home_team_id, home_team_tri_code = schedule.get_team_id(home_team_name)
    away_team_id, away_team_tri_code = schedule.get_team_id(away_team_name)

    logging.info("[NEWAPI] Home Team Name: %s / Record: %s", home_team_name, home_team_record)
    logging.info("[NEWAPI] Away Team Name: %s / Record: %s", away_team_name, away_team_record)

    # V3 - Create Team Objects (Attribute by Attribute)
    home_team = Team(
        team_id=home_team_id,
        team_name=home_team_name,
        short_name=home_team_short_name,
        tri_code=home_team_tri_code,
        home_away="home",
        tv_channel=broadcasts["home"]["network"],
        games=home_team_numgames,
        record=home_team_record,
        season=gamecenter["season"],
        tz_id=None,
        standings=home_standings,
        logo=home_team_logo,
    )

    away_team = Team(
        team_id=away_team_id,
        team_name=away_team_name,
        short_name=away_team_short_name,
        tri_code=away_team_tri_code,
        home_away="away",
        tv_channel=broadcasts["away"]["network"],
        games=away_team_numgames,
        record=away_team_record,
        season=gamecenter["season"],
        tz_id=None,
        standings=away_standings,
        logo=away_team_logo,
    )

    # If lines are being overriden by a local lineup file,
    # set the overrlide lines property to True
    if args.overridelines:
        home_team.overridelines = True
        away_team.overridelines = True

    # The preferred team is the team the bot is running as
    # This allows us to track if the preferred team is home / away
    home_team.preferred = bool(home_team.team_name == team_name)
    away_team.preferred = bool(away_team.team_name == team_name)
    preferred = "home" if home_team.preferred else "away"
    preferred_team = home_team if home_team.preferred else away_team

    # Set Timezone of Preferred Team
    preferred_team_timezone = schedule.get_team_timezone(preferred_team.tri_code)
    preferred_team.tz_id = preferred_team_timezone

    # Create the Game Object!
    game = Game(
        game_id=game_id,
        game_type=gamecenter["gameType"],
        date_time=gamecenter["startTimeUTC"],
        game_state=gamecenter["gameState"],
        game_schedule_state=gamecenter["gameScheduleState"],
        venue=gamecenter["venue"],
        home=home_team,
        away=away_team,
        preferred=preferred,
        live_feed=f"gamecenter/{game_id}/play-by-play",
        season=gamecenter["season"],
    )

    # game = Game.from_json_and_teams(game_info, home_team, away_team)
    GlobalGame.game = game

    # TESTING: Three Stars Image
    # boxscore = gamecenter["summary"]["threeStars"]
    # images.three_stars_image(game, boxscore)
    # sys.exit()

    # Setup API V1 and V2 for Twitter (Store them in the Global Game Instance)
    if config.get("socials").get("twitter"):
        logging.info("Setting up Twitter API Clients & storing them in the GlobalGame.")
        twitter_api_v1 = socialhandler.twitter.get_api()
        twitter_api_v2 = socialhandler.twitter.get_api_v2()
        GlobalGame.game.twitter_api_v1 = twitter_api_v1
        GlobalGame.game.twitter_api_v2 = twitter_api_v2

    # Override Game State for localdata testing
    game.game_state = "Live" if args.localdata else game.game_state

    # Update the Team Objects with the gameday rosters
    roster.gameday_roster_update(game)

    # print(vars(game))
    # print(vars(away_team))
    # print(vars(home_team))

    # If the codedGameState is set to 9 originally, game is postponed (exit immediately)
    if game.game_schedule_state == GameScheduleState.POSTPONED.value:
        logging.warning("This game is marked as postponed during our first run - exit silently.")
        end_game_loop(game)

    # Return the game object to use in the game loop function
    return game


if __name__ == "__main__":
    # Run the application (creates main objects)
    game = run()

    # All necessary Objects are created, start the game loop!
    logging.info("Starting main game loop now!")
    start_game_loop(game)
