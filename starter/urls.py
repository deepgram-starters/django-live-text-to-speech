"""HTTP URL routing"""
from django.urls import path
from . import views

urlpatterns = [
    path('api/metadata', views.metadata, name='metadata'),
]
