import json
import os
from unittest import IsolatedAsyncioTestCase

os.environ.setdefault("DEEPGRAM_API_KEY", "test-key")

from starter.consumers import LiveTTSConsumer, _browser_error


class RecordingConnection:
    def __init__(self):
        self.calls = []

    async def send_text(self, message):
        self.calls.append(("Speak", message.text))

    async def send_flush(self):
        self.calls.append(("Flush", None))

    async def send_clear(self):
        self.calls.append(("Clear", None))

    async def send_close(self):
        self.calls.append(("Close", None))


class BrokenConnection:
    async def send_text(self, _):
        raise RuntimeError("upstream lost")


class ConsumerTests(IsolatedAsyncioTestCase):
    def make_consumer(self, connection):
        consumer = LiveTTSConsumer()
        consumer.connection = connection
        return consumer

    async def test_control_messages_are_mapped_to_sdk_methods(self):
        connection = RecordingConnection()
        consumer = self.make_consumer(connection)

        await consumer.receive(text_data=json.dumps({"type": "Speak", "text": "Hello"}))
        await consumer.receive(text_data=json.dumps({"type": "Flush"}))
        await consumer.receive(text_data=json.dumps({"type": "Clear"}))
        await consumer.receive(text_data=json.dumps({"type": "Close"}))

        self.assertEqual(
            connection.calls,
            [("Speak", "Hello"), ("Flush", None), ("Clear", None), ("Close", None)],
        )

    async def test_upstream_write_failure_notifies_and_closes_browser(self):
        consumer = self.make_consumer(BrokenConnection())
        sent = []
        closed = []

        async def send(*, text_data=None, bytes_data=None):
            sent.append((text_data, bytes_data))

        async def close(code=None):
            closed.append(code)

        consumer.send = send
        consumer.close = close

        await consumer.receive(text_data=json.dumps({"type": "Speak", "text": "Hello"}))

        self.assertEqual(json.loads(sent[0][0]), {
            "type": "Error",
            "error": {
                "type": "ProviderError",
                "code": "AUDIO_GENERATION_ERROR",
                "message": "Failed to connect to Deepgram (RuntimeError)",
            },
        })
        self.assertEqual(closed, [3000])

    def test_browser_errors_use_the_contract_envelope(self):
        self.assertEqual(json.loads(_browser_error("CONNECTION_FAILED", "No connection")), {
            "type": "Error",
            "error": {
                "type": "ProviderError",
                "code": "CONNECTION_FAILED",
                "message": "No connection",
            },
        })
