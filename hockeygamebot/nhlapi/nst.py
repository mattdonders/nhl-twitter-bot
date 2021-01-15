"""
This module contains functions related to gathering information
from Natural Stat Trick - we get quite a few things from here so it makes
a bit of sense to break these items out from the general 3rd party module.
"""

import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns
from bs4 import BeautifulSoup
from dateutil.parser import parse
from fake_useragent import UserAgent
from matplotlib import ticker
from requests.adapters import HTTPAdapter

from hockeygamebot.definitions import IMAGES_PATH
from hockeygamebot.core import images
from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.game import Game
from hockeygamebot.models.sessions import SessionFactory
from hockeygamebot.models.team import Team
from hockeygamebot.nhlapi import thirdparty


def nst_abbreviation(team_name: str) -> str:
    """Returns the 3-character team abbreviation used in Shift Charts & therefore by most other
        third party stats sites (ex - N.J instead of NJD).

    Args:
        team_name: NHL Team Name

    Returns:
        nss_team: 3-character team abbreviation used at NSS
    """

    # fmt: off
    team_name = team_name.replace("é", "e")
    nss_teams = {
        "Anaheim Ducks": "ANA", "Arizona Coyotes": "ARI", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF",
        "Carolina Hurricanes": "CAR", "Columbus Blue Jackets": "CBJ", "Calgary Flames": "CGY",
        "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Dallas Stars": "DAL", "Detroit Red Wings": "DET",
        "Edmonton Oilers": "EDM", "Florida Panthers": "FLA", "Los Angeles Kings": "L.A", "Minnesota Wild": "MIN",
        "Montreal Canadiens": "MTL", "New Jersey Devils": "N.J", "Nashville Predators": "NSH", "New York Islanders": "NYI",
        "New York Rangers": "NYR", "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT",
        "San Jose Sharks": "S.J", "St. Louis Blues": "STL", "Tampa Bay Lightning": "T.B", "Toronto Maple Leafs": "TOR",
        "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK", "Winnipeg Jets": "WPG", "Washington Capitals": "WSH",
    }
    # fmt: on

    return nss_teams[team_name]


def get_nst_stat(item):
    text = item.text
    value = "0" if text == "-" else text
    return float(value)


def get_nst_report_url(game: Game, full=False):
    """Returns the URL for the Natural Stat Trick report page corresponding to the current game."

    Args:
        game (game): An NHL Game Event game object.
        full (bool): Should the full report be returned.

    Returns:
        nst_rpt_url: The URL for the Natural Stat Trick game report.
    """

    urls = utils.load_urls()
    nst_base = urls["endpoints"]["nst"]

    full_limited = "" if full else "&view=limited"

    nst_rpt_url = (
        f"{nst_base}/game.php?season={game.season}{full_limited}"
        f"&game={game.game_id_gametype_shortid}{game.game_id_shortid}"
    )

    return nst_rpt_url


def is_nst_ready(team_name):
    """Scrapes the Natural Stat Trick home page to determine if our game has been tracked into intermission / Final.
        This avoids us scraping a full report before it's ready to give us all stats.

    Args:
        team_name (String): The short name of our NHL team.

    Returns:
        boolean: If the period or game has been tracked to completion.
    """

    urls = utils.load_urls()
    nst_base = urls["endpoints"]["nst"]

    resp = thirdparty.thirdparty_request(nst_base)
    soup = thirdparty.bs4_parse(resp.content)

    # Find all currently playing games
    games = soup.find_all("table", class_="boxscore")

    # Iterate over today's games to find our team game & then determine if we can scrape it yet.
    for game in games:
        try:
            game_title = game.find_all("tr")[0]
            game_details = game_title.find_all("td")
            away_team = game_details[0].text
            home_team = game_details[4].text
            period = game_details[2].text

            if team_name in (away_team, home_team):
                if "End" in period or "Final" in period:
                    logging.info("Specified team game is either in intermission or has ended.")
                    logging.info("%s / %s - Period: %s", away_team, home_team, period)
                    return True

                # Game detected, but not in intermission, we can sleep for now
                logging.warning(
                    "Specified team game found, but not in intermission or Final - sleep & try again"
                )
                logging.info("%s / %s - Period: %s", away_team, home_team, period)
                return False
        except:
            logging.warning("Error reading this NST row - skipping.")

    logging.error("The specified team cannot be found or is not playing today.")
    return False


###################################################
# NST SOUP PARSING FUNCTIONS - CREATES DICTS & DF
###################################################


def parse_team_table(team_keys, teamtable):
    pass


def parse_overview(ov_keys, overview):
    # Initialize the return dictionary
    overview_stats = {"home": dict(), "away": dict()}

    # Find all home team stats in the Overview Section (by column)
    # And del the team name element off the array
    ov_home = overview.find_all("tr")[0].find_all("td")
    del ov_home[0]

    ov_stats_home = list()
    for col in ov_home:
        ov_stats_home.append([s for s in col.text.splitlines() if s])

    ov_stats_home = list(zip(*ov_stats_home))
    ov_stats_home_final = {
        x.get("Period"): x for x in [dict(zip(ov_keys, values)) for values in ov_stats_home]
    }

    # Find all home team stats in the Overview Section (by column)
    # And del the team name element off the array
    ov_away = overview.find_all("tr")[1].find_all("td")
    del ov_away[0]

    ov_stats_away = list()
    for col in ov_away:
        ov_stats_away.append([s for s in col.text.splitlines() if s])

    ov_stats_away = list(zip(*ov_stats_away))
    ov_stats_away_final = {
        x.get("Period"): x for x in [dict(zip(ov_keys, values)) for values in ov_stats_away]
    }

    overview_stats["home"] = ov_stats_home_final
    overview_stats["away"] = ov_stats_away_final

    return overview_stats


