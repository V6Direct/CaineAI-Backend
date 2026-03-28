import asyncio
import math
import time
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_brain import call_caine, warmup_model
from data_loader import load_world_state, save_world_state, load_memory, save_memory, load_map_presets

from data_loader import load_world_state, save_world_state, load_memory, save_memory, load_map_presets, load_lore


pending_responses: list  = []
autonomous_busy: bool    = False
autonomous_running: bool = True

player_executor     = ThreadPoolExecutor(max_workers=1, thread_name_prefix="caine_player")
autonomous_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="caine_auto")

MAP_EVOLVE_MIN = 35
MAP_EVOLVE_MAX = 70
SPEAK_MIN      = 150
SPEAK_MAX      = 300

_current_map_brief: dict = {}


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    loop.run_in_executor(autonomous_executor, warmup_model)

    from vision_loader import scan_images_folder
    loop.run_in_executor(autonomous_executor, scan_images_folder)

    memory = load_memory()
    memory["session_start"] = datetime.utcnow().isoformat()
    save_memory(memory)

    t1 = asyncio.create_task(map_evolution_loop())
    t2 = asyncio.create_task(autonomous_speak_loop())
    yield
    t1.cancel()
    t2.cancel()
    for t in [t1, t2]:
        try:
            await t
        except asyncio.CancelledError:
            pass
    player_executor.shutdown(wait=False)
    autonomous_executor.shutdown(wait=False)

memory = load_memory()
memory["caine_lore"] = load_lore()  # <- hinzufügen
memory["session_start"] = datetime.utcnow().isoformat()
save_memory(memory)

