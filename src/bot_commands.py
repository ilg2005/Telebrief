"""
Bot command handlers for instant digest generation.
"""

import asyncio
import logging
import html
from datetime import datetime, timedelta
from typing import Optional

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from src.config_loader import Config
from src.core import generate_and_send_channel_digests, generate_history_digest
from src.scheduler import DigestScheduler


class BotCommandHandler:
    """Handles bot commands for manual digest generation."""

    def __init__(
        self, config: Config, logger: logging.Logger, scheduler: Optional[DigestScheduler] = None
    ):
        """
        Initialize bot command handler.

        Args:
            config: Application configuration
            logger: Logger instance
            scheduler: Scheduler instance (for status command)
        """
        self.config = config
        self.logger = logger
        self.scheduler = scheduler
        self.app: Optional[Application] = None

    def setup_application(self) -> Application:
        """
        Set up Telegram bot application.

        Returns:
            Configured Application instance
        """
        # Create application
        self.app = Application.builder().token(self.config.telegram_bot_token).build()

        # Add command handlers
        self.app.add_handler(CommandHandler("digest", self.handle_digest))
        self.app.add_handler(CommandHandler("history", self.handle_history))
        self.app.add_handler(CommandHandler("cleanup", self.handle_cleanup))
        self.app.add_handler(CommandHandler("remove", self.handle_remove))
        self.app.add_handler(CommandHandler("status", self.handle_status))
        self.app.add_handler(CommandHandler("help", self.handle_help))
        self.app.add_handler(CommandHandler("start", self.handle_help))

        # Add callback query handler
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))

        # Add message handler for forwarded messages (ID checker)
        self.app.add_handler(MessageHandler(filters.FORWARDED, self.handle_id_check))

        self.logger.info("Bot command handlers registered")
        return self.app

    async def setup_bot_menu(self) -> None:
        """
        Set up bot command menu for easy command discovery.
        This creates the menu that appears when users type '/' in the chat.
        """
        if not self.app:
            self.logger.warning("Application not initialized, cannot set up bot menu")
            return

        commands = [
            BotCommand("start", "Начать работу сботом"),
            BotCommand("digest", "Сгенерировать дайджест за 24 часа"),
            BotCommand("history", "Анализ истории канала"),
            BotCommand("remove", "Удалить канал из списка"),
            BotCommand("cleanup", "Удалить старые дайджесты"),
            BotCommand("status", "Показать статус и настройки"),
            BotCommand("help", "Показать справку"),
        ]

        try:
            await self.app.bot.set_my_commands(commands)
            self.logger.info("✅ Bot command menu configured successfully")
        except Exception as e:
            self.logger.error(f"Failed to set up bot menu: {e}")

    def is_authorized(self, user_id: int) -> bool:
        """
        Check if user is authorized.

        Args:
            user_id: Telegram user ID

        Returns:
            True if authorized
        """
        return user_id == self.config.settings.target_user_id

    async def handle_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /digest command.

        Args:
            update: Telegram update
            context: Bot context
        """
        # Type checks for command handlers
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id

        # Security check
        if not self.is_authorized(user_id):
            self.logger.warning(f"Unauthorized /digest attempt from user {user_id}")
            return  # Silently ignore

        self.logger.info(f"Manual digest requested by user {user_id}")

        # Send "processing" message
        await update.message.reply_text(
            "⏳ Генерирую дайджест за последние 24 часа...\n" "Это может занять 1-2 минуты."
        )

        try:
            # Generate and send digest
            success = await generate_and_send_channel_digests(
                config=self.config, logger=self.logger, hours=24, user_id=user_id
            )

            if success:
                await update.message.reply_text(
                    "✅ Дайджест готов! Каждый канал отправлен отдельным сообщением."
                )
            else:
                await update.message.reply_text(
                    "❌ Ошибка при генерации дайджеста. " "Проверьте логи для деталей."
                )

        except Exception as e:
            self.logger.error(f"Error in /digest command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def handle_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /history command.
        Displays channel selection menu.

        Args:
            update: Telegram update
            context: Bot context
        """
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id

        if not self.is_authorized(user_id):
            self.logger.warning(f"Unauthorized /history attempt from user {user_id}")
            return

        self.logger.info(f"History menu requested by user {user_id}")

        # Parse arguments to determine period (optional)
        args = context.args
        period_arg = None
        if args:
            period_arg = args[0]  # Take first argument as period (e.g. 7d)

        # Store period in user_data for later use
        context.user_data["history_period"] = period_arg

        # Create keyboard with channels
        keyboard = []
        for channel in self.config.channels:
            # Callback data: history:CHANNEL_ID
            keyboard.append(
                [InlineKeyboardButton(channel.name, callback_data=f"history:{channel.id}")]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📊 Выберите канал для анализа истории:", reply_markup=reply_markup
        )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle callback queries from inline keyboards.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        query = update.callback_query
        await query.answer()

        data = query.data
        if not data:
            return

        # Handle Add Channel actions
        if data.startswith("add_channel:"):
            action = data.split(":")[1]
            
            if action == "cancel":
                await query.edit_message_reply_markup(reply_markup=None)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Добавление канала отменено."
                )
                if "pending_channel" in context.user_data:
                    del context.user_data["pending_channel"]
                return
            
            elif action == "confirm":
                if "pending_channel" not in context.user_data:
                    await query.edit_message_text("⚠️ Ошибка: данные устарели. Перешлите сообщение снова.")
                    return
                
                channel_info = context.user_data["pending_channel"]
                channel_id = channel_info["id"]
                channel_name = channel_info["name"]
                
                # Add to config file
                from src.config_loader import add_channel_to_config_file, ChannelConfig
                
                success = add_channel_to_config_file("config.yaml", channel_id, channel_name)
                
                if success:
                    # Update runtime config
                    self.config.channels.append(ChannelConfig(id=channel_id, name=channel_name))
                    
                    await query.edit_message_reply_markup(reply_markup=None)
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"✅ Канал **\"{channel_name}\"** успешно добавлен в настройки!\n"
                             f"Он появится в дайджестах со следующего запуска.",
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text("❌ Ошибка при записи в файл конфигурации.")
                
                # Cleanup
                del context.user_data["pending_channel"]
                return

        # Handle Remove Channel actions
        if data.startswith("remove_ask:"):
            try:
                channel_id = int(data.split(":")[1])
                channel_name = "Unknown"
                for ch in self.config.channels:
                    if str(ch.id) == str(channel_id):
                        channel_name = ch.name
                        break
                
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Да, удалить", callback_data=f"remove_confirm:{channel_id}"),
                        InlineKeyboardButton("❌ Отмена", callback_data="remove_cancel")
                    ]
                ]
                await query.edit_message_text(
                    f"⚠️ Вы уверены, что хотите удалить канал **{channel_name}**?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return
            except Exception:
                await query.edit_message_text("❌ Ошибка обработки запроса.")
                return

        if data.startswith("remove_confirm:"):
            try:
                channel_id = int(data.split(":")[1])
                
                # Remove from config file
                from src.config_loader import remove_channel_from_config_file
                success = remove_channel_from_config_file("config.yaml", channel_id)
                
                if success:
                    # Remove from runtime config
                    self.config.channels = [ch for ch in self.config.channels if str(ch.id) != str(channel_id)]
                    
                    await query.edit_message_text("✅ Канал успешно удален из настроек.")
                else:
                    await query.edit_message_text("❌ Не удалось удалить канал из файла конфигурации.")
                return
            except Exception:
                await query.edit_message_text("❌ Ошибка удаления.")
                return

        if data == "remove_cancel":
            await query.edit_message_text("❌ Удаление отменено.")
            return

        if not data.startswith("history:"):
            return

        # Extract channel ID
        try:
            channel_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("❌ Ошибка: неверный ID канала")
            return

        # Get stored period or default
        period_arg = context.user_data.get("history_period")
        start_date: Optional[datetime] = None
        end_date: Optional[datetime] = None
        period_display = "За все время"

        if period_arg:
            # Parse period logic (same as before)
            if period_arg.endswith("d") and period_arg[:-1].isdigit():
                days = int(period_arg[:-1])
                start_date = datetime.utcnow() - timedelta(days=days)
                period_display = f"Последние {days} дн."
            elif period_arg.endswith("m") and period_arg[:-1].isdigit():
                months = int(period_arg[:-1])
                start_date = datetime.utcnow() - timedelta(days=months * 30)
                period_display = f"Последние {months} мес."
            elif period_arg.endswith("y") and period_arg[:-1].isdigit():
                years = int(period_arg[:-1])
                start_date = datetime.utcnow() - timedelta(days=years * 365)
                period_display = f"Последние {years} г."
            elif "-" in period_arg:
                try:
                    parts = period_arg.split("-")
                    if len(parts) == 2:
                        start_date = datetime.strptime(parts[0], "%d.%m.%Y")
                        end_date = datetime.strptime(parts[1], "%d.%m.%Y")
                        end_date = end_date.replace(hour=23, minute=59, second=59)
                        period_display = f"{parts[0]} - {parts[1]}"
                except ValueError:
                    await query.edit_message_text("❌ Ошибка в формате даты.")
                    return

        # Find channel name for display
        channel_name = "Unknown"
        for ch in self.config.channels:
            if ch.id == channel_id:
                channel_name = ch.name
                break

        await query.edit_message_text(
            f"⏳ Анализирую историю канала **{channel_name}** ({period_display})...\n"
            "Это может занять время.",
            parse_mode="Markdown",
        )

        user_id = update.effective_user.id

        try:
            success = await generate_history_digest(
                config=self.config,
                logger=self.logger,
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
                period_display=period_display,
                target_channel_id=channel_id,
            )

            if success:
                # We can't edit the message to show the digest because it's a new message
                # Just send a confirmation or do nothing (digest is sent separately)
                pass
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Ошибка при генерации анализа истории. Проверьте логи.",
                )

        except Exception as e:
            self.logger.error(f"Error in history generation: {e}", exc_info=True)
            await context.bot.send_message(chat_id=user_id, text=f"❌ Ошибка: {str(e)}")

    async def handle_cleanup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /cleanup command.

        Args:
            update: Telegram update
            context: Bot context
        """
        # Type checks for command handlers
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id

        # Security check
        if not self.is_authorized(user_id):
            self.logger.warning(f"Unauthorized /cleanup attempt from user {user_id}")
            return  # Silently ignore

        self.logger.info(f"Manual cleanup requested by user {user_id}")

        # Send "processing" message
        await update.message.reply_text("🧹 Удаляю предыдущие дайджесты...")

        try:
            from src.sender import DigestSender

            sender = DigestSender(self.config, self.logger)
            success = await sender.cleanup_old_digests(user_id)

            if success:
                await update.message.reply_text("✅ Предыдущие дайджесты успешно удалены!")
            else:
                await update.message.reply_text(
                    "⚠️ Не удалось удалить некоторые сообщения. Проверьте логи для деталей."
                )

        except Exception as e:
            self.logger.error(f"Error in /cleanup command: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def handle_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /remove command.
        """
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            return

        if not self.config.channels:
            await update.message.reply_text("ℹ️ Список каналов пуст.")
            return

        keyboard = []
        for channel in self.config.channels:
            # remove_ask:CHANNEL_ID
            btn_text = f"🗑️ {channel.name}"
            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=f"remove_ask:{channel.id}")]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🗑️ **Удаление канала**\nВыберите канал, который хотите удалить:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /status command.
        
        Args:
            update: Telegram update
            context: Bot context
        """
        # Type checks for command handlers
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id

        # Security check
        if not self.is_authorized(user_id):
            self.logger.warning(f"Unauthorized /status attempt from user {user_id}")
            return

        # Gather status information
        status_lines = [
            "📊 **Статус Telebrief**\n",
            f"🤖 Модель: {self.config.settings.openai_model}",
            f"📺 Каналов настроено: {len(self.config.channels)}",
            f"🧹 Автоочистка: {'Включена' if self.config.settings.auto_cleanup_old_digests else 'Выключена'}",
        ]

        if self.scheduler:
            next_run = self.scheduler.get_next_run_time()
            status_lines.append(f"⏰ Следующий дайджест: {next_run}")
        else:
            status_lines.append("⏰ Планировщик не запущен")

        status_lines.extend(
            [
                "",
                "**Доступные команды:**",
                "/digest - Сгенерировать дайджест сейчас",
                "/history - Анализ истории (меню выбора)",
                "/remove - Удалить канал из списка (меню выбора)",
                "/cleanup - Удалить предыдущие дайджесты",
                "/status - Показать этот статус",
                "/help - Помощь",
                "",
                "💡 **Совет:**",
                "- Чтобы добавить канал, просто перешлите мне из него любое сообщение.",
                "- Чтобы удалить канал, используйте команду /remove.",
            ]
        )

        await update.message.reply_text("\n".join(status_lines), parse_mode="Markdown")

    async def handle_id_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle forwarded messages to display source ID.
        """
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id
        
        # Security check (optional, but good practice to keep bot private)
        if not self.is_authorized(user_id):
            return

        msg = update.message
        
        # Support for python-telegram-bot v20+ (forward_origin)
        if hasattr(msg, 'forward_origin') and msg.forward_origin:
            origin = msg.forward_origin
            
            if origin.type in ['channel', 'chat']:
                chat = origin.chat
                chat_title = html.escape(chat.title)
                chat_id = chat.id
                username = chat.username
                
                # Check if already configured
                is_configured = False
                for ch in self.config.channels:
                    if ch.id == str(chat_id) or ch.id == chat_id:
                        is_configured = True
                        break
                
                response = (
                    f"🆔 <b>Информация о канале/чате</b>\n\n"
                    f"📝 Название: {chat_title}\n"
                    f"🔢 ID: <code>{chat_id}</code>\n"
                )
                if username:
                    response += f"🔗 Username: @{username}\n"
                
                if is_configured:
                    response += "\n✅ <b>Этот канал уже добавлен в настройки.</b>"
                    await msg.reply_text(response, parse_mode="HTML")
                else:
                    response += "\n❓ <b>Добавить этот канал в список для дайджестов?</b>"
                    
                    # Store pending channel info (unescaped title for config)
                    context.user_data["pending_channel"] = {
                        "id": chat_id,
                        "name": chat.title
                    }
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ Добавить", callback_data="add_channel:confirm"),
                            InlineKeyboardButton("❌ Отмена", callback_data="add_channel:cancel")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await msg.reply_text(response, reply_markup=reply_markup, parse_mode="HTML")
                
                return

            elif origin.type == 'user':
                user = origin.sender_user
                user_title = user.first_name
                if user.last_name:
                    user_title += f" {user.last_name}"
                
                user_title = html.escape(user_title)
                user_id_src = user.id
                username = user.username
                
                response = (
                    f"👤 <b>Информация о пользователе</b>\n\n"
                    f"📝 Имя: {user_title}\n"
                    f"🔢 ID: <code>{user_id_src}</code>\n"
                )
                if username:
                    response += f"🔗 Username: @{username}\n"
                    
                await msg.reply_text(response, parse_mode="HTML")
                return
            
            elif origin.type == 'hidden_user':
                 sender_name = html.escape(origin.sender_user_name) if origin.sender_user_name else "Unknown"
                 await msg.reply_text(
                     f"👤 <b>Скрытый пользователь</b>\n"
                     f"Имя: {sender_name}\n"
                     "ID скрыт настройками приватности."
                 , parse_mode="HTML")
                 return

        # Fallback (if forward_origin is somehow missing but it was a forward)
        await msg.reply_text("❌ Не удалось определить источник (возможно, скрыт настройками приватности).")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /help and /start commands.

        Args:
            update: Telegram update
            context: Bot context
        """
        # Type checks for command handlers
        assert update.effective_user is not None
        assert update.message is not None

        user_id = update.effective_user.id

        # Security check
        if not self.is_authorized(user_id):
            return

        help_text = """
