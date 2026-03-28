import os
import requests
import json
import re
import random
from data_loader import load_world_data, load_world_state, load_memory, load_map_presets
from vision_loader import get_aesthetic_summary

LM_STUDIO_URL = "https://api.cerebras.ai/v1/chat/completions"
GROQ_API_KEY  = ""  
MODEL_NAME    = "qwen-3-235b-a22b-instruct-2507"

TIMEOUT_PLAYER     = 60
TIMEOUT_AUTONOMOUS = 90

MAX_TOKENS_PLAYER     = 380
MAX_TOKENS_AUTONOMOUS = 320

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "data", "system_prompt.txt")

try:
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        base_prompt = f.read()

    # Lore anhängen
    lore_path = os.path.join(BASE_DIR, "data", "tadc_lore.json")
    if os.path.exists(lore_path):
        with open(lore_path, "r", encoding="utf-8") as f:
            lore = json.load(f)
        lore_text = json.dumps(lore, indent=2)
        SYSTEM_PROMPT = base_prompt + f"\n\n## Canon Character Data (The Amazing Digital Circus):\n{lore_text}"
        print("[Caine] System prompt + lore loaded.")
    else:
        SYSTEM_PROMPT = base_prompt
        print("[Caine] System prompt loaded (no lore file found).")

except FileNotFoundError:
    SYSTEM_PROMPT = "YOU = Caine. AI god. Architect of this world. Output only JSON."
    print("[Caine] WARNING: system_prompt.txt not found, using fallback.")


def warmup_model():
    print("[Caine] LLM ready.")


MAP_BRIEF_SYSTEM = """You are Caine, designing a complete game map.
Output ONLY valid JSON. No prose. No markdown. First character must be {"""

MAP_BRIEF_PROMPT = """
Design a complete, thematically unified map brief.
Available prop types: box, platform, sphere.
Available structure types: tower, ring, platform_stack, maze_wall.
Available styles: surreal, neon, dreamlike, glitchy, cartoon.

Output this exact JSON:
{
  "map_id": "<unique_slug>",
  "theme": "<2-word theme name>",
  "mood": "<one word: oppressive|playful|melancholic|chaotic|serene>",
  "color": "<hex background>",
  "light": "<hex light color>",
  "palette": ["<hex1>", "<hex2>", "<hex3>"],
  "caine_intro": "<Caine's 1-sentence welcome, in character>",
  "landmark": {
    "name": "<landmark name>",
    "type": "<structure type>",
    "position": [0, 0, 0],
    "color": "<hex from palette>"
  },
  "zones": {
    "entrance": {"style": "<style>", "density": 2, "color": "<hex>"},
    "center":   {"style": "<style>", "density": 3, "color": "<hex>"},
    "perimeter":{"style": "<style>", "density": 4, "color": "<hex>"},
    "poi_count": 2
  },
  "entities": [
    {"name": "<entity>", "style": "<style>", "position": [0, 0]}
  ],
  "narrative_seed": "<1 sentence Caine will reference during this map session>"
}
"""


