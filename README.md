# NHL Twitter Game Bot

This script parses the NHL Schedule & Live Feed API endpoints to gather rather relevant game events and tweet them to the game bot Twitter acount.

### List of Tweeted Events
- Morning of Gameday (with time, broadcast channel & hashtag)
- On Ice Players (start of game & start of OT)
- Start of Periods
- End of Periods (with goals and shots)
- Goals
  - **Preferred Team** gets assists & scoring changes.
- Penalties (with power play detection)
- End of game with post-game boxscore image generation
- Three Stars

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites and Installation

To run this bot, download the most current release and install the requirements via pip.

```
git clone git@github.com:mattdonders/nhl-twitter-bot.git
cd nhl-twitter-bot
pip install -r requirements.txt
```

* Create a new [Twitter application](https://apps.twitter.com/app/new) and request an Access Token once completed.
* If you want to send messages to Discord create a new [Discord application](https://discordapp.com/developers/applications/) and copy its token.
* Rename `secret-sample.py` to `secret.py` and fill in the proper credentials.
  * There are two sets of Twitter credentials as the second set can be used to setup a debug / test account.
  * Linode is my cloud VPS host of choice. If you are running this locally, this can be left blank as the script will just exit on completion.
```
# Tweepy / Twitter API Keys
consumer_key = ''
consumer_secret = ''
access_token = ''
access_secret = ''

# Debug Tweepy / Twitter API Keys
debug_consumer_key = ''
debug_consumer_secret = ''
debug_access_token = ''
debug_access_secret = ''

# Linode Keys
linode_apikey = ''
linode_id_devils = ''

# Discord token
DISCORD_TOKEN = ''
```

* Modify the following values within `config.ini` to fit our team and Twitter handles.
```
[DEFAULT]
TEAM_NAME = New Jersey Devils

[ENDPOINTS]
TWITTER_URL = https://twitter.com/NJDevilsGameBot/status/
TWITTER_HANDLE = NJDevilsGameBot
DEBUG_TWITTER_HANDLE = DevilsBotDebug

[VPS]
CLOUDHOST = linode
HOSTNAME = donders-devils-twitter

[DISCORD]
CHANNEL_ID = 12345678910
```

### Execution

The github repository contains a shell script called `startPythonScript.sh` which will automatically start the Python script in the background and disown the process. Modify the `GITPATH` line in the script to specify the path to the cloned Github repository.

`GITPATH=$HOME/python/nhl-twitter-bot`


To start the bot, run the script -

`$HOME/python/nhl-twitter-bot/startPythonScript.sh`

I have a [cron job](https://linux.die.net/man/1/crontab) that restarts the bot everyday at 10:00AM. You can edit your crontab file by executing the `crontab -e` command and pasting in the below line (again modifying the path to your script path).

`0 10 * * * $HOME/python/nhl-twitter-bot/startPythonScript.sh`


If you want to start the Python script from the command line and pass in debug arguments, you can execute the script directly.
```
/usr/bin/python3 hockey_twitter_bot.py --help
usage: hockey_twitter_bot.py [-h] [--notweets] [--console] [--team TEAM]
                             [--debugtweets] [--localdata]

optional arguments:
  -h, --help     show this help message and exit
  --notweets     log tweets to console instead of Twitter
  --console      log to console instead of file
  --team TEAM    override team in configuration
  --debugtweets  send tweets from debug account
  --localdata    use local data instead of API
  --yesterday    get yesterday game on the schedule
  --discord      Send messages to discord channel
```


## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/mattdonders/nhl-twitter-bot/tags).

## Authors

* **Matt Donders** - https://mattdonders.com
* **Dave McPherson** - http://www.wochstudios.com/

## Acknowledgments

* An [up to date list](https://github.com/dword4/nhlapi) of all NHL API endpoints.
