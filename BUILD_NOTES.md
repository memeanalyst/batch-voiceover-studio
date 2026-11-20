# Batch Voiceover Studio — build notes

**Actor:** magnova/batch-voiceover-studio — https://apify.com/magnova/batch-voiceover-studio
**Actor ID:** azKvwsv0BZLLmcACa
**Repo:** https://github.com/memeanalyst/batch-voiceover-studio
**Launched:** 2026-11-21 (private staging → gates → publish, same night)
**Final build at publish:** uZJZb7dupcNpZZdTJ

## What it is

Batch text-to-speech: input is an array of scripts ({title?, text, voice?})
plus a global voice and outputFormat (mp3/wav). One dataset row per script
with a public KV `audioUrl`. Engine: Gradium **Phonon 31M**
(gradium/phonon-31m-en @92741c5b, q8 GGUF, Apache-2.0) via the `ptts`
0.7.1 runtime, CPU-only, 24 kHz. Model + the English voices of the pinned
phonon-voices catalog (@da6c9ec0) are **baked into the Docker image** by
fetch_assets.py (classic HF resolve path; Xet rate-limits unauthenticated
IPs) — runs never download anything. Long scripts are split into
≤600-char sentence chunks and stitched with 0.3 s gaps (prosody-reset
mitigation). Server mode (standby) mirrors the fleet pattern: ≤3 scripts
per request, charges billed once per request with X-Actor-Request-ID
passthrough. Failure self-reporting (reporter.py) + drift telemetry
(drift.py, expected_shape.json over delivered OK records) ship from day
one, dormant unless MAGNOVA_ALERTS_TOKEN is set.

## Pricing (verified on the live record after publish)

Event `chars-1000`, pay-per-event, **no start fee**: BRONZE/FREE $0.01,
SILVER $0.0085, GOLD/PLATINUM/DIAMOND $0.007 per 1,000 characters.
Bill = ceil(chars/1000) per successful script, min 1; failed scripts $0.

## Staging evidence (all runs on the private staging actor)

| Run | Gate | Result |
|---|---|---|
| iRgfcJj2qdKudJvnL | (a) example input (schema prefill, 2 scripts) | 2 OK rows (Harper 107 chars → 7.82 s; Easton override 182 chars → 10.13 s), charged 2 |
| 4u8KTfetPTcVg015O | (b) 3 scripts, global Maeve + Zoey/Miles overrides, WAV | 3 OK rows, voices exactly as resolved, charged 3 |
| 1iWY4Qp8Ko9RJqcc7 | (c) long script, pre-fix build (1,420 chars) | OK, 3 chunks, 81.46 s audio, charged 2 — but 318.5 s processing (0.26x realtime): see speed fix below |
| dVjJvfDj9w8myKcOv | (c) long script >2,000 chars, fixed build (2,412 chars) | OK, 5 chunks, one MP3 of 139.9 s, 85.4 s processing (1.64x realtime), charged 3 |
| 1TDe9g5UmktsHj0xq | (d) batch with one empty-text item | Batch completes: 2 OK + 1 ERROR row ("Script text is empty…"), empty item charged 0, total charged 2 |
| DyDVxyrj90ekR1BSH | Voice verification: all 37 schema voices, one short script each | **37/37 OK**, charged 37 |
| 1rLZsZgQN5o6v5vBO | Regression on the final (publish) build, example input | 2 OK rows, charged 2 |

**Charge audit (gate 2):** after a settle delay, every run's
chargedEventCounts was re-read: expected Σ ceil(chars/1000) over
successful scripts = **51 units; charged = 51 units. Exact.**

**Audio verification (gate 3):** MP3s downloaded from their public KV
URLs and probed with ffprobe — run (a) file: valid MP3, 7.76 s vs the
record's 7.82 s; long-chapter file: valid MP3, 139.84 s vs 139.9 s
recorded. Consistent.

**Drift census:** the 37-record voice run doubles as the claims census —
every delivered OK record populated title, voice, audioUrl, format,
audioSeconds and charactersBilled at 100%, matching expected_shape.json.

## Speed fix found in staging (deviation worth knowing)

The first staging build synthesized long scripts at 0.26x realtime in a
1 GB container (318 s for 81 s of audio) while short scripts burst at
~4x. Cause: Apify CPU quota scales with memory (1 GB ≈ 0.25 vCPU) and
the uncapped ptts thread pool oversubscribed it. Fix, both halves
evidence-based: (1) engine caps ptts threads at 4 (PHONON_THREADS env
override); (2) default run memory raised to **4096 MB** (standby
2048 MB). After the fix: 1.64x realtime sustained on a 2,412-char
script. Local unit tests: 9 passed (chunking, billing units, server
handler contract, mixed OK/ERROR batch).

## Verified voices (37 — the full schema enum, all synthesized OK on platform)

Zoey, Juniper, Everly, Harper, Hadley, Delia, Easton, Micah, Trevor,
Russell, Preston, Miles, Maeve, Freya, Pippa, Elodie-Rose, Imogen,
Lottie, Alfie, Hugh, Edwin, Spencer, Toby, Teddy, Bryony,
Captain Silas Blackwater, Morwenna of the Deep, Old Mortlake, Azgorath,
Fennick the Young Elf, The Thing Under the Stairs, Vyrmathrax the
Ancient, Grub the Ogre, Master Aldric, The Snow Queen, Sir Bramwell,
Fairy Godmother.

## Publish read-back (gate 4)

isPublic true; categories [AI, VIDEOS, FOR_CREATORS]; pricing tiers as
above; defaultRunOptions 4096 MB / 3600 s; actorPermissionLevel
LIMITED_PERMISSIONS; actorStandby enabled, tenancy SINGLE_TENANT;
**notice: NONE**. Store search shows the listing live.

## Icons

Four options generated into icons/ (media-generation-*):
- **A — violet microphone + waveform bars (LAUNCH PICK)** —
  icons/icon-a-launch.png (512×512 PNG) is ready to upload.
- B — teal waveform-play mark (clean, generic).
- C — coral microphone in a speech bubble (friendly alternate).
- D — stacked waveform layers (mic too small; weakest).

**Deviation:** the icon is NOT yet on the actor. The public Apify API
has no icon/picture endpoint (verified against the official OpenAPI
spec — pictureUrl is read-only), so, as with the HDB/Hotel launches,
the upload is a one-click Console step: Actor → Settings → upload
icons/icon-a-launch.png. Everything else about the launch is done.

## Other deviations from the original sketch

- Actor version is 0.0 (the API auto-creates 0.0 on actor creation;
  the fleet's newer actors use the same).
- Title shortened to "Batch Voiceover Studio — Text to Speech, Scripts
  to MP3" (platform caps titles at 63 chars); SEO title likewise ≤60.
- The LICENSE file is not fetched at the pinned model revision (it was
  added to the HF repo later and 404s there); the Apache-2.0 license is
  documented in the README instead. No runtime impact.

## Follow-ups (not built in this task, per brief)

- MCP wrapper: queued as **Batch 13** in
  goals/apify-actor-revenue/hidden_files/mcp-batch-procedure.md.
- Postman collection refresh to include this actor.
- ClawHub skill submission.
- Make template (one scenario: Sheets/Drive scripts → actor → Drive
  MP3s) and n8n template — the Audio to MIDI template pattern applies
  directly; a Rogue LLM video on the one-month-old model is the
  natural launch content.
- Icon upload via Console (above).
