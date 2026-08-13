"""WebSocket consumer for Live TTS — bridges the browser to Deepgram speak.v1 via the SDK."""
import os
import json
import asyncio
from urllib.parse import parse_qs

import jwt
from channels.generic.websocket import AsyncWebsocketConsumer
from dotenv import load_dotenv

from deepgram import AsyncDeepgramClient
from deepgram.environment import DeepgramClientEnvironment
from deepgram.core.api_error import ApiError
from deepgram.speak.v1.types import SpeakV1Text
from starter.views import SESSION_SECRET

load_dotenv()
API_KEY = os.environ.get("DEEPGRAM_API_KEY")
if not API_KEY:
    raise ValueError("DEEPGRAM_API_KEY required")

DEFAULT_MODEL = "aura-asteria-en"
DEFAULT_ENCODING = "linear16"
DEFAULT_SAMPLE_RATE = "48000"
DEFAULT_CONTAINER = "none"


# One async SDK client, reused across connections; the browser never sees the API key.
# DEEPGRAM_BASE_URL (e.g. wss://api.staging.deepgram.com) overrides the default
# production endpoint. speak.v1 uses environment.production for the /v1/speak ws.
def _build_client():
    base_url = os.environ.get("DEEPGRAM_BASE_URL")
    if base_url:
        https = base_url.replace("wss://", "https://").replace("ws://", "http://")
        env = DeepgramClientEnvironment(
            base=https, production=base_url, agent=base_url, agent_rest=https
        )
        print(f"Using custom Deepgram base URL: {base_url}")
        return AsyncDeepgramClient(api_key=API_KEY, environment=env)
    return AsyncDeepgramClient(api_key=API_KEY)


deepgram = _build_client()


def _safe_error_detail(e):
    """Build a browser-safe (and log-safe) description of a Deepgram error.

    NEVER surface str(e): a deepgram-sdk ApiError stringifies its request
    headers, which include `Authorization: Token <api-key>`. Forwarding that
    to the browser (or writing it to logs) leaks the API key, so we only ever
    expose the exception's HTTP status or type name.
    """
    if isinstance(e, ApiError):
        return f"Deepgram rejected the connection (HTTP {e.status_code})"
    return f"Failed to connect to Deepgram ({type(e).__name__})"


class LiveTTSConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = None
        self._connection_cm = None
        self.forward_task = None

    async def connect(self):
        """Accept WebSocket connection from client"""
        # Validate JWT from subprotocol
        protocols = self.scope.get("subprotocols", [])
        valid_proto = None
        for proto in protocols:
            if proto.startswith("access_token."):
                token = proto[len("access_token."):]
                try:
                    jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
                    valid_proto = proto
                except Exception:
                    pass
                break

        if not valid_proto:
            await self.close(code=4401)
            return

        await self.accept(subprotocol=valid_proto)
        print("Client connected to /api/live-text-to-speech")

        # Parse query parameters from scope
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        params = parse_qs(query_string)

        model = params.get('model', [DEFAULT_MODEL])[0]
        encoding = params.get('encoding', [DEFAULT_ENCODING])[0]
        sample_rate = params.get('sample_rate', [DEFAULT_SAMPLE_RATE])[0]
        container = params.get('container', [DEFAULT_CONTAINER])[0]

        print(f"Connecting to Deepgram TTS: model={model}, encoding={encoding}, sample_rate={sample_rate}")

        try:
            # `connect()` is an async context manager; enter it manually so the
            # connection lives across the consumer's connect/disconnect lifecycle.
            # `container` is not a first-class connect() kwarg, so pass it through
            # as an additional query parameter to preserve the original behavior.
            self._connection_cm = deepgram.speak.v1.connect(
                model=model,
                encoding=encoding,
                sample_rate=sample_rate,
                request_options={"additional_query_parameters": {"container": container}},
            )
            self.connection = await self._connection_cm.__aenter__()
            print("Connected to Deepgram TTS API")

            self.forward_task = asyncio.create_task(self.forward_from_deepgram())

        except Exception as e:
            detail = _safe_error_detail(e)
            print(f"Error connecting to Deepgram: {detail}")
            await self.send(text_data=json.dumps({
                "type": "Error",
                "description": detail,
                "code": "CONNECTION_FAILED"
            }))
            await self.close(code=3000)

    async def disconnect(self, close_code):
        """Cleanup on disconnect"""
        print(f"Client disconnected: {close_code}")

        if self.forward_task:
            self.forward_task.cancel()
            try:
                await self.forward_task
            except asyncio.CancelledError:
                pass

        if self._connection_cm:
            try:
                await self._connection_cm.__aexit__(None, None, None)
            except Exception as e:
                print(f"Error closing Deepgram connection: {_safe_error_detail(e)}")

    async def receive(self, text_data=None, bytes_data=None):
        """Forward browser control messages (JSON) to Deepgram."""
        if not self.connection or not text_data:
            return
        try:
            data = json.loads(text_data)
        except (ValueError, TypeError):
            print("Ignoring non-JSON message from client")
            return

        msg_type = data.get("type")
        try:
            if msg_type == "Speak":
                await self.connection.send_text(SpeakV1Text(text=data.get("text", "")))
            elif msg_type == "Flush":
                await self.connection.send_flush()
            elif msg_type == "Clear":
                await self.connection.send_clear()
            elif msg_type == "Close":
                await self.connection.send_close()
            else:
                print(f"Ignoring unknown client message type: {msg_type}")
        except Exception as e:
            print(f"Error forwarding to Deepgram: {_safe_error_detail(e)}")

    async def forward_from_deepgram(self):
        """Forward Deepgram messages to the browser: bytes as binary, models as JSON."""
        try:
            async for message in self.connection:
                if isinstance(message, (bytes, bytearray)):
                    await self.send(bytes_data=bytes(message))
                elif hasattr(message, "model_dump_json"):
                    await self.send(text_data=message.model_dump_json())
                else:
                    await self.send(text_data=json.dumps(
                        {"type": getattr(message, "type", "Unknown")}
                    ))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            detail = _safe_error_detail(e)
            print(f"Error forwarding from Deepgram: {detail}")
            try:
                await self.send(text_data=json.dumps({
                    "type": "Error",
                    "description": detail,
                    "code": "PROVIDER_ERROR"
                }))
            except Exception:
                pass
        finally:
            try:
                await self.close(code=1000)
            except Exception:
                pass