def parse_nst_timeonice(ind_5v5, ind_pp, ind_pk):
    # Calculate Time on Ice Graph
    # Player = 0, TOI = 2
    ind_stats = list()
    toi_dict = dict()
    toi_dict["5v5"] = dict()
    toi_dict["pk"] = dict()
    toi_dict["pp"] = dict()
    toi_dict["total"] = dict()

    for player in ind_5v5:
        items = player.find_all("td")
        name = items[0].text.replace("\xa0", " ")
        position = items[1].text
        toi = float(items[2].text)
        ixg = float(items[10].text)
        toi_dict["5v5"][name] = toi
        toi_dict["total"][name] = toi
        toi_dict["pp"][name] = 0
        toi_dict["pk"][name] = 0
        if position != "D":
            ind_stats.append({"player": name, "ixg": ixg, "toi": toi})

    for player in ind_pp:
        items = player.find_all("td")
        name = items[0].text.replace("\xa0", " ")
        toi = float(items[2].text)
        toi_dict["pp"][name] = toi
        toi_dict["total"][name] += toi

    for player in ind_pk:
        items = player.find_all("td")
        name = items[0].text.replace("\xa0", " ")
        toi = float(items[2].text)
        toi_dict["pk"][name] = toi
        toi_dict["total"][name] += toi

    return toi_dict, ind_stats


def parse_nst_oistats(oi_sva):
    oi_sva_stats = list()

    for player in oi_sva:
        items = player.find_all("td")
        name = items[0].text.replace("\xa0", " ")
        toi = float(items[2].text)

        cf = float(items[3].text)
        ca = float(items[4].text)
        corsi_diff = round(cf - ca, 2)

        sf = float(items[11].text)
        sa = float(items[12].text)
        shots_diff = round(sf - sa, 2)

        xgf = float(items[19].text)
        xga = float(items[20].text)
        xg_diff = round(xgf - xga, 2)

        hdcf = float(items[27].text)
        hdca = float(items[28].text)
        hdc_diff = round(hdcf - hdca, 2)

        stats = {
            "player": name,
            "toi": toi,
            "cf": cf,
            "ca": ca,
            "corsi_diff": corsi_diff,
            "sa": sa,
            "sf": sf,
            "shots_diff": shots_diff,
            "xgf": xgf,
            "xga": xga,
            "xg_diff": xg_diff,
            "hdcf": xgf,
            "hdca": xga,
            "hdc_diff": hdc_diff,
        }
        oi_sva_stats.append(stats)

    return oi_sva_stats


def parse_nst_fwdstats(fwd_sva):
    # For Forward Line Attribute Values
    # F1 = 0, F2 = 1, F3 = 2, TOI = 3
    # CF = 4, CA = 5
    # xGF = 20, xGA = 21
    # HDCF = 28, HDCA = 29
    fwd_sva_stats = list()

    for player in fwd_sva:
        items = player.find_all("td")
        f1 = " ".join(items[0].text.replace("\xa0", " ").split()[1:])
        f2 = " ".join(items[1].text.replace("\xa0", " ").split()[1:])
        f3 = " ".join(items[2].text.replace("\xa0", " ").split()[1:])
        fwds = "-".join([f1, f2, f3])
        toi = float(items[3].text)
        # toi_mm = int(toi)
        # toi_ss = (toi * 60) % 60
        # toi_mmss = "%02d:%02d" % (toi_mm, toi_ss)
        # line_label = f"{fwds}\n(TOI: {toi_mmss})"

        cf = float(items[4].text)
        ca = float(items[5].text)
        cfpct = get_nst_stat(items[6])
        corsi_diff = round(cf - ca, 2)

        xgf = float(items[20].text)
        xga = float(items[21].text)
        xgfpct = get_nst_stat(items[22])
        xg_diff = round(xgf - xga, 2)

        hdcf = float(items[28].text)
        hdca = float(items[29].text)
        hdcfpct = get_nst_stat(items[30])
        hdc_diff = round(hdcf - hdca, 2)

        stats = {
            "line": fwds,
            "toi": toi,
            "cf": cf,
            "ca": ca,
            "corsi_diff": corsi_diff,
            "cfpct": cfpct,
            "xgf": xgf,
            "xga": xga,
            "xg_diff": xg_diff,
            "xgfpct": xgfpct,
            "hdcf": hdcf,
            "hdca": hdca,
            "hdc_diff": hdc_diff,
            "hdcdpct": hdcfpct,
        }
        fwd_sva_stats.append(stats)

    return fwd_sva_stats


def parse_nst_defstats(soup, def_player_ids, def_players_dict):
    def_sva_stats = list()

    for player_id in def_player_ids:
        def_name = " ".join(def_players_dict[player_id].split()[1:])
        linemates_tbl_sva = soup.find(id=f"tl{player_id}s").find("tbody").find_all("tr")

        for linemates_sva in linemates_tbl_sva:
            items = linemates_sva.find_all("td")
            name = items[0].text.replace("\xa0", " ")
            last_name = " ".join(name.split()[1:])
            position = items[1].text
            if position != "D":
                continue
            toi = float(items[2].text)
            line_label = f"{def_name}-{last_name}"

            cf = float(items[3].text)
            ca = float(items[4].text)
            cfpct = get_nst_stat(items[5])
            corsi_diff = round(cf - ca, 2)

            xgf = float(items[19].text)
            xga = float(items[20].text)
            xgfpct = get_nst_stat(items[21])
            xg_diff = round(xgf - xga, 2)

            hdcf = float(items[27].text)
            hdca = float(items[28].text)
            hdcfpct = get_nst_stat(items[29])
            hdc_diff = round(hdcf - hdca, 2)

            if (
                any(d["corsi_diff"] == corsi_diff for d in def_sva_stats)
                and any(d["xg_diff"] == xg_diff for d in def_sva_stats)
                and any(d["hdc_diff"] == hdc_diff for d in def_sva_stats)
            ):
                # print(f"{def_name} & {last_name} pairing already exists, skipping.")
                continue

            stats = {
                "line": line_label,
                "toi": toi,
                "cf": cf,
                "ca": ca,
                "corsi_diff": corsi_diff,
                "cfpct": cfpct,
                "xgf": xgf,
                "xga": xga,
                "xg_diff": xg_diff,
                "xgfpct": xgfpct,
                "hdcf": hdcf,
                "hdca": hdca,
                "hdc_diff": hdc_diff,
                "hdcfpct": hdcfpct,
            }
            def_sva_stats.append(stats)

    return def_sva_stats


