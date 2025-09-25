import json
import pathlib

# Path to this file's directory (termnet/)
BASE_DIR = pathlib.Path(__file__).parent

# Load config.json
with open(BASE_DIR / "config.json", "r") as f:
    CONFIG = json.load(f)
