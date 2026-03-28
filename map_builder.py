# map_builder.py — new file

import random
import math

ZONE_RADII = {
    "entrance":  (10, 14),   # outer ring
    "center":    (0,  4),    # inner core
    "perimeter": (14, 18),   # boundary markers
}

def _polar_to_xyz(r: float, angle_deg: float) -> list:
    a = math.radians(angle_deg)
    return [round(r * math.cos(a), 2), 0, round(r * math.sin(a), 2)]

def _place_prop(pos: list, color: str, density: int, style: str) -> list:
    """Generate density-many props around a position."""
    events = []
    for _ in range(density):
        offset = [pos[0] + random.uniform(-2, 2), 0, pos[2] + random.uniform(-2, 2)]
        prop_type = random.choice(["box", "platform"])
        size = (
            [random.uniform(0.3, 0.8), random.uniform(2.0, 6.0), random.uniform(0.3, 0.8)]
            if prop_type == "box"
            else [random.uniform(1.5, 3.5), 0.3, random.uniform(1.5, 3.5)]
        )
        events.append({"cmd": "SPAWN_PROP", "data": {
            "type": prop_type, "pos": offset, "size": size, "color": color
        }})
    return events

def build_map_from_brief(brief: dict) -> list:
    """Returns a list of world events that fully construct the map."""
    events = []
    palette = brief.get("palette", ["#440066", "#220044", "#660044"])

    # 1. Clear current map
    events.append({"cmd": "CLEAR_MAP", "data": {}})

    # 2. Set theme/environment
    events.append({"cmd": "CHANGE_THEME", "data": {
        "theme": brief["theme"],
        "color": brief["color"],
        "light": brief.get("light", "#6600FF")
    }})

    # 3. Place landmark first at center
    lm = brief["landmark"]
    events.append({"cmd": "SPAWN_STRUCTURE", "data": {
        "structure": lm["type"],
        "position": lm.get("position", [0, 0, 0]),
        "color": lm["color"]
    }})

    # 4. Place zones
    zones = brief.get("zones", {})
    placed_positions = set()

    for zone_name, (r_min, r_max) in ZONE_RADII.items():
        zone = zones.get(zone_name, {})
        density = zone.get("density", 2)
        color   = zone.get("color", random.choice(palette))
        style   = zone.get("style", "surreal")

        # Evenly distribute props around the ring
        num_clusters = max(1, density)
        for i in range(num_clusters):
            angle = (360 / num_clusters) * i + random.uniform(-15, 15)
            r = random.uniform(r_min, r_max)
            pos = _polar_to_xyz(r, angle)
            pos_key = (round(pos[0]), round(pos[2]))
            if pos_key in placed_positions:
                continue
            placed_positions.add(pos_key)
            events.extend(_place_prop(pos, color, min(density, 3), style))

    # 5. Place POIs — small platform clusters at interesting angles
    poi_count = zones.get("poi_count", 2)
    for i in range(poi_count):
        angle = random.uniform(0, 360)
        pos   = _polar_to_xyz(random.uniform(6, 10), angle)
        events.append({"cmd": "SPAWN_PROP", "data": {
            "type": "platform",
            "pos":  [pos[0], random.uniform(1.5, 4.0), pos[2]],
            "size": [2.5, 0.3, 2.5],
            "color": random.choice(palette)
        }})

    # 6. Entities
    for entity in brief.get("entities", []):
        events.append({"cmd": "SPAWN_ENTITY", "data": entity})

    return events