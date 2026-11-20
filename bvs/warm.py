"""Build-time warm-up: loads the baked model + catalog and
synthesizes one line in two voices, so a broken asset download or
runtime mismatch fails the build instead of the first user run.
"""
import numpy as np

from . import engine as E

tts = E.get_tts()
for voice in ("Harper", "Captain Silas Blackwater"):
    wave = np.asarray(tts.synth("Warm up. The studio is ready.", voice=voice))
    assert wave.size > E.SAMPLE_RATE // 2, f"warm-up produced too little audio for {voice}"
    print(f"warm-up ok: {voice} -> {wave.size / E.SAMPLE_RATE:.2f}s")
chunks = E.chunk_text("One. Two! Three? " * 60)
assert len(chunks) > 1 and all(len(c) <= E.MAX_CHUNK_CHARS for c in chunks)
print("warm-up ok: chunking ->", len(chunks), "chunks")
