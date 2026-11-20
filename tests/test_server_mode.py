"""Server (standby) mode: delivery sink + HTTP handler contract,
plus a stubbed-engine _run over a mixed batch (OK + ERROR rows).

Charges are per 1,000 characters ('chars-1000'), accumulated in
the sink in server mode and billed once by the handler. Offline
tests: the TTS engine's synthesize is stubbed (the handler
contract never touches the model), Actor storage/charge calls
are stubbed.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from bvs import main as m


class _FakeRequest:
    def __init__(self, payload, raw: bytes | None = None, headers=None):
        self._payload = payload
        self._raw = raw
        self.headers = headers or {}

    async def json(self):
        if self._raw is not None:
            return json.loads(self._raw.decode())
        return self._payload


class _FakeKVS:
    def __init__(self):
        self.values = {}

    async def set_value(self, key, value, content_type=None):
        self.values[key] = value

    async def get_public_url(self, key):
        return f"https://example.test/kvs/{key}"


class _FakeChargingManager:
    def calculate_max_event_charge_count_within_limit(self, event):
        return None


@pytest.fixture(autouse=True)
def _reset_delivery():
    m._DELIVERY.collect = None
    m._DELIVERY.charges = {}
    yield
    m._DELIVERY.collect = None
    m._DELIVERY.charges = {}


def test_charge_helper_accumulates_in_server_mode():
    async def go():
        m._DELIVERY.collect = []
        await m._charge(m.EVENT, 2)
        await m._charge(m.EVENT, 3)
        return dict(m._DELIVERY.charges)

    assert asyncio.run(go()) == {m.EVENT: 5}


def test_server_handle_rejects_non_json():
    async def go():
        resp = await m._server_handle(_FakeRequest(None, raw=b"not json"))
        return resp.status

    assert asyncio.run(go()) == 400


def test_server_handle_charges_once_after_response(monkeypatch):
    charged = []

    async def fake_run(inp, server_mode=False):
        await m._charge(m.EVENT, 4)
        return {"stats": {"ok": 1}}

    async def fake_charge(**kwargs):
        charged.append(kwargs)

    monkeypatch.setattr(m, "_run", fake_run)
    monkeypatch.setattr(m.Actor, "charge", fake_charge)

    async def go():
        req = _FakeRequest({"scripts": [{"text": "hi"}]},
                           headers={"x-actor-request-id": "req-123"})
        resp = await m._server_handle(req)
        return resp.status, json.loads(resp.text)

    status, body = asyncio.run(go())
    assert status == 200
    assert body["summary"]["mode"] == "server"
    assert charged == [{"event_name": m.EVENT, "count": 4, "request_id": "req-123"}]


def test_run_mixed_batch_ok_and_error_rows(monkeypatch):
    async def fake_open_kvs():
        return _FakeKVS()

    def fake_synth(text, voice):
        return np.zeros(m.E.SAMPLE_RATE, dtype=np.float32), 1

    monkeypatch.setattr(m, "SERVER_MAX_SCRIPTS", 10)
    monkeypatch.setattr(m.Actor, "open_key_value_store", fake_open_kvs)
    monkeypatch.setattr(m.Actor, "get_charging_manager",
                        lambda: _FakeChargingManager())
    monkeypatch.setattr(m.E, "synthesize", fake_synth)

    payload = {
        "scripts": [
            {"title": "Good", "text": "Narrate me please."},
            {"title": "Empty", "text": "   "},
            {"title": "Bad voice", "text": "Hello.", "voice": "Nobody"},
            {"title": "Long", "text": "x " * 600},  # 1200 chars -> 2 units
        ],
        "voice": "Harper",
        "outputFormat": "wav",
    }

    async def go():
        m._DELIVERY.collect = []
        summary = await m._run(payload, server_mode=True)
        return summary, list(m._DELIVERY.collect), dict(m._DELIVERY.charges)

    summary, rows, charges = asyncio.run(go())
    assert [r["status"] for r in rows] == ["OK", "ERROR", "ERROR", "OK"]
    assert rows[0]["charactersBilled"] == 1
    assert rows[1]["charactersBilled"] == 0
    assert rows[3]["charactersBilled"] == 2
    assert rows[0]["audioUrl"].endswith(".wav")
    assert charges == {m.EVENT: 3}
    assert summary["stats"]["ok"] == 2
    assert summary["stats"]["error"] == 2
