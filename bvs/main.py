"""Batch Voiceover Studio: a list of scripts -> downloadable MP3/WAV
voiceovers (Phonon 31M, Gradium, Apache-2.0), one dataset row per
script, charged per 1,000 characters of successful scripts only.
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import re
import subprocess
import tempfile
import time
import wave
from datetime import datetime, timezone
from typing import Any

import numpy as np
from aiohttp import web
from apify import Actor

from . import engine as E
from .drift import compute_fingerprint, find_breaches, load_expected_shape, report_drift
from .reporter import actor_build_label, report_failure

ACTOR_NAME = "batch-voiceover-studio"
EVENT = "chars-1000"
MAX_CHARS_PER_SCRIPT = 100_000
MAX_SCRIPTS_PER_RUN = 500


class ItemError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def billed_units(characters: int) -> int:
    """Pay-per-event units for one successful script: $0.01 per
    1,000 characters, rounded up, minimum 1."""
    return max(1, math.ceil(characters / 1000))


def safe_key(i: int, title: str | None, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.\-]+", "-", (title or "script").strip()).strip("-.")[:60]
    return f"{i + 1:03d}-{base or 'script'}.{ext}"


def empty_row(index: int) -> dict:
    return {
        "index": index,
        "title": None,
        "status": "ERROR",
        "error": None,
        "voice": None,
        "characters": 0,
        "charactersBilled": 0,
        "chunks": 0,
        "audioSeconds": None,
        "format": None,
        "audioUrl": None,
        "processingSecs": None,
        "generatedAt": None,
    }


def write_wav(samples: np.ndarray, path: str) -> None:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(E.SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def encode_mp3(wav_path: str, mp3_path: str) -> None:
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "4", mp3_path],
        capture_output=True, text=True, timeout=600,
    )
    if p.returncode != 0 or not os.path.exists(mp3_path):
        raise ItemError(f"MP3 encoding failed: {(p.stderr or '').strip()[-200:]}")


def probe_seconds(path: str) -> float | None:
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60,
        )
        return float(p.stdout.strip())
    except Exception:
        return None


class _Delivery:
    """Where finished rows go, and what they cost. Batch mode: the
    default dataset, charged per item as rows are pushed. Server
    mode: an in-memory list the HTTP handler returns in the
    response; charges accumulate here and are billed once, after
    the response is built."""

    def __init__(self) -> None:
        self.collect: list[dict] | None = None
        self.charges: dict[str, int] = {}


_DELIVERY = _Delivery()


async def _emit_row(row: dict) -> None:
    if _DELIVERY.collect is not None:
        _DELIVERY.collect.append(row)
    else:
        await Actor.push_data(row)


async def _charge(event: str, count: int):
    """Charge an event now (batch) or accumulate it (server).
    Returns the charge result in batch mode, None in server mode."""
    if _DELIVERY.collect is not None:
        _DELIVERY.charges[event] = _DELIVERY.charges.get(event, 0) + count
        return None
    return await Actor.charge(event, count=count)


# ------------------------------------------------------------------
# Server mode (Apify Standby / "Server Actors").
#
# When the platform starts the actor as a server, the same batch
# answers single HTTP requests: POST a JSON body with the usual
# input fields (scripts, voice, outputFormat) and get
# {"records": [...], "summary": {...}} back — no run to start, no
# dataset to poll. Rows carry the same public audioUrl download
# links as batch runs. One request narrates at most
# SERVER_MAX_SCRIPTS scripts. Charges match batch runs exactly —
# 'chars-1000' per billed 1,000 characters — billed once per
# request to the caller's own Apify account, after the response
# is built. Requests are serialized per container.
# ------------------------------------------------------------------

SERVER_MAX_SCRIPTS = 3
SERVER_REQUEST_TIMEOUT_S = 240.0
_SERVER_LOCK = asyncio.Lock()


def _is_standby() -> bool:
    meta = str(getattr(Actor.configuration, "meta_origin", "") or "")
    return "STANDBY" in meta.upper()


async def _server_handle(request):  # noqa: ANN001 - aiohttp request
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - any bad body is a 400
        return web.json_response(
            {"error": "request body must be a JSON object"}, status=400
        )
    if not isinstance(payload, dict):
        return web.json_response(
            {"error": "request body must be a JSON object"}, status=400
        )

    collected: list[dict] = []
    summary: dict | None = None
    failure: Exception | None = None
    timed_out = False
    async with _SERVER_LOCK:
        _DELIVERY.collect = collected
        _DELIVERY.charges = {}
        try:
            summary = await asyncio.wait_for(
                _run(payload, server_mode=True),
                timeout=SERVER_REQUEST_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            timed_out = True
        except Exception as exc:  # noqa: BLE001 - reported in the body
            failure = exc
        finally:
            charges = dict(_DELIVERY.charges)
            _DELIVERY.collect = None

    # Charge once per event, after the work, for exactly what is
    # being returned. Multi-tenant attribution needs the request's
    # X-Actor-Request-ID header passed through.
    charge_kwargs: dict = {}
    request_id = request.headers.get("x-actor-request-id")
    if request_id:
        charge_kwargs["request_id"] = request_id
    for event, count in charges.items():
        if count:
            await Actor.charge(event_name=event, count=count, **charge_kwargs)

    if failure is not None:
        return web.json_response(
            {
                "error": f"{type(failure).__name__}: {failure}",
                "records": collected,
                "chargedEvents": charges,
            },
            status=500,
        )
    if summary is None:  # timed out mid-batch: partial answer
        summary = {"items": len(collected)}
    summary = {**summary, "mode": "server", "timedOut": timed_out}
    return web.json_response({"records": collected, "summary": summary})


async def _server_root(request):  # noqa: ANN001 - aiohttp request
    return web.json_response({
        "service": "magnova/batch-voiceover-studio",
        "mode": "server",
        "usage": (
            "POST a JSON body with the usual input fields (same as "
            "the actor input) and get voiceover records back in the "
            "response. $0.01 per 1,000 characters of successful "
            "scripts."
        ),
    })


@web.middleware
async def _readiness_middleware(request, handler):  # noqa: ANN001, ANN202
    if "x-apify-container-server-readiness-probe" in request.headers:
        return web.Response(text="ok")
    return await handler(request)


async def _serve() -> None:
    app = web.Application(middlewares=[_readiness_middleware])
    app.router.add_post("/", _server_handle)
    app.router.add_get("/", _server_root)
    runner = web.AppRunner(app)
    await runner.setup()
    port = Actor.configuration.web_server_port
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    Actor.log.info("Server mode: listening on port %s", port)
    await asyncio.Event().wait()


async def main() -> None:
    async with Actor:
        if _is_standby():
            await _serve()
            return
        try:
            await _run()
        except Exception as exc:  # noqa: BLE001 - self-report, then fail
            await report_failure(
                actor_name=ACTOR_NAME, build=actor_build_label(),
                run_status="FAILED", error_class=type(exc).__name__,
                message=str(exc), counts={},
            )
            raise


async def evaluate_drift(records: list[dict]) -> None:
    """Fingerprint delivered OK records against the claims table
    and report any silent shape drift. Fail-silent by design."""
    try:
        shape = load_expected_shape()
        fingerprint = compute_fingerprint(records, shape, "standard")
        breaches = find_breaches(fingerprint, shape, "standard")
        if breaches:
            await report_drift(
                actor_name=ACTOR_NAME, build=actor_build_label(),
                breaches=breaches,
            )
    except Exception:  # noqa: BLE001 - telemetry never breaks a run
        pass


def _deadline() -> float | None:
    timeout_at = os.environ.get("ACTOR_TIMEOUT_AT") or os.environ.get("APIFY_TIMEOUT_AT")
    if not timeout_at:
        return None
    try:
        return datetime.fromisoformat(timeout_at.replace("Z", "+00:00")).timestamp() - 60
    except ValueError:
        return None


async def _run(inp: dict[str, Any] | None = None,
               server_mode: bool = False) -> dict[str, Any]:
    if inp is None:
        inp = await Actor.get_input() or {}

    raw_scripts = inp.get("scripts")
    global_voice = inp.get("voice") or E.DEFAULT_VOICE
    out_format = str(inp.get("outputFormat") or "mp3").lower()
    if out_format not in ("mp3", "wav"):
        out_format = "mp3"

    if not isinstance(raw_scripts, list) or not raw_scripts:
        msg = 'No input: add at least one script to "scripts" (each item needs a "text").'
        Actor.log.error(msg)
        if not server_mode:
            await Actor.set_status_message(msg)
            await Actor.set_value("SUMMARY", {"error": msg})
        return {"error": msg}

    scripts = raw_scripts[:SERVER_MAX_SCRIPTS] if server_mode else raw_scripts[:MAX_SCRIPTS_PER_RUN]
    deadline = _deadline()

    def keep_going() -> bool:
        return deadline is None or time.time() < deadline

    cm = Actor.get_charging_manager()

    def units_budget() -> int:
        try:
            n = cm.calculate_max_event_charge_count_within_limit(EVENT)
            return 10**9 if n is None else int(n)
        except Exception:
            return 10**9

    kvs = await Actor.open_key_value_store()  # the run's default store (never a named one)
    tmp = tempfile.mkdtemp(prefix="bvs-")
    stats = {"ok": 0, "error": 0, "units": 0, "characters": 0}
    per_item: list[dict] = []
    ok_records: list[dict] = []
    stop = False

    for i, item in enumerate(scripts):
        row = empty_row(i)
        t0 = time.time()
        charged = 0
        try:
            if stop:
                raise ItemError("Skipped: your maximum charge for this run was reached.")
            if not keep_going():
                raise ItemError("Skipped: run timeout reached before this script. "
                                "Increase the run timeout or split the batch.")
            if not isinstance(item, dict):
                raise ItemError('Script item must be an object with a "text" field.')
            _title = item.get("title")
            row["title"] = str(_title).strip()[:200] if _title else f"Script {i + 1}"
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ItemError('Script "text" is empty. Add the words to narrate.')
            if len(text) > MAX_CHARS_PER_SCRIPT:
                raise ItemError(
                    f"Script is {len(text):,} characters, above the "
                    f"{MAX_CHARS_PER_SCRIPT:,}-character limit per script. "
                    "Split it into several scripts. Not charged."
                )
            voice = item.get("voice") or global_voice
            if voice not in E.VOICES:
                raise ItemError(
                    f"Unknown voice {voice!r}. Use one of the voices listed in the input schema."
                )
            title = item.get("title")
            title = str(title).strip()[:200] if title else None
            row.update({
                "title": title or f"Script {i + 1}",
                "voice": voice,
                "characters": len(text),
                "format": out_format,
            })
            units = billed_units(len(text))
            if units_budget() < units:
                stop = True
                raise ItemError("Skipped: your maximum charge for this run was reached.")

            samples, n_chunks = await asyncio.to_thread(E.synthesize, text, voice)
            row["chunks"] = n_chunks
            wav_path = os.path.join(tmp, f"{i}.wav")
            write_wav(samples, wav_path)
            if out_format == "mp3":
                out_path = os.path.join(tmp, f"{i}.mp3")
                await asyncio.to_thread(encode_mp3, wav_path, out_path)
                content_type = "audio/mpeg"
            else:
                out_path = wav_path
                content_type = "audio/wav"
            seconds = probe_seconds(out_path)
            row["audioSeconds"] = round(seconds, 2) if seconds else round(len(samples) / E.SAMPLE_RATE, 2)
            key = safe_key(i, row["title"], out_format)
            with open(out_path, "rb") as f:
                await kvs.set_value(key, f.read(), content_type=content_type)
            row["audioUrl"] = await kvs.get_public_url(key)
            row["status"] = "OK"
            charged = units
        except ItemError as e:
            row["error"] = str(e)
        except Exception as e:  # noqa: BLE001 - one bad item never aborts the batch
            row["error"] = f"Unexpected error: {type(e).__name__}: {str(e)[:300]}"
        row["processingSecs"] = round(time.time() - t0, 1)
        row["charactersBilled"] = charged
        row["generatedAt"] = now_iso()
        await _emit_row(row)
        if charged:
            res = await _charge(EVENT, charged)
            if res is not None and getattr(res, "event_charge_limit_reached", False):
                stop = True
        stats[row["status"].lower()] = stats.get(row["status"].lower(), 0) + 1
        stats["units"] += charged
        stats["characters"] += row["characters"] if row["status"] == "OK" else 0
        if row["status"] == "OK":
            ok_records.append(row)
        per_item.append({
            "index": i, "title": row["title"], "status": row["status"],
            "voice": row["voice"], "characters": row["characters"],
            "charactersBilled": charged, "audioUrl": row["audioUrl"],
            "error": row["error"],
        })
        Actor.log.info("[%d/%d] %s: %s, %d chars, %d unit(s), voice=%s",
                       i + 1, len(scripts), (row["title"] or "")[:60],
                       row["status"], row["characters"], charged, row["voice"])

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    summary = {"stats": stats, "items": per_item, "finishedAt": now_iso()}
    if not server_mode:
        await Actor.set_value("SUMMARY", summary)
        msg = (f"Narrated {stats['ok']} script(s), {stats['units']} billed unit(s) "
               f"({stats['characters']:,} characters); {stats['error']} error(s).")
        await Actor.set_status_message(msg)
        Actor.log.info(msg)
        if stats["ok"] == 0 and stats["error"] > 0:
            # Every script errored: the run still succeeds (callers
            # may have sent impossible input) but self-report — a
            # genuine engine outage looks exactly like this.
            await report_failure(
                actor_name=ACTOR_NAME, build=actor_build_label(),
                run_status="SUCCEEDED", error_class="AllItemsErrored",
                message="run delivered nothing; every script errored",
                counts={"itemsDelivered": 0, "itemsErrored": stats["error"]},
            )
        if ok_records:
            await evaluate_drift(ok_records)
    return summary
