"""Bot lifecycle: build the application, run polling, shut down."""

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ..config import load_config
from . import chat, commands

logger = logging.getLogger(__name__)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Error while handling update %s: %s", update, context.error)


class BotRunner:
    """Owns the python-telegram-bot Application and its lifecycle."""

    def __init__(self) -> None:
        self.application: Application | None = None

    async def initialize(self) -> None:
        """Build the application and register all handlers."""
        config = load_config()
        application = Application.builder().token(config.telegram.bot_token).build()

        application.add_handler(CommandHandler("start", commands.start))
        application.add_handler(CommandHandler("help", commands.show_help))
        application.add_handler(CommandHandler("info", commands.show_info))
        application.add_handler(CommandHandler("stats", commands.show_stats))
        application.add_handler(CommandHandler("clear", commands.clear_history))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, chat.handle_message)
        )
        application.add_error_handler(_on_error)

        self.application = application
        logger.info("Bot initialized")

    async def start_polling(self) -> None:
        """Run the bot in polling mode until interrupted."""
        if self.application is None:
            raise RuntimeError("BotRunner.initialize() must be called before start_polling()")

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot started in polling mode")

        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        if self.application is None:
            return
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        if self.application.running:
            await self.application.stop()
        await self.application.shutdown()
        logger.info("Bot stopped")
