import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def load_world_data() -> dict:
    with open(os.path.join(DATA_DIR, "world_data.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def load_world_state() -> dict:
    with open(os.path.join(DATA_DIR, "world_state.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def save_world_state(state: dict):
    with open(os.path.join(DATA_DIR, "world_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def load_memory() -> dict:
    with open(os.path.join(DATA_DIR, "memory.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(memory: dict):
    with open(os.path.join(DATA_DIR, "memory.json"), "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

def load_map_presets() -> dict:
    path = os.path.join(DATA_DIR, "map_presets.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_lore():
    path = os.path.join(DATA_DIR, "tadc_lore.json")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return json.dumps(json.load(f), indent=2)