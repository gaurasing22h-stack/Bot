#!/usr/bin/env python3
"""
🤖 Telegram Group Welcome Bot — Full Admin Panel
Features:
  ✅ Auto Welcome New Members (Bold/Italic formatting)
  ✅ Admin Panel with Inline Buttons
  ✅ Set Media (Photo / GIF / Video) with Welcome
  ✅ Broadcast to All Known Members
  ✅ Change Group/Channel Link Anytime
  ✅ Add/Remove Admins

FIXES APPLIED:
  - escape_mdv2() helper: properly escapes ALL MarkdownV2 special chars incl. underscore
  - escape_code_span() helper: for text inside backtick code spans
  - format_welcome(): bold+italic now uses *_text_* (was ***text***)
  - edit_welcome button: instructions show `{name}` correctly (no stray backslashes)
  - edit_welcome button: current text shown in ``` block with proper escaping
  - cmd_start / cmd_setup: user.first_name now escaped before inserting in MarkdownV2
  - change_link response: link escaped correctly for code span
  - stats: link escaped correctly for code span
  - preview: back button added
  - add_admin: new_name escaped for code span
"""

import os
import json
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Bot Token ───────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")

# ─── Config file ─────────────────────────────────────────────────────────────
CONFIG_FILE = "config.json"

