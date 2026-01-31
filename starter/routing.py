"""WebSocket URL routing"""
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('tts/stream', consumers.LiveTTSConsumer.as_asgi()),
]
