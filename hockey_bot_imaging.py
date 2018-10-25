"""This module contains functions related to gathering
   advanced post-game stats to tweet."""

# pylint: disable=too-few-public-methods

import configparser
import datetime
import logging
import os
import re

import dateutil.tz
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

import nhl_game_events


PROJECT_ROOT = os.path.dirname(os.path.realpath(__file__))

log = logging.getLogger('root')
config = configparser.ConfigParser()
conf_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.ini')
config.read(conf_path)

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Utility Imaging Functions
# ------------------------------------------------------------------------------

def custom_font_size(fontName, size):
    return ImageFont.truetype(fontName, size)


def scaled_color(percentage):
    if 75 <= percentage <= 100:
        color = (0, 50, 191)
    elif 62.5 <= percentage <= 75:
        color = (63, 37, 143)
    elif 50 <= percentage <= 62.5:
        color = (0, 0, 0)
    elif 37.5 <= percentage <= 50:
        color = (191, 12, 47)
    else:
        color = (255, 0, 0)

    return color


def draw_centered_text(draw, coords, width, text, color, font):
    # Get individual coordinates
    x_coords = coords[0]
    y_coords = coords[1]

    # Get text size (string length & font)
    w, h = draw.textsize(text, font)
    x_coords_new = x_coords + ((width - w) / 2)
    coords_new = (x_coords_new, y_coords)

    # Draw the text with the new coordinates
    draw.text(coords_new, text, color, font)

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Image Generators
# ------------------------------------------------------------------------------

