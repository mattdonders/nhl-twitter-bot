"""
This module handles all interactions with Twitter.
"""

import logging

import tweepy

from hockeygamebot.helpers import arguments, utils
from hockeygamebot.models.hashtag import Hashtag


def get_api():
    """
    Returns an Authorized session of the Tweepy API.

    Input:
        None

    Output:
        tweepy_session - authorized twitter session that can send a tweet.
    """
    args = arguments.get_arguments()

    twitterenv = "debug" if args.debugsocial else "prod"
    twitter_config = utils.load_config()["twitter"][twitterenv]

    consumer_key = twitter_config["consumer_key"]
    consumer_secret = twitter_config["consumer_secret"]
    access_token = twitter_config["access_token"]
    access_secret = twitter_config["access_secret"]

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_secret)

    tweepy_session = tweepy.API(auth)
    return tweepy_session


def send_tweet(
    tweet_text, media=None, reply=None, hashtags=None, team_hashtag=None, game_hashtag=None
):
    """ Generic tweet function that uses logic to call other specific functions.

    Args:
        tweet_text: The text to send as a tweet (may contain URL at end to qote tweet).
        media: Any media we want to upload to Twitter (images, videos, GIFs)
        reply: Are we replying to a specific tweet (for threading purposes)

    Returns:
        last_tweet - A link to the last tweet sent (or search result if duplicate)
                     If duplicate cannot be found, returns base URL (also raises error)
    """
    logging.info("[TWITTER] %s (Media: %s, Reply: %s)", tweet_text, media, reply)
    args = arguments.get_arguments()

    twitterenv = "debug" if args.debugsocial else "prod"
    twitter_config = utils.load_config()["twitter"][twitterenv]
    twitter_handle = twitter_config["handle"]
    if args.notweets:
        logging.info("%s", tweet_text)
        return "https://twitter.com/{handle}/status".format(handle=twitter_handle)

    # Get the API session & send a tweet depending on the parameters sent
    api = get_api()

    # Add any hashtags that need to be added
    # Start with team hashtag (most required)
    # if hashtags:
    #     tweet_text = f'{tweet_text}\n\n{hashtags}'
    if game_hashtag:
        tweet_text = f"{tweet_text}\n\n{Hashtag.game_hashtag}"

    try:
        if not reply and not media:
            status = api.update_status(status=tweet_text)
        elif not reply and media:
            if isinstance(media, list):
                media_ids = [api.media_upload(i).media_id_string for i in media]
                status = api.update_status(status=tweet_text, media_ids=media_ids)
            else:
                status = api.update_with_media(status=tweet_text, filename=media)
        elif reply and not media:
            tweet_text = f"@{twitter_handle} {tweet_text}"
            status = api.update_status(status=tweet_text, in_reply_to_status_id=reply)
        elif reply and media:
            tweet_text = f"@{twitter_handle} {tweet_text}"
            if isinstance(media, list):
                media_ids = [api.media_upload(i).media_id_string for i in media]
                status = api.update_status(
                    status=tweet_text, media_ids=media_ids, in_reply_to_status_id=reply
                )
            else:
                status = api.update_with_media(
                    status=tweet_text, filename=media, in_reply_to_status_id=reply
                )

        return status.id_str

    except Exception as e:
        logging.error("Failed to send tweet : %s", tweet_text)
        logging.error(e)
        return None


def search_twitter(search_term, num_items):
    """ Searches Twitter for a specified search term and returns a number of results.

    Args:
        search_term: What to search Twitter for
        num_items: number of matching tweets to return

    Returns:
        tweets: ItemIterator of tweets matching the search term
    """
    api = get_api()

    tweets = tweepy.Cursor(api.search, q=search_term).items(num_items)
    return tweets
