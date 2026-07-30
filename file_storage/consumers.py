from channels.generic.websocket import AsyncWebsocketConsumer
from .connection_manager import ConnectionManager
from urllib.parse import parse_qs
import json


class ProgressConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        
        query_string = self.scope["query_string"].decode()

        params = parse_qs(query_string)

        self.job_id = params.get("job_id", [None])[0]

        if not self.job_id:
            await self.close()
            return

        await self.accept()

        ConnectionManager.register(self.job_id, self)

        # print("Users:", ConnectionManager.connection)

        # await self.send(

        #     text_data=json.dumps({
        #         "type": "connection",
        #         "message": "Connected successfully",
        #         "job_id": self.job_id
        #     })
        # )
        # await ConnectionManager.send(
        #      self.job_id,
        #             {
        #                 "type": "test",
        #                 "message": "This came through ConnectionManager!"
        #             }
        # )

    async def disconnect(self, close_code):
        ConnectionManager.unregister(self.job_id)
        pass

    async def receive(self, text_data):
        pass