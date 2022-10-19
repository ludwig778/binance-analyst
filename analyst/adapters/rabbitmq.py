import json

import aio_pika


class RabbitMQAdapter:
    def __init__(self, settings):
        self.settings = settings

    async def get_connection(self):
        return await aio_pika.connect_robust(
            f"amqp://{self.settings.username}:{self.settings.password}@"
            f"{self.settings.host}:{self.settings.port}/"
        )

    async def send_msg(self, routing_key, message):
        connection = await self.get_connection()

        async with await connection.channel() as channel:
            await channel.default_exchange.publish(
                aio_pika.Message(body=message.encode()),
                routing_key=routing_key,
            )

    async def listen(self, queue_name):
        from pprint import pprint

        connection = await self.get_connection()

        channel = await connection.channel()

        await channel.set_qos(prefetch_count=50)

        # Declaring queue
        queue = await channel.declare_queue(queue_name, auto_delete=True)

        async for message in queue.iterator():
            async with message.process():
                try:
                    message = json.loads(message.body)
                    pprint(message)
                except json.JSONDecodeError:
                    print(message.body)
                except Exception as exc:
                    print("EXCEPTION, ", exc)