def parse_nst_opposition(team_abbrev, soup, players_ids, players_dict):
    oppo_toi = dict()
    oppo_cfwith = dict()
    oppo_soup = soup.find(id=f"{team_abbrev}wyoplb").find_parent("div")
    for player_id in players_ids:
        player_name = players_dict[player_id]
        oppo_toi[player_name] = dict()
        oppo_cfwith[player_name] = dict()

        oppo_tbl_5v5 = oppo_soup.find(id=f"to{player_id}5").find("tbody").find_all("tr")

        for oppo in oppo_tbl_5v5:
            items = oppo.find_all("td")
            name = items[0].text.replace("\xa0", " ")
            last_name = " ".join(name.split()[1:])
            toi = float(items[2].text)

            oppo_toi[player_name][last_name] = toi

            cfwith = get_nst_stat(items[5])
            oppo_cfwith[player_name][last_name] = cfwith / 100

    return oppo_toi, oppo_cfwith


def parse_nst_linemate(team_abbrev, soup, players_ids, players_dict):
    linemate_toi = dict()
    linemate_cfwith = dict()
    linemate_soup = soup.find(id=f"{team_abbrev}wylmlb").find_parent("div")
    for player_id in players_ids:
        player_name = players_dict[player_id]
        linemate_toi[player_name] = dict()
        linemate_cfwith[player_name] = dict()
        linemate_tbl_5v5 = linemate_soup.find(id=f"tl{player_id}5").find("tbody").find_all("tr")

        for linemate in linemate_tbl_5v5:
            items = linemate.find_all("td")
            name = items[0].text.replace("\xa0", " ")
            last_name = " ".join(name.split()[1:])
            toi = float(items[2].text)
            linemate_toi[player_name][last_name] = toi

            cfwith = get_nst_stat(items[5])
            linemate_cfwith[player_name][last_name] = cfwith / 100

    return linemate_toi, linemate_cfwith


###################################################
# ALL CHARTING FUNCTIONS - MATPLOTLIB & SEABORN
###################################################


def toi_to_mmss(toi):
    toi_mm = int(toi)
    toi_ss = (toi * 60) % 60
    toi_mmss = "%02d:%02d" % (toi_mm, toi_ss)
    return toi_mmss


def floor_ceil(number):
    rounded = math.floor(number) if number < 0 else math.ceil(number)
    return rounded


def calculate_xticks(spacing, df_min, df_max):
    xtick_min = df_min - (df_min % spacing) if df_min < 0 else df_min - (df_min % spacing) + (2 * spacing)
    xtick_max = df_max - (df_max % spacing) if df_max < 0 else df_max - (df_max % spacing) + (2 * spacing)
    return (xtick_min, xtick_max)


def charts_heatmap_oppo_lm(game_title, team, oppo_toi, oppo_cfwith, linemate_toi, linemate_cfwith):
    colormap = "Blues"

    oppo_df = pd.DataFrame(oppo_toi).T

    linemate_df = pd.DataFrame(linemate_toi).T
    linemate_df = linemate_df.apply(lambda col: col.where((col.name == col.index) | col.notnull(), 0))
    corr = linemate_df.corr()

    # Create the CF% With Dataframes
    oppo_cf_df = pd.DataFrame(oppo_cfwith).T.fillna(0)
    linemate_cf_df = pd.DataFrame(linemate_cfwith).T.fillna(0)

    # Sort DFs Alphabetically (Better Organization in Heatmaps)
    linemate_df = linemate_df.sort_index().sort_index(axis=1)
    linemate_cf_df = linemate_cf_df.sort_index().sort_index(axis=1)
    oppo_df = oppo_df.sort_index()

    # Generate a mask for the upper triangle
    mask = np.zeros_like(corr, dtype=np.bool)
    mask[np.triu_indices_from(mask)] = True

    heatmap_oppo_lm_fig, ((ax1, ax2)) = plt.subplots(2, 1, figsize=(10, 10))
    # sns.set(font_scale=0.6)

    # Create the Opposition TOI Heatmap
    sns.heatmap(
        oppo_df,
        ax=ax1,
        annot=oppo_cf_df,
        linewidths=0.5,
        fmt=".1%",
        cmap=colormap,
        annot_kws={"size": 6},
        cbar_kws={"label": "Time on Ice"},
    )

    ax1.set_xticklabels(ax1.get_xticklabels(), rotation=-90, ha="center")
    ax1.title.set_text(f"{team} Opposition - 5v5 TOI (with CF%)")

    # Create the Linemates TOI Heatmap
    sns.heatmap(
        linemate_df,
        mask=mask,
        ax=ax2,
        annot=linemate_cf_df,
        fmt=".1%",
        linewidths=0.5,
        cmap=colormap,
        annot_kws={"size": 6},
        cbar_kws={"label": "Time on Ice"},
    )

    ax2.set_xticklabels(ax2.get_xticklabels(), rotation=-90, ha="center")
    ax2.title.set_text(f"{team} Linemates - 5v5 TOI (with CF%)")

    heatmap_oppo_lm_fig.tight_layout(rect=[0, 0.0, 1, 0.92], pad=2)
    heatmap_oppo_lm_fig.suptitle(
        f"{game_title}\nLinemates & Opposition Data\nData Courtesy: Natural Stat Trick",
        x=0.45,
        fontsize=14,
    )

    return heatmap_oppo_lm_fig


