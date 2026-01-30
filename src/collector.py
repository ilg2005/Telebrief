"""
Message collector using Telethon to fetch messages from Telegram channels.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.types import Message as TelegramMessage

from src.config_loader import ChannelConfig, Config
from src.utils import get_lookback_time


@dataclass
class Message:
    """Represents a collected message."""

    text: str
    sender: str
    timestamp: datetime
    link: str
    channel_name: str
    message_id: int
    has_media: bool
    media_type: str


class MessageCollector:
    """Collects messages from Telegram channels using Telethon."""

    def __init__(self, config: Config, logger: logging.Logger):
        """
        Initialize message collector.

        Args:
            config: Application configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger
        self.client = TelegramClient(
            "sessions/user", config.telegram_api_id, config.telegram_api_hash
        )

    async def connect(self):
        """Connect to Telegram."""
        await self.client.start()
        self.logger.info("Connected to Telegram User API")

        # Cache all dialogs to populate entity cache
        try:
            dialogs = await self.client.get_dialogs()
            self.logger.info(f"Cached {len(dialogs)} dialogs for entity resolution")
        except Exception as e:
            self.logger.warning(f"Could not cache dialogs: {e}")

    async def disconnect(self):
        """Disconnect from Telegram."""
        await self.client.disconnect()
        self.logger.info("Disconnected from Telegram")

    async def fetch_messages(
        self,
        hours: int = 24,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        target_channel_id: Optional[str] = None,
    ) -> Dict[str, List[Message]]:
        """
        Fetch messages from all configured channels.

        Args:
            hours: Number of hours to look back
            start_date: Start date for fetching messages
            end_date: End date for fetching messages
            target_channel_id: ID of specific channel to fetch

        Returns:
            Dictionary mapping channel names to lists of messages
        """
        if start_date:
            log_msg = f"Fetching messages from {len(self.config.channels)} channels ({start_date} - {end_date or 'now'})"
        elif hours == 0:
            # Case for full history fetch
            start_date = datetime(2000, 1, 1)  # Telegram launched in 2013, so 2000 is safe
            log_msg = f"Fetching messages from {len(self.config.channels)} channels (FULL HISTORY)"
        else:
            log_msg = f"Fetching messages from {len(self.config.channels)} channels (last {hours}h)"
            start_date = get_lookback_time(hours)

        if target_channel_id:
            log_msg += f" [Target ID: {target_channel_id}]"

        self.logger.info(log_msg)

        all_messages = {}

        for channel_config in self.config.channels:
            # Skip if target_channel_id is set and doesn't match
            if target_channel_id and str(channel_config.id) != str(target_channel_id):
                continue

            try:
                messages = await self._fetch_channel_messages(channel_config, start_date, end_date)
                all_messages[channel_config.name] = messages
                self.logger.info(f"✓ {channel_config.name}: {len(messages)} messages")
            except ChannelPrivateError:
                self.logger.warning(
                    f"✗ {channel_config.name}: Channel is private or not accessible"
                )
                all_messages[channel_config.name] = []
            except FloodWaitError as e:
                self.logger.warning(
                    f"✗ {channel_config.name}: Rate limited, need to wait {e.seconds}s"
                )
                await asyncio.sleep(e.seconds)
                # Retry once
                try:
                    messages = await self._fetch_channel_messages(
                        channel_config, start_date, end_date
                    )
                    all_messages[channel_config.name] = messages
                except Exception as retry_error:
                    self.logger.error(f"Retry failed for {channel_config.name}: {retry_error}")
                    all_messages[channel_config.name] = []
            except ValueError as e:
                # Entity resolution error
                if "Could not find the input entity" in str(e):
                    self.logger.error(
                        f"✗ {channel_config.name}: Channel not found. "
                        f"Make sure you've joined this channel with your Telegram account "
                        f"and the channel ID ({channel_config.id}) is correct."
                    )
                else:
                    self.logger.error(f"✗ {channel_config.name}: {e}")
                all_messages[channel_config.name] = []
            except Exception as e:
                self.logger.error(f"✗ {channel_config.name}: Error fetching messages: {e}")
                all_messages[channel_config.name] = []

        total_messages = sum(len(msgs) for msgs in all_messages.values())
        self.logger.info(f"Total messages collected: {total_messages}")

        return all_messages

    async def _fetch_channel_messages(
        self,
        channel_config: ChannelConfig,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> List[Message]:
        """
        Fetch messages from a single channel.

        Args:
            channel_config: Channel configuration
            start_date: Earliest message time
            end_date: Latest message time (optional)

        Returns:
            List of Message objects
        """
        messages = []
        # If fetching history (start_date provided explicitly and it is old), we might want to increase limit
        # For now, let's just use a higher limit if it looks like a history request?
        # Or just respect config. Let's respect config but maybe warn if it's hit.
        max_messages = self.config.settings.max_messages_per_channel

        # If we are fetching a specific large period, we might need more messages.
        # But let's stick to config limit for safety for now.

        offset_date = end_date if end_date else datetime.utcnow()

        try:
            # Get channel entity
            entity = await self.client.get_entity(self._coerce_entity_ref(channel_config.id))

            # Fetch messages
            async for message in self.client.iter_messages(
                entity, limit=max_messages, offset_date=offset_date
            ):
                # Stop if message is older than start_date
                if message.date < start_date.replace(tzinfo=message.date.tzinfo):
                    break

                # Skip messages without text
                if not message.text:
                    # Handle media-only messages
                    if message.media:
                        media_type = self._get_media_type(message)
                        text = f"[{media_type}]"
                    else:
                        continue
                else:
                    text = message.text
                    media_type = self._get_media_type(message) if message.media else ""

                # Get sender name
                sender = await self._get_sender_name(message)

                # Generate message link
                link = await self._generate_message_link(entity, message.id)

                messages.append(
                    Message(
                        text=text,
                        sender=sender,
                        timestamp=message.date,
                        link=link,
                        channel_name=channel_config.name,
                        message_id=message.id,
                        has_media=message.media is not None,
                        media_type=media_type or "",
                    )
                )

        except Exception as e:
            self.logger.error(f"Error fetching from {channel_config.name}: {e}")
            raise

        return messages

    @staticmethod
    def _coerce_entity_ref(raw: object) -> object:
        raw_str = str(raw).strip()
        if not raw_str:
            return raw
        if raw_str.startswith("@"):
            return raw_str
        try:
            return int(raw_str)
        except ValueError:
            return raw_str

    def _get_media_type(self, message: TelegramMessage) -> str:
        """
        Determine media type from message.

        Args:
            message: Telegram message

        Returns:
            Media type string
        """
        if not message.media:
            return ""

        media_type = type(message.media).__name__

        if "Photo" in media_type:
            return "Фото"
        elif "Video" in media_type or "Document" in media_type:
            if hasattr(message.media, "document"):
                mime = getattr(message.media.document, "mime_type", "")
                if "video" in mime:
                    return "Видео"
                elif "audio" in mime:
                    return "Аудио"
                else:
                    return "Документ"
            return "Видео"
        elif "Voice" in media_type or "Audio" in media_type:
            return "Голосовое сообщение"
        elif "Poll" in media_type:
            return "Опрос"
        elif "Geo" in media_type or "Location" in media_type:
            return "Геолокация"
        else:
            return "Медиа"

    async def _get_sender_name(self, message: TelegramMessage) -> str:
        """
        Get sender name from message.

        Args:
            message: Telegram message

        Returns:
            Sender name or "Unknown"
        """
        try:
            if message.sender:
                sender = await message.get_sender()
                if hasattr(sender, "first_name"):
                    name = str(sender.first_name)
                    if hasattr(sender, "last_name") and sender.last_name:
                        name += f" {sender.last_name}"
                    return name
                elif hasattr(sender, "title"):
                    return str(sender.title)
                elif hasattr(sender, "username"):
                    return f"@{sender.username}"
            return "Unknown"
        except Exception:
            return "Unknown"

    async def _generate_message_link(self, entity, message_id: int) -> str:
        """
        Generate clickable link to message.

        Args:
            entity: Channel entity
            message_id: Message ID

        Returns:
            Message link URL
        """
        try:
            # For public channels/groups
            if hasattr(entity, "username") and entity.username:
                return f"https://t.me/{entity.username}/{message_id}"
            # For private channels/groups
            elif hasattr(entity, "id"):
                # Format: https://t.me/c/CHANNEL_ID/MESSAGE_ID
                # Remove -100 prefix from channel ID
                channel_id = str(entity.id).replace("-100", "")
                return f"https://t.me/c/{channel_id}/{message_id}"
            else:
                return "#"
        except Exception:
            return "#"


async def main():
    """Test message collector."""
    from src.config_loader import load_config
    from src.utils import setup_logging

    config = load_config()
    logger = setup_logging(config.log_level)

    collector = MessageCollector(config, logger)

    try:
        await collector.connect()
        messages = await collector.fetch_messages(hours=1)

        for channel_name, msgs in messages.items():
            print(f"\n{channel_name}: {len(msgs)} messages")
            for msg in msgs[:3]:  # Show first 3
                print(f"  - {msg.sender}: {msg.text[:50]}...")

    finally:
        await collector.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
