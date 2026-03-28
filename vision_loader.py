import os
import json
import re
from PIL import Image

IMAGES_DIR        = "data/images"
AESTHETICS_FILE   = "data/learned_aesthetics.json"
PROCESSED_FILE    = "data/processed_images.json"

STRUCTURED_PROMPT = """Analyze this image for a 3D game world builder.
Output ONLY valid JSON, nothing else. First character must be {

{
  "palette": ["#hex1", "#hex2", "#hex3"],
  "mood": "<one phrase: e.g. oppressive neon, dreamlike pastel, chaotic glitch>",
  "structures": ["<thing you see, described as a 3D object>", "<another>"],
  "prop_ideas": ["<small object idea>", "<another>"],
  "layout_hint": "<one sentence about spatial arrangement>",
  "color_theme": "<dominant color name>",
  "style": "<surreal|neon|glitchy|dreamlike|cartoon>"
}"""


def _extract_colors_from_image(img: Image.Image) -> list:
    """Extract dominant hex colors using simple quantization."""
    small = img.resize((100, 100)).convert("RGB")
    quantized = small.quantize(colors=5).convert("RGB")
    palette_data = quantized.getcolors(maxcolors=10000)
    if not palette_data:
        return ["#1A0033", "#FF00AA", "#00FFCC"]
    sorted_colors = sorted(palette_data, key=lambda x: x[0], reverse=True)
    hexes = []
    for _, rgb in sorted_colors[:3]:
        hexes.append("#{:02X}{:02X}{:02X}".format(rgb[0], rgb[1], rgb[2]))
    return hexes


_moondream_model     = None
_moondream_tokenizer = None

def _get_moondream():
    global _moondream_model, _moondream_tokenizer
    if _moondream_model is not None:
        return _moondream_model, _moondream_tokenizer
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        model_id = "vikhyatk/moondream2"
        revision = "2025-01-09"
        print("[Vision] Loading Moondream2...")
        _moondream_tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        _moondream_model     = AutoModelForCausalLM.from_pretrained(
            model_id, trust_remote_code=True, revision=revision
        )
        print("[Vision] Moondream2 ready.")
        return _moondream_model, _moondream_tokenizer
    except Exception as e:
        print(f"[Vision] Moondream2 failed to load: {e}")
        return None, None


def _analyze_image_structured(image_path: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    palette = _extract_colors_from_image(img)

    try:
        model, tokenizer = _get_moondream()
        if model is None:
            raise RuntimeError("model not loaded")

        result = model.query(img, STRUCTURED_PROMPT)["answer"]
        result = result.strip()
        result = re.sub(r"^```(?:json)?", "", result, flags=re.MULTILINE).strip()
        result = re.sub(r"```$",          "", result, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            parsed = json.loads(match.group()) if match else {}

        parsed["palette"] = palette   # always override with real pixel colors
        parsed["source"]  = os.path.basename(image_path)
        return parsed

    except Exception as e:
        print(f"[Vision] Moondream query failed for {image_path}: {e}")
        return {
            "palette":     palette,
            "mood":        "unknown",
            "structures":  [],
            "prop_ideas":  [],
            "layout_hint": "",
            "color_theme": "dark",
            "style":       "surreal",
            "source":      os.path.basename(image_path)
        }


def scan_images_folder():
    """Scan images/, analyze new ones, save structured aesthetics."""
    os.makedirs(IMAGES_DIR, exist_ok=True)

    processed = {}
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r") as f:
                processed = json.load(f)
        except:
            processed = {}

    aesthetics = []
    if os.path.exists(AESTHETICS_FILE):
        try:
            with open(AESTHETICS_FILE, "r") as f:
                aesthetics = json.load(f)
        except:
            aesthetics = []

    supported = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    new_count  = 0

    for fname in os.listdir(IMAGES_DIR):
        if not any(fname.lower().endswith(ext) for ext in supported):
            continue
        if fname in processed:
            continue

        path   = os.path.join(IMAGES_DIR, fname)
        print(f"[Vision] Analyzing: {fname}")
        result = _analyze_image_structured(path)

        if result:
            aesthetics.append(result)
            processed[fname] = True
            new_count += 1
            print(f"[Vision] Learned: mood='{result.get('mood')}' style='{result.get('style')}' palette={result.get('palette')}")

    if new_count > 0:
        with open(AESTHETICS_FILE, "w") as f:
            json.dump(aesthetics, f, indent=2)
        with open(PROCESSED_FILE, "w") as f:
            json.dump(processed, f, indent=2)
        print(f"[Vision] {new_count} new images learned. Total: {len(aesthetics)}")
    else:
        print(f"[Vision] No new images. {len(aesthetics)} aesthetics loaded.")


def get_aesthetic_summary() -> str:
    """Return a rich structured summary for injection into Caine's prompt."""
    if not os.path.exists(AESTHETICS_FILE):
        return ""
    try:
        with open(AESTHETICS_FILE, "r") as f:
            aesthetics = json.load(f)
        if not aesthetics:
            return ""

        # Pick 2 random aesthetics to keep prompt fresh
        import random
        chosen = random.sample(aesthetics, min(2, len(aesthetics)))

        parts = []
        for a in chosen:
            part = (
                f"[img:{a.get('source','?')} "
                f"mood:{a.get('mood','?')} "
                f"style:{a.get('style','?')} "
                f"palette:{','.join(a.get('palette',[]))} "
                f"structures:{','.join(a.get('structures',[])[:2])} "
                f"props:{','.join(a.get('prop_ideas',[])[:2])} "
                f"layout:{a.get('layout_hint','')}]"
            )
            parts.append(part)

        return " | ".join(parts)
    except:
        return ""