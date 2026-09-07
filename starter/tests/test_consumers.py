import json
import os
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

os.environ.setdefault("DEEPGRAM_API_KEY", "test-key")

from deepgram.core.api_error import ApiError
from starter.consumers import LiveTTSConsumer, _browser_error, _safe_error_detail


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


class ProviderErrorConnection:
    def __init__(self, message):
        self._websocket = self
        self.message = json.dumps(message)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.message is None:
            raise StopAsyncIteration
        message = self.message
        self.message = None
        return message


class ConnectionContextManager:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_):
        return None


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

    async def test_connect_passes_all_audio_options_to_sdk(self):
        consumer = LiveTTSConsumer()
        consumer.scope = {
            "subprotocols": ["access_token.test-token"],
            "query_string": b"?model=aura-asteria-en&encoding=linear16&sample_rate=48000&container=wav",
        }
        context_manager = ConnectionContextManager(RecordingConnection())
        accepted = []

        async def accept(*, subprotocol=None):
            accepted.append(subprotocol)

        async def forward_from_deepgram():
            return None

        consumer.accept = accept
        consumer.forward_from_deepgram = forward_from_deepgram

        with patch("starter.consumers.jwt.decode"), patch(
            "starter.consumers.deepgram.speak.v1.connect", return_value=context_manager
        ) as connect:
            await consumer.connect()

        connect.assert_called_once_with(
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate="48000",
            request_options={"additional_query_parameters": {"container": "wav"}},
        )
        self.assertEqual(accepted, ["access_token.test-token"])
        await consumer.forward_task

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
                "message": "Deepgram failed during audio generation (RuntimeError)",
            },
        })
        self.assertEqual(closed, [3000])

    async def test_unmodeled_provider_error_reaches_browser(self):
        provider_error = {
            "type": "Error",
            "error": {
                "type": "ProviderError",
                "code": "AUDIO_GENERATION_ERROR",
                "message": "Upstream synthesis failed",
            },
        }
        consumer = self.make_consumer(ProviderErrorConnection(provider_error))
        sent = []

        async def send(*, text_data=None, bytes_data=None):
            sent.append((text_data, bytes_data))

        async def close(code=None):
            return None

        consumer.send = send
        consumer.close = close

        await consumer.forward_from_deepgram()

        self.assertEqual(json.loads(sent[0][0]), provider_error)

    def test_browser_errors_use_the_contract_envelope(self):
        self.assertEqual(json.loads(_browser_error("CONNECTION_FAILED", "No connection")), {
            "type": "Error",
            "error": {
                "type": "ProviderError",
                "code": "CONNECTION_FAILED",
                "message": "No connection",
            },
        })

    def test_api_error_detail_excludes_authorization_header(self):
        error = ApiError(
            status_code=400,
            headers={"Authorization": "Token test-key"},
            body="Invalid request",
        )
        browser_error = _browser_error(
            "CONNECTION_FAILED", _safe_error_detail(error, "connection")
        )

        self.assertIn("HTTP 400", browser_error)
        self.assertNotIn("test-key", browser_error)
        self.assertNotIn("Token", browser_error)
        self.assertNotIn("Authorization", browser_error)