def image_generator_nss_linetool(stats_dictionary):
    logging.info('Generating the advanced stats image (via nss_linetool data).')
    logging.info('NSS Dictionary - %s', stats_dictionary)

    # Font Color & Constants
    FONT_COLOR_BLACK = (0, 0, 0)

    FONT_OPENSANS_REGULAR = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Regular.ttf')
    FONT_OPENSANS_BOLD = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Bold.ttf')
    CUSTOM_LINE_FONT = custom_font_size(FONT_OPENSANS_BOLD, 21)
    CUSTOM_STATS_FONT = custom_font_size(FONT_OPENSANS_REGULAR, 21)

    # Width & Coordinate Constants
    WIDTH_STAT = 92
    COORDS_LINE_Y = 222

    COORDS_LINE_NAME_X = 150
    COORDS_CF_X = 548
    COORDS_SCF_X = 665
    COORDS_GF_X = 781
    COORDS_HDCF_X = 899

    WIDTH_TOI = 125
    COORDS_TOI_X = 1015

    # Load background image & create draw objects
    bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayV3-AdvancedStats.png'))
    draw = ImageDraw.Draw(bg)
    draw.fontmode = "0"

    # Draw Forward / Defense stats
    for line, attr in stats_dictionary.items():
        if line[0] not in ('F', 'D'):
            continue

        logging.debug('Advanced Stats Image Generator for Line - %s', line)

        line_names = attr.get('name')
        line_cf = str(attr.get('CF'))
        line_scf = str(attr.get('SCF'))
        line_gf = str(attr.get('GF'))
        line_hdcf = str(attr.get('HDCF'))
        line_toi = attr.get('TOI')

        # Draw all text elements
        draw.text((COORDS_LINE_NAME_X, COORDS_LINE_Y), line_names, FONT_COLOR_BLACK, CUSTOM_LINE_FONT)
        draw_centered_text(draw, (COORDS_CF_X, COORDS_LINE_Y), WIDTH_STAT, line_cf, FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
        draw_centered_text(draw, (COORDS_SCF_X, COORDS_LINE_Y), WIDTH_STAT, line_scf, FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
        draw_centered_text(draw, (COORDS_GF_X, COORDS_LINE_Y), WIDTH_STAT, line_gf, FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
        draw_centered_text(draw, (COORDS_HDCF_X, COORDS_LINE_Y), WIDTH_STAT, line_hdcf, FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
        draw_centered_text(draw, (COORDS_TOI_X, COORDS_LINE_Y), WIDTH_TOI, line_toi, FONT_COLOR_BLACK, CUSTOM_STATS_FONT)

        # Increment the Y-Coordinate (to shift down a row)
        COORDS_LINE_Y += 57

    # Draw Team Totals Stats
    team_stats = stats_dictionary.get('team')
    draw_centered_text(draw, (COORDS_CF_X, COORDS_LINE_Y), WIDTH_STAT, team_stats.get('CF'), FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
    draw_centered_text(draw, (COORDS_SCF_X, COORDS_LINE_Y), WIDTH_STAT, team_stats.get('SCF'), FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
    draw_centered_text(draw, (COORDS_GF_X, COORDS_LINE_Y), WIDTH_STAT, team_stats.get('GF'), FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
    draw_centered_text(draw, (COORDS_HDCF_X, COORDS_LINE_Y), WIDTH_STAT, team_stats.get('HDCF'), FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
    draw_centered_text(draw, (COORDS_TOI_X, COORDS_LINE_Y), WIDTH_TOI, team_stats.get('TOI'), FONT_COLOR_BLACK, CUSTOM_STATS_FONT)

    return bg


def image_generator_nss_opposition(opposition_dictionary):
    logging.info('Generating the primary opposition image (via nss_opposition data).')
    logging.info('NSS Dictionary - %s', opposition_dictionary)

    # Font Color & Constants
    FONT_COLOR_BLACK = (0, 0, 0)

    FONT_OPENSANS_BOLD = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Bold.ttf')
    FONT_OPENSANS_REGULAR = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Regular.ttf')
    CUSTOM_STATS_FONT = custom_font_size(FONT_OPENSANS_BOLD, 21)
    CUSTOM_OPP_FONT = custom_font_size(FONT_OPENSANS_REGULAR, 20)

    # Width & Coordinate Constants
    WIDTH_OPP = 282
    COORDS_LINE_Y = 222
    COORDS_OPP_Y = 225

    COORDS_LINE_NAME_X = 150
    COORDS_FWD_X = 548
    COORDS_DEF_X = 858

    # Load background image & create draw objects
    bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/GamedayV3-PrimaryOpposition.png'))
    draw = ImageDraw.Draw(bg)
    draw.fontmode = "0"

    for line, attr in opposition_dictionary.items():
        line_names = attr.get('line')
        opp_fwd = ', '.join(attr.get('FWD'))
        opp_def = ', '.join(attr.get('DEF'))
        draw.text((COORDS_LINE_NAME_X, COORDS_LINE_Y), line_names, FONT_COLOR_BLACK, CUSTOM_STATS_FONT)
        draw_centered_text(draw, (COORDS_FWD_X, COORDS_LINE_Y), WIDTH_OPP, opp_fwd, FONT_COLOR_BLACK, CUSTOM_OPP_FONT)
        draw_centered_text(draw, (COORDS_DEF_X, COORDS_LINE_Y), WIDTH_OPP, opp_def, FONT_COLOR_BLACK, CUSTOM_OPP_FONT)
        COORDS_LINE_Y += 57

    return bg


def image_generator_shotmap(game, all_plays):
    """
    Takes a game & JSON object of game events and generates a shot map.

    Input:
    game - current game as a Game object
    all_plays - JSON object of allPlays from the liveFeed API

    Ouput:
    bg (Image): Image object of shot map.
    """

    logging.info('Generating shotmap for both teams.')

    MAPPED_EVENTS = ('SHOT', 'MISSED_SHOT', 'GOAL')
    IMG_HALF_WIDTH = 512
    IMG_WIDTH = 1024
    IMG_HALF_HEIGHT_RINK = 218
    IMG_HALF_HEIGHT_ALL = 256

    preferred_team = game.preferred_team.team_name
    other_team = game.other_team.team_name
    home_team = game.home_team.team_name
    home_team_short = game.home_team.short_name
    away_team = game.away_team.team_name
    away_team_short = game.away_team.short_name

    logging.info('Preferred Team: %s', preferred_team)
    logging.info('Other Team: %s', other_team)
    logging.info('Home Team: %s', home_team)
    logging.info('Away Team: %s', away_team)

    home_events = []
    away_events = []

    # Loop through all plays and build a list of mapped events
    for play in all_plays:
        event_type = play['result']['eventTypeId']

        # If play is not mapped, continue (skips loop iteration)
        if event_type not in MAPPED_EVENTS:
            continue

        team = play['team']['name']
        period = play['about']['period']
        coords_x = play['coordinates']['x']
        coords_y = play['coordinates']['y']

        # Flip coordinates if 2nd period (or overtime)
        if period % 2 == 0:
            coords_x = coords_x * -1
            coords_y = coords_y * -1

        # If play is outside of the grid, skip it (unless its a Goal)
        if event_type != "GOAL" and (abs(coords_x) > 100 or abs(coords_y) > 42.5):
            continue

        coords_img_x = (IMG_HALF_WIDTH * (coords_x / 100)) + IMG_HALF_WIDTH
        coords_img_y = (IMG_HALF_HEIGHT_RINK * (coords_y / 42.5)) + IMG_HALF_HEIGHT_ALL

        event = {}
        event['period'] = period
        event['event_type'] = event_type
        event['team'] = team
        event['coords_x'] = coords_x
        event['coords_y'] = coords_y
        event['coords_img_x'] = coords_img_x
        event['coords_img_y'] = coords_img_y

        if team == home_team:
            home_events.append(event)
        else:
            away_events.append(event)

    # Get Team Colors (via functions)
    pref_colors = nhl_game_events.team_colors(preferred_team)
    other_colors = nhl_game_events.team_colors(other_team)
    logging.debug("Pref Colors - %s // Other Colors - %s", pref_colors, other_colors)

    if pref_colors["primary"]["bg"] == other_colors["primary"]["bg"]:
        logging.debug("Primary Colors are the same!")
        pref_color = pref_colors["primary"]["bg"]
        other_color = other_colors["secondary"]["bg"]
    else:
        pref_color = pref_colors["primary"]["bg"]
        other_color = other_colors["primary"]["bg"]

    if preferred_team == home_team:
        logging.info('Preferred Team is home.')
        home_color = pref_color
        away_color = other_color
    else:
        logging.info('Preferred Team is away.')
        home_color = other_color
        away_color = pref_color

    # Setup Fonts, Constants & Sizing
    FONT_COLOR_BLACK = (0, 0, 0)
    FONT_OPENSANS_BOLD = os.path.join(PROJECT_ROOT, 'resources/fonts/OpenSans-Bold.ttf')
    SHOT_FONT = custom_font_size(FONT_OPENSANS_BOLD, 15)
    GOAL_FONT = custom_font_size(FONT_OPENSANS_BOLD, 20)
    TITLE_FONT = custom_font_size(FONT_OPENSANS_BOLD, 28)
    SUBTITLE_FONT = custom_font_size(FONT_OPENSANS_BOLD, 15)
    LEGEND_FONT = custom_font_size(FONT_OPENSANS_BOLD, 11)
    MARKERS_DICT = {"MISSED_SHOT": "x", "SHOT": "o", "GOAL": "G"}

    # Load background & create a draw object
    bg = Image.open(os.path.join(PROJECT_ROOT, 'resources/images/Rink-Shotmap-Blank.png'))
    draw = ImageDraw.Draw(bg)
    title = f'{home_team} vs. {away_team}'

    if home_events[0]['coords_x'] > 0:
        right_subtitle = f'{home_team_short} Shot Distribution'
        left_subtitle = f'{away_team_short} Shot Distribution'
    else:
        left_subtitle = f'{home_team_short} Shot Distribution'
        right_subtitle = f'{away_team_short} Shot Distribution'

    legend_text = 'x - Missed Shot | o - Shot on Goal | G - Goal'
    draw_centered_text(draw, (0, 0), IMG_WIDTH, title, FONT_COLOR_BLACK, TITLE_FONT)
    draw_centered_text(draw, (0, 480), 380, left_subtitle, FONT_COLOR_BLACK, SUBTITLE_FONT)
    draw_centered_text(draw, (640, 480), 380, right_subtitle, FONT_COLOR_BLACK, SUBTITLE_FONT)
    draw_centered_text(draw, (380, 483), 260, legend_text, FONT_COLOR_BLACK, LEGEND_FONT)


    # Loop through list of events (for each team) and map points
    for event in home_events:
        event_type = event['event_type']
        marker = MARKERS_DICT[event_type]
        if event_type == "GOAL":
            coords = (event['coords_img_x'] - 15, event['coords_img_y'] - 15)
            draw.text(coords, marker, home_color, GOAL_FONT)
        else:
            coords = (event['coords_img_x'] - 10, event['coords_img_y'] - 10)
            draw.text(coords, marker, home_color, SHOT_FONT)

    for event in away_events:
        coords = (event['coords_img_x'], event['coords_img_y'])
        event_type = event['event_type']
        marker = MARKERS_DICT[event_type]
        if event_type == "GOAL":
            coords = (event['coords_img_x'] - 15, event['coords_img_y'] - 15)
            draw.text(coords, marker, away_color, GOAL_FONT)
        else:
            coords = (event['coords_img_x'] - 10, event['coords_img_y'] - 10)
            draw.text(coords, marker, away_color, SHOT_FONT)

    return bg
