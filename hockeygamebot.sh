#!/bin/bash

if [ "$#" -lt 2 ]; then
	echo "Usage: ./hockeygamebot.sh <VENV|PYTHONEXEC> <SCRIPT-PARAMS>"
    echo "VENV|PYTHONEXEC is the path to the virtual environment to active or the Python binary to use."
    echo "SCRIPT-PARAMS are the parameters being passed into the game bot script."
	exit 1
fi

SCRIPTPATH=$(dirname "$0")
LOGFILE="${SCRIPTPATH}/hockeygamebot.log"
VENV=$1

echo "[INFO] Starting new instance of the Hockey Game Bot!" > $LOGFILE

# Change Directory into this script directory
cd $SCRIPTPATH
echo "[INFO] Moving to script directory - $(pwd)" >> $LOGFILE

# Activate the Virtual Environment (Unless Python Executable)
if [[ $VENV == *"python"* ]]; then
    PYTHONEXEC=$VENV
else
    source $VENV/bin/activate
    PYTHONEXEC=$(command -v python)
fi

if [[ ! -x "$PYTHONEXEC" ]]; then
    echo "[ERROR] The Python executable '$PYTHONEXEC' is not valid - please validate and try again." >> $LOGFILE
    exit 1
fi

echo "[INFO] Using the following Python executable - $PYTHONEXEC" >> $LOGFILE

# Perform a `git pull` to make sure our code is up to date
echo "[INFO] Doing a 'git pull' to make sure we have the most up to date code." >> $LOGFILE
git pull

# Shift the input arguments by 2 (to get to the Python script arguments)
shift 1

# $* passes all arguments from the bash script into the python script
echo "[INFO] Executing the following game bot script." >> $LOGFILE
echo "[EXEC] $PYTHONEXEC -m hockeygamebot $*" >> $LOGFILE
nohup $PYTHONEXEC -m hockeygamebot $* >> $LOGFILE 2>&1 &
