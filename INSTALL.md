# Installation

## Requirements

Tested on Debian Linux with a graphical desktop audio session, Chromium and
Python 3.13. The server and speakers run on the same computer. Microphone
recording requires a browser secure context; loopback HTTP is supported by
Chromium. A plain LAN IP over HTTP is not equivalent and may block recording.

## 1. System packages

Install the packages through your normal administration process. If root access
is required, run the following as root:

```sh
# execute as root
apt-get install git espeak ffmpeg pulseaudio-utils alsa-utils chromium
```

A working PipeWire/PulseAudio desktop session is required for local playback.
Do not run the application as root.

## 2. Get the application

```sh
git clone https://github.com/magnetix-cgn/gpt-gadgets.git
cd gpt-gadgets
```

Inside XvX, keep this checkout under `externals/gpt-gadgets/` and use the existing
`xvx-venv/bin/python`. Do not create a second XvX virtual environment.

On a separate installation, use an existing suitable environment or create one:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The commands below use `.venv/bin/python` as an example. Substitute your existing
interpreter, such as the absolute path to XvX's `xvx-venv/bin/python`, as needed.
Whisper installs PyTorch and other dependencies; plan disk space accordingly.

## 3. Install the local recognition model once

If `~/.cache/whisper/base.pt` already exists, skip this step. Otherwise, download
the base model once using Whisper's explicit setup command:

```sh
.venv/bin/python -c 'import whisper; whisper.load_model("base", device="cpu")'
```

This setup command uses the network. Recording and recognition afterwards use
the local model file. The application refuses transcription if that model is
missing rather than silently downloading it. Never add model files to Git.

## 4. Start the local server

Select the local JSONL transcript of the Codex chat whose assistant replies
should be read. Codex stores these under its local `sessions` directory.

```sh
.venv/bin/python app.py --session-file /absolute/path/to/chat.jsonl
```

Alternatively, launch from a Codex task with `CODEX_THREAD_ID` set:

```sh
.venv/bin/python app.py
```

The automatic selector uses `CODEX_HOME/sessions`, or `~/.codex/sessions` by
default. Only one chat is watched per process. Do not run duplicate processes
for the same chat. Use `--port` to select another local port if necessary.

Open <http://127.0.0.1:8766/> in Chromium. Leave the server terminal running.
Stop it with Ctrl+C. Start it again with the same command when needed; existing
settings are preserved. No system service or reboot autostart is installed.

## 5. Use speech output

1. Set **Lokale Sprachausgabe** to **Ein**.
2. Select **Deutsch** or **English**, and choose a comfortable speaking speed.
3. Click **Stimme testen**. New chat responses should now be read automatically.
4. Use **Wiedergabe stoppen** to clear the current output and pending speech,
   or switch **Aus** to disable further speech.

The voice language is explicit; it does not translate the text.

## 6. Use the microphone

1. Choose the recording language, **Deutsch** or **English**.
2. Click **Aufnahme starten** and allow the browser to use the microphone.
3. The device list becomes available after permission is granted. Select another
   microphone before the next recording if necessary.
4. Speak, then click **Stoppen & transkribieren**. Recording also stops after
   60 seconds. The first transcription may take longer while the model loads.
5. Review the editable transcript and click **Text kopieren**.
6. Paste the text into the intended chat and send it.

There is no automatic sending to Codex. CPU recognition can take several
seconds. Recognition can make mistakes; review names and important details.
Audio and text remain in the configured local output directory.

## Troubleshooting

- **No sound:** check the desktop output device and app volume, then use the
  voice test. The process needs access to your user audio session. A sandbox
  or remote shell may not have that access. Successful WAV generation alone
  does not prove audible playback.
- **Replies remain silent:** check that the right chat file was selected and
  speech is enabled. The dashboard shows the last message and playback errors.
- **Microphone permission denied:** allow it for the loopback site in Chromium's
  site settings. The built-in cloud voice mode is not required.
- **No transcript:** verify ffmpeg and the local Whisper model are installed.
  Silent or very quiet recordings are rejected. Uploads must be WebM, Ogg or
  MP4 audio and no larger than 12 MB.
- **Server unavailable:** restart the command in step 4 and check its terminal.
- **Privacy:** do not commit runtime output, recordings, local configuration,
  environment files or credentials. The supplied `.gitignore` excludes them.
