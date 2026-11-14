# GPT Gadgets

A small local dashboard for spoken Codex chat replies and microphone dictation.
Speech synthesis and speech recognition run on your own computer. No cloud
speech API or API key is required. The language model that writes chat replies
is separate and may still consume cloud usage.

## Features

- Automatically read new visible assistant replies and progress messages from
  one selected local Codex chat. Old messages are not replayed on startup.
- Enable or disable local speech, stop playback, and test the voice.
- Select **German (DE)** or **English (EN)** independently for speech output and
  microphone recognition. Selections and speaking speed are saved locally.
- Record up to 60 seconds in the browser, preview the recording, and transcribe
  it locally with Whisper. Speech output pauses while recording.
- Edit recognized text and click **An Chat senden** to queue it for the
  connected Codex chat, or copy it manually. Nothing is sent without a click.

The default voice is eSpeak, which sounds synthetic. A valid local Piper model
can be used through the speech command-line helper. The dashboard currently
controls eSpeak.

## Quick start

See [INSTALL.md](INSTALL.md) for system packages, Python dependencies, the
one-time Whisper model setup, and troubleshooting.

Run with an existing Python environment that has the required dependencies:

```sh
/path/to/existing/python app.py --session-file /absolute/path/to/chat.jsonl
```

When launched by Codex with `CODEX_THREAD_ID` set, the app can select that chat
automatically:

```sh
/path/to/existing/python app.py
```

Open **<http://127.0.0.1:8766/>** in Chromium. Speech is enabled by default.
The microphone activates only after clicking **Aufnahme starten** and granting
browser permission. Choose German or English before recording.

## How it works

The app watches one local Codex JSONL transcript and speaks new visible
assistant messages through eSpeak and the desktop audio session. It ignores
user messages, tool output and internal reasoning. It supports the observed
`commentary`, `final`, and `final_answer` response phases. This is a companion
process, not a modification of the built-in Codex voice engine. The transcript
format is an integration detail that may change in future Codex versions.

Browser audio is posted only to this loopback server, normalized with ffmpeg,
and transcribed with an already downloaded Whisper base model on the CPU.
There are no model downloads during transcription. DE and EN are explicit
choices; other languages and automatic language detection are not offered.

## Send dictation to the chat

The **An Chat senden** button uses the installed local Codex CLI's
`queue --thread ... --message ... --resume` command. Its destination comes only
from the selected transcript's session metadata, never from browser input.
The button requires non-empty text and an available CLI. A successful result
means Codex accepted the message into its queue; it does not mean an answer
has already been generated. The original editable text is retained.

Set `GPT_GADGETS_CODEX_CLI` to an absolute Codex executable path if needed.
Otherwise the app uses `CODEX_APP_RUNTIME_CLI_PATH` or finds `codex` on PATH.
The CLI must support `codex queue`. A failed resume can leave an accepted
message waiting for the chat to resume in Codex. Requests are deduplicated by
identifier within the running server process; there is no automatic retry.

## Local data and configuration

By default, settings, recordings and transcripts live in `out.user.local/`;
generated speech is under `out.user.local/audio/local/`. These files are ignored
by Git. Recordings are kept until you remove them. No transcript history or
credentials are bundled in this repository.

Set `GPT_GADGETS_DATA_DIR` to an absolute directory to keep runtime data elsewhere.
The local `settings.json` contains:

```json
{
  "enabled": true,
  "language": "de",
  "input_language": "de",
  "speed": 155
}
```

Both language fields accept only `de` or `en`. Speed is 100–240 words per minute.
The dashboard saves changes immediately. The server reads configuration at
startup; use the dashboard while it is running.

The server binds only to loopback, checks request host and origin, and limits
recording uploads to supported audio formats and 12 MB. It has no remote login
system. Do not expose it through a public proxy or change its binding without
adding appropriate access controls. The page can be closed while speech runs.
The process must remain running; reboot autostart is not installed automatically.

## Development

```sh
/path/to/existing/python test_app.py
```

`app.py` uses the Python standard library. `recording.py` needs Whisper and
ffmpeg; `speech.py` invokes local eSpeak/Piper and paplay/aplay executables.
The dashboard has no external JavaScript, font, or CDN dependencies.

## Branding

The dashboard uses the Eventhacker logo supplied through the project owner's
[Eventhacker profile](https://profil.eventhacker.de/). The shipped asset is a
lossless WebP derivative with transparency; private media-source configuration
is not included in this repository.
