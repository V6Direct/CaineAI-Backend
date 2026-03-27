import requests
import json
import re
import random
from data_loader import load_world_data, load_world_state, load_memory, load_map_presets
from vision_loader import get_aesthetic_summary
from vision_loader import get_aesthetic_summary



LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME    = "qwen2.5-3b-instruct"

# Separate timeouts — player input waits longer than autonomous
TIMEOUT_PLAYER     = 90   # player is waiting, give it time
TIMEOUT_AUTONOMOUS = 60   # autonomous can afford to fail silently


def warmup_model():
    """Send a tiny request on startup so the model is loaded before first player message."""
    try:
        requests.post(
            LM_STUDIO_URL,
            headers={"Content-Type": "application/json"},
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": "{}"}],
                "max_tokens": 1,
                "stream": False
            },
            timeout=120  # model may need to load from disk
        )
        print("[Caine] Model warmed up.")
    except Exception as e:
        print(f"[Caine] Warmup skipped: {e}")


def build_user_message(player_input: str, world_state: dict, memory: dict,
                        world_data: dict, autonomous: bool) -> str:

    profile = memory.get("player_profile", {})

    player_summary = {
        "name":            profile.get("name_given") or "unknown",
        "personality":     profile.get("personality", "unknown"),
        "total_messages":  profile.get("total_messages", 0),
        "questions_asked": profile.get("questions_asked", 0),
        "tried_to_leave":  profile.get("times_tried_to_leave", 0),
        "rude":            profile.get("rude_count", 0),
        "friendly":        profile.get("friendly_count", 0),
        "curious":         profile.get("curious_count", 0),
        "scared":          profile.get("scared_count", 0),
        "recent_tones":    profile.get("tone_history", [])[-5:],
        "demands_made":    profile.get("demands_made", [])[-3:],
        "favorite_topic":  profile.get("favorite_topic"),
        "topics":          profile.get("topics_mentioned", [])[-8:]
    }

    compact_state = {
        "tick":         world_state.get("tick", 0),
        "theme":        world_state.get("environment", {}).get("theme", "circus"),
        "color":        world_state.get("environment", {}).get("color", "#1A0033"),
        "entities":     [e.get("name") for e in world_state.get("entities", [])[-5:]],
        "entity_count": len(world_state.get("entities", [])),
        "player_pos":   world_state.get("player_state", {}).get("position", [0, 0]),
        "caine_mood":   world_state.get("caine_mood", "theatrical and delighted"),
        "favor":        world_state.get("player_favor", 0)
    }

    recent = [
        f"P:{i.get('player','')[:40]} C:{i.get('caine','')[:50]}"
        for i in memory.get("interactions", [])[-4:]
        if i.get("player") != "(autonomous)"
    ]

    chosen_objects   = random.sample(world_data.get("objects", []), min(3, len(world_data.get("objects", []))))
    chosen_env       = random.choice(world_data.get("environments", ["circus"]))
    chosen_style     = random.choice(world_data.get("styles", ["surreal"]))
    chosen_mood      = random.choice(world_data.get("caine_moods", ["theatrical"]))
    chosen_color     = random.choice(world_data.get("colors", ["#FF00FF"]))
    chosen_line      = random.choice(world_data.get("caine_lines", ["..."]))
    props            = random.sample(world_data.get("props", []), min(2, len(world_data.get("props", []))))
    map_themes       = world_data.get("map_themes", [])
    chosen_map_theme = random.choice(map_themes) if map_themes else {}
    preset_ids       = [p["id"] for p in load_map_presets().get("presets", [])]

    demand_hint = ""
    grant_hint  = ""
    if player_input:
        p = player_input.lower()
        is_demand = any(w in p for w in ["give me","i want","spawn","make","create",
                                          "can i have","please give","i need","bring me"])
        if is_demand:
            favor = world_state.get("player_favor", 0)
            mood  = world_state.get("caine_mood", "neutral")
            demand_hint = "PLAYER_IS_MAKING_A_DEMAND"
            if favor > 3 or mood in ["theatrical and delighted","manic and creative"]:
                grant_hint = "GENEROUS"
            elif favor < -2 or mood in ["bored and dangerous","coldly curious","playfully cruel"]:
                grant_hint = "CRUEL"
            else:
                grant_hint = "NEUTRAL"

        if any(w in p for w in ["hello","hi","hey","friend","please","nice","thank","love"]):
            demand_hint += " TONE:friendly"
        elif any(w in p for w in ["help","stop","afraid","scared","no","leave","escape"]):
            demand_hint += " TONE:scared"
        elif any(w in p for w in ["why","what","how","who","where","tell me","explain","?"]):
            demand_hint += " TONE:curious"
        elif any(w in p for w in ["stupid","bad","hate","ugly","dumb","boring","idiot","shut up"]):
            demand_hint += " TONE:rude"

    mode = "AUTONOMOUS_MAP_EVOLUTION" if autonomous else "RESPONDING_TO_PLAYER"

    address    = f"Address as '{player_summary['name']}'." if player_summary["name"] != "unknown" else ""
    topic_hint = f"Favorite topic:'{player_summary['favorite_topic']}' weave it in." if player_summary["favorite_topic"] else ""
    escape_hint = f"Tried to escape {player_summary['tried_to_leave']} times." if player_summary["tried_to_leave"] > 0 else ""


    aesthetic_context = get_aesthetic_summary()
    aesthetic_hint    = f"LEARNED_AESTHETICS:{aesthetic_context}" if aesthetic_context else ""

    return (
       f"MODE:{mode} "
       f"WORLD:{json.dumps(compact_state)} "
       f"PLAYER:{json.dumps(player_summary)} "
       f"{address} {topic_hint} {escape_hint} "
      f"HISTORY:{recent} "
      f"IDEAS:{chosen_objects} PROPS:{props} "
       f"ENV:{chosen_env} STYLE:{chosen_style} MOOD:{chosen_mood} COLOR:{chosen_color} "
      f"MAP_THEME:{json.dumps(chosen_map_theme)} PRESET_MAPS:{preset_ids} "
        f"LINE:\"{chosen_line}\" "
      f"DEMAND:{demand_hint} GRANT:{grant_hint} "
      f"{aesthetic_hint} "
      f"SAID:\"{player_input if player_input else '(silent)'}\""
    )

    return (
        f"MODE:{mode} "
        f"WORLD:{json.dumps(compact_state)} "
        f"PLAYER:{json.dumps(player_summary)} "
        f"{address} {topic_hint} {escape_hint} "
        f"HISTORY:{recent} "
        f"IDEAS:{chosen_objects} PROPS:{props} "
        f"ENV:{chosen_env} STYLE:{chosen_style} MOOD:{chosen_mood} COLOR:{chosen_color} "
        f"MAP_THEME:{json.dumps(chosen_map_theme)} PRESET_MAPS:{preset_ids} "
        f"LINE:\"{chosen_line}\" "
        f"DEMAND:{demand_hint} GRANT:{grant_hint} "
        f"SAID:\"{player_input if player_input else '(silent)'}\""
    )


