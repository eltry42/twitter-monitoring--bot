import logging
import aiohttp
import asyncio

from typing import List, Union, Optional

from notifier_base import Message, NotifierBase


def _remove_http(text: str) -> str:
    text = text.replace('https://', '')
    text = text.replace('http://', '')
    return text


class CqhttpMessage(Message):
    def __init__(
        self,
        url_list: List[str],
        text: str,
        photo_url_list: Union[List[str], None] = None,
        video_url_list: Union[List[str], None] = None
    ):
        super().__init__(text, photo_url_list, video_url_list)
        self.url_list = url_list


class CqhttpNotifier(NotifierBase):
    notifier_name = 'Cqhttp'
    headers: Optional[dict] = None
    logger: Optional[logging.Logger] = None

    @classmethod
    async def init(cls, token: str, logger_name: str):
        cls.headers = {'Authorization': f'Bearer {token}'} if token else None
        cls.logger = logging.getLogger(logger_name)
        cls.logger.info('Init cqhttp notifier succeed.')
        await super().init()  # ✅ fix: await base init

    @classmethod
    async def _post(cls, session: aiohttp.ClientSession, url: str, data: dict):
        async with session.post(url, headers=cls.headers, data=data, timeout=60) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Post failed [{resp.status}]: {body}")
            result = await resp.json()
            if result.get("status") != "ok":
                raise RuntimeError(f"Response error: {result}")

    @classmethod
    async def _send_text(cls, session: aiohttp.ClientSession, url: str, text: str):
        data = {'message': _remove_http(text)}
        await cls._post(session, url, data)

    @classmethod
    async def _send_photo(cls, session: aiohttp.ClientSession, url: str, photo_url: str):
        data = {'message': f'[CQ:image,file={photo_url}]'}
        await cls._post(session, url, data)

    @classmethod
    async def _send_video(cls, session: aiohttp.ClientSession, url: str, video_url: str):
        data = {'message': f'[CQ:video,file={video_url}]'}
        await cls._post(session, url, data)

    @classmethod
    async def send_message(cls, message: CqhttpMessage):
        assert cls.initialized
        assert isinstance(message, CqhttpMessage)

        async with aiohttp.ClientSession() as session:
            for url in message.url_list:
                try:
                    await cls._send_text(session, url, message.text)

                    if message.photo_url_list:
                        for photo_url in message.photo_url_list:
                            await cls._send_photo(session, url, photo_url)

                    if message.video_url_list:
                        for video_url in message.video_url_list:
                            await cls._send_video(session, url, video_url)
                except Exception as e:
                    cls.logger.error(f"Failed to send message to {url}: {e}")
