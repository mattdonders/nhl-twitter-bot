"""
This module contains functions related to gathering information
from Natural Stat Trick for advanced stats reports.
"""

import logging
from bs4 import BeautifulSoup

import requests
from datetime import datetime, timedelta
from dateutil.parser import parse
from requests.adapters import HTTPAdapter
from fake_useragent import UserAgent

from hockeygamebot.helpers import utils
from hockeygamebot.models.sessions import SessionFactory