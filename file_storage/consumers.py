from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs
import json


class ProgressConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        query_string = self.scope["query_string"].decode()
        params = parse_qs(query_string)

        job_id = params.get("job_id", [None])[0]

        self.group_name = f"progress_{job_id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):

        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        pass