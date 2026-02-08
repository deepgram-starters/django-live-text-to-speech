"""WebSocket URL routing"""
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('api/live-text-to-speech', consumers.LiveTTSConsumer.as_asgi()),
]
