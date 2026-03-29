import json
import os
import threading
from pathlib import Path

DATA_DIR   = Path(os.getenv("DATA_DIR", "./data"))
_file_lock = threading.Lock()

WORLD_STATE_FILE = DATA_DIR / "world_state.json"
MEMORY_FILE      = DATA_DIR / "memory.json"
MAP_PRESETS_FILE = DATA_DIR / "map_presets.json"
LORE_FILE        = DATA_DIR / "lore.json"

DEFAULT_WORLD_STATE = {
    "tick": 0,
    "player_state": {"position": [0, 0], "last_input": "", "locked": False, "lock_duration": 0},
    "caine_mood": "theatrical and delighted",
    "player_favor": 0,
    "active_map_id": "",
    "environment": {"theme": "circus", "color": "#1A0033"},
    "entities": [],
    "npcs": [],
    "events": [],
    "active_brief": {},
    "active_minigame": None,
}

def _read_json(path: Path, default):
    with _file_lock:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default() if callable(default) else default

def _write_json(path: Path, data):
    with _file_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

def load_world_state() -> dict:
    state = _read_json(WORLD_STATE_FILE, dict)
    for key, val in DEFAULT_WORLD_STATE.items():
        state.setdefault(key, val)
    return state

def save_world_state(state: dict):
    _write_json(WORLD_STATE_FILE, state)

def load_memory() -> dict:
    return _read_json(MEMORY_FILE, dict)

def save_memory(memory: dict):
    _write_json(MEMORY_FILE, memory)

def load_map_presets() -> dict:
    return _read_json(MAP_PRESETS_FILE, lambda: {"presets": []})

def load_lore() -> dict:
    return _read_json(LORE_FILE, dict)