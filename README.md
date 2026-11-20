## What does Batch Voiceover Studio do?

**Batch Voiceover Studio turns a list of scripts into finished voiceovers.** Give it an array of scripts and it returns, for every script, a downloadable **MP3 or WAV** narration file plus a dataset row with the voice used, the character count and the audio length. It runs Gradium's open [Phonon 31M](https://huggingface.co/gradium/phonon-31m-en) text-to-speech model (Apache-2.0) on CPU inside Apify, so there is no API key to get, no GPU and no per-minute cloud TTS bill: you pay **$0.01 per 1,000 characters** of scripts that succeed, and nothing for scripts that fail.

It is built for **automation**: faceless video channels narrating a week of scripts in one run, agencies producing ad variants, course and podcast pipelines, IVR and notification voice, and AI agents that need speech out of a text workflow. Pick from **37 English voices** — American and British narrators plus character voices — set one voice for the batch or override it per script.

Honest positioning: this is fast, keyless CPU narration for pipelines and creators. It is **not** a replacement for a studio voice actor on a flagship brand film, and it does not clone voices — every voice is a stock voice from the Phonon catalog.

## Why use Batch Voiceover Studio?

- **Content pipelines and faceless channels**: paste or generate 50 scripts, get 50 MP3s back in one run, each named and linked in its own row.
- **Agencies and marketers**: produce the same ad in several voices, or a week's worth of short-form narrations, for cents.
- **Developers**: add "scripts in, voiceovers out" to a product with one API call instead of running and hosting a TTS model yourself.
- **AI agents and LLM apps**: flat JSON in, flat JSON out — the row's `audioUrl` is a public link an agent can hand to a user or pass to the next tool.
- **No key, no quota math**: the model ships inside the Actor. Your only cost is the per-character price below.

## How to narrate a batch of scripts