def charts_toi_individual(game_title, team, toi_dict, ind_stats, oi_sva_stats):
    # Clear & Reset Any Existing Figures
    plt.clf()

    # Set the Colormap for All Graphs
    color_map = plt.cm.get_cmap("Blues")

    toi_ind_fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(13, 10))

    # (AX1) Time on Ice Breakdown
    df_toi = pd.DataFrame(toi_dict).sort_values("total", ascending=True).drop(columns=["total"])
    df_toi.plot(kind="barh", stacked=True, ax=ax1, color=["dodgerblue", "red", "green"])
    xtick_max = round(max(toi_dict["total"].values()) + 2)
    ax1.set_xticks(np.arange(0, xtick_max, 3.0))
    ax1.grid(True, which="major", axis="x")
    ax1.title.set_text(f"Time on Ice Breakdown - {team}")

    # (AX2) Generates ixG Graph from Dataframe
    df_ixg = pd.DataFrame(ind_stats).sort_values("ixg", ascending=True)
    df_ixg_toi = df_ixg["toi"]
    max_ixg_toi = max(df_ixg_toi)
    ixg_toi_color = df_ixg_toi / float(max_ixg_toi)
    ixg_colormap = color_map(ixg_toi_color)

    ax2.barh(width=df_ixg.ixg, y=df_ixg.player, color=ixg_colormap)
    xtick_max = df_ixg.ixg.max() + 0.25
    ax2.set_xticks(np.arange(0, xtick_max, 0.1))
    ax2.grid(True, which="major", axis="x")
    ax2.title.set_text(f"iXG by Forward - {team}")

    for i, v in enumerate(df_ixg.ixg):
        ax2.text(v, i, " " + str(v), color="black", va="center", fontsize=8)

    # (AX3) Generates On-Ice Corsi Graph from Dataframe
    df_oi_corsi = pd.DataFrame(oi_sva_stats).sort_values("corsi_diff", ascending=True)
    df_oi_corsi_toi = df_oi_corsi["toi"]
    max_oi_corsi_toi = max(df_oi_corsi_toi)
    oi_corsi_toi_color = df_oi_corsi_toi / float(max_oi_corsi_toi)
    oi_corsi_colormap = color_map(oi_corsi_toi_color)
    oi_corsi_colormap_shots = plt.cm.get_cmap("Reds")(oi_corsi_toi_color)

    ax3.barh(width=df_oi_corsi.corsi_diff, y=df_oi_corsi.player, color=oi_corsi_colormap)
    # NOTE: Uncomment the below two lines to add Red shots on top of Coris
    # ax3.barh(width=df_oi_corsi.shots_diff, y=df_oi_corsi.player, color=oi_corsi_colormap_shots)
    # ax3.title.set_text(f"5v5 (SVA) On-Ice Corsi (Blue) & Shots (Red) Differential - {team}")
    spacing = 3
    xtick_min, xtick_max = calculate_xticks(
        spacing, df_oi_corsi.corsi_diff.min(), df_oi_corsi.corsi_diff.max()
    )
    ax3.set_xticks(np.arange(xtick_min, xtick_max, spacing))
    ax3.grid(True, which="major", axis="x")
    ax3.title.set_text(f"5v5 (SVA) On-Ice Corsi (Blue) Differential - {team}")

    # (AX4) Generates On-Ice xG Graph from Dataframe
    df_oi_xg = pd.DataFrame(oi_sva_stats).sort_values("xg_diff", ascending=True)
    df_oi_xg_toi = df_oi_xg["toi"]
    max_oi_xg_toi = max(df_oi_xg_toi)
    oi_xg_toi_color = df_oi_xg_toi / float(max_oi_xg_toi)
    oi_xg_colormap = color_map(oi_xg_toi_color)

    ax4.barh(width=df_oi_xg.xg_diff, y=df_oi_xg.player, color=oi_xg_colormap)
    spacing = 0.25
    xtick_min, xtick_max = calculate_xticks(spacing, df_oi_xg.xg_diff.min(), df_oi_xg.xg_diff.max())
    ax4.set_xticks(np.arange(xtick_min, xtick_max, spacing))
    ax4.grid(True, which="major", axis="x")
    ax4.title.set_text(f"5v5 (SVA) On-Ice xG Differential - {team}")

    # Tight Layout (Making Space for Title)
    toi_ind_fig.tight_layout(rect=[0, 0.0, 1, 0.92], pad=2)
    toi_ind_fig.suptitle(
        f"{game_title}\nIndividual & On-Ice Data\nData Courtesy: Natural Stat Trick",
        x=0.45,
        fontsize=14,
    )

    # Add a Global Colorbar
    toi_ind_fig.subplots_adjust(right=0.8, left=0)
    cbar_ax = toi_ind_fig.add_axes([0, 0.1, 1, 0.75])
    cbar_ax.axis("off")

    cbar_norm = mpl.colors.Normalize(vmin=0, vmax=1)
    cbar_sm = plt.cm.ScalarMappable(cmap=color_map, norm=cbar_norm)
    cbar_sm.set_array([])
    fig_cbar = plt.colorbar(cbar_sm, ax=cbar_ax)

    tick_locator = ticker.MaxNLocator(nbins=4)
    fig_cbar.locator = tick_locator
    fig_cbar.update_ticks()
    fig_cbar.ax.set_yticklabels(["0:00", "", "", "", toi_to_mmss(max_oi_xg_toi)])
    fig_cbar.set_label("Time on Ice", rotation=90)

    return toi_ind_fig