🤖 **Telebrief - Telegram Digest Generator**

Я автоматически генерирую ежедневные дайджесты из ваших Telegram-каналов с помощью AI.

**Команды:**

/digest - Сгенерировать дайджест за последние 24 часа
/history - Анализ истории канала (меню выбора)
/remove - Удалить канал из списка (меню выбора)
/cleanup - Удалить предыдущие дайджесты вручную
/status - Показать статус и настройки
/help - Показать эту справку

**📢 Управление каналами:**
• **Добавить:** Перешлите мне любое сообщение из канала. Я предложу добавить его в мониторинг.
• **Удалить:** Используйте команду /remove для выбора и удаления канала.

**Автоматический режим:**
Дайджест генерируется автоматически каждый день в {}

**Возможности:**
• Обработка каналов на любых языках
• Вывод всегда на русском языке
• Умные суммаризации с помощью настроенной модели нейросети
• Анализ истории и трендов канала
• Ссылки на оригинальные сообщения
• Автоматическая очистка старых дайджестов (настраивается)
        """.format(
            self.config.settings.schedule_time + " UTC"
        )

        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def run(self):
        """Run the bot (polling mode)."""
        if not self.app:
            self.setup_application()

        assert self.app is not None
        assert self.app.updater is not None

        self.logger.info("Starting bot polling...")
        await self.app.initialize()
        await self.app.start()

        # Set up bot command menu
        await self.setup_bot_menu()

        await self.app.updater.start_polling()

        self.logger.info("✅ Bot is running and listening for commands")

    async def stop(self):
        """Stop the bot."""
        if self.app and self.app.updater:
            self.logger.info("Stopping bot...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()


async def main():
    """Test bot commands."""
    from src.config_loader import load_config
    from src.utils import setup_logging

    config = load_config()
    logger = setup_logging(config.log_level)

    handler = BotCommandHandler(config, logger)
    handler.setup_application()

    logger.info("Bot command handler ready. Starting polling...")

    try:
        await handler.run()
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping...")
        await handler.stop()


if __name__ == "__main__":
    asyncio.run(main())