app = FastAPI(title="CaineAI Backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Models ────────────────────────────────────────────────────────────────────
class PlayerInput(BaseModel):
    text: str           = ""
    position: list      = [0, 0]
    # ↓ NEW: Godot sends these back so backend stays in sync
    caine_mood: Optional[str] = None
    player_favor: Optional[int] = None
    active_map_id: Optional[str] = None
    npcs: Optional[list] = None
    entities: Optional[list] = None


# ── Client state sync ─────────────────────────────────────────────────────────
def sync_client_state(inp: PlayerInput) -> None:
    """
    Merge state that Godot tracks locally (mood, favor, map, npcs, entities)
    back into world_state.json before we call the AI.
    This ensures the AI always reasons from the real current state,
    not a stale server-side snapshot.
    """
    state = load_world_state()

    state["player_state"]["position"]   = inp.position
    state["player_state"]["last_input"] = inp.text

    if inp.caine_mood is not None:
        state["caine_mood"] = inp.caine_mood

    if inp.player_favor is not None:
        state["player_favor"] = max(-10, min(10, inp.player_favor))

    if inp.active_map_id is not None and inp.active_map_id != "":
        state["active_map_id"] = inp.active_map_id

    if inp.npcs is not None:
        state["npcs"] = inp.npcs[:10]

    if inp.entities is not None:
        state["entities"] = inp.entities[:30]

    save_world_state(state)


# ── Player profiling ──────────────────────────────────────────────────────────
def update_player_profile(text: str):
    memory  = load_memory()
    profile = memory.setdefault("player_profile", {})
    p       = text.lower().strip()

    profile["total_messages"] = profile.get("total_messages", 0) + 1

    if any(w in p for w in ["hate", "stupid", "dumb", "boring", "bad", "ugly", "idiot", "shut up"]):
        profile["rude_count"] = profile.get("rude_count", 0) + 1
        profile.setdefault("tone_history", []).append("rude")
    elif any(w in p for w in ["hello", "hi", "hey", "thanks", "please", "nice", "love", "friend", "thank"]):
        profile["friendly_count"] = profile.get("friendly_count", 0) + 1
        profile.setdefault("tone_history", []).append("friendly")
    elif any(w in p for w in ["why", "what", "how", "who", "where", "when", "tell me", "explain", "?"]):
        profile["curious_count"] = profile.get("curious_count", 0) + 1
        profile.setdefault("tone_history", []).append("curious")
        profile["questions_asked"] = profile.get("questions_asked", 0) + 1
    elif any(w in p for w in ["help", "stop", "scared", "afraid", "leave", "exit", "escape", "let me out"]):
        profile["scared_count"] = profile.get("scared_count", 0) + 1
        profile.setdefault("tone_history", []).append("scared")
        if any(w in p for w in ["leave", "exit", "escape", "let me out", "go home"]):
            profile["times_tried_to_leave"] = profile.get("times_tried_to_leave", 0) + 1

    profile["tone_history"] = profile.get("tone_history", [])[-20:]

    counts = {
        "rude":     profile.get("rude_count", 0),
        "friendly": profile.get("friendly_count", 0),
        "curious":  profile.get("curious_count", 0),
        "scared":   profile.get("scared_count", 0),
    }
    profile["personality"] = max(counts, key=counts.get)

    if any(w in p for w in ["give me", "i want", "spawn", "make", "create",
                              "can i have", "please give", "i need", "bring me"]):
        profile.setdefault("demands_made", []).append(text[:60])
        profile["demands_made"] = profile["demands_made"][-10:]

    name_match = re.search(r"(?:my name is|i am|call me|i'm)\s+([a-zA-Z]+)", p)
    if name_match and not profile.get("name_given"):
        profile["name_given"] = name_match.group(1).capitalize()
        print(f"[Profile] Player name: {profile['name_given']}")

    topic_keywords = [
        "ball", "sword", "gun", "weapon", "door", "light", "dark", "color",
        "music", "sound", "map", "floor", "sky", "entity", "mirror", "clock",
        "circus", "tower", "platform", "arch", "pillar", "game", "world"
    ]
    found = [kw for kw in topic_keywords if kw in p]
    if found:
        profile.setdefault("topics_mentioned", []).extend(found)
        profile["topics_mentioned"] = list(set(profile["topics_mentioned"]))[-20:]
        profile["favorite_topic"] = Counter(profile["topics_mentioned"]).most_common(1)[0][0]

    memory["player_profile"] = profile
    save_memory(memory)


# ── Map generation ────────────────────────────────────────────────────────────
def _fallback_to_random_preset():
    try:
        presets = load_map_presets().get("presets", [])
        if not presets:
            return
        preset = random.choice(presets)
        state  = load_world_state()
        state.setdefault("events", []).append({"cmd": "LOAD_PRESET_MAP", "data": preset})
        state["entities"]             = preset.get("entities", [])
        state["environment"]["theme"] = preset.get("theme", {}).get("theme", "circus")
        state["environment"]["color"] = preset.get("theme", {}).get("color", "#1A0033")
        state["active_brief"]         = {}
        save_world_state(state)
        pending_responses.append({
            "text": preset.get("caine_intro", "...the world shifts."),
            "commands": []
        })
        print(f"[MapGen] Fallback preset → {preset['id']}")
    except Exception as e:
        print(f"[MapGen] Fallback failed: {e}")


async def _trigger_new_map():
    global _current_map_brief
    from ai_brain import generate_map_brief
    from map_builder import build_map_from_brief
    from vision_loader import get_aesthetic_summary

    print("[MapGen] Generating new map brief...")
    loop  = asyncio.get_event_loop()
    brief = await loop.run_in_executor(
        autonomous_executor,
        lambda: generate_map_brief(get_aesthetic_summary())
    )

    if not brief:
        print("[MapGen] Brief failed, using fallback preset")
        _fallback_to_random_preset()
        return

    _current_map_brief = brief
    events = build_map_from_brief(brief)

    state = load_world_state()
    state["events"]               = events[-20:]
    state["environment"]["theme"] = brief["theme"]
    state["environment"]["color"] = brief["color"]
    state["entities"]             = brief.get("entities", [])
    state["tick"]                 = state.get("tick", 0)
    state["active_brief"]         = {
        "theme":          brief["theme"],
        "mood":           brief.get("mood", ""),
        "narrative_seed": brief.get("narrative_seed", "")
    }
    save_world_state(state)

    pending_responses.append({
        "text": brief.get("caine_intro", "...something stirs."),
        "commands": []
    })
    print(f"[MapGen] New map: '{brief['theme']}' — {len(events)} events queued")


def _organic_evolve(state: dict, brief: dict):
    if not brief:
        return
    palette = brief.get("palette", ["#440066"])
    color   = random.choice(palette)
    r       = random.uniform(4, 12)
    angle   = math.radians(random.uniform(0, 360))
    pos     = [round(r * math.cos(angle), 2), 0, round(r * math.sin(angle), 2)]
    state.setdefault("events", []).append({"cmd": "SPAWN_PROP", "data": {
        "type":  random.choice(["box", "platform"]),
        "pos":   pos,
        "size":  [random.uniform(0.3, 1.2), random.uniform(1.5, 5.0), random.uniform(0.3, 1.2)],
        "color": color
    }})


async def map_evolution_loop():
    global autonomous_busy, _current_map_brief
    await asyncio.sleep(25)
    await _trigger_new_map()

    while autonomous_running:
        interval = random.randint(MAP_EVOLVE_MIN, MAP_EVOLVE_MAX)
        await asyncio.sleep(interval)
        if autonomous_busy:
            continue
        autonomous_busy = True
        try:
            state = load_world_state()
            tick  = state.get("tick", 0)
            if tick > 0 and tick % 8 == 0:
                await _trigger_new_map()
            else:
                _organic_evolve(state, _current_map_brief)
                state["tick"] = tick + 1
                save_world_state(state)
        except Exception as e:
            print(f"[Map evolve error] {e}")
        finally:
            autonomous_busy = False


# ── Autonomous speak ──────────────────────────────────────────────────────────
async def autonomous_speak_loop():
    global pending_responses, autonomous_busy
    await asyncio.sleep(90)
    while autonomous_running:
        interval = random.randint(SPEAK_MIN, SPEAK_MAX)
        print(f"[Caine] Speaking in {interval}s")
        await asyncio.sleep(interval)
        if autonomous_busy:
            continue
        autonomous_busy = True
        try:
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                autonomous_executor,
                lambda: call_caine(player_input="", autonomous=True)
            )
            apply_commands_to_world(result.get("commands", []))
            record_interaction("(autonomous)", result)
            text = result.get("text", "")
            if text and "*static*" not in text and text != "":
                pending_responses.append(result)
            print(f"[Caine] {text[:80]}")
        except Exception as e:
            print(f"[Speak error] {e}")
        finally:
            autonomous_busy = False