def charts_fwds_def(game_title, team, fwd_sva_stats, def_sva_stats):
    plt.clf()

    # Set the Colormap for All Graphs
    color_map = plt.cm.get_cmap("Blues")

    fwds_def_fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(13, 10))

    # Generate the FWD & DEF Dataframes
    df_fwd = pd.DataFrame(fwd_sva_stats).sort_values("toi", ascending=True)
    df_def = pd.DataFrame(def_sva_stats).sort_values("toi", ascending=True)

    # Only Take the 3 Highest TOI Pairings
    df_fwd = df_fwd.tail(4)
    df_def = df_def.tail(3)
    df_all_lines = pd.concat([df_fwd, df_def], sort=True)

    # (AX1) COMING SOON TEXT
    # ax1.text(0.2, 0.5, 'MORE DATA COMING SOON!', style='italic', weight="bold",
    #         bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 10})

    df_lines_stats_toi = df_all_lines["toi"]
    max_lines_stats_toi = max(df_lines_stats_toi)
    lines_stats_toi_color = df_lines_stats_toi / float(max_lines_stats_toi)
    lines_stats_colormap = color_map(lines_stats_toi_color)
    cmap_orange = plt.cm.get_cmap("Greens")(lines_stats_toi_color)
    cmap_green = plt.cm.get_cmap("Oranges")(lines_stats_toi_color)

    bar_height = 0.25
    ind = np.arange(len(df_all_lines))
    ax1.barh(
        width=df_all_lines.hdcfpct,
        y=2 * bar_height + ind,
        height=bar_height,
        color=cmap_green,
        edgecolor="white",
        label="HDCF%",
    )
    ax1.barh(
        width=df_all_lines.xgfpct,
        y=bar_height + ind,
        height=bar_height,
        color=cmap_orange,
        edgecolor="white",
        label="xGF%",
    )
    ax1.barh(
        width=df_all_lines.cfpct,
        y=ind,
        height=bar_height,
        color=lines_stats_colormap,
        edgecolor="white",
        label="CF%",
    )

    ax1.set_xticks(np.arange(0, 101, 10))
    ax1.set_yticks(bar_height + ind)
    ax1.set_yticklabels(df_all_lines.line)
    ax1.grid(True, which="major", axis="x")
    ax1.legend(loc="best")
    ax1.title.set_text(f"5v5 (SVA) CF%, xGF% & HDCF% - {team}")

    # (AX2) Generates ixG Graph from Dataframe
    df_lines_xg = df_all_lines.sort_values("xg_diff", ascending=True)

    df_lines_xg_toi = df_lines_xg["toi"]
    max_lines_xg_toi = max(df_lines_xg_toi)
    lines_xg_toi_color = df_lines_xg_toi / float(max_lines_xg_toi)
    # color_map = plt.cm.get_cmap('Reds')
    lines_xg_colormap = color_map(lines_xg_toi_color)

    ax2.barh(width=df_lines_xg.xg_diff, y=df_lines_xg.line, color=lines_xg_colormap)

    spacing = 0.25
    xtick_min, xtick_max = calculate_xticks(spacing, df_lines_xg.xg_diff.min(), df_lines_xg.xg_diff.max())
    ax2.set_xticks(np.arange(xtick_min, xtick_max, spacing))
    ax2.grid(True, which="major", axis="x")
    ax2.title.set_text(f"5v5 (SVA) xG Differential - {team}")

    # (AX3) Generates Lines Corsi Graph from Dataframe
    df_lines_corsi = df_all_lines.sort_values("corsi_diff", ascending=True)

    df_lines_corsi_toi = df_lines_corsi["toi"]
    max_lines_corsi_toi = max(df_lines_corsi_toi)
    lines_corsi_toi_color = df_lines_corsi_toi / float(max_lines_corsi_toi)
    # color_map = plt.cm.get_cmap('Reds')
    lines_corsi_colormap = color_map(lines_corsi_toi_color)

    ax3.barh(width=df_lines_corsi.corsi_diff, y=df_lines_corsi.line, color=lines_corsi_colormap)

    spacing = 3
    xtick_min, xtick_max = calculate_xticks(
        spacing, df_lines_corsi.corsi_diff.min(), df_lines_corsi.corsi_diff.max()
    )
    ax3.set_xticks(np.arange(xtick_min, xtick_max, spacing))
    ax3.grid(True, which="major", axis="x")
    ax3.title.set_text(f"5v5 (SVA) Corsi Differential - {team}")

    # (AX4) Generates Lines High Danger Graph from Dataframe
    df_lines_hdc = df_all_lines.sort_values("hdc_diff", ascending=True)

    df_lines_hdc_toi = df_lines_hdc["toi"]
    max_lines_hdc_toi = max(df_lines_hdc_toi)
    lines_hdc_toi_color = df_lines_hdc_toi / float(max_lines_hdc_toi)
    lines_hdc_colormap = color_map(lines_hdc_toi_color)

    ax4.barh(width=df_lines_hdc.hdc_diff, y=df_lines_hdc.line, color=lines_hdc_colormap)

    spacing = 1
    xtick_min, xtick_max = calculate_xticks(spacing, df_lines_hdc.hdc_diff.min(), df_lines_hdc.hdc_diff.max())
    ax4.set_xticks(np.arange(xtick_min, xtick_max, spacing))
    ax4.grid(True, which="major", axis="x")
    ax4.title.set_text(f"5v5 (SVA) High Danger Differential - {team}")

    # Tight Layout (Making Space for Title)
    fwds_def_fig.tight_layout(rect=[0, 0.0, 1, 0.93], pad=2)
    fwds_def_fig.suptitle(
        f"{game_title}\nForward Lines & Defensive Pairings\nData Courtesy: Natural Stat Trick",
        x=0.45,
        fontsize=14,
    )

    # Add a Global Colorbar
    fwds_def_fig.subplots_adjust(right=0.8, left=0)
    cbar_ax = fwds_def_fig.add_axes([0, 0.1, 1, 0.75])
    cbar_ax.axis("off")

    cbar_norm = mpl.colors.Normalize(vmin=0, vmax=1)
    cbar_sm = plt.cm.ScalarMappable(cmap=color_map, norm=cbar_norm)
    cbar_sm.set_array([])
    fig_cbar = plt.colorbar(cbar_sm, ax=cbar_ax)

    tick_locator = ticker.MaxNLocator(nbins=4)
    fig_cbar.locator = tick_locator
    fig_cbar.update_ticks()
    fig_cbar.ax.set_yticklabels(["0:00", "", "", "", toi_to_mmss(max_lines_corsi_toi)])
    fig_cbar.set_label("Time on Ice", rotation=90)

    return fwds_def_fig


