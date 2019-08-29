import os

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from hockeygamebot.definitions import PROJECT_ROOT
from hockeygamebot.helpers import utils
from hockeygamebot.models.game import Game


class Backgrounds:
    """ Paths to background images & files used in the imaging module. """

    PREGAME = os.path.join(PROJECT_ROOT, "resources/images/BG2019-Gameday-Pregame.png")


class Colors:
    """ Specifies commonly used colors. """

    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)


class FontFiles:
    """ Paths to font files used in the imaging module. """

    BITTER_REGULAR = os.path.join(PROJECT_ROOT, "resources/fonts/Bitter-Regular.ttf")
    BITTER_BOLD = os.path.join(PROJECT_ROOT, "resources/fonts/Bitter-Bold.ttf")


class FontSizes:
    """ Font sizes used in the imaging module. """

    TITLE = 80
    DETAIL_LARGE = 56
    DETAIL_SMALL = 50
    RECORD = 38
    GAMENUMBER = 40
    PRESEASON = 28


def center_text(draw, left, top, width, text, color, font, vertical=False, height=None):
    """ Draws text (at least) horizontally centered in a specified width. Can also
        center vertically if specified.

    Args:
        draw: Current PIL draw Object
        left: left coordinate (x) of the bounding box
        top: top coordinate (y) of the bounding box
        width: width of the bounding box
        text: text to draw
        color: color to draw the text in
        font: ImageFont instance

        vertical: align vertically
        height: height of the box to align vertically

    Returns:
        None
    """

    # Get text size (string length & font)
    w, h = draw.textsize(text, font)
    left_new = left + ((width - w) / 2)

    if not vertical:
        coords_new = (left_new, top)
        # Draw the text with the new coordinates
        draw.text(coords_new, text, fill=color, font=font, align="center")
    else:
        _, offset_y = font.getoffset(text)
        top_new = top + ((height - h - offset_y) / 2)
        coords_new = (left_new, top_new)
        # Draw the text with the new coordinates
        draw.text(coords_new, text, fill=color, font=font, align="center")


def pregame_image(game: Game):
    """ Generates the pre-game image that is sent to social media platforms at the first
        run of the hockeygamebot script per day.

    Args:
        game: Current Game object

    Returns:
        None
    """

    # Fonts used within the pregame image
    FONT_TITLE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.TITLE)
    FONT_RECORD = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.RECORD)
    FONT_DETAIL_LARGE = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.DETAIL_LARGE)
    FONT_DETAIL_SMALL = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.DETAIL_SMALL)
    FONT_GAMENUMBER = ImageFont.truetype(FontFiles.BITTER_BOLD, FontSizes.GAMENUMBER * 3)

    # Pre-game specific constant values (incl coordinates)
    HEADER_TEXT = "PRE-GAME MATCHUP"
    LOGO_Y = 150
    COORDS_HOME_X = 245
    COORDS_AWAY_X = 650
    COORDS_HOME_LOGO = (COORDS_HOME_X, LOGO_Y)
    COORDS_AWAY_LOGO = (COORDS_AWAY_X, LOGO_Y)
    COORDS_GAME_NUM = (-90, 80)
    TEAM_RECORD_Y = LOGO_Y + 200

    # Generate records, venue & other strings
    home_pts = game.home_team.points
    home_record_str = f"{home_pts} PTS • {game.home_team.current_record}"
    away_pts = game.away_team.points
    away_record_str = f"{away_pts} PTS • {game.away_team.current_record}"

    text_gamenumber = (
        "PRESEASON" if game.game_type == "PR" else f"{game.preferred_team.games + 1} OF 82"
    )

    text_datetime = f"{game.game_date_short} • {game.game_time_local}"
    text_hashtags = (
        f"{utils.team_hashtag(game.preferred_team.team_name, game.game_type)} • {game.game_hashtag}"
    )

    bg = Image.open(Backgrounds.PREGAME)
    bg_w, bg_h = bg.size

    away_team = game.away_team.team_name.replace(" ", "")
    home_team = game.home_team.team_name.replace(" ", "")
    away_logo = Image.open(os.path.join(PROJECT_ROOT, f"resources/logos/{away_team}.png"))
    home_logo = Image.open(os.path.join(PROJECT_ROOT, f"resources/logos/{home_team}.png"))

    # Paste the home / away logos with the mask the same as the image
    bg.paste(away_logo, COORDS_AWAY_LOGO, away_logo)
    bg.paste(home_logo, COORDS_HOME_LOGO, home_logo)

    # Generates a 'draw' object that we use to draw on top of the image
    draw = ImageDraw.Draw(bg)

    # Draw text items on the background now
    center_text(
        draw=draw, left=0, top=0, width=bg_w, text=HEADER_TEXT, color=Colors.WHITE, font=FONT_TITLE
    )

    center_text(
        draw=draw,
        left=COORDS_HOME_X,
        top=TEAM_RECORD_Y,
        width=300,
        text=home_record_str,
        color=Colors.WHITE,
        font=FONT_RECORD,
    )

    center_text(
        draw=draw,
        left=COORDS_AWAY_X,
        top=TEAM_RECORD_Y,
        width=300,
        text=away_record_str,
        color=Colors.WHITE,
        font=FONT_RECORD,
    )

    center_text(
        draw=draw,
        left=0,
        top=480,
        width=bg_w,
        text=text_datetime,
        color=Colors.WHITE,
        font=FONT_DETAIL_LARGE,
    )

    center_text(
        draw=draw,
        left=0,
        top=540,
        width=bg_w,
        text=game.venue.upper(),
        color=Colors.WHITE,
        font=FONT_DETAIL_LARGE,
    )

    center_text(
        draw=draw,
        left=0,
        top=600,
        width=bg_w,
        text=text_hashtags,
        color=Colors.WHITE,
        font=FONT_DETAIL_SMALL,
    )

    # Create a new image to put the game number & cleanly rotate it
    txt = Image.new("L", (900, 900))
    d = ImageDraw.Draw(txt)
    center_text(
        draw=d, left=0, top=0, width=900, text=text_gamenumber, color=255, font=FONT_GAMENUMBER
    )
    w = txt.rotate(315, expand=True, resample=Image.BICUBIC)
    w_resize = w.resize((300, 300), Image.ANTIALIAS)
    bg.paste(w_resize, COORDS_GAME_NUM, w_resize)

    return bg