# ── Command applicator ────────────────────────────────────────────────────────
def apply_commands_to_world(commands: list):
    state = load_world_state()
    state["tick"] = state.get("tick", 0) + 1

    for cmd in commands:
        ctype = cmd.get("type", "")
        data  = cmd.get("data", {})

        if ctype in ("CREATE_ENTITY", "SPAWN_ENTITY"):
            if len(state["entities"]) < 30:
                state["entities"].append({
                    "name":     data.get("name", "unknown"),
                    "style":    data.get("style", "surreal"),
                    "position": data.get("position", [0, 0]),
                    "id":       f"entity_{int(time.time() * 1000)}"
                })

        elif ctype == "DELETE_ENTITY":
            state["entities"] = [
                e for e in state["entities"] if e.get("name") != data.get("name", "")
            ]

        elif ctype == "CLEAR_ENTITIES":
            state["entities"] = []

        elif ctype == "MODIFY_ENTITY":
            for entity in state["entities"]:
                if entity.get("name") == data.get("name", ""):
                    entity[data.get("property", "style")] = data.get("value", "")

        elif ctype == "MODIFY_WORLD":
            if data.get("property"):
                state["environment"][data["property"]] = data.get("value")

        elif ctype == "CHANGE_THEME":
            state["environment"]["theme"] = data.get("theme", state["environment"]["theme"])
            state["environment"]["color"] = data.get("color", "#1A0033")
            state.setdefault("events", []).append({"cmd": "CHANGE_THEME", "data": data})

        elif ctype == "TELEPORT_PLAYER":
            state["player_state"]["position"] = data.get("position", [0, 0])
            state.setdefault("events", []).append({"cmd": "TELEPORT_PLAYER", "data": data})

        elif ctype == "LOCK_PLAYER":
            state["player_state"]["locked"]        = True
            state["player_state"]["lock_duration"] = data.get("duration", 2)

        elif ctype == "FORCE_EVENT":
            event = data.get("event", "")
            if event:
                state.setdefault("events", []).append(event)

        elif ctype == "SET_MOOD":
            state["caine_mood"] = data.get("mood", "neutral")
            print(f"[Mood] → {state['caine_mood']}")

        elif ctype == "ADJUST_FAVOR":
            delta = int(data.get("delta", 0))
            state["player_favor"] = max(-10, min(10, state.get("player_favor", 0) + delta))
            print(f"[Favor] {state['player_favor']:+d}")

        elif ctype == "TELEPORT_TO_MAP":
            try:
                presets = load_map_presets()
                preset  = next(
                    (p for p in presets["presets"] if p["id"] == data.get("map_id", "")),
                    None
                )
                if preset:
                    state.setdefault("events", []).append({"cmd": "LOAD_PRESET_MAP", "data": preset})
                    state["entities"]             = preset.get("entities", [])
                    state["environment"]["theme"] = preset.get("theme", {}).get("theme", "circus")
                    state["environment"]["color"] = preset.get("theme", {}).get("color", "#1A0033")
                    print(f"[Teleport] → {data.get('map_id')}")
            except Exception as e:
                print(f"[Preset error] {e}")

        elif ctype == "SPAWN_NPC":
            if len(state.get("npcs", [])) < 10:
                state.setdefault("npcs", []).append({
                    "name":     data.get("name", "unknown"),
                    "role":     data.get("role", "wanderer"),
                    "position": data.get("position", [0, 0, 0]),
                    "color":    data.get("color", "#880088"),
                    "dialogue": data.get("dialogue", ""),
                    "action":   "idle",
                    "id":       f"npc_{int(time.time() * 1000)}"
                })
            state.setdefault("events", []).append({"cmd": "SPAWN_NPC", "data": data})

        elif ctype == "COMMAND_NPC":
            for npc in state.get("npcs", []):
                if npc.get("name") == data.get("name", ""):
                    npc["action"] = data.get("action", "idle")
            state.setdefault("events", []).append({"cmd": "COMMAND_NPC", "data": data})

        elif ctype in ["SPAWN_STRUCTURE", "BUILD_MAP", "CLEAR_MAP", "SPAWN_PROP",
                       "RESHAPE_FLOOR", "SPAWN_PARTICLE", "SPAWN_LIGHT"]:
            state.setdefault("events", []).append({"cmd": ctype, "data": data})

    state["events"] = state.get("events", [])[-20:]
    save_world_state(state)