def charts_overview(game, game_title, overview_stats):
    # Get the Team Colors (for the split / stacked bars)
    colors_dict = images.both_team_colors_compared(game.preferred_team.team_name, game.other_team.team_name)
    pref_colors = colors_dict["first"]
    other_colors = colors_dict["second"]

    overview_fig, ax1 = plt.subplots(1, 1, figsize=(10, 5))
    df_overview = pd.DataFrame(overview_stats).T
    df_overview_ltd = df_overview[["CF%", "SCF%", "HDCF%", "xGF%", "GF%"]]
    df_overview_ltd = (
        df_overview_ltd.replace({"%": ""}, regex=True).replace({"-": "0"}, regex=True).apply(pd.to_numeric)
    )

    # Re-Transpose & Reverse
    df_overview_ltd = df_overview_ltd.T.iloc[::-1]
    df_overview_ltd.plot(
        kind="barh",
        stacked=True,
        ax=ax1,
        color=[[x / 255 for x in pref_colors["bg"]], [x / 255 for x in other_colors["bg"]]],
    )
    ax1.grid(True, which="major", axis="x", color="#cccccc")
    ax1.set_axisbelow(True)
    ax1.set(frame_on=False)
    ax1.legend(
        [game.preferred_team.short_name, game.other_team.short_name],
        bbox_to_anchor=(0.5, -0.2),
        loc="lower center",
        ncol=2,
        frameon=False,
    )
    ax1.title.set_text(f"{game_title}\nTeam Overview Stats - 5v5 (SVA)\nData Courtesy: Natural Stat Trick")

    for i, v in enumerate(df_overview_ltd["pref"].values):
        if v > 0:
            ax1.text(
                float(v) - 2,
                i,
                str(v),
                va="center",
                ha="right",
                color=[x / 255 for x in pref_colors["text"]],
                fontweight="bold",
            )

    for i, v in enumerate(df_overview_ltd["other"].values):
        if v > 0:
            ax1.text(
                100 - 2,
                i,
                str(v),
                va="center",
                ha="right",
                color=[x / 255 for x in other_colors["text"]],
                fontweight="bold",
            )

    return overview_fig


