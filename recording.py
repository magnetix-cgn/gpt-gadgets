"""Normalize browser recordings and transcribe with the existing local Whisper skill."""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
import wave



def transcribe(source, language, output):
    if language not in ('de', 'en'):
        raise ValueError('Only German and English are supported')
    model_path = Path.home() / '.cache/whisper/base.pt'
    if not model_path.is_file():
        raise ValueError('Local Whisper base model is missing; no automatic download is performed')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'json', str(source)], capture_output=True, text=True, timeout=20)
    if probe.returncode:
        raise ValueError('Invalid or unsupported audio recording')
    duration = json.loads(probe.stdout).get('format', {}).get('duration')
    if duration is not None and (not math.isfinite(float(duration)) or float(duration) > 65):
        raise ValueError('Recording exceeds the 60-second limit')
    wav_path = output.with_suffix('.wav')
    conversion = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
                                '-t', '65', '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le',
                                str(wav_path)], capture_output=True, text=True, timeout=30)
    if conversion.returncode:
        raise ValueError('Recording could not be converted to WAV')
    with wave.open(str(wav_path), 'rb') as wav:
        samples = array('h', wav.readframes(wav.getnframes()))
    if not samples or math.sqrt(sum(s*s for s in samples)/len(samples)) < 80:
        raise ValueError('The recording is silent or too quiet; check the microphone')
    import whisper
    model = whisper.load_model(str(model_path), device='cpu')
    result = model.transcribe(str(wav_path), language=language, fp16=False)
    text = str(result.get('text', '')).strip()
    if not text:
        raise ValueError('No speech recognized')
    output.write_text(text + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--language', choices=('de', 'en'), default='de')
    args = parser.parse_args()
    try:
        transcribe(args.input, args.language, args.output)
    except Exception as error:
        print(f'Transcription failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
