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
    CUSTOM_STATS_FONT =custom_font_size(FONT_OPENSANS_REGULAR, 21)

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