1. Click **Try for free** and edit **Scripts to narrate**: an array of objects with a `text` (the words to speak), an optional `title`, and an optional per-script `voice`.
2. Pick the batch **Voice** and the **Output format** (MP3 or WAV).
3. Click **Start**. Each script becomes one row in the dataset with an `audioUrl` you can download or hot-link right away.
4. Download results as JSON, CSV or Excel, or call the Actor through the [Apify API](https://docs.apify.com/api/v2) from your own code.

Long scripts are handled for you: text is split into sentence chunks (about 600 characters each) before synthesis and stitched back into one continuous file, which keeps the narration natural on book-length input. One script is capped at 100,000 characters; a batch can hold up to 500 scripts.

## Input example

```json
{
  "scripts": [
    {"title": "Welcome message", "text": "Welcome to Batch Voiceover Studio. This sample was generated entirely on a CPU, with no API key and no GPU."},
    {"title": "Product teaser", "text": "Turn a list of scripts into finished voiceovers in one run. One flat rate per thousand characters, thirty-seven voices to choose from, and audio files you can download straight away.", "voice": "Easton"}
  ],
  "voice": "Harper",
  "outputFormat": "mp3"
}
```

Only `scripts` is required; each item needs only a `text`.

## Output example

One dataset item per input script:

```json
{
  "index": 0,
  "title": "Welcome message",
  "status": "OK",
  "error": null,
  "voice": "Harper",
  "characters": 107,
  "charactersBilled": 1,
  "chunks": 1,
  "audioSeconds": 7.82,
  "format": "mp3",
  "audioUrl": "https://api.apify.com/v2/key-value-stores/<storeId>/records/001-Welcome-message.mp3",
  "processingSecs": 1.6,
  "generatedAt": "2026-11-20T23:20:40Z"
}
```

| Field | What it is |
|---|---|
| `audioUrl` | Public download link of the finished voiceover (MP3 or WAV) |
| `status` | `OK` (narrated and charged) or `ERROR` (failed, never charged) |
| `error` | Why the script failed; null when fine |
| `voice` | The narrator voice used (per-script override or the batch voice) |
| `characters` | Characters in the script text |
| `charactersBilled` | Charged units: ceil(characters / 1000), minimum 1 per successful script |
| `chunks` | Sentence chunks the script was split into for synthesis |
| `audioSeconds` | Length of the finished audio file |
| `format` | `mp3` or `wav` |

The **audio files** live in the run's default key-value store (Storage tab, or the "Audio files" output link) and follow your account's data retention. A failed script (empty text, unknown voice, text over the per-script limit) still gets a row explaining the problem — and is never charged.

## Voices

All 37 English voices in the Phonon catalog, each verified working with this Actor:

| Voice | Character |
|---|---|
| Zoey | Playful, upbeat Gen Z energy, standard American accent. |
| Juniper | Cheerful with real resonance; personable on intimate copy, decisive on the final line. |
| Everly | Rounded, soft-edged tone with a gentle lift at the end of phrases; relaxed delivery. |
| Harper | Modern, confident and friendly, standard American accent. |
| Hadley | Settled, even-toned and genuinely kind, with crisp consonants. |
| Delia | Low, grounded and quick to the point; sincere. |
| Easton | Punchy and close in, crisp consonant attack that cuts through a music bed. |
| Micah | Buoyant, high energy, playful lift at the ends of phrases. |
| Trevor | Buoyant energy over a resonant mid-low core; phrases land softly. |
| Russell | High-energy American adult voice; pushes and encourages. |
| Preston | Trim, focused delivery, clean consonant edges, steady low-set core. |
| Miles | Resonant and decisive with genuine dynamic range. |
| Maeve | Sparky, attentive British English adult voice; gets to the point with a smile. |
| Freya | Young British voice, glossy and confident, bubbly sparkle. |
| Pippa | Confident, upbeat British English adult voice with infectious energy. |
| Elodie-Rose | Young British voice with sharp, enthusiastic energy and crisp articulation. |
| Imogen | Bubbly, friendly British English adult voice; puts listeners at ease. |
| Lottie | Sparky and to the point, high forward energy, clean consonant edges. |
| Alfie | Punchy and forward British voice, crisp attack, pitch lifts across a line. |
| Hugh | Soft and close British voice, airy texture, lively pitch movement. |
| Edwin | Efficient and firm British voice with tidy articulation. |
| Spencer | Light and airy British voice, crisp consonants, slow patient delivery. |
| Toby | Sparky, attentive British English adult voice; efficient and warm. |
| Teddy | Sparky and close in British voice, quick off the mark, firm consonants. |
| Bryony | Full, rich mid-range British tones, softly relaxed, spoken close to the mic. |
| Captain Silas Blackwater | Character voice: an old British pirate captain from the West Country, deep and gravelly. |
| Morwenna of the Deep | Character voice: a sultry woman in her thirties, low husky alto, close to the microphone. |
| Old Mortlake | Character voice: an elderly Victorian gravedigger, low, raspy and half whispered. |
| Azgorath | Character voice: an enormous ancient demon, cavernous impossibly deep bass. |
| Fennick the Young Elf | Character voice: a curious, kind-hearted elf boy of about ten, warm natural child's voice. |
| The Thing Under the Stairs | Character voice: a monstrous creature lurking in the dark, gravelly and breathy. |
| Vyrmathrax the Ancient | Character voice: an ancient dragon, very low and resonant with deep chest weight. |
| Grub the Ogre | Character voice: a big, good-natured ogre, gruff and grainy, rumbling low. |
| Master Aldric | Character voice: a wise old British wizard around eighty, rich and resonant with an aged grain. |
| The Snow Queen | Character voice: a regal, cold-hearted queen of ice, cool crystalline mezzo, poised. |
| Sir Bramwell | Character voice: a brave but pompous English knight, booming, plummy and theatrical. |
| Fairy Godmother | Character voice: a kind fairy godmother in her sixties, low warm velvety alto. |

## Use it as an API (Server Actor)

This actor also runs as a **server**: send one HTTP request and get the narration records back in the response — no run to start, no dataset to poll.

```
POST https://magnova--batch-voiceover-studio.apify.actor
Authorization: Bearer <your Apify API token>
Content-Type: application/json

{"scripts": [{"text": "Your script here."}], "voice": "Harper", "outputFormat": "mp3"}
```

The body takes the same fields as the normal input. The response is `{"records": [...], "summary": {...}}` — the same rows a normal run writes to the dataset, including the public `audioUrl` download link for each voiceover. One request narrates at most 3 scripts. Charges match normal runs exactly — $0.01 per 1,000 characters of successful scripts (tiered by your Apify plan), billed to your own Apify account.

## Use with AI agents / MCP

The Actor is built to be called zero-shot by AI agents through the [Apify MCP server](https://mcp.apify.com) or the API: one required field, a working example, and flat JSON output. Minimal call:

```json
{ "scripts": [{ "text": "Tonight, we look at three stories everyone missed." }] }
```

The agent gets back an `audioUrl` per script to hand to the user or feed into a video-assembly tool, plus `audioSeconds` for timing captions and edits.

## How much does it cost?

Pay per event, with no start fee and no monthly subscription:

| Event | BRONZE | SILVER | GOLD and above |
|---|---|---|---|
| `chars-1000` — 1,000 characters narrated (per successful script, rounded up, min 1 unit) | $0.01 | $0.0085 | $0.007 |

Worked examples: a 280-character short costs 1 unit ($0.01). A 4,200-character explainer script costs 5 units ($0.05). A batch of 20 scripts totalling 30,000 characters costs about $0.30. Failed scripts cost $0. (Apify platform usage for the run itself is billed by Apify as usual.)

## The model

Narration is synthesized by [Phonon 31M](https://huggingface.co/gradium/phonon-31m-en) from Gradium — a 31-million-parameter text-to-speech model built on Kyutai's Pocket TTS lineage, running the 8-bit quantized weights (about 65 MB) on CPU at 24 kHz. The model, tokenizer and voices are released under the **Apache-2.0** license, which permits commercial use; the model files are baked into the Actor, so runs work without any external TTS service. English only.

## Limits

- English scripts only (the model is an English checkpoint).
- One script: up to 100,000 characters. One batch run: up to 500 scripts (server requests: up to 3).
- Stock catalog voices only — no voice cloning, no custom voice uploads.
- Narration quality is strong for explainers, ads, shorts and pipeline voice; for a flagship brand read, hire the human.

⭐ Finding this useful? A rating on the Apify Store helps other users discover this Actor — thank you!
