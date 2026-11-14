"""Verify explicit chat delivery without sending live messages."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid
from app import Bridge
from chat import selected_thread, send_message


class ChatTests(unittest.TestCase):
    def test_destination_and_literal_text(self):
        target = str(uuid.uuid4())
        text = 'Hello; $(this is literal text)'
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, '', '')
        self.assertEqual(send_message('/local/codex', target, text, runner)['state'], 'queued')
        self.assertEqual(calls[0], ['/local/codex', 'queue', '--thread', target, '--message', text, '--resume'])
        for invalid in ('', 'a'*16001, None, 'text\x00'):
            with self.assertRaises(ValueError):
                send_message('/local/codex', target, invalid, runner)
        self.assertEqual(len(calls), 1)

    def test_session_metadata_and_duplicate_request(self):
        with tempfile.TemporaryDirectory() as folder:
            target = str(uuid.uuid4())
            session = Path(folder)/'session.jsonl'
            session.write_text(json.dumps({'type':'session_meta','payload':{'id':target}})+'\n')
            self.assertEqual(selected_thread(session), target)
            bridge = Bridge(session, Path(folder)/'settings.json')
            request_id = str(uuid.uuid4())
            with patch('app.send_message', return_value={'state':'queued'}) as sender:
                bridge.send_chat('Hello', request_id)
                bridge.send_chat('Hello', request_id)
                sender.assert_called_once()
            with self.assertRaises(ValueError):
                bridge.send_chat('Hello', 'invalid')


if __name__ == '__main__':
    unittest.main()
