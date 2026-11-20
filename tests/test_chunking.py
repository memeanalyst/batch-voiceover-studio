"""Chunking + billing units (pure functions)."""

from bvs import engine as E
from bvs.main import billed_units


def test_chunking_packs_sentences_under_limit():
    text = " ".join(f"Sentence number {i} is here to be narrated." for i in range(60))
    chunks = E.chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= E.MAX_CHUNK_CHARS for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunking_hard_splits_one_long_sentence():
    text = " ".join(["word"] * 400)  # ~2000 chars, no sentence breaks
    chunks = E.chunk_text(text)
    assert len(chunks) >= 4
    assert all(len(c) <= E.MAX_CHUNK_CHARS for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunking_short_text_single_chunk():
    assert E.chunk_text("Hello world. How are you?") == ["Hello world. How are you?"]


def test_chunking_empty_text():
    assert E.chunk_text("") == []
    assert E.chunk_text("   \n ") == []


def test_billed_units():
    assert billed_units(1) == 1
    assert billed_units(999) == 1
    assert billed_units(1000) == 1
    assert billed_units(1001) == 2
    assert billed_units(2500) == 3
    assert billed_units(100_000) == 100
