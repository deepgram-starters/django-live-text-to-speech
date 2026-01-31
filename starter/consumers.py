"""WebSocket consumer for Live TTS"""
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from deepgram import DeepgramClient
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("DEEPGRAM_API_KEY")
if not API_KEY:
    raise ValueError("DEEPGRAM_API_KEY required")

deepgram = DeepgramClient(api_key=API_KEY)

class LiveTTSConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print("Client connected to /tts/stream")

    async def disconnect(self, close_code):
        print("Client disconnected")

    async def receive(self, text_data):
        """Receive text from client, synthesize, send audio back"""
        try:
            # This is a simplified placeholder
            # Real implementation would stream audio
            pass
        except Exception as e:
            print(f"Error: {e}")
