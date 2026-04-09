"""System command handlers: /start, /help, /cancel."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.states import BotStateService
from app.core.database import get_session_factory

_HELP_TEXT = (
    "📖 <b>Available commands</b>\n\n"
    "/add <i>name</i> — create a new project and get its API key\n"
    "/projects — list all your projects\n"
    "/events — browse event types for a project\n"
    "/report [event] — send a chart for an event (7d / 30d / 90d, day / week)\n"
    "/alerts — list all active alerts across all projects\n"
    "/help — show this message\n"
    "/cancel — cancel the current operation\n\n"
    "💡 <b>Tip:</b> Charts support period switching and period-over-period comparison"
)

_START_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("📊 My Projects", callback_data="home:projects")],
        [
            InlineKeyboardButton("📈 Reports", callback_data="home:reports"),
            InlineKeyboardButton("🔔 Alerts", callback_data="home:alerts"),
        ],
        [InlineKeyboardButton("📖 Help", callback_data="home:help")],
    ]
)


async def start_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text(
        "👋 <b>Welcome to tgram-analytics!</b>\n\n"
        "Self-hosted analytics you control via Telegram.",
        parse_mode="HTML",
        reply_markup=_START_KEYBOARD,
    )


async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text(_HELP_TEXT, parse_mode="HTML")


async def cancel_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    factory = get_session_factory()
    async with factory() as session:
        svc = BotStateService(session)
        await svc.clear(chat_id)
        await session.commit()

    await update.message.reply_text("✅ Operation cancelled.")
