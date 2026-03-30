import json
import os
from config.settings import STORAGE_DIR

STATES_FILE = os.path.join(STORAGE_DIR, "pending_states.json")

def load_states() -> dict:
    if not os.path.exists(STATES_FILE):
        return {}
    try:
        with open(STATES_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_states(states: dict):
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(STATES_FILE, "w") as f:
        json.dump(states, f)