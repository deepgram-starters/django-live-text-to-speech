from django.urls import path
from django.http import HttpResponse
from django.conf import settings
import os

def index(request):
    index_path = os.path.join(settings.STATIC_ROOT, 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return HttpResponse(f.read(), content_type='text/html')
    return HttpResponse("Build frontend first", status=404)

urlpatterns = [
    path('', index),
    path('', include('starter.urls')),
]

# Import after defining index
from django.urls import include
