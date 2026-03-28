import random
import math
import json
import os

ZONE_RADII = {
    "entrance":  (8,  13),
    "center":    (0,   4),
    "perimeter": (14, 17),
}

BOUNDS = 17.0

_THEMES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "map_themes.json")
try:
    with open(_THEMES_PATH) as f:
        THEME_BLUEPRINTS = json.load(f)["themes"]
    print(f"[MapBuilder] Loaded {len(THEME_BLUEPRINTS)} theme blueprints.")
except Exception as e:
    THEME_BLUEPRINTS = {}
    print(f"[MapBuilder] No theme blueprints loaded: {e}")


def _clamp(v: float, lo: float = -BOUNDS, hi: float = BOUNDS) -> float:
    return max(lo, min(hi, v))


def _polar(r: float, angle_deg: float, y: float = 0) -> list:
    a = math.radians(angle_deg)
    return [round(_clamp(r * math.cos(a)), 2), round(y, 2), round(_clamp(r * math.sin(a)), 2)]


def _ev(cmd: str, data: dict) -> dict:
    return {"cmd": cmd, "data": data}


def _prop(pos: list, size: list, color: str, ptype: str = "box") -> dict:
    return _ev("SPAWN_PROP", {"type": ptype, "pos": pos, "size": size, "color": color})


def _pillar(pos: list, height: float, color: str) -> dict:
    return _prop(
        [pos[0], height / 2, pos[2]],
        [random.uniform(0.4, 0.9), height, random.uniform(0.4, 0.9)],
        color
    )


def _platform(pos: list, size: float, y: float, color: str) -> dict:
    return _prop([pos[0], y, pos[2]], [size, 0.3, size], color, "platform")


def _staircase(start: list, end: list, steps: int, color: str) -> list:
    events = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        x = start[0] + (end[0] - start[0]) * t
        z = start[2] + (end[2] - start[2]) * t
        y = (i / steps) * 3.0
        events.append(_platform([x, 0, z], 1.8, y + 0.15, color))
    return events


def _ring_of_pillars(radius: float, count: int, height: float, color: str, offset_angle: float = 0) -> list:
    events = []
    for i in range(count):
        angle = (360 / count) * i + offset_angle
        pos   = _polar(radius, angle)
        events.append(_pillar(pos, height, color))
    return events


def _archway(pos: list, color: str) -> list:
    x, _, z = pos
    return [
        _prop([x - 1.0, 2.5, z], [0.4, 5.0, 0.4], color),
        _prop([x + 1.0, 2.5, z], [0.4, 5.0, 0.4], color),
        _prop([x,        5.2, z], [2.6, 0.4, 0.4], color),
    ]


def _scattered_props(center: list, count: int, spread: float,
                     color: str, min_spacing: float = 1.5) -> list:
    events   = []
    occupied = []
    for _ in range(count * 4):
        if len(events) >= count:
            break
        angle = random.uniform(0, 360)
        r     = random.uniform(0.5, spread)
        pos   = [
            _clamp(center[0] + r * math.cos(math.radians(angle))),
            0,
            _clamp(center[2] + r * math.sin(math.radians(angle)))
        ]
        too_close = any(
            math.hypot(pos[0] - o[0], pos[2] - o[2]) < min_spacing
            for o in occupied
        )
        if too_close:
            continue
        occupied.append(pos)
        is_tall = random.random() > 0.6
        height  = random.uniform(3.0, 7.0) if is_tall else random.uniform(1.0, 2.5)
        ptype   = "box" if is_tall else random.choice(["box", "platform"])
        w       = random.uniform(0.3, 0.8) if is_tall else random.uniform(1.2, 2.5)
        d       = random.uniform(0.3, 0.8) if is_tall else random.uniform(1.2, 2.5)
        events.append(_prop([pos[0], height / 2, pos[2]], [w, height, d], color, ptype))
    return events


def _build_from_blueprint(bp: dict, brief: dict) -> list:
    events  = []
    palette = bp.get("palette", brief.get("palette", ["#440066"]))

    events.append(_ev("CLEAR_MAP", {}))
    events.append(_ev("CLEAR_ENTITIES", {}))
    events.append(_ev("CHANGE_THEME", {
        "theme": brief["theme"],
        "color": bp.get("bg_color", brief["color"])
    }))

    # Structures
    for s in bp.get("structures", []):
        events.append(_ev("SPAWN_STRUCTURE", {
            "structure": s["type"],
            "position":  s.get("position", [0, 0, 0]),
            "color":     s["color"]
        }))

    # Props
    for p in bp.get("props", []):
        count   = p.get("count", 1)
        radius  = p.get("ring_radius")
        y_range = p.get("y_range", [0, 0])
        for i in range(count):
            if radius:
                angle = (360 / count) * i + random.uniform(-10, 10)
                pos   = _polar(
                    radius + random.uniform(-1, 1),
                    angle,
                    random.uniform(y_range[0], y_range[1]) if y_range[1] > 0 else 0
                )
            else:
                pos = [
                    _clamp(random.uniform(-12, 12)),
                    random.uniform(y_range[0], y_range[1]),
                    _clamp(random.uniform(-12, 12))
                ]
            events.append(_prop(pos, p["size"], p["color"], p["type"]))

    # Lights
    for l in bp.get("lights", []):
        events.append(_ev("SPAWN_LIGHT", {
            "position":  l["position"],
            "color":     l["color"],
            "intensity": l["intensity"],
            "range":     l["range"]
        }))

    # Paths as staircases
    for path in bp.get("paths", []):
        src = path["from"]
        dst = path["to"]
        if len(src) == 2:
            src = [src[0], 0, src[1]]
        if len(dst) == 2:
            dst = [dst[0], 0, dst[1]]
        events.extend(_staircase(src, dst, steps=5, color=random.choice(palette)))

    # Entities
    for name in bp.get("entities", []):
        angle = random.uniform(0, 360)
        pos   = _polar(random.uniform(3, 8), angle)
        events.append(_ev("CREATE_ENTITY", {
            "name":     name,
            "style":    "surreal",
            "position": [pos[0], pos[2]]
        }))

    return events