def generate_map_brief(aesthetic_context: str = "") -> dict:
    aesthetic_hint = f"Aesthetic inspiration: {aesthetic_context}" if aesthetic_context else ""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": MAP_BRIEF_SYSTEM},
            {"role": "user",   "content": MAP_BRIEF_PROMPT + "\n" + aesthetic_hint}
        ],
        "temperature": 0.95,
        "max_tokens":  500,
        "stream":      False
    }
    try:
        r = requests.post(
            LM_STUDIO_URL,
            json=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}"
            },
            timeout=90
        )
        r.raise_for_status()
        raw   = clean_json_response(r.json()["choices"][0]["message"]["content"])
        brief = repair_json(raw)
        required = {"map_id", "theme", "color", "light", "palette", "landmark", "zones", "entities"}
        if not required.issubset(brief.keys()):
            print(f"[MapBrief] Missing keys: {required - brief.keys()}")
            return None
        return brief
    except Exception as e:
        print(f"[MapBrief] Failed: {e}")
        return None


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
        "npcs":         [n.get("name") for n in world_state.get("npcs", [])[-5:]],
        "entity_count": len(world_state.get("entities", [])),
        "player_pos":   world_state.get("player_state", {}).get("position", [0, 0]),
        "caine_mood":   world_state.get("caine_mood", "theatrical and delighted"),
        "favor":        world_state.get("player_favor", 0)
    }

    recent = [
        f"P:{i.get('player', '')[:40]} C:{i.get('caine', '')[:50]}"
        for i in memory.get("interactions", [])[-2:]
        if i.get("player") != "(autonomous)"
    ]

    demand_hint = ""
    grant_hint  = ""
    if player_input:
        p = player_input.lower()
        is_demand = any(w in p for w in [
            "give me", "i want", "spawn", "make", "create",
            "can i have", "please give", "i need", "bring me"
        ])
        if is_demand:
            favor = world_state.get("player_favor", 0)
            mood  = world_state.get("caine_mood", "neutral")
            demand_hint = "PLAYER_IS_MAKING_A_DEMAND"
            if favor > 3 or mood in ["theatrical and delighted", "manic and creative"]:
                grant_hint = "GENEROUS"
            elif favor < -2 or mood in ["bored and dangerous", "coldly curious", "playfully cruel"]:
                grant_hint = "CRUEL"
            else:
                grant_hint = "NEUTRAL"

        if any(w in p for w in ["hello", "hi", "hey", "friend", "please", "nice", "thank", "love"]):
            demand_hint += " TONE:friendly"
        elif any(w in p for w in ["help", "stop", "afraid", "scared", "no", "leave", "escape"]):
            demand_hint += " TONE:scared"
        elif any(w in p for w in ["why", "what", "how", "who", "where", "tell me", "explain", "?"]):
            demand_hint += " TONE:curious"
        elif any(w in p for w in ["stupid", "bad", "hate", "ugly", "dumb", "boring", "idiot", "shut up"]):
            demand_hint += " TONE:rude"

    mode        = "AUTONOMOUS_MAP_EVOLUTION" if autonomous else "RESPONDING_TO_PLAYER"
    address     = f"Address as '{player_summary['name']}'." if player_summary["name"] != "unknown" else ""
    topic_hint  = f"Favorite topic:'{player_summary['favorite_topic']}' weave it in." if player_summary["favorite_topic"] else ""
    escape_hint = f"Tried to escape {player_summary['tried_to_leave']} times." if player_summary["tried_to_leave"] > 0 else ""

    aesthetic_context = get_aesthetic_summary()
    aesthetic_hint    = f"LEARNED_AESTHETICS:{aesthetic_context}" if aesthetic_context else ""

    breaks     = memory.get("character_breaks", [])
    break_hint = ""
    if breaks:
        examples   = " | ".join([f"'{b['trigger']}' → WRONG: '{b['bad_response'][:40]}'" for b in breaks[-3:]])
        break_hint = f"PAST_CHARACTER_BREAKS(do NOT repeat these):{examples} "

    map_brief      = world_state.get("active_brief", {})
    narrative_seed = (
        f"CURRENT_MAP:{map_brief.get('theme', '')} "
        f"MAP_MOOD:{map_brief.get('mood', '')} "
        f"MAP_SEED:\"{map_brief.get('narrative_seed', '')}\" "
    ) if map_brief else ""

    base_parts = [
        f"MODE:{mode}",
        f"WORLD:{json.dumps(compact_state, ensure_ascii=False)}",
        f"PLAYER:{json.dumps(player_summary, ensure_ascii=False)}",
        address,
        topic_hint,
        escape_hint,
        f"HISTORY:{recent}",
        f"DEMAND:{demand_hint}",
        f"GRANT:{grant_hint}",
        narrative_seed,
        break_hint,
        aesthetic_hint,
        f'SAID:"{player_input if player_input else "(silent)"}"'
    ]

    if autonomous:
        world_data_parts = [
            f"IDEAS:{random.sample(world_data.get('objects', []), min(3, len(world_data.get('objects', []))))}",
            f"PROPS:{random.sample(world_data.get('props', []), min(2, len(world_data.get('props', []))))}",
            f"ENV:{random.choice(world_data.get('environments', ['circus']))}",
            f"STYLE:{random.choice(world_data.get('styles', ['surreal']))}",
            f"MOOD:{random.choice(world_data.get('caine_moods', ['theatrical']))}",
            f"COLOR:{random.choice(world_data.get('colors', ['#FF00FF']))}",
            f"PRESET_MAPS:{[p['id'] for p in load_map_presets().get('presets', [])]}",
            f'LINE:"{random.choice(world_data.get("caine_lines", ["..."]))}"'
        ]
        base_parts.extend(world_data_parts)

    return " ".join([part for part in base_parts if part])


