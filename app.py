"""Local control panel and speech bridge for one Codex chat."""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import signal
import sys
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
OUTPUT = Path(os.environ.get('GPT_GADGETS_DATA_DIR', str(BASE / 'out.user.local'))).expanduser().resolve()
CONFIG = OUTPUT / 'settings.json'
TTS = BASE / 'speech.py'
PYTHON = Path(sys.executable)


def speech_text(row):
    if row.get('type') != 'response_item':
        return ''
    p = row.get('payload', {})
    if p.get('type') != 'message' or p.get('role') != 'assistant':
        return ''
    if p.get('phase') not in ('commentary', 'final', 'final_answer'):
        return ''
    text = '\n'.join(c.get('text', '') for c in p.get('content', []) if c.get('type') == 'output_text')
    text = re.sub(r'^\[(?:STATUS|COMPLETE)\]\s*', '', text)
    text = re.sub(r'^::[^\n]*\n?', '', text, flags=re.M)
    text = re.sub(r'```.*?```', ' Code ist im Chat sichtbar. ', text, flags=re.S)
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', ' Link im Chat ', text)
    return re.sub(r'[*#`_]', '', text).strip()


class Bridge:
    def __init__(self, session, config=CONFIG):
        self.session = session
        self.config = config
        self.lock = threading.RLock()
        self.queue = collections.deque()
        self.process = None
        self.last_text = ''
        self.error = ''
        self.spoken = 0
        self.enabled = True
        self.language = 'de'
        self.input_language = 'de'
        self.speed = 155
        self.recording = False
        self.recording_until = 0
        self.transcription = {'state': 'idle', 'text': '', 'error': ''}
        self.running = True
        self.offset = session.stat().st_size
        if config.exists():
            values = json.loads(config.read_text(encoding='utf-8'))
            self.enabled = values.get('enabled', True) is True
            self.language = values.get('language', 'de')
            self.input_language = values.get('input_language', 'de')
            self.speed = values.get('speed', 155)
        self.validate(self.language, self.speed)
        self.validate(self.input_language, self.speed)

    @staticmethod
    def validate(language, speed):
        if language not in ('de', 'en') or type(speed) is not int or not 100 <= speed <= 240:
            raise ValueError('Use German or English and a speed between 100 and 240')

    def status(self):
        with self.lock:
            return dict(enabled=self.enabled, language=self.language, input_language=self.input_language, speed=self.speed,
                        speaking=self.process is not None, queued=len(self.queue),
                        spoken=self.spoken, last_text=self.last_text, error=self.error,
                        chat='Current connected chat', recording=self.recording,
                        transcription=dict(self.transcription))

    def stop(self):
        with self.lock:
            self.queue.clear()
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def settings(self, values):
        with self.lock:
            enabled = values.get('enabled', self.enabled)
            language = values.get('language', self.language)
            input_language = values.get('input_language', self.input_language)
            speed = values.get('speed', self.speed)
            if type(enabled) is not bool:
                raise ValueError('enabled must be boolean')
            self.validate(language, speed)
            self.validate(input_language, speed)
            self.config.parent.mkdir(parents=True, exist_ok=True)
            temp = self.config.with_suffix('.tmp')
            temp.write_text(json.dumps(dict(enabled=enabled, language=language, input_language=input_language, speed=speed), indent=2) + '\n', encoding='utf-8')
            temp.replace(self.config)
            self.enabled, self.language, self.input_language, self.speed = enabled, language, input_language, speed
            if not enabled:
                self.stop()

    def enqueue(self, text):
        with self.lock:
            if self.enabled and text:
                self.queue.append(text)

    def set_recording(self, active):
        if type(active) is not bool:
            raise ValueError('active must be boolean')
        with self.lock:
            if active:
                self.stop()
            self.recording = active
            self.recording_until = time.monotonic() + 90 if active else 0

    def upload(self, data, mime, language):
        formats = {'audio/webm': ('.webm', b'\x1aE\xdf\xa3'),
                   'audio/ogg': ('.ogg', b'OggS'), 'audio/mp4': ('.m4a', b'ftyp')}
        if mime not in formats or language not in ('de', 'en'):
            raise ValueError('Unsupported recording format or language')
        suffix, signature = formats[mime]
        if (data[4:8] if mime == 'audio/mp4' else data[:4]) != signature:
            raise ValueError('Recording content does not match its audio format')
        with self.lock:
            if self.transcription['state'] == 'busy':
                raise ValueError('A transcription is already running')
            OUTPUT.mkdir(parents=True, exist_ok=True)
            source = OUTPUT / ('recording_' + uuid.uuid4().hex + suffix)
            source.write_bytes(data)
            self.transcription = {'state': 'busy', 'text': '', 'error': ''}
            self.recording = False
            threading.Thread(target=self.transcribe, args=(source, language), daemon=True).start()

    def transcribe(self, source, language):
        target = source.with_suffix('.txt')
        try:
            result = subprocess.run([str(PYTHON), str(BASE / 'recording.py'), '--input', str(source),
                                     '--output', str(target), '--language', language],
                                    capture_output=True, timeout=300)
            if result.returncode:
                raise ValueError(result.stderr.decode('utf-8', errors='replace')[-1500:] or 'Transcription failed')
            text = target.read_text(encoding='utf-8').strip()
            with self.lock:
                self.transcription = {'state': 'done', 'text': text, 'error': ''}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            with self.lock:
                self.transcription = {'state': 'error', 'text': '', 'error': str(error)}

    def poll(self):
        with self.session.open(encoding='utf-8') as source:
            if self.session.stat().st_size < self.offset:
                self.offset = 0
            source.seek(self.offset)
            while True:
                position = source.tell()
                line = source.readline()
                if not line or not line.endswith('\n'):
                    self.offset = position
                    break
                self.offset = source.tell()
                try:
                    self.enqueue(speech_text(json.loads(line)))
                except json.JSONDecodeError:
                    continue

    def watch(self):
        while self.running:
            try:
                self.poll()
            except OSError as error:
                with self.lock:
                    self.error = str(error)
            time.sleep(0.3)

    def speak(self):
        while self.running:
            with self.lock:
                if self.recording and time.monotonic() > self.recording_until:
                    self.recording = False
                text = self.queue.popleft() if self.enabled and not self.recording and self.queue else None
                if text:
                    self.last_text = text
                    self.error = ''
                    try:
                        self.process = subprocess.Popen(
                            [str(PYTHON), str(TTS), '--stdin', '--play', '--language', self.language,
                             '--speed', str(self.speed)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                    except OSError as error:
                        self.error = str(error)
                        self.process = None
            if text and self.process:
                process = self.process
                try:
                    _, error = process.communicate(text.encode('utf-8'), timeout=900)
                    with self.lock:
                        if process.returncode == 0:
                            self.spoken += 1
                        elif process.returncode != -signal.SIGTERM:
                            self.error = error.decode('utf-8', errors='replace')[-1500:]
                except subprocess.TimeoutExpired:
                    self.stop()
                    process.communicate()
                    with self.lock:
                        self.error = 'Speech playback timed out'
                finally:
                    with self.lock:
                        self.process = None
            else:
                time.sleep(0.1)


def handler(bridge, port):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, value, content_type='application/json'):
            data = value.encode('utf-8') if isinstance(value, str) else json.dumps(value).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            origin = self.headers.get('Origin')
            return self.headers.get('Host') in hosts and (not origin or origin in {'http://' + h for h in hosts})

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': 'Local access only'})
            path = urlparse(self.path).path
            if path == '/':
                return self.send(200, (BASE / 'index.html').read_text(encoding='utf-8'), 'text/html')
            if path == '/api/status':
                return self.send(200, bridge.status())
            return self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if self.path.startswith('/api/transcribe?'):
                if not self.allowed():
                    return self.send(403, {'error': 'Local access only'})
                try:
                    from urllib.parse import parse_qs
                    language = parse_qs(urlparse(self.path).query).get('language', ['de'])[0]
                    mime = self.headers.get('Content-Type', '').split(';')[0]
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 12 * 1024 * 1024:
                        raise ValueError('Recording must be between 1 byte and 12 MB')
                    if mime not in ('audio/webm', 'audio/ogg', 'audio/mp4'):
                        raise ValueError('Unsupported audio format')
                    bridge.upload(self.rfile.read(size), mime, language)
                    return self.send(202, bridge.status())
                except (ValueError, OSError) as error:
                    return self.send(400, {'error': str(error)})
            if not self.allowed() or self.headers.get('Content-Type') != 'application/json':
                return self.send(403, {'error': 'Local JSON requests only'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('Invalid request size')
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict):
                    raise ValueError('Expected an object')
                if self.path == '/api/settings':
                    bridge.settings(value)
                elif self.path == '/api/test':
                    bridge.enqueue('Die lokale Sprachausgabe ist eingeschaltet.' if bridge.language == 'de' else 'Local speech output is enabled.')
                elif self.path == '/api/recording':
                    bridge.set_recording(value.get('active'))
                elif self.path == '/api/stop':
                    bridge.stop()
                else:
                    return self.send(404, {'error': 'Not found'})
                return self.send(200, bridge.status())
            except (ValueError, OSError) as error:
                return self.send(400, {'error': str(error)})

        def log_message(self, format, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--session-file', type=Path)
    args = parser.parse_args()
    session = args.session_file
    if session is None:
        thread = os.environ.get('CODEX_THREAD_ID')
        if not thread:
            parser.error('Use --session-file or run from the intended Codex chat')
        matches = list((Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'sessions').rglob(f'*{thread}.jsonl'))
        if len(matches) != 1:
            parser.error('Could not identify exactly one local chat transcript')
        session = matches[0]
    bridge = Bridge(session.resolve())
    # Persist defaults so the dashboard always has an editable configuration file.
    bridge.settings({})
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(bridge, args.port))
    for worker in (bridge.watch, bridge.speak):
        threading.Thread(target=worker, daemon=True).start()
    print(f'GPT Gadgets: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        bridge.running = False
        bridge.stop()
        server.server_close()


if __name__ == '__main__':
    main()
