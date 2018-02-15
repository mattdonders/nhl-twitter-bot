#!/bin/bash

GITPATH=$HOME/python/nhl-twitter-bot
ARCHIVE=$GITPATH/archive
LOGNAME="NHLTwitterBot.log"

# Change to python code directory
# cd /home/twitter/python/devilstwittergoalbot/
cd $GITPATH

mkdir -p $ARCHIVE

# Truncate nohup.out
truncate -s 0 $GITPATH/nohup.out

# Restart log file
DATE=$(date +'%Y%m%d%H%M%S')
mv $GITPATH/Twitter-DevilsGoalBot.log $ARCHIVE/$LOGNAME.$DATE
mv $GITPATH/nohup.out $ARCHIVE/nohup.out.$DATE
touch $GITPATH/$LOGNAME

# Start command using nohup & send to background
# /usr/bin/python3 /home/twitter/python/devilstwittergoalbot/checkGameStatus.py onreboot
nohup /usr/bin/python3 $HOME/python/nhl-twitter-bot/hockey_twitter_bot.py &

exit 0