def generate_all_charts(game: Game):
    # This is our return value, which is a list of file paths.
    list_of_charts = list()

    nst_report_url = get_nst_report_url(game, full=True)
    logging.info("NST Report URL: %s", nst_report_url)
    resp = thirdparty.thirdparty_request(nst_report_url)
    soup = thirdparty.bs4_parse(resp.content)

    # Find Game Title (For Chart Header)
    game_title = soup.find("h1").text

    # Section off separate parts of NST for different parsing routins
    ov_sva = soup.find("table", id=f"tbtssva").find("tbody")
    ov_header = soup.find("table", id=f"tbtsall").find("thead").find_all("th")
    ov_keys = [x.text for x in ov_header if x.text]

    ov_sva_stats = parse_overview(ov_keys, ov_sva)

    # Add pref / other keys to this final dictionary so we can re-arrange if necessary
    ov_sva_final_stats = {
        # "home": ov_sva_stats["home"]["Final"],
        # "away": ov_sva_stats["away"]["Final"],
        "pref": ov_sva_stats[game.preferred_team.home_away]["Final"],
        "other": ov_sva_stats[game.other_team.home_away]["Final"],
    }

    logging.info("Generating Team Overview Chart.")
    # flipped_game_title = game_title.replace(" @ ", "@").split("@")
    # flipped_game_title = f"{flipped_game_title[1]} vs. {flipped_game_title[0]}"
    title_separator = "vs" if game.preferred_team.home_away == "home" else "@"
    preferred_game_title = f"{game.preferred_team.team_name} {title_separator} {game.other_team.team_name}"
    overview_chart = charts_overview(game, preferred_game_title, ov_sva_final_stats)
    overview_chart_path = os.path.join(IMAGES_PATH, "temp", f"allcharts-overview-{game.game_id_shortid}.png")
    logging.info("Image Path: %s", overview_chart_path)
    overview_chart.savefig(overview_chart_path, bbox_inches="tight")

    # Add the overview image path to our list
    list_of_charts.append(overview_chart_path)

    # Generate team specific charts (2x per team)
    teams = [game.preferred_team, game.other_team]
    for team in teams:
        team_abbrev = nst_abbreviation(team.team_name).replace(".", "")
        logging.info("%s (%s)", team.team_name, team_abbrev)

        # Find Game Title (For Chart Header)
        game_title = soup.find("h1").text

        # Section off separate parts of NST for different parsing routins
        ov_sva = soup.find("table", id=f"tbtssva").find("tbody")
        ov_header = soup.find("table", id=f"tbtsall").find("thead").find_all("th")
        ov_keys = [x.text for x in ov_header if x.text]

        ind_5v5 = soup.find(id=f"tb{team_abbrev}st5v5").find("tbody").find_all("tr")
        ind_pp = soup.find(id=f"tb{team_abbrev}stpp").find("tbody").find_all("tr")
        ind_pk = soup.find(id=f"tb{team_abbrev}stpk").find("tbody").find_all("tr")
        oi_sva = soup.find(id=f"tb{team_abbrev}oisva").find("tbody").find_all("tr")
        fwd_sva = soup.find(id=f"tb{team_abbrev}flsva").find("tbody").find_all("tr")

        # Create Dictionarys needed for parsing players
        players = soup.find(id=f"tb{team_abbrev}st5v5").find("tbody").find_all("tr")
        all_players = [x.find_all("td")[0].text.replace("\xa0", " ") for x in players]
        defense = [
            x.find_all("td")[0].text.replace("\xa0", " ") for x in players if x.find_all("td")[1].text == "D"
        ]

        team_dropdown = soup.find(id=f"s{team_abbrev}lb").find_next_sibling("ul").find_all("li")
        all_players_ids = [x.label.attrs["for"][2:] for x in team_dropdown]
        all_players_dict = {
            x.label.attrs["for"][2:]: " ".join(x.text.replace("\xa0", " ").split()[1:]) for x in team_dropdown
        }
        def_player_ids = [
            x.label.attrs["for"][2:] for x in team_dropdown if x.text.replace("\xa0", " ") in defense
        ]
        def_players_dict = {
            x.label.attrs["for"][2:]: x.text.replace("\xa0", " ")
            for x in team_dropdown
            if x.text.replace("\xa0", " ") in defense
        }

        # All NST Parsing Routines
        toi_dict, ind_stats = parse_nst_timeonice(ind_5v5, ind_pp, ind_pk)
        oi_sva_stats = parse_nst_oistats(oi_sva)
        fwd_sva_stats = parse_nst_fwdstats(fwd_sva)
        def_sva_stats = parse_nst_defstats(soup, def_player_ids, def_players_dict)

        # oppo_toi, oppo_cfwith = parse_nst_opposition(team_abbrev, soup, all_players_ids, all_players_dict)
        # linemate_toi, linemate_cfwith = parse_nst_linemate(team_abbrev, soup, all_players_ids, all_players_dict)

        # Now create all necessary graphs, charts, heatmaps, etc
        # heatmap = charts_heatmap_oppo_lm(game_title, team.short_name, oppo_toi, oppo_cfwith, linemate_toi, linemate_cfwith)
        # heatmap.savefig(f'{PROJECT_ROOT}/allcharts-heatmaps-{team_abbrev}-{game.game_id_shortid}.png')

        logging.info("Generating Individual / On-Ice charts for %s.", team.team_name)
        ind_onice_chart = charts_toi_individual(
            game_title, team.short_name, toi_dict, ind_stats, oi_sva_stats
        )
        ind_onice_chart_path = os.path.join(
            IMAGES_PATH, "temp", f"allcharts-ind-onice-{team_abbrev}-{game.game_id_shortid}.png"
        )
        logging.info("Image Path: %s", ind_onice_chart_path)
        ind_onice_chart.savefig(ind_onice_chart_path, bbox_inches="tight")

        logging.info("Generating Forwards Lines / Defensive Pairing charts for %s.", team.team_name)
        fwds_def_chart = charts_fwds_def(game_title, team.short_name, fwd_sva_stats, def_sva_stats)
        fwds_def_chart_path = os.path.join(
            IMAGES_PATH, "temp", f"allcharts-fwd-def-{team_abbrev}-{game.game_id_shortid}.png"
        )
        logging.info("Image Path: %s", fwds_def_chart_path)
        fwds_def_chart.savefig(fwds_def_chart_path, bbox_inches="tight")

        list_of_charts.append(ind_onice_chart_path)
        list_of_charts.append(fwds_def_chart_path)

    return list_of_charts


def team_season_rank(df: pd.DataFrame, stat, team_name):
    """ Takes a dataframe, a stat & a team name and finds the "rank" of that team in the DataFrame. """

    # Sort the dataframe and find the team index
    # Add 1 because a Dataframe is 0-index
    sorted_df = df.sort_values(stat, ascending=False).reset_index(drop=True)
    rank = sorted_df.index[sorted_df["Team"] == team_name].tolist()[0] + 1
    return rank


