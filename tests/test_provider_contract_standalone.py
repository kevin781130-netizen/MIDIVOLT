"""Standard-library tests for provider completion; no network or model access."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "src/midivolt/_provider_contract.py"
spec = importlib.util.spec_from_file_location("_provider_contract", MODULE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ProviderContractTests(unittest.TestCase):
    def test_openai_complete(self):
        self.assertEqual(contract.decode_response_text("openai", {"choices": [{"finish_reason": "stop", "message": {"content": '{"tracks":[]}'}}]}), '{"tracks":[]}')

    def test_ollama_complete(self):
        self.assertEqual(contract.decode_response_text("ollama", {"done": True, "message": {"content": '{"tracks":[]}'}}), '{"tracks":[]}')

    def test_openai_missing_finish_reason_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "incomplete"):
            contract.decode_response_text("openai", {"choices": [{"message": {"content": '{}'}}]})

    def test_openai_length_truncation_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "incomplete"):
            contract.decode_response_text("openai", {"choices": [{"finish_reason": "length", "message": {"content": '{}'}}]})

    def test_openai_refusal_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "refused"):
            contract.decode_response_text("openai", {"choices": [{"finish_reason": "stop", "message": {"refusal": "no", "content": '{}'}}]})

    def test_ollama_missing_done_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "not complete"):
            contract.decode_response_text("ollama", {"message": {"content": '{}'}})

    def test_ollama_incomplete_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "not complete"):
            contract.decode_response_text("ollama", {"done": False, "message": {"content": '{}'}})

    def test_empty_text_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "no text"):
            contract.decode_response_text("ollama", {"done": True, "message": {"content": '  '}})

    def test_malformed_payload_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "missing"):
            contract.decode_response_text("openai", {"choices": []})

    def test_unknown_provider_rejected(self):
        with self.assertRaisesRegex(contract.ProviderProtocolError, "Unknown"):
            contract.decode_response_text("invalid", {})


if __name__ == "__main__":
    unittest.main()
