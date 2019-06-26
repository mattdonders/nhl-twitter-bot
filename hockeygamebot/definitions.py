import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
LOGS_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, os.pardir, "logs"))
