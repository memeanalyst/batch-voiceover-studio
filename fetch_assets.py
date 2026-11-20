"""Build-time asset download (runs inside the Docker build only).

Bakes the Phonon 31M English model (gradium/phonon-31m-en, Apache-2.0)
and the English voices of the pinned phonon-voices catalog into the
image, so actor runs never download anything at startup.

Downloads use the classic Hugging Face resolve path (the Xet path
rate-limits unauthenticated IPs). Revisions are pinned to the exact
commits the ptts runtime defaults to.
"""

import json
import os
import sys
import urllib.request

MODEL_REPO = "gradium/phonon-31m-en"
MODEL_REV = "92741c5b07d085ff840e26fea8ce43110b87852f"
VOICES_REPO = "gradium/phonon-voices"
VOICES_REV = "da6c9ec0d47be8df5c87c730a3aa97187f3229c3"

MODEL_FILES = [
    "config.json",
    "generation_config.json",
    "processor_config.json",
    "tokenizer.json",
    "tokenizer.model",
    "tokenizer.5.0.0.json",
    "tokenizer_config.json",
    "default-voice.safetensors",
    "model.q8.gguf",
]

DEST = os.environ.get("PHONON_ASSETS_DIR", "/opt/phonon")


def fetch(repo: str, rev: str, filename: str, dest: str) -> None:
    url = f"https://huggingface.co/{repo}/resolve/{rev}/{filename}"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "magnova-asset-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    size = os.path.getsize(dest)
    assert size > 0, f"empty download: {url}"
    print(f"  {filename}: {size:,} bytes")


def main() -> None:
    model_dir = os.path.join(DEST, "model")
    catalog_dir = os.path.join(DEST, "catalog")
    print(f"Fetching model {MODEL_REPO}@{MODEL_REV[:8]} -> {model_dir}")
    for name in MODEL_FILES:
        fetch(MODEL_REPO, MODEL_REV, name, os.path.join(model_dir, name))

    print(f"Fetching voice catalog {VOICES_REPO}@{VOICES_REV[:8]} -> {catalog_dir}")
    raw_jsonl = os.path.join(catalog_dir, "voices.jsonl.raw")
    fetch(VOICES_REPO, VOICES_REV, "voices.jsonl", raw_jsonl)
    en_voices = []
    with open(raw_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("language") == "en":
                en_voices.append(entry)
    os.remove(raw_jsonl)
    assert len(en_voices) >= 30, f"suspiciously few English voices: {len(en_voices)}"
    with open(os.path.join(catalog_dir, "voices.jsonl"), "w", encoding="utf-8") as f:
        for entry in en_voices:
            f.write(json.dumps(entry) + "\n")
    for entry in en_voices:
        vid = entry["voice_id"]
        fetch(VOICES_REPO, VOICES_REV, f"voices/{vid}.safetensors",
              os.path.join(catalog_dir, "voices", f"{vid}.safetensors"))
    print(f"Assets ready: model + {len(en_voices)} English voices")


if __name__ == "__main__":
    sys.exit(main())
