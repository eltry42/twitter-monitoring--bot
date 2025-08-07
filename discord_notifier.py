import logging
from typing import List, Union, Optional

import aiohttp
import asyncio

from notifier_base import Message, NotifierBase


class DiscordMessage(Message):
    def __init__(
        self,
        webhook_url_list: List[str],
        text: str,
        photo_url_list: Union[List[str], None] = None,
        video_url_list: Union[List[str], None] = None,
    ):
        super().__init__(text, photo_url_list, video_url_list)
        self.webhook_url_list = webhook_url_list


class DiscordNotifier(NotifierBase):
    notifier_name = 'Discord'
    logger: Optional[logging.Logger] = None

    @classmethod
    async def init(cls, logger_name: str):
        cls.logger = logging.getLogger(logger_name)
        cls.logger.info("Init discord notifier succeed.")
        await super().init()  # ✅ FIX: Await base class init

    @classmethod
    async def _post(cls, session: aiohttp.ClientSession, url: str, content: str):
        data = {"content": content}
        async with session.post(url, json=data, timeout=60) as resp:
            if resp.status != 204:
                text = await resp.text()
                raise RuntimeError(
                    f"Discord webhook failed [{resp.status}]: {text}\nurl: {url}\ndata: {data}"
                )

    @classmethod
    async def send_message(cls, message: DiscordMessage):
        assert cls.initialized
        assert isinstance(message, DiscordMessage)

        async with aiohttp.ClientSession() as session:
            for url in message.webhook_url_list:
                try:
                    # Send main text
                    await cls._post(session, url, message.text)

                    # Send photos
                    if message.photo_url_list:
                        for photo_url in message.photo_url_list:
                            await cls._post(session, url, photo_url)

                    # Send videos
                    if message.video_url_list:
                        for video_url in message.video_url_list:
                            await cls._post(session, url, video_url)

                except Exception as e:
                    cls.logger.error(f"Failed to send message to {url}: {e}")
