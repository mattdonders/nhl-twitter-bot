#!/bin/bash

SCRIPTPATH=$(dirname "$0")
ARCHIVE=$SCRIPTPATH/archive
LOGNAME="NHLTwitterBot.log"

# Change to python code directory
# cd /home/twitter/python/devilstwittergoalbot/
cd $SCRIPTPATH

mkdir -p $ARCHIVE

# Truncate nohup.out
# truncate -s 0 $SCRIPTPATH/nohup.out

# Restart log file
DATE=$(date +'%Y%m%d%H%M%S')
mv $SCRIPTPATH/$LOGNAME $ARCHIVE/$LOGNAME.$DATE
mv $SCRIPTPATH/nohup.out $ARCHIVE/nohup.out.$DATE
touch $SCRIPTPATH/$LOGNAME

# Start command using nohup & send to background
# /usr/bin/python3 /home/twitter/python/devilstwittergoalbot/checkGameStatus.py onreboot
# Source the Virtual Environment (if exists)
if [ -d "$SCRIPTPATH/env" ]; then
  source env/bin/activate
fi

nohup python3 $SCRIPTPATH/hockey_twitter_bot.py &

exit 0
