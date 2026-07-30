import json
class ConnectionManager:
    connection ={}

    @classmethod
    def register(cls, job_id, consumer):
        cls.connection[job_id] = consumer
    
    @classmethod
    def unregister(cls, job_id):
        cls.connection.pop(job_id, None)

    @classmethod
    async def send(cls, job_id, message):

        consumer = cls.connection.get(job_id)

        if consumer is None:
            print(f"[ConnectionManager] No active connection found for job_id: {job_id}")
            return False
        
        await consumer.send(
                text_data=json.dumps(message)
            )
        return True