# ── Memory ────────────────────────────────────────────────────────────────────
def record_interaction(player_input: str, response: dict):
    memory = load_memory()
    memory.setdefault("interactions", [])
    memory.setdefault("world_changes", [])
    memory.setdefault("character_breaks", [])
    memory.setdefault("chaos_count", 0)

    text = response.get("text", "")

    broke_character = any(phrase in text.lower() for phrase in [
        "i'm an ai", "i am an ai", "i'm a language model", "as an ai",
        "i was created", "i don't have feelings", "i cannot",
        "i'm here to help", "how can i assist", "certainly!", "of course!",
        "great question", "i'd be happy"
    ])

    memory["interactions"].append({
        "time":            datetime.utcnow().isoformat(),
        "player":          player_input[:100],
        "caine":           text[:120],
        "broke_character": broke_character
    })

    if broke_character:
        memory.setdefault("character_breaks", []).append({
            "trigger":      player_input[:60],
            "bad_response": text[:80]
        })
        memory["character_breaks"] = memory["character_breaks"][-10:]

    memory["world_changes"].append({
        "time":     datetime.utcnow().isoformat(),
        "commands": [c.get("type") for c in response.get("commands", [])]
    })
    memory["interactions"]  = memory["interactions"][-40:]
    memory["world_changes"] = memory["world_changes"][-40:]
    memory["chaos_count"]   = memory.get("chaos_count", 0) + 1
    save_memory(memory)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/player_input")
async def player_input_endpoint(inp: PlayerInput):
    global pending_responses

    # 1. Merge Godot-side state into world_state.json first
    sync_client_state(inp)

    # 2. Update player profile from the message text
    if inp.text:
        update_player_profile(inp.text)

    # 3. Call the AI (it now reads the freshly synced state)
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        player_executor,
        lambda: call_caine(player_input=inp.text, autonomous=False)
    )

    # 4. Apply returned commands back into world_state
    apply_commands_to_world(result.get("commands", []))
    record_interaction(inp.text, result)
    pending_responses.append(result)
    return result


@app.get("/world_state")
async def get_world_state():
    global pending_responses
    state     = load_world_state()
    caine_out = pending_responses.pop(0) if pending_responses else None

    # ↓ Include mood + favor in response so Godot can update GameState
    response = {
        "caine": caine_out,
        "world": state,
        "sync": {
            "caine_mood":   state.get("caine_mood", "theatrical and delighted"),
            "player_favor": state.get("player_favor", 0),
            "active_map_id": state.get("active_map_id", "")
        }
    }

    state["events"]                 = []
    state["player_state"]["locked"] = False
    save_world_state(state)
    return response


@app.get("/health")
async def health():
    return {"status": "alive", "message": "Caine watches."}