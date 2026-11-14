"""Behavior checks for the transcript-to-speech boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from app import Bridge, speech_text


def message(text, role='assistant', phase='final_answer'):
    return dict(type='response_item', payload=dict(type='message', role=role, phase=phase,
                content=[dict(type='output_text', text=text)]))


class BridgeTests(unittest.TestCase):
    def test_only_new_messages_and_complete_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder) / 'session.jsonl'
            session.write_text(json.dumps(message('History'))+'\n')
            bridge = Bridge(session, Path(folder) / 'settings.json')
            with session.open('a') as f:
                f.write(json.dumps(message('Do not speak', 'user'))+'\n')
                f.write(json.dumps(message('Private', phase='analysis'))+'\n')
                f.write(json.dumps(message('New reply')))
            bridge.poll()
            self.assertEqual(list(bridge.queue), [])
            with session.open('a') as f:
                f.write('\n')
            bridge.poll()
            bridge.poll()
            self.assertEqual(list(bridge.queue), ['New reply'])
            bridge.settings({'enabled': False})
            self.assertEqual(list(bridge.queue), [])
            bridge.enqueue('Muted')
            self.assertEqual(list(bridge.queue), [])
            restored = Bridge(session, bridge.config)
            self.assertFalse(restored.enabled)
            with self.assertRaises(ValueError):
                bridge.settings({'language': 'ja'})

    def test_recorder_rejects_mismatched_files_and_languages(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder) / 'session.jsonl'
            session.touch()
            bridge = Bridge(session, Path(folder) / 'settings.json')
            for data, mime, language in [(b'not audio', 'audio/webm', 'de'),
                                          (b'OggSdata', 'audio/ogg', 'ja'),
                                          (b'OggSdata', 'text/plain', 'de')]:
                with self.assertRaises(ValueError):
                    bridge.upload(data, mime, language)
            bridge.set_recording(True)
            self.assertTrue(bridge.recording)
            bridge.set_recording(False)
            self.assertFalse(bridge.recording)

    def test_languages_are_independent_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder) / 'session.jsonl'
            session.touch()
            config = Path(folder) / 'settings.json'
            bridge = Bridge(session, config)
            bridge.settings({'language': 'en', 'input_language': 'de'})
            restored = Bridge(session, config)
            self.assertEqual(restored.language, 'en')
            self.assertEqual(restored.input_language, 'de')
            bridge.settings({'language': 'de', 'input_language': 'en'})
            restored = Bridge(session, config)
            self.assertEqual(restored.language, 'de')
            self.assertEqual(restored.input_language, 'en')
            with self.assertRaises(ValueError):
                bridge.settings({'input_language': 'ja'})

    def test_both_final_phase_names(self):
        for phase in ('final', 'final_answer', 'commentary'):
            self.assertEqual(speech_text(message('Visible answer', phase=phase)), 'Visible answer')

    def test_visible_text_only(self):
        self.assertEqual(speech_text(message('See [photo](https://example.org).')), 'See photo.')
        self.assertEqual(speech_text({'type':'event_msg','payload':{'type':'agent_message','message':'duplicate'}}), '')


if __name__ == '__main__':
    unittest.main()
