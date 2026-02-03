"""Django settings for Live TTS starter with Channels"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-key')
DEBUG = True
ALLOWED_HOSTS = ['*']

PORT = int(os.environ.get('PORT', 8081))
HOST = os.environ.get('HOST', '0.0.0.0')
FRONTEND_PORT = int(os.environ.get('FRONTEND_PORT', 8080))

INSTALLED_APPS = [
    'daphne',  # Must be first for Channels
    'corsheaders',
    'starter',
    'channels',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'config.urls'
ASGI_APPLICATION = 'config.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

DATABASES = {}

CORS_ALLOWED_ORIGINS = [
    f"http://localhost:{FRONTEND_PORT}",
    f"http://127.0.0.1:{FRONTEND_PORT}",
]
CORS_ALLOW_CREDENTIALS = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
