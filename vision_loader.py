import os
os.environ["HF_TOKEN"]                = "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"
os.environ["HUGGING_FACE_HUB_TOKEN"]  = "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"
os.environ["HUGGINGFACE_TOKEN"]       = "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"

import json
import random
import re
from pathlib import Path
from PIL import Image

IMAGES_DIR   = Path("data/images")
LEARNED_FILE = Path("data/learned_aesthetics.json")

_moondream_model = None



def _get_moondream():
    global _moondream_model
    if _moondream_model is None:
        print("[Vision] Loading Moondream2 via transformers...")
        from transformers import AutoModelForCausalLM, AutoTokenizer
        model_id = "vikhyatk/moondream2"
        revision = "2024-05-08"           # stable, encode_image/answer_question API
        tokenizer = AutoTokenizer.from_pretrained(
            model_id, revision=revision, trust_remote_code=True
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision, trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        model.eval()
        _moondream_model = (model, tokenizer)
        print("[Vision] Moondream2 ready.")
    return _moondream_model


def _describe_with_moondream(image_path: Path) -> str:
    model, tokenizer = _get_moondream()
    from PIL import Image as PILImage
    image   = PILImage.open(image_path).convert("RGB")
    enc     = model.encode_image(image)
    caption = model.answer_question(enc, "Describe this image.", tokenizer)
    detail  = model.answer_question(
        enc,
        "Describe the dominant colors, mood, shapes, and lighting in one sentence.",
        tokenizer
    )
    return f"{caption} {detail}"

def _describe_with_moondream(image_path: Path) -> str:
    model, tokenizer = _get_moondream()
    from PIL import Image as PILImage
    image   = PILImage.open(image_path).convert("RGB")
    enc     = model.encode_image(image)
    caption = model.answer_question(enc, "Describe this image in detail.", tokenizer)
    detail  = model.answer_question(enc, "What are the dominant colors, mood, and lighting?", tokenizer)
    return f"{caption} {detail}"





# ── Caption parsing ───────────────────────────────────────────────────────────
COLOR_MAP = {
    "dark":    "#0A0008", "black":   "#050505", "red":     "#CC0000",
    "blue":    "#000066", "purple":  "#330044", "green":   "#003300",
    "white":   "#F0F0F0", "gold":    "#DAA520", "neon":    "#FF00FF",
    "orange":  "#FF6600", "yellow":  "#FFD700", "pink":    "#FF66AA",
    "grey":    "#444444", "gray":    "#444444", "silver":  "#C0C0C0",
    "cyan":    "#00FFCC", "glowing": "#AA00FF", "brown":   "#5C3317",
    "crimson": "#8B0000", "violet":  "#440088", "teal":    "#007777",
}

MOOD_MAP = {
    "dark":      "oppressive and silent",
    "bright":    "open and exposed",
    "ancient":   "ancient and watching",
    "ruin":      "decayed and forgotten",
    "glow":      "manic and electric",
    "empty":     "cold and infinite",
    "strange":   "unsettling and liminal",
    "ornate":    "decadent and dangerous",
    "fire":      "consuming and beautiful",
    "fog":       "dissolving and dreamlike",
    "mist":      "dissolving and dreamlike",
    "mirror":    "fractured and recursive",
    "tall":      "grand and hollow",
    "float":     "surreal and weightless",
    "blood":     "violent and intimate",
    "cathedral": "grand and hollow",
    "circus":    "theatrical and unsettling",
    "void":      "cold and infinite",
    "neon":      "manic and electric",
    "dream":     "soft and dissolving",
    "shadow":    "oppressive and silent",
    "light":     "open and exposed",
    "crumbl":    "decayed and forgotten",
    "haunt":     "unsettling and liminal",
    "frozen":    "still and merciless",
    "decay":     "decayed and forgotten",
}

SHAPE_MAP = {
    "arch":      "curved gateway",
    "tower":     "vertical spire",
    "pillar":    "standing column",
    "column":    "standing column",
    "stair":     "ascending steps",
    "corridor":  "winding corridor",
    "hall":      "grand interior hall",
    "dome":      "curved ceiling",
    "bridge":    "spanning arch",
    "wall":      "flat vertical surface",
    "platform":  "elevated flat surface",
    "spiral":    "spiral form",
    "cage":      "iron enclosure",
    "gate":      "framed entrance",
    "window":    "framed opening",
    "ring":      "circular frame",
    "statue":    "standing figure",
    "throne":    "elevated seat",
}

LIGHTING_MAP = {
    "dark":      "single point source casting long shadows",
    "neon":      "harsh colored emission with bloom",
    "soft":      "diffused ambient glow",
    "candle":    "warm flickering point light",
    "sunlight":  "harsh overhead directional light",
    "moon":      "cold blue overhead flood",
    "shadow":    "low-key dramatic side lighting",
    "glow":      "internal emission from surfaces",
    "fire":      "flickering orange from below",
    "fog":       "diffused sourceless ambient",
    "fluoresc":  "cold flat overhead",
    "torch":     "warm point source from below",
}


def _parse_caption(caption: str, filename: str) -> dict:
    text     = caption.lower()
    combined = text + " " + filename.lower().replace("_", " ").replace("-", " ")

    colors = list(dict.fromkeys([v for k, v in COLOR_MAP.items() if k in combined]))[:4]
    if not colors:
        colors = ["#1A0033", "#0A0A1A", "#220044"]

    mood = "mysterious and undefined"
    for k, v in MOOD_MAP.items():
        if k in combined:
            mood = v
            break

    shapes = list(dict.fromkeys([v for k, v in SHAPE_MAP.items() if k in combined]))[:4]

    lighting = "ambient diffused"
    for k, v in LIGHTING_MAP.items():
        if k in combined:
            lighting = v
            break

    keywords = list(dict.fromkeys([
        w for w in re.findall(r'\b[a-z]{4,}\b', combined)
        if w not in {"with","that","this","from","have","been","they","their",
                     "there","when","what","which","also","into","some","over"}
    ]))[:8]

    return {
        "mood":     mood,
        "colors":   colors,
        "shapes":   shapes,
        "lighting": lighting,
        "keywords": keywords,
        "summary":  caption[:150]
    }


# ── Filename fallback ─────────────────────────────────────────────────────────
FILENAME_MOOD_COLORS = {
    "dark":      {"mood": "oppressive and silent",       "colors": ["#0A0008","#1A0020","#050010"]},
    "neon":      {"mood": "manic and electric",          "colors": ["#FF00FF","#00FFCC","#FF4400"]},
    "circus":    {"mood": "theatrical and unsettling",   "colors": ["#CC0033","#FFD700","#1A0033"]},
    "void":      {"mood": "cold and infinite",           "colors": ["#000000","#0A0A0A","#111133"]},
    "blood":     {"mood": "violent and intimate",        "colors": ["#8B0000","#330000","#FF2200"]},
    "cathedral": {"mood": "grand and hollow",            "colors": ["#111122","#2A1A4A","#4A3A6A"]},
    "mirror":    {"mood": "fractured and recursive",     "colors": ["#C0C0C0","#A0A0FF","#E0E0E0"]},
    "dream":     {"mood": "soft and dissolving",         "colors": ["#9966CC","#FFB3FF","#66AAFF"]},
    "carnival":  {"mood": "frantic and hollow",          "colors": ["#FF6600","#FFDD00","#CC0066"]},
    "glitch":    {"mood": "broken and aware",            "colors": ["#00FF00","#FF00FF","#00FFFF"]},
    "palace":    {"mood": "decadent and dangerous",      "colors": ["#2A0A4A","#4A1A6A","#6A2A8A"]},
    "wasteland": {"mood": "desolate and honest",         "colors": ["#3D2B1F","#5C4033","#2A1A10"]},
    "fire":      {"mood": "consuming and beautiful",     "colors": ["#FF4400","#FF8800","#FFCC00"]},
    "ice":       {"mood": "still and merciless",         "colors": ["#AADDFF","#CCEEFF","#88CCFF"]},
    "forest":    {"mood": "ancient and watching",        "colors": ["#002200","#004400","#001100"]},
    "rust":      {"mood": "decayed and forgotten",       "colors": ["#5C2E00","#8B4513","#A0522D"]},
    "purple":    {"mood": "regal and unsettling",        "colors": ["#330033","#660066","#440044"]},
    "gold":      {"mood": "corrupt and alluring",        "colors": ["#FFD700","#DAA520","#B8860B"]},
    "red":       {"mood": "urgent and primal",           "colors": ["#CC0000","#880000","#FF0000"]},
    "blue":      {"mood": "deep and melancholic",        "colors": ["#000033","#000066","#000099"]},
}

def _learn_from_filename(path: Path) -> dict:
    stem     = path.stem.lower().replace("-", "_").replace(" ", "_")
    parts    = stem.split("_")
    colors, moods, shapes = [], [], []

    for part in parts:
        if part in FILENAME_MOOD_COLORS:
            entry = FILENAME_MOOD_COLORS[part]
            moods.append(entry["mood"])
            colors.extend(entry["colors"])
        if part in SHAPE_MAP:
            shapes.append(SHAPE_MAP[part])

    colors = list(dict.fromkeys(colors))[:4] or ["#1A0033","#0A0A1A"]
    moods  = list(dict.fromkeys(moods))      or ["mysterious and undefined"]

    return {
        "source":   path.name,
        "mood":     moods[0],
        "colors":   colors,
        "shapes":   shapes[:3],
        "lighting": "ambient diffused",
        "keywords": parts[:6],
        "summary":  f"Filename-learned: {path.stem.replace('_',' ')}"
    }


# ── Main scanner ──────────────────────────────────────────────────────────────
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

def scan_images_folder() -> list:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    existing        = load_learned_aesthetics()
    already_learned = {e["source"] for e in existing}

    candidates = [
        p for p in sorted(IMAGES_DIR.iterdir())
        if p.suffix.lower() in SUPPORTED and p.name not in already_learned
    ]

    if not candidates:
        print(f"[Vision] No new images. {len(existing)} aesthetics already loaded.")
        return existing

    print(f"[Vision] Found {len(candidates)} new image(s) to learn.")
    print(f"[Vision] Estimated time: ~{len(candidates) * 25}s on CPU. Sit tight.")

    new_entries = []
    for i, img_path in enumerate(candidates, 1):
        print(f"[Vision] Processing {i}/{len(candidates)}: {img_path.name}")
        try:
            combined_text = _describe_with_moondream(img_path)
            parsed        = _parse_caption(combined_text, img_path.stem)
            parsed["source"] = img_path.name
            print(f"[Vision] ✓ {img_path.name}: {parsed['mood']} | {parsed['colors'][:2]}")
            new_entries.append(parsed)
        except Exception as e:
            print(f"[Vision] ✗ {img_path.name} failed ({e}) — using filename fallback")
            new_entries.append(_learn_from_filename(img_path))

    all_entries = existing + new_entries
    LEARNED_FILE.write_text(json.dumps(all_entries, indent=2))
    print(f"[Vision] Done. {len(new_entries)} new aesthetics saved. "
          f"Total library: {len(all_entries)}")
    return all_entries



def load_learned_aesthetics() -> list:
    if not LEARNED_FILE.exists():
        return []
    try:
        return json.loads(LEARNED_FILE.read_text())
    except Exception:
        return []


def get_aesthetic_summary() -> str:
    aesthetics = load_learned_aesthetics()
    if not aesthetics:
        return ""
    sample = random.sample(aesthetics, min(3, len(aesthetics)))
    lines  = []
    for a in sample:
        lines.append(
            f"[{a.get('source','?')}] "
            f"mood:{a.get('mood','?')} "
            f"colors:{a.get('colors',[][:2])} "
            f"shapes:{a.get('shapes',[][:2])} "
            f"keywords:{a.get('keywords',[][:4])}"
        )
    return " | ".join(lines)
