import asyncio
from abc import ABC, abstractmethod
from typing import List, Union, Optional

from status_tracker import StatusTracker
from utils import check_initialized


class Message:
    def __init__(
        self,
        text: str,
        photo_url_list: Optional[List[str]] = None,
        video_url_list: Optional[List[str]] = None,
    ):
        self.text = text
        self.photo_url_list = photo_url_list
        self.video_url_list = video_url_list


class NotifierBase(ABC):
    initialized = False
    message_queue: asyncio.Queue = asyncio.Queue()
    logger = None  # Optional[logging.Logger]

    def __new__(cls):
        raise Exception('Do not instantiate this class!')

    @classmethod
    async def init(cls):
        StatusTracker.set_notifier_status(cls.notifier_name, True)
        cls.initialized = True
        asyncio.create_task(cls._work())

    @classmethod
    @abstractmethod
    async def send_message(cls, message: Message):
        pass

    @classmethod
    @check_initialized
    async def _work(cls):
        while True:
            message = await cls.message_queue.get()
            try:
                StatusTracker.set_notifier_status(cls.notifier_name, False)
                await cls.send_message(message)
                StatusTracker.set_notifier_status(cls.notifier_name, True)
            except Exception as e:
                print(e)
                if cls.logger:
                    cls.logger.error(e)

    @classmethod
    @check_initialized
    def put_message_into_queue(cls, message: Message):
        cls.message_queue.put_nowait(message)
