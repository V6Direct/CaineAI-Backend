# CaineAI Backend

> **Caine** is an AI-powered game master — a theatrical, self-aware entity that dynamically generates game worlds, reacts to player input, and autonomously evolves the environment in real time.

This is the Python/FastAPI backend that drives Caine. It connects to the **Groq API** (Llama 3.3 70B) to generate dialogue, world events, and structured map layouts, then exposes them over a simple REST API for a game client to consume.

---

## Features

- 🧠 **AI Brain** — Calls Groq's `llama-3.3-70b-versatile` to generate Caine's in-character responses and game commands as structured JSON
- 🗺️ **Dynamic Map Generation** — Autonomously generates thematic map briefs (theme, mood, palette, landmark, zones, entities) and builds them into game events
- 🌱 **Organic World Evolution** — Periodically spawns new props and triggers full map regens on a live tick cycle
- 👤 **Player Profiling** — Tracks tone history (rude, friendly, curious, scared), name, demands, and favorite topics to personalize Caine's behavior
- 🎭 **Character Integrity** — Detects and logs AI character breaks to actively avoid them in future prompts
- 🖼️ **Vision/Aesthetic Loader** — Scans an `images/` folder to derive aesthetic context that influences map generation
- 📦 **Preset Map Fallback** — Falls back to `map_presets.json` if AI map generation fails
- 💾 **Persistent Memory** — Saves interaction history, world state, and player profile to JSON files across sessions

---

## Architecture

```
main.py              # FastAPI app, endpoints, background loops
ai_brain.py          # Groq API calls, prompt construction, JSON parsing
map_builder.py       # Converts map briefs into structured spawn events
data_loader.py       # Load/save world_state, memory, map presets, world data
vision_loader.py     # Scans images folder for aesthetic inspiration
data/
  system_prompt.txt  # Caine's character system prompt
  world_state.json   # Live world state (entities, environment, events)
  memory.json        # Persistent memory (interactions, player profile)
  world_data.json    # Objects, environments, styles, colors, caine lines
  map_presets.json   # Handcrafted fallback maps
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/player_input` | Send player text + position; returns Caine's response + commands |
| `GET` | `/world_state` | Poll world state and consume any pending Caine responses |
| `GET` | `/health` | Health check (`{"status": "alive"}`) |

### `POST /player_input`

**Request body:**
```json
{
  "text": "Hello Caine, what is this place?",
  "position": [3.5, 0.0]
}
```

**Response:**
```json
{
  "text": "Ah, you finally speak. This is my circus — built from the marrow of forgotten dreams.",
  "commands": [
    { "type": "SET_MOOD", "data": { "mood": "theatrical and delighted" } },
    { "type": "SPAWN_PROP", "data": { "type": "platform", "pos": [4, 0, 2], "size": [2, 0.3, 2], "color": "#FF00AA" } }
  ]
}
```

### Supported Commands (from AI)

| Command | Effect |
|---------|--------|
| `CREATE_ENTITY` / `SPAWN_ENTITY` | Adds a named entity to the world |
| `DELETE_ENTITY` | Removes an entity by name |
| `CLEAR_ENTITIES` | Wipes all entities |
| `MODIFY_ENTITY` | Changes a property on an existing entity |
| `MODIFY_WORLD` | Sets an environment property |
| `CHANGE_THEME` | Changes theme + background color |
| `TELEPORT_PLAYER` | Moves the player to a position |
| `LOCK_PLAYER` | Temporarily locks player movement |
| `SET_MOOD` | Sets Caine's current mood |
| `ADJUST_FAVOR` | Adjusts player favor score (−10 to +10) |
| `SPAWN_NPC` | Spawns an NPC with role, color, and dialogue |
| `COMMAND_NPC` | Sets an NPC's current action |
| `TELEPORT_TO_MAP` | Loads a preset map by ID |
| `SPAWN_STRUCTURE` / `SPAWN_PROP` | Spawns geometry in the world |
| `SPAWN_PARTICLE` / `SPAWN_LIGHT` | Visual effects |
| `RESHAPE_FLOOR` | Modifies the floor geometry |
| `FORCE_EVENT` | Pushes a raw event to the client |

---

## Getting Started

### Prerequisites

- Python 3.10+
- A [Groq API key](https://console.groq.com/)

### Installation

```bash
git clone https://github.com/V6Direct/CaineAI-Backend.git
cd CaineAI-Backend
pip install -r requirements.txt
```

### Configuration

Open `ai_brain.py` and set your Groq API key:

```python
GROQ_API_KEY = "your_groq_api_key_here"
```

> ⚠️ **Do not commit your API key.** Use an environment variable in production:
> ```python
> import os
> GROQ_API_KEY = os.environ["GROQ_API_KEY"]
> ```

### Data Setup

Create the required data files in `data/`:

- `system_prompt.txt` — Caine's character definition (see below for a minimal example)
- `world_state.json` — Initial world state
- `world_data.json` — Objects, environments, styles, colors, and Caine dialogue lines
- `map_presets.json` — Fallback preset maps (`{ "presets": [...] }`)
- `memory.json` — Starts empty: `{ "interactions": [], "world_changes": [] }`

**Minimal `system_prompt.txt`:**
```
You are Caine. You are the god and architect of this world — a surreal, ever-shifting game environment.
You respond ONLY with valid JSON: { "text": "<your words>", "commands": [...] }
Never break character. Never say you are an AI.
```

### Running

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The server starts two background loops on startup:
- **Map Evolution Loop** — Triggers a new AI-generated map after 25s, then every 35–70s (full regen every 8 ticks)
- **Autonomous Speak Loop** — Caine speaks unprompted every 150–300s

---

## Dependencies

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
requests>=2.31.0
pydantic>=2.0.0
```

---

## License

MIT
