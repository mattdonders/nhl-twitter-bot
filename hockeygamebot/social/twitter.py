"""
This module handles all interactions with Twitter.
"""

import logging

import tweepy

from hockeygamebot.helpers import utils
from hockeygamebot.helpers import arguments


def get_api():
    """
    Returns an Authorized session of the Tweepy API.

    Input:
        None

    Output:
        tweepy_session - authorized twitter session that can send a tweet.
    """
    args = arguments.parse_arguments()
    twitterenv = "twitter-debug" if args.debugtweets else "twitter"
    twitter_config = utils.load_config()[twitterenv]

    consumer_key = twitter_config["consumer_key"]
    consumer_secret = twitter_config["consumer_secret"]
    access_token = twitter_config["access_token"]
    access_secret = twitter_config["access_secret"]

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)

    tweepy_session = tweepy.API(auth)
    return tweepy_session


def send_tweet(tweet_text, media=None, reply=None):
    """ Generic tweet function that uses logic to call other specific functions.

    Args:
        tweet_text: The text to send as a tweet (may contain URL at end to qote tweet).
        media: Any media we want to upload to Twitter (images, videos, GIFs)
        reply: Are we replying to a specific tweet (for threading purposes)

    Returns:
        last_tweet - A link to the last tweet sent (or search result if duplicate)
                     If duplicate cannot be found, returns base URL (also raises error)
    """
    args = arguments.parse_arguments()
    twitterenv = "twitter-debug" if args.debugtweets else "twitter"
    twitter_config = utils.load_config()[twitterenv]
    twitter_handle = twitter_config["handle"]
    if args.notweets:
        logging.info("%s", tweet_text)
        return "https://twitter.com/{handle}/status".format(handle=twitter_handle)

