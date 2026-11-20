"""Phonon 31M text-to-speech engine wrapper (Gradium, Apache-2.0).

The model (gradium/phonon-31m-en, q8 GGUF) and the English voice
catalog (gradium/phonon-voices) are baked into the Docker image at
build time by fetch_assets.py — nothing is downloaded at run time.
Synthesis runs entirely on CPU via the `ptts` runtime.

Long scripts are split into <= MAX_CHUNK_CHARS chunks at sentence
boundaries: the model resets prosody on very long inputs, so chunked
synthesis stitched with short silences sounds more natural than one
long pass.
"""

from __future__ import annotations

import os
import re
import threading

import numpy as np

MODEL_DIR = os.environ.get("PHONON_MODEL_DIR", "/opt/phonon/model")
CATALOG_DIR = os.environ.get("PHONON_CATALOG_DIR", "/opt/phonon/catalog")
SAMPLE_RATE = 24000
MAX_CHUNK_CHARS = 600
GAP_SECONDS = 0.3

# The English voices of the pinned phonon-voices catalog revision.
# Every name here is verified against the baked catalog during
# staging (see BUILD_NOTES.md); the input schema enum mirrors this
# list exactly.
VOICES: dict[str, str] = {
    "Zoey": "Playful, upbeat Gen Z energy, standard American accent.",
    "Juniper": "Cheerful with real resonance; personable on intimate copy, decisive on the final line.",
    "Everly": "Rounded, soft-edged tone with a gentle lift at the end of phrases; relaxed delivery.",
    "Harper": "Modern, confident and friendly, standard American accent.",
    "Hadley": "Settled, even-toned and genuinely kind, with crisp consonants.",
    "Delia": "Low, grounded and quick to the point; sincere.",
    "Easton": "Punchy and close in, crisp consonant attack that cuts through a music bed.",
    "Micah": "Buoyant, high energy, playful lift at the ends of phrases.",
    "Trevor": "Buoyant energy over a resonant mid-low core; phrases land softly.",
    "Russell": "High-energy American adult voice; pushes and encourages.",
    "Preston": "Trim, focused delivery, clean consonant edges, steady low-set core.",
    "Miles": "Resonant and decisive with genuine dynamic range.",
    "Maeve": "Sparky, attentive British English adult voice; gets to the point with a smile.",
    "Freya": "Young British voice, glossy and confident, bubbly sparkle.",
    "Pippa": "Confident, upbeat British English adult voice with infectious energy.",
    "Elodie-Rose": "Young British voice with sharp, enthusiastic energy and crisp articulation.",
    "Imogen": "Bubbly, friendly British English adult voice; puts listeners at ease.",
    "Lottie": "Sparky and to the point, high forward energy, clean consonant edges.",
    "Alfie": "Punchy and forward British voice, crisp attack, pitch lifts across a line.",
    "Hugh": "Soft and close British voice, airy texture, lively pitch movement.",
    "Edwin": "Efficient and firm British voice with tidy articulation.",
    "Spencer": "Light and airy British voice, crisp consonants, slow patient delivery.",
    "Toby": "Sparky, attentive British English adult voice; efficient and warm.",
    "Teddy": "Sparky and close in British voice, quick off the mark, firm consonants.",
    "Bryony": "Full, rich mid-range British tones, softly relaxed, spoken close to the mic.",
    "Captain Silas Blackwater": "Character voice: an old British pirate captain from the West Country, deep and gravelly.",
    "Morwenna of the Deep": "Character voice: a sultry woman in her thirties, low husky alto, close to the microphone.",
    "Old Mortlake": "Character voice: an elderly Victorian gravedigger, low, raspy and half whispered.",
    "Azgorath": "Character voice: an enormous ancient demon, cavernous impossibly deep bass.",
    "Fennick the Young Elf": "Character voice: a curious, kind-hearted elf boy of about ten, warm natural child's voice.",
    "The Thing Under the Stairs": "Character voice: a monstrous creature lurking in the dark, gravelly and breathy.",
    "Vyrmathrax the Ancient": "Character voice: an ancient dragon, very low and resonant with deep chest weight.",
    "Grub the Ogre": "Character voice: a big, good-natured ogre, gruff and grainy, rumbling low.",
    "Master Aldric": "Character voice: a wise old British wizard around eighty, rich and resonant with an aged grain.",
    "The Snow Queen": "Character voice: a regal, cold-hearted queen of ice, cool crystalline mezzo, poised.",
    "Sir Bramwell": "Character voice: a brave but pompous English knight, booming, plummy and theatrical.",
    "Fairy Godmother": "Character voice: a kind fairy godmother in her sixties, low warm velvety alto.",
}

DEFAULT_VOICE = "Harper"

_tts = None
_lock = threading.Lock()


def get_tts():
    """Load the model once per process (thread-safe singleton)."""
    global _tts
    if _tts is None:
        with _lock:
            if _tts is None:
                import ptts

                # Cap worker threads: on many-core hosts an uncapped
                # pool oversubscribes the container's CPU quota and
                # sustained synthesis slows to a crawl (measured on
                # the platform: 0.26x realtime uncapped in a 1 GB
                # container vs ~1x per core expected).
                try:
                    ptts.set_num_threads(int(os.environ.get("PHONON_THREADS", "4")))
                except Exception:
                    pass
                _tts = ptts.TTS(
                    MODEL_DIR, lang="en", quant="q8_0", voice_catalog=CATALOG_DIR
                )
    return _tts


_SENTENCE_RE = re.compile(r"[^.!?…\n]+(?:[.!?…]+[\"'”’)\]]*)?\s*|\n+")


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-ish units, keeping punctuation."""
    parts = [p.strip() for p in _SENTENCE_RE.findall(text)]
    return [p for p in parts if p]


def _hard_split(sentence: str, limit: int) -> list[str]:
    """Split one over-long sentence at word boundaries."""
    out: list[str] = []
    rest = sentence.strip()
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def chunk_text(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack sentences into chunks of at most `limit` characters."""
    chunks: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        pieces = (
            _hard_split(sentence, limit) if len(sentence) > limit else [sentence]
        )
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= limit:
                current = f"{current} {piece}"
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def synthesize(text: str, voice: str) -> tuple[np.ndarray, int]:
    """Synthesize a full script. Returns (float32 mono samples, chunks).

    Raises ValueError for an unknown voice; ptts raises for text it
    cannot synthesize — the caller turns both into an ERROR row.
    """
    if voice not in VOICES:
        raise ValueError(
            f"Unknown voice {voice!r}. Use one of the voices listed in the input schema."
        )
    tts = get_tts()
    gap = np.zeros(int(SAMPLE_RATE * GAP_SECONDS), dtype=np.float32)
    parts: list[np.ndarray] = []
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        wave = np.asarray(tts.synth(chunk, voice=voice), dtype=np.float32)
        if wave.size == 0:
            raise ValueError(f"Synthesis produced no audio for chunk {i + 1}.")
        if i:
            parts.append(gap)
        parts.append(wave)
    if not parts:
        raise ValueError("Synthesis produced no audio.")
    return np.concatenate(parts), len(chunks)
