from django.urls import path
from file_storage.consumers import ProgressConsumer

websocket_urlpatterns = [
    path("file/progress/", ProgressConsumer.as_asgi()),
]