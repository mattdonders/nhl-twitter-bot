#!/bin/bash

if [ "$#" -lt 2 ]; then
	echo "Usage: ./hockeygamebot.sh <VENV|PYTHONEXEC> <SCRIPT-PARAMS>"
	exit 1
fi

SCRIPTPATH=$(dirname "$0")
VENV=$1

# Change Directory into this script directory
cd $SCRIPTPATH
echo "[INFO] Moving to script directory - $(pwd)"

# Activate the Virtual Environment (Unless Python Executable)
if [[ $VENV == *"python"* ]]; then
    PYTHONEXEC=$VENV
else
    source $VENV/bin/activate
    PYTHONEXEC=$(command -v python)
fi

if [[ ! -x "$PYTHONEXEC" ]]; then
    echo "[ERROR] The Python executable '$PYTHONEXEC' is not valid - please validate and try again."
    exit 1
fi

echo "[INFO] Using the following Python executable - $PYTHONEXEC"

# Perform a `git pull` to make sure our code is up to date
echo "[INFO] Doing a 'git pull' to make sure we have the most up to date code."
git pull

# Shift the input arguments by 2 (to get to the Python script arguments)
shift 1

# $* passes all arguments from the bash script into the python script
echo "[INFO] Executing the following game bot script."
echo "[EXEC] $PYTHONEXEC -m hockeygamebot $*"
$PYTHONEXEC -m hockeygamebot $*