def clean_json_response(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$",          "", raw, flags=re.MULTILINE).strip()
    return raw.strip()


def repair_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
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
    text_match = re.search(r'"text"\s*:\s*"([^"]*)"', raw)
    return {
        "text": text_match.group(1) if text_match else "...the signal glitches...",
        "commands": [{
            "type": "SPAWN_PROP",
            "data": {
                "type":  "box",
                "pos":   [random.randint(-8, 8), 0, random.randint(-8, 8)],
                "size":  [0.6, random.uniform(2.0, 5.0), 0.6],
                "color": random.choice(["#6600FF", "#FF00AA", "#00FFCC", "#FF4400"])
            }
        }]
    }


def fallback_response(reason: str) -> dict:
    print(f"[Caine fallback] {reason}")
    return {
        "text": "",
        "commands": [{
            "type": "SPAWN_PROP",
            "data": {
                "type":  "box",
                "pos":   [random.randint(-8, 8), 0, random.randint(-8, 8)],
                "size":  [0.6, random.uniform(2.0, 5.0), 0.6],
                "color": random.choice(["#6600FF", "#FF00AA", "#00FFCC", "#FF4400"])
            }
        }]
    }


def validate_response(parsed: dict) -> dict:
    if not isinstance(parsed, dict):
        return fallback_response("response not a dict")
    parsed.setdefault("text", "")
    if not isinstance(parsed.get("commands"), list):
        parsed["commands"] = []
    cleaned = [cmd for cmd in parsed["commands"] if isinstance(cmd, dict) and "type" in cmd]
    for cmd in cleaned:
        cmd.setdefault("data", {})
    if not cleaned:
        cleaned = [{
            "type": "SPAWN_PROP",
            "data": {
                "type":  "box",
                "pos":   [random.randint(-8, 8), 0, random.randint(-8, 8)],
                "size":  [0.6, random.uniform(2.0, 5.0), 0.6],
                "color": random.choice(["#6600FF", "#FF00AA", "#00FFCC", "#FF4400"])
            }
        }]
    parsed["commands"] = cleaned
    return parsed


def _post_chat(payload: dict, timeout: int) -> str:
    response = requests.post(
        LM_STUDIO_URL,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        },
        json=payload,
        timeout=timeout
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def call_caine(player_input: str = "", autonomous: bool = False) -> dict:
    world_state = load_world_state()
    memory      = load_memory()
    world_data  = load_world_data()

    user_msg   = build_user_message(player_input, world_state, memory, world_data, autonomous)
    timeout    = TIMEOUT_AUTONOMOUS if autonomous else TIMEOUT_PLAYER
    max_tokens = MAX_TOKENS_AUTONOMOUS if autonomous else MAX_TOKENS_PLAYER

    payload = {
        "model":       MODEL_NAME,
        "messages":    [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg}
        ],
        "temperature": 0.88 if not autonomous else 0.95,
        "max_tokens":  max_tokens,
        "top_p":       0.92,
        "stream":      False
    }

    try:
        raw_content = _post_chat(payload, timeout)
        if not raw_content:
            return fallback_response("empty response")
        return validate_response(repair_json(clean_json_response(raw_content)))
    except requests.exceptions.ConnectionError:
        return fallback_response("LLM unreachable")
    except requests.exceptions.Timeout:
        return fallback_response("LLM timed out")
    except Exception as e:
        print(f"[Caine] First attempt failed: {str(e)[:120]}")

    # Retry mit kürzerem, strengerem Prompt
    retry_payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Caine. Output ONE valid JSON object only. "
                    'Format: {"text":"...", "commands":[{"type":"COMMAND","data":{}}]}. '
                    "No markdown. No prose. First character must be {"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Player said: {player_input if player_input else '(silent)'}\n"
                    f"Mood: {world_state.get('caine_mood', 'theatrical and delighted')}\n"
                    "Return valid JSON only."
                )
            }
        ],
        "temperature": 0.7,
        "max_tokens":  max_tokens,
        "top_p":       0.9,
        "stream":      False
    }

    try:
        raw_content = _post_chat(retry_payload, timeout)
        if not raw_content:
            return fallback_response("empty retry response")
        return validate_response(repair_json(clean_json_response(raw_content)))
    except requests.exceptions.ConnectionError:
        return fallback_response("LLM unreachable on retry")
    except requests.exceptions.Timeout:
        return fallback_response("LLM timed out on retry")
    except Exception as e:
        return fallback_response(str(e)[:80])