def generate_team_season_charts(team_name, situation, lastgames=False):
    urls = utils.load_urls()
    nst_base = urls["endpoints"]["nst"]
    last_games_mod = "" if not lastgames else f"&gp={lastgames}&gpf=c"
    nst_team_url = f"{nst_base}/teamtable.php?sit={situation}{last_games_mod}"

    resp = thirdparty.thirdparty_request(nst_team_url)
    soup = thirdparty.bs4_parse(resp.content)

    # Get the team table information, convert to a Dataframe
    # And add the league average as an extra row
    teams = soup.find("table", id=f"teams")
    teams_df = pd.read_html(str(teams), index_col=0)[0]

    # Before we calculate the average, store a copy of the dataframe that we can use to get rankings
    rank_df = teams_df.copy()

    teams_df.loc["avg"] = teams_df.mean()
    teams_df.reset_index(drop=True)
    num_rows = teams_df.shape[0]
    last_row_index = num_rows - 1
    teams_df.iloc[last_row_index, teams_df.columns.get_loc("Team")] = "Average"

    # Create two dataframes (for the two halves) of the report card
    pref_df = teams_df.loc[teams_df["Team"].isin([team_name, "Average"])]
    pref_df_no_against = pref_df[["Point %", "xGF", "GF", "SH%", "SV%", "PDO", "HDSH%", "HDSV%"]]
    pref_df = pref_df[["CF%", "SCF%", "HDCF%", "xGF%", "GF%"]]

    # Transpose them to make them easier to work with in the correct form
    pref_df_T = pref_df.T
    pref_df_no_against = pref_df_no_against.T

    # Manipulate the data frames to drop & rename columns for named access
    pref_df_T["FOR"] = pref_df_T.iloc[:, 0]
    pref_df_T.drop(pref_df_T.columns[0], axis=1, inplace=True)
    pref_df_T.drop("avg", axis=1, inplace=True)
    pref_df_no_against["FOR"] = pref_df_no_against.iloc[:, 0]
    pref_df_no_against.drop(pref_df_no_against.columns[0], axis=1, inplace=True)

    # Perform DataFrame data clean up
    # Convert the "Against Column to 100-value" to make sure each row totals 100
    # Convert PDO & Point % to full percentage values
    pref_df_T["AGAINST"] = pref_df_T.apply(lambda row: 100 - row.FOR, axis=1)
    pref_df_no_against["FOR"]["Point %"] = pref_df_no_against["FOR"]["Point %"] * 100
    pref_df_no_against["FOR"]["PDO"] = pref_df_no_against["FOR"]["PDO"] * 100
    pref_df_no_against["avg"]["Point %"] = pref_df_no_against["avg"]["Point %"] * 100
    pref_df_no_against["avg"]["PDO"] = pref_df_no_against["avg"]["PDO"] * 100

    # Reverse the Order of the DataFrame rows to make the graph look cleaner
    pref_df_T = pref_df_T.iloc[::-1]
    pref_df_no_against = pref_df_no_against.iloc[::-1]

    # Get the team primary bg & text color
    team_colors = images.team_colors(team_name)
    team_colors = team_colors["primary"]
    team_color_bg = images.rgb_to_hex(team_colors["bg"])
    team_color_text = images.rgb_to_hex(team_colors["text"])

    # For each index value of the dataframe, add the rank to that index
    # We transpose twice because volumns are easier to work with
    ranked_columns = list()
    pref_df_T = pref_df_T.T
    for col in pref_df_T.columns:
        stat_rank = utils.ordinal(team_season_rank(rank_df, col, team_name))
        ranked_col = f"{col} ({stat_rank})"
        ranked_columns.append(ranked_col)
    pref_df_T.columns = ranked_columns
    pref_df_T = pref_df_T.T

    ranked_columns = list()
    pref_df_no_against = pref_df_no_against.T
    for col in pref_df_no_against.columns:
        stat_rank = utils.ordinal(team_season_rank(rank_df, col, team_name))
        ranked_col = f"{col} ({stat_rank})"
        ranked_columns.append(ranked_col)
    pref_df_no_against.columns = ranked_columns
    pref_df_no_against = pref_df_no_against.T

    # Create the figure that we will plot the two separate graphs on
    overview_fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))

    # Plot the top (no against) bar graph & the leage average line graph
    pref_df_no_against[["FOR"]].plot.barh(ax=ax1, color=team_color_bg)

    ax1.plot(
        pref_df_no_against[["avg"]].avg.values,
        pref_df_no_against[["avg"]].index.values,
        # marker="H",
        marker="X",
        linestyle="",
        color="#AAAAAA",
    )

    # Plot the bottom (split bar graph) in the team & a gray color for the opposition
    pref_df_T.plot(kind="barh", stacked=True, ax=ax2, color=[team_color_bg, "#AAAAAA"])

    # Clean up the plots (fixes axes, legends, etc)
    ax1.legend().remove()
    ax1.legend(["League Average"], bbox_to_anchor=(0.5, -0.2), loc="lower center", ncol=1, frameon=False)

    ax2.legend(
        [team_name, "Opponents"],
        bbox_to_anchor=(0.5, -0.2),
        loc="lower center",
        ncol=2,
        frameon=False,
    )

    for ax in [ax1, ax2]:
        ax.grid(True, which="major", axis="x", color="#cccccc")
        ax.set_axisbelow(True)
        ax.set(frame_on=False)

    # Add the Figure Title
    last_games_title = "Season Stats" if not lastgames else f"Last {lastgames} Games"
    sit_label = "5v5 (SVA)" if situation == "sva" else "All Situations"
    print(situation, sit_label)
    ax1.title.set_text(f"{team_name} {last_games_title} - {sit_label}\nData Courtesy: Natural Stat Trick")

    # Draw the text labels on each of the corresponding bars
    # The top graph values are centered in the bar so it doesn't conflict with the average marker
    for i, v in enumerate(pref_df_no_against["FOR"].values):
        ax1.text(
            float(v) / 2,
            i,
            str(round(v, 2)),
            va="center",
            ha="center",
            color=team_color_text,
            fontweight="bold",
        )

    for i, v in enumerate(pref_df_T["FOR"].values):
        ax2.text(
            float(v) - 2,
            i,
            str(v),
            va="center",
            ha="right",
            color=team_color_text,
            fontweight="bold",
        )

    for i, v in enumerate(pref_df_T["AGAINST"].values):
        ax2.text(100 - 2, i, str(v), va="center", ha="right", color=team_color_text, fontweight="bold")

    last_games_file = "" if not lastgames else f"-last{lastgames}-"
    overview_fig_path = os.path.join(
        IMAGES_PATH, "temp", f"allcharts-yesterday-team-season-{situation}-{last_games_file}.png"
    )
    overview_fig.savefig(overview_fig_path, bbox_inches="tight")
    return overview_fig_path