# ─── Conversation states ──────────────────────────────────────────────────────
STATE_EDIT_WELCOME  = "EDIT_WELCOME"
STATE_BROADCAST     = "BROADCAST"
STATE_CHANGE_LINK   = "CHANGE_LINK"
STATE_AWAIT_MEDIA   = "AWAIT_MEDIA"
STATE_ADD_ADMIN     = "ADD_ADMIN"

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    defaults = {
        "welcome_text": "Hello {name}, welcome!! 🧠 Learn AI and Machine Learning free 👉 {link}",
        "bold":         True,
        "italic":       False,
        "group_link":   "https://t.me/your_group",
        "media_file_id": None,
        "media_type":   None,   # "photo" | "video" | "animation"
        "admin_ids":    [],
        "group_ids":    [],
        "known_members": [],
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            logger.warning(f"Config load error: {e}")
    return defaults


cfg: dict = load_config()


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
#  MARKDOWNV2 ESCAPE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def escape_mdv2(text: str) -> str:
    """
    FIX: Escape ALL MarkdownV2 special characters for plain text.
    Previously missing: underscore (_) — extremely common in Telegram links
    and usernames — caused parse errors and broken welcome messages.
    Must escape backslash FIRST before escaping other chars.
    """
    text = text.replace("\\", "\\\\")          # MUST be first
    for ch in r'_*[]()~`>#+-=|{}.!':
        text = text.replace(ch, f"\\{ch}")
    return text


def escape_code_span(text: str) -> str:
    """
    FIX: For text placed INSIDE a backtick code span.
    Inside code spans, ONLY backtick and backslash need escaping.
    Previously the bot was escaping . ! - _ which was wrong and
    showed stray backslashes to the user.
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("`", "\\`")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
#  FORMATTING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def format_welcome(name: str) -> str:
    """
    Build the welcome message with bold/italic and proper MarkdownV2 escaping.

    FIX 1: All special chars including _ are now escaped (was missing _ before).
    FIX 2: Bold+Italic now uses *_text_* format (was ***text*** which is invalid MarkdownV2).
    FIX 3: * is now properly escaped in content before wrapping with bold markers.
    """
    raw = cfg["welcome_text"].replace("{name}", name).replace("{link}", cfg["group_link"])
    escaped = escape_mdv2(raw)

    if cfg["bold"] and cfg["italic"]:
        return f"*_{escaped}_*"   # FIX: was f"***{escaped}***"
    elif cfg["bold"]:
        return f"*{escaped}*"
    elif cfg["italic"]:
        return f"_{escaped}_"
    return escaped


def is_admin(user_id: int) -> bool:
    return user_id in cfg["admin_ids"]


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════════════

def main_panel_kb() -> InlineKeyboardMarkup:
    bold_label   = "𝐁 Bold ✅ ON"  if cfg["bold"]   else "𝐁 Bold ❌ OFF"
    italic_label = "𝐼 Italic ✅ ON" if cfg["italic"] else "𝐼 Italic ❌ OFF"
    media_label  = f"🖼 Media: {cfg['media_type'].upper()}" if cfg["media_type"] else "🖼 Set Media (Photo/GIF/Video)"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Welcome Message",       callback_data="edit_welcome")],
        [
            InlineKeyboardButton(bold_label,   callback_data="toggle_bold"),
            InlineKeyboardButton(italic_label, callback_data="toggle_italic"),
        ],
        [InlineKeyboardButton(media_label,                    callback_data="set_media")],
        [InlineKeyboardButton("🗑 Remove Media",              callback_data="remove_media")],
        [InlineKeyboardButton("📢 Broadcast Message",         callback_data="broadcast")],
        [InlineKeyboardButton("🔗 Change Group/Channel Link", callback_data="change_link")],
        [InlineKeyboardButton("👤 Add Admin",                 callback_data="add_admin")],
        [InlineKeyboardButton("👀 Preview Welcome",           callback_data="preview")],
        [InlineKeyboardButton("📊 Stats",                     callback_data="stats")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back to Panel", callback_data="open_panel")
    ]])


# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not cfg["admin_ids"]:
        text = (
            "👋 *Welcome Bot Setup*\n\n"
            "No admins set yet\\.\n"
            "Use /setup to register yourself as the first admin\\."
        )
    elif is_admin(user.id):
        # FIX: user.first_name was inserted raw — crash if name had _ . ! etc.
        safe_name = escape_mdv2(user.first_name)
        text = (
            f"✅ *Welcome back, {safe_name}\\!*\n\n"
            "Use /panel to open the admin panel\\."
        )
    else:
        text = "👋 Hello\\! I'm a group welcome bot\\."

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """First-time setup — only works when no admins exist."""
    user = update.effective_user
    if cfg["admin_ids"]:
        await update.message.reply_text(
            "⚠️ Bot is already configured\\. Ask an existing admin to add you\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return
    cfg["admin_ids"].append(user.id)
    save_config()
    # FIX: user.first_name was inserted raw — crash if name had _ . ! etc.
    safe_name = escape_mdv2(user.first_name)
    await update.message.reply_text(
        f"✅ *Setup complete\\!*\n\n"
        f"You \\({safe_name}\\) are now the bot admin\\.\n"
        f"Use /panel to manage settings\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ You are not authorized\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    context.user_data.pop("state", None)
    await update.message.reply_text(
        "🎛 *Admin Panel*\n\nManage your group welcome bot settings:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=main_panel_kb(),
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("state", None)
    await update.message.reply_text(
        "❌ Cancelled\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=back_kb(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  CALLBACK BUTTON HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = query.from_user
    data  = query.data

    if not is_admin(user.id):
        await query.edit_message_text("❌ Unauthorized\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    # ── Open / Back ─────────────────────────────────────────────────────
    if data == "open_panel":
        context.user_data.pop("state", None)
        await query.edit_message_text(
            "🎛 *Admin Panel*\n\nManage your group welcome bot settings:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_panel_kb(),
        )

    # ── Toggle Bold ──────────────────────────────────────────────────────
    elif data == "toggle_bold":
        cfg["bold"] = not cfg["bold"]
        save_config()
        await query.edit_message_text(
            f"✅ Bold is now *{'ON' if cfg['bold'] else 'OFF'}*",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_panel_kb(),
        )

    # ── Toggle Italic ────────────────────────────────────────────────────
    elif data == "toggle_italic":
        cfg["italic"] = not cfg["italic"]
        save_config()
        await query.edit_message_text(
            f"✅ Italic is now *{'ON' if cfg['italic'] else 'OFF'}*",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=main_panel_kb(),
        )

    # ── Preview ──────────────────────────────────────────────────────────
    elif data == "preview":
        preview = format_welcome("Rahul")
        # FIX: Back button added (was missing)
        await query.message.reply_text(
            f"👀 *Welcome Message Preview:*\n\n{preview}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Stats ────────────────────────────────────────────────────────────
    elif data == "stats":
        # FIX: Link is inside code span — use escape_code_span, not escape_mdv2
        # Previously raw link was used; if link had backtick/backslash it would break
        safe_link = escape_code_span(cfg["group_link"])
        await query.edit_message_text(
            f"📊 *Bot Stats*\n\n"
            f"👥 Known Members: `{len(cfg['known_members'])}`\n"
            f"👤 Admins: `{len(cfg['admin_ids'])}`\n"
            f"🔗 Group Link: `{safe_link}`\n"
            f"🖼 Media: `{cfg['media_type'] or 'None'}`\n"
            f"𝐁 Bold: `{cfg['bold']}`  𝐼 Italic: `{cfg['italic']}`",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Remove Media ─────────────────────────────────────────────────────
    elif data == "remove_media":
        cfg["media_file_id"] = None
        cfg["media_type"]    = None
        save_config()
        await query.edit_message_text(
            "🗑 *Media removed\\!* Welcome messages will be text only\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Edit Welcome ─────────────────────────────────────────────────────
    elif data == "edit_welcome":
        context.user_data["state"] = STATE_EDIT_WELCOME
        # FIX 1: current text shown in ``` code block — only escape ` and \
        #         Previously wrong: .replace(".", "\\.").replace("!", "\\!") etc.
        #         which caused stray backslashes to show inside the code block.
        # FIX 2: Instructions now correctly show `{name}` and `{link}`
        #         Previously: "Use `\\{name\\}`" → showed `\{name\}` to user (wrong)
        current = escape_code_span(cfg["welcome_text"])
        await query.edit_message_text(
            "✏️ *Edit Welcome Message*\n\n"
            "Send the new welcome text\\.\n"
            "Use `{name}` → member name\n"
            "Use `{link}` → group link\n\n"
            f"*Current:*\n```\n{current}\n```\n\n"
            "Send /cancel to abort\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── Broadcast ────────────────────────────────────────────────────────
    elif data == "broadcast":
        context.user_data["state"] = STATE_BROADCAST
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            f"Will be sent to *{len(cfg['known_members'])}* known members\\.\n\n"
            "Send your message now \\(text, photo, video, or GIF\\)\\.\n"
            "Send /cancel to abort\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── Change Link ──────────────────────────────────────────────────────
    elif data == "change_link":
        context.user_data["state"] = STATE_CHANGE_LINK
        # FIX: Link is in code span — only escape ` and \ (not . - _ etc.)
        safe_link = escape_code_span(cfg["group_link"])
        await query.edit_message_text(
            f"🔗 *Change Group/Channel Link*\n\n"
            f"Current: `{safe_link}`\n\n"
            "Send the new link now\\.\n"
            "Send /cancel to abort\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── Set Media ────────────────────────────────────────────────────────
    elif data == "set_media":
        context.user_data["state"] = STATE_AWAIT_MEDIA
        await query.edit_message_text(
            "🖼 *Set Welcome Media*\n\n"
            "Send a *Photo*, *GIF*, or *Video* to attach to welcome messages\\.\n\n"
            "Send /cancel to abort\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── Add Admin ────────────────────────────────────────────────────────
    elif data == "add_admin":
        context.user_data["state"] = STATE_ADD_ADMIN
        await query.edit_message_text(
            "👤 *Add Admin*\n\n"
            "Forward any message from the user you want to add as admin,\n"
            "OR send their numeric Telegram user ID\\.\n\n"
            "Send /cancel to abort\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER (private chat state machine)
# ═══════════════════════════════════════════════════════════════════════════════

async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    state = context.user_data.get("state")

    if not state or not is_admin(user.id):
        return

    msg = update.message

    # ── Edit Welcome Text ────────────────────────────────────────────────
    if state == STATE_EDIT_WELCOME:
        if not msg.text:
            await msg.reply_text("⚠️ Please send text only for the welcome message\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return
        cfg["welcome_text"] = msg.text
        save_config()
        context.user_data.pop("state")
        preview = format_welcome(user.first_name)
        await msg.reply_text(
            f"✅ *Welcome message updated\\!*\n\n*Preview:*\n{preview}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Broadcast ────────────────────────────────────────────────────────
    elif state == STATE_BROADCAST:
        context.user_data.pop("state")
        sent, failed = 0, 0
        for member_id in cfg["known_members"]:
            try:
                if msg.photo:
                    await context.bot.send_photo(member_id, msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.video:
                    await context.bot.send_video(member_id, msg.video.file_id, caption=msg.caption or "")
                elif msg.animation:
                    await context.bot.send_animation(member_id, msg.animation.file_id, caption=msg.caption or "")
                else:
                    await context.bot.send_message(member_id, msg.text or "")
                sent += 1
            except Exception as e:
                logger.warning(f"Broadcast failed for {member_id}: {e}")

        await msg.reply_text(
            f"📢 *Broadcast Complete\\!*\n\n✅ Sent: `{sent}`\n❌ Failed: `{failed}`",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Change Link ──────────────────────────────────────────────────────
    elif state == STATE_CHANGE_LINK:
        if not msg.text:
            await msg.reply_text("⚠️ Please send the link as text\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return
        cfg["group_link"] = msg.text.strip()
        save_config()
        context.user_data.pop("state")
        # FIX: was .replace(".", "\\.").replace("-", "\\-").replace("_", "\\_")
        #      which is wrong inside a code span (shows literal backslashes)
        safe_link = escape_code_span(cfg["group_link"])
        await msg.reply_text(
            f"✅ *Group link updated\\!*\n\nNew link: `{safe_link}`",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Set Media ────────────────────────────────────────────────────────
    elif state == STATE_AWAIT_MEDIA:
        if msg.photo:
            cfg["media_file_id"] = msg.photo[-1].file_id
            cfg["media_type"]    = "photo"
        elif msg.video:
            cfg["media_file_id"] = msg.video.file_id
            cfg["media_type"]    = "video"
        elif msg.animation:
            cfg["media_file_id"] = msg.animation.file_id
            cfg["media_type"]    = "animation"
        else:
            await msg.reply_text(
                "❌ Please send a *Photo*, *GIF*, or *Video*\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        save_config()
        context.user_data.pop("state")
        await msg.reply_text(
            f"✅ *Media set\\!* Type: `{cfg['media_type']}`",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=back_kb(),
        )

    # ── Add Admin ────────────────────────────────────────────────────────
    elif state == STATE_ADD_ADMIN:
        if msg.forward_from:
            new_id   = msg.forward_from.id
            new_name = msg.forward_from.first_name
        elif msg.text:
            try:
                new_id   = int(msg.text.strip())
                new_name = str(new_id)
            except ValueError:
                await msg.reply_text(
                    "❌ Send a valid numeric user ID or forward a message from that user\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
        else:
            await msg.reply_text("❌ Invalid input\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return

        if new_id not in cfg["admin_ids"]:
            cfg["admin_ids"].append(new_id)
            save_config()
            # FIX: new_name inside code span — use escape_code_span
            safe_name = escape_code_span(str(new_name))
            await msg.reply_text(
                f"✅ *Admin added\\!*\n\nUser `{safe_name}` \\(ID: `{new_id}`\\) is now an admin\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=back_kb(),
            )
        else:
            await msg.reply_text(
                "⚠️ This user is already an admin\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=back_kb(),
            )
        context.user_data.pop("state")


# ═══════════════════════════════════════════════════════════════════════════════
#  GROUP: WELCOME NEW MEMBERS
# ═══════════════════════════════════════════════════════════════════════════════

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in cfg["group_ids"]:
        cfg["group_ids"].append(chat_id)
        save_config()

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        if member.id not in cfg["known_members"]:
            cfg["known_members"].append(member.id)
            save_config()

        # format_welcome now properly escapes all chars including _ in links/names
        welcome_text = format_welcome(member.first_name)

        try:
            if cfg["media_file_id"] and cfg["media_type"]:
                if cfg["media_type"] == "photo":
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=cfg["media_file_id"],
                        caption=welcome_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                elif cfg["media_type"] == "video":
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=cfg["media_file_id"],
                        caption=welcome_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                elif cfg["media_type"] == "animation":
                    await context.bot.send_animation(
                        chat_id=chat_id,
                        animation=cfg["media_file_id"],
                        caption=welcome_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=welcome_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        except Exception as e:
            logger.error(f"Welcome failed for {member.first_name}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  GROUP: TRACK ACTIVE MEMBERS
# ═══════════════════════════════════════════════════════════════════════════════

async def track_group_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id not in cfg["known_members"]:
        cfg["known_members"].append(user.id)
        save_config()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        logger.error("❌ Set your BOT_TOKEN first! Edit the file or set BOT_TOKEN env variable.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # ── Commands ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("setup",  cmd_setup))
    app.add_handler(CommandHandler("panel",  cmd_panel))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # ── Inline button callbacks ───────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(button_handler))

    # ── New member joins group ────────────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        welcome_new_member
    ))

    # ── Private chat: admin state machine ────────────────────────────────
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION),
        private_message_handler
    ))

    # ── Group messages: track members for broadcast ───────────────────────
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT,
        track_group_member
    ))

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=["message", "callback_query", "chat_member"])


if __name__ == "__main__":
    main()
