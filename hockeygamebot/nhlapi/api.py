"""
Single module to call the NHL API.
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from subprocess import Popen

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, RequestException

from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.sessions import SessionFactory


def nhl_api(url):
    sf = SessionFactory()
    session = sf.get()

    retries = HTTPAdapter(max_retries=3)
    session.mount("https://", retries)
    session.mount("http://", retries)

    try:
        logging.info("Sending API Request - %s", url)
        response = session.get(url)
        return response
    except ConnectionError as ce:
        logging.error(ce)
        return None
    except RequestException as re:
        logging.error(re)
        return None
