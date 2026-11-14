"""Create German WAV speech locally; optionally play it on this computer."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

BASE_DIR = Path(os.environ.get('GPT_GADGETS_DATA_DIR', str(Path(__file__).resolve().parent / 'out.user.local'))).expanduser().resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--text')
    source.add_argument('--file', type=Path, help='UTF-8 .txt or .md file')
    source.add_argument('--stdin', action='store_true')
    parser.add_argument('--user', default='local')
    parser.add_argument('--name', help='ASCII output basename without extension')
    parser.add_argument('--model', type=Path, help='Optional local Piper ONNX model')
    parser.add_argument('--piper', type=Path, default=Path.home() / 'tools/piper/install/piper')
    parser.add_argument('--play', action='store_true')
    parser.add_argument('--language', choices=('de', 'en'), default='de')
    parser.add_argument('--speed', type=int, choices=range(100, 241), default=155)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', args.user):
            raise ValueError('Invalid user identifier')
        if args.name and not re.fullmatch(r'[a-zA-Z0-9_-]+', args.name):
            raise ValueError('Output name must use ASCII letters, digits, underscores or hyphens')
        if args.file and args.file.suffix.lower() not in {'.txt', '.md'}:
            raise ValueError('Unsupported format; provide UTF-8 .txt or .md, or extract text first')
        text = args.file.read_text(encoding='utf-8') if args.file else (
            sys.stdin.buffer.read().decode('utf-8') if args.stdin else args.text
        )
        if not text.strip():
            raise ValueError('Input text is empty')
        player = (shutil.which('paplay') or shutil.which('aplay')) if args.play else None
        if args.play and not player:
            raise ValueError('Playback requires paplay or aplay')
        if args.model:
            if not args.piper.is_file() or not os.access(args.piper, os.X_OK):
                raise ValueError(f'Piper executable unavailable: {args.piper}')
            config = json.loads(Path(str(args.model) + '.json').read_text(encoding='utf-8'))
            if not isinstance(config, dict) or not args.model.is_file():
                raise ValueError('Invalid Piper model or configuration')
            command = [str(args.piper), '--model', str(args.model), '--output_file']
        else:
            engine = shutil.which('espeak-ng') or shutil.which('espeak')
            if not engine:
                raise ValueError('No local speech engine available; install eSpeak or supply a Piper model')
            command = [engine, '-v', args.language, '-s', str(args.speed), '--stdin', '-w']
        output_dir = BASE_DIR / 'audio' / args.user
        output_dir.mkdir(parents=True, exist_ok=True)
        name = args.name or datetime.now().strftime('speech_%Y%m%d_%H%M%S_%f')
        output = output_dir / f'{name}.wav'
        with tempfile.TemporaryDirectory(prefix='tts_', dir=output_dir) as temporary:
            wav_path = Path(temporary) / 'speech.wav'
            result = subprocess.run(command + [str(wav_path)], input=text.encode('utf-8'), capture_output=True, timeout=600)
            if result.returncode:
                raise ValueError('Speech synthesis failed: ' + result.stderr.decode('utf-8', errors='replace')[-1500:])
            with wave.open(str(wav_path), 'rb') as audio:
                if not audio.getnframes():
                    raise ValueError('Speech engine produced an empty WAV')
                duration = audio.getnframes() / audio.getframerate()
            # Refuse to overwrite an existing user output, including concurrent runs.
            os.link(wav_path, output)
        print(f'WAV: {output}\nDuration: {duration:.1f} seconds', flush=True)
        if player:
            subprocess.run([player, str(output)], check=True)
        return 0
    except (OSError, ValueError, EOFError, wave.Error, subprocess.SubprocessError) as error:
        print(f'TTS error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