def build_map_from_brief(brief: dict) -> list:
    # Blueprint lookup — theme name normalisieren
    theme_raw = brief.get("theme", "")
    theme_key = theme_raw.lower().replace(" ", "_")
    bp        = THEME_BLUEPRINTS.get(theme_key)

    if bp:
        print(f"[MapBuilder] Using blueprint: {theme_key}")
        return _build_from_blueprint(bp, brief)

    print(f"[MapBuilder] No blueprint for '{theme_key}', using procedural build.")

    events  = []
    palette = brief.get("palette", ["#440066", "#220044", "#660044"])
    c1      = palette[0]
    c2      = palette[1 % len(palette)]
    c3      = palette[2 % len(palette)]

    # 1. Clear
    events.append(_ev("CLEAR_MAP", {}))
    events.append(_ev("CLEAR_ENTITIES", {}))

    # 2. Theme
    events.append(_ev("CHANGE_THEME", {
        "theme": brief["theme"],
        "color": brief["color"]
    }))
    events.append(_ev("SPAWN_LIGHT", {
        "position":  [0, 7, 0],
        "color":     brief.get("light", "#6600FF"),
        "intensity": 2.5,
        "range":     20.0
    }))

    # 3. Landmark
    lm = brief.get("landmark", {})
    if lm:
        events.append(_ev("SPAWN_STRUCTURE", {
            "structure": lm.get("type", "tower"),
            "position":  lm.get("position", [0, 0, 0]),
            "color":     lm.get("color", c1)
        }))

    # 4. Inner circle
    events.extend(_ring_of_pillars(radius=5.0, count=6, height=2.5, color=c2, offset_angle=30))
    events.extend(_scattered_props([0, 0, 0], count=5, spread=3.5, color=c1))

    # 5. Arched entrances
    for angle in [0, 90, 180, 270]:
        pos = _polar(9.0, angle)
        events.extend(_archway(pos, c3))

    # 6. Mid ring
    zones   = brief.get("zones", {})
    mid_col = zones.get("entrance", {}).get("color", c2)
    events.extend(_ring_of_pillars(radius=8.5, count=8, height=4.0, color=mid_col))
    events.extend(_scattered_props([0, 0, 0], count=8, spread=11.0, color=mid_col, min_spacing=2.0))

    # 7. Elevated platforms with staircases
    for i in range(3):
        angle    = i * 120 + random.uniform(-20, 20)
        plat_pos = _polar(6.5, angle)
        y_height = random.uniform(2.5, 4.5)
        events.append(_platform(plat_pos, 3.5, y_height, c1))
        stair_start    = _polar(9.5, angle)
        stair_start[1] = 0
        events.extend(_staircase(stair_start, plat_pos, steps=4, color=c2))
        events.append(_ev("SPAWN_LIGHT", {
            "position":  [plat_pos[0], y_height - 0.5, plat_pos[2]],
            "color":     random.choice(palette),
            "intensity": 1.5,
            "range":     5.0
        }))

    # 8. Perimeter
    perim_col = zones.get("perimeter", {}).get("color", c3)
    events.extend(_ring_of_pillars(radius=15.5, count=12, height=6.0, color=perim_col))

    # 9. POIs
    poi_count = zones.get("poi_count", 2)
    for i in range(poi_count):
        angle   = (360 / max(poi_count, 1)) * i + 45
        poi_pos = _polar(random.uniform(10, 13), angle)
        y       = random.uniform(1.0, 3.0)
        events.append(_platform(poi_pos, 2.0, y, random.choice(palette)))
        events.append(_ev("SPAWN_LIGHT", {
            "position":  [poi_pos[0], y + 2, poi_pos[2]],
            "color":     random.choice(palette),
            "intensity": 1.2,
            "range":     4.0
        }))

    # 10. Entities
    for entity in brief.get("entities", []):
        events.append(_ev("CREATE_ENTITY", entity))

    return events