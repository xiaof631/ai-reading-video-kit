import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import wave

import doubao_tts
from safe_paths import child_path


class PathTests(unittest.TestCase):
    def test_reject_traversal_absolute_and_control_names(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("../secret", "/tmp/secret", "a/b", "a\\b", "C:foo",
                         "..", ".", "", "a\n", "a\x00", None):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    child_path(d, name)

    def test_accept_normal_filename(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(child_path(d, "字幕.png"), Path(d).resolve() / "字幕.png")

    def test_reject_existing_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "outside.png"
            link.symlink_to(Path(d).parent / "outside.png")
            with self.assertRaises(ValueError):
                child_path(d, link.name)


class TtsTests(unittest.TestCase):
    def synth(self, output):
        return doubao_tts.synth("offline test", str(output), "TEST_SECRET_SENTINEL",
                                "test-speaker")

    def test_https_request_and_pcm_wav(self):
        pcm = b"\x00\x00" * 120
        response = json.dumps({"code": 0, "data": base64.b64encode(pcm).decode()})
        with tempfile.TemporaryDirectory() as d, patch.object(
                urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(response.encode())
            output = Path(d) / "test.wav"
            self.synth(output)
            req = factory.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, doubao_tts.API_URL)
            self.assertTrue(req.full_url.startswith("https://"))
            self.assertEqual(req.get_header("X-api-key"), "TEST_SECRET_SENTINEL")
            self.assertNotIn(b"TEST_SECRET_SENTINEL", req.data)
            self.assertIsInstance(factory.call_args.args[0], doubao_tts.NoRedirect)
            with wave.open(str(output)) as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getframerate(), 24000)
                self.assertEqual(wav.readframes(120), pcm)

    def test_redirect_does_not_forward_credentials(self):
        req = urllib.request.Request(doubao_tts.API_URL,
                                     headers={"X-Api-Key": "TEST_SECRET_SENTINEL"})
        for status in (301, 302, 303, 307, 308):
            self.assertIsNone(doubao_tts.NoRedirect().redirect_request(
                req, None, status, "redirect", {}, "https://example.invalid/"))

    def test_http_error_does_not_print_body(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = urllib.error.HTTPError(
                doubao_tts.API_URL, 401, "secret", {}, io.BytesIO(b"TEST_SECRET_SENTINEL"))
            output = Path(d) / "test.wav"
            with self.assertRaises(SystemExit) as error:
                self.synth(output)
            self.assertIn("401", str(error.exception))
            self.assertNotIn("TEST_SECRET_SENTINEL", str(error.exception))
            self.assertFalse(output.exists())

    def test_api_error_and_malformed_body_are_redacted(self):
        for payload in (b'{"code": 401, "message": "TEST_SECRET_SENTINEL"}',
                        b"TEST_SECRET_SENTINEL"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as d, \
                    patch.object(urllib.request, "build_opener") as factory, \
                    patch.object(doubao_tts.time, "sleep"):
                factory.return_value.open.side_effect = lambda *a, **kw: io.BytesIO(payload)
                output = Path(d) / "test.wav"
                with self.assertRaises(SystemExit) as error:
                    self.synth(output)
                self.assertNotIn("TEST_SECRET_SENTINEL", str(error.exception))
                self.assertFalse(output.exists())

    def test_exception_details_are_redacted(self):
        with tempfile.TemporaryDirectory() as d, patch.object(
                urllib.request, "build_opener") as factory, patch.object(doubao_tts.time, "sleep"):
            factory.return_value.open.side_effect = OSError("TEST_SECRET_SENTINEL")
            with self.assertRaises(SystemExit) as error:
                self.synth(Path(d) / "test.wav")
            self.assertNotIn("TEST_SECRET_SENTINEL", str(error.exception))


if __name__ == "__main__":
    unittest.main()