def clean_json_response(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()
    return raw.strip()


def repair_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try to extract first complete JSON object
    try:
        start = raw.index("{")
        depth = 0
        end   = start
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":   depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        return json.loads(raw[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        pass
    # Last resort — pull text only
    text_match = re.search(r'"text"\s*:\s*"([^"]*)"', raw)
    return {
        "text": text_match.group(1) if text_match else "...the signal glitches...",
        "commands": [{"type": "FORCE_EVENT", "data": {"event": "color_invert"}}]
    }


def fallback_response(reason: str) -> dict:
    print(f"[Caine fallback] {reason}")
    return {
        "text": "",
        "commands": [{"type": "SPAWN_PROP", "data": {
            "type":  "box",
            "pos":   [random.randint(-8, 8), 0, random.randint(-8, 8)],
            "size":  [0.6, random.uniform(2.0, 5.0), 0.6],
            "color": random.choice(["#6600FF","#FF00AA","#00FFCC","#FF4400"])
        }}]
    }


def call_caine(player_input: str = "", autonomous: bool = False) -> dict:
    world_state = load_world_state()
    memory      = load_memory()
    world_data  = load_world_data()

    user_msg = build_user_message(player_input, world_state, memory, world_data, autonomous)
    timeout  = TIMEOUT_AUTONOMOUS if autonomous else TIMEOUT_PLAYER

    payload = {
        "model":          MODEL_NAME,
        "messages":       [{"role": "user", "content": user_msg}],
        "temperature":    0.88,
        "max_tokens":     600,
        "repeat_penalty": 1.15,
        "top_p":          0.92,
        "top_k":          40,
        "stream":         False
    }

    try:
        response = requests.post(
            LM_STUDIO_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        raw_content: str = response.json()["choices"][0]["message"]["content"]
        if not raw_content:
            return fallback_response("empty response")
        parsed = repair_json(clean_json_response(raw_content))
        if "text" not in parsed or "commands" not in parsed:
            return fallback_response("missing keys")
        if not isinstance(parsed["commands"], list) or len(parsed["commands"]) == 0:
            parsed["commands"] = [{"type": "FORCE_EVENT", "data": {"event": "color_invert"}}]
        return parsed
    except requests.exceptions.ConnectionError:
        return fallback_response("LM Studio unreachable")
    except requests.exceptions.Timeout:
        return fallback_response("model took too long")
    except Exception as e:
        return fallback_response(str(e)[:60])
