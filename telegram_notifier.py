import logging
import os
import asyncio
from datetime import datetime, timezone
from typing import List, Union, Optional

from telegram import Bot, Update, InputMediaPhoto
from telegram.request import HTTPXRequest
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError

from notifier_base import Message, NotifierBase


class TelegramMessage(Message):
    def __init__(
        self,
        chat_id_list: List[int],
        text: str,
        photo_url_list: Optional[List[str]] = None,
        video_url_list: Optional[List[str]] = None,
    ):
        super().__init__(text, photo_url_list, video_url_list)
        self.chat_id_list = chat_id_list


class TelegramNotifier(NotifierBase):
    notifier_name = 'Telegram'
    bot: Optional[Bot] = None
    logger: Optional[logging.Logger] = None
    update_offset: Optional[int] = None
    initialized: bool = False

    @classmethod
    async def init(cls, token: str, logger_name: str):
        assert token
        request = HTTPXRequest(connect_timeout=10.0, read_timeout=30.0)
        cls.bot = Bot(token=token, request=request)
        cls.logger = logging.getLogger(logger_name)
        updates = await cls._get_updates()
        cls.update_offset = updates[-1].update_id + 1 if updates else None
        cls.logger.info("Init telegram notifier succeed.")
        cls.initialized = True
        await super().init()

    @classmethod
    async def _retry(cls, func, *args, tries=5, delay=5, **kwargs):
        for i in range(tries):
            try:
                return await func(*args, **kwargs)
            except (RetryAfter, TimedOut, NetworkError) as e:
                cls.logger.warning(f"Retrying after error: {e} (Attempt {i+1}/{tries})")
                await asyncio.sleep(delay)
        raise RuntimeError("Max retries exceeded.")

    @classmethod
    async def _send_message_to_single_chat(
        cls,
        chat_id: Union[int, str],
        text: str,
        photo_url_list: Optional[List[str]],
        video_url_list: Optional[List[str]],
    ):
        assert cls.bot
        if video_url_list:
            await cls._retry(cls.bot.send_video, chat_id=chat_id, video=video_url_list[0], caption=text, timeout=60)
        elif photo_url_list:
            if len(photo_url_list) == 1:
                await cls._retry(cls.bot.send_photo, chat_id=chat_id, photo=photo_url_list[0], caption=text, timeout=60)
            else:
                media_group = [InputMediaPhoto(media=photo_url_list[0], caption=text)]
                for photo_url in photo_url_list[1:10]:
                    media_group.append(InputMediaPhoto(media=photo_url))
                await cls._retry(cls.bot.send_media_group, chat_id=chat_id, media=media_group, timeout=60)
        else:
            await cls._retry(cls.bot.send_message, chat_id=chat_id, text=text, disable_web_page_preview=True)

    @classmethod
    async def send_message(cls, message: TelegramMessage):
        assert cls.initialized
        assert isinstance(message, TelegramMessage)
        for chat_id in message.chat_id_list:
            try:
                await cls._send_message_to_single_chat(chat_id, message.text, message.photo_url_list, message.video_url_list)
            except BadRequest as e:
                cls.logger.error(f"{e}, sending without media.")
                await cls._send_message_to_single_chat(chat_id, message.text, None, None)

    @classmethod
    async def _get_updates(cls, offset: Optional[int] = None) -> List[Update]:
        assert cls.bot
        return await cls._retry(cls.bot.get_updates, offset=offset)

    @classmethod
    async def _get_new_updates(cls) -> List[Update]:
        updates = await cls._get_updates(offset=cls.update_offset)
        if updates:
            cls.update_offset = updates[-1].update_id + 1
        return updates

    @classmethod
    async def confirm(cls, message: TelegramMessage) -> bool:
        assert cls.initialized
        assert isinstance(message, TelegramMessage)

        message.text = f"{message.text}\nPlease reply Y/N"
        await cls.send_message(message)

        sending_time = datetime.now(timezone.utc)

        while True:
            updates = await cls._get_new_updates()
            for update in updates:
                if not update.message:
                    continue
                if update.message.date < sending_time:
                    continue
                if update.message.chat.id not in message.chat_id_list:
                    continue
                text = update.message.text.strip().upper()
                if text == "Y":
                    return True
                if text == "N":
                    return False
            await asyncio.sleep(10)

    @classmethod
    async def listen_exit_command(cls, chat_id: int):
        starting_time = datetime.now(timezone.utc)

        while True:
            updates = await cls._get_new_updates()
            for update in updates:
                if not update.message:
                    continue
                if update.message.date < starting_time:
                    continue
                if update.message.chat.id != chat_id:
                    continue
                text = update.message.text.strip().upper()
                if text == "EXIT":
                    confirmed = await cls.confirm(
                        TelegramMessage([chat_id], "Do you want to exit the program?")
                    )
                    if confirmed:
                        await cls.send_message(
                            TelegramMessage([chat_id], "Program will exit after 5 sec.")
                        )
                        cls.logger.error("The program exits by the telegram command.")
                        await asyncio.sleep(5)
                        os._exit(0)
            await asyncio.sleep(20)


async def send_alert(token: str, chat_id: int, message: str):
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message, timeout=60)
