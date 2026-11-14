"""Send explicitly confirmed text to the selected local Codex chat."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid


def selected_thread(session):
    # Read only session metadata, never infer a destination from browser input.
    with session.open(encoding='utf-8') as source:
        for _ in range(10):
            line = source.readline()
            if not line:
                break
            try:
                row = json.loads(line)
                if row.get('type') == 'session_meta':
                    value = row.get('payload', {}).get('id', '')
                    return str(uuid.UUID(value))
            except (ValueError, TypeError):
                continue
    return None


def codex_cli():
    configured = os.environ.get('GPT_GADGETS_CODEX_CLI') or os.environ.get('CODEX_APP_RUNTIME_CLI_PATH')
    path = configured or shutil.which('codex')
    return str(Path(path).resolve()) if path and Path(path).is_file() else None


def send_message(cli, thread, text, runner=subprocess.run):
    if not cli or not thread:
        raise ValueError('No local Codex CLI or connected chat is available')
    if not isinstance(text, str) or not text.strip() or len(text) > 16000 or '\x00' in text:
        raise ValueError('Message must contain 1 to 16000 characters without NUL bytes')
    result = runner([cli, 'queue', '--thread', thread, '--message', text.strip(), '--resume'],
                    capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise ValueError('Codex could not queue the message: ' + (result.stderr or result.stdout)[-1200:])
    # Queue acceptance is distinct from an assistant reply or completed execution.
    return {'state': 'queued', 'notice': 'Text für den verbundenen Codex-Chat eingereiht.'}
