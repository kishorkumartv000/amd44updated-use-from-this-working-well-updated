import bot.helpers.translations as lang

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config

from ..settings import bot_set
from ..helpers.buttons.settings import *
from ..helpers.database.pg_impl import set_db

from ..helpers.message import edit_message, check_user, send_message
from ..helpers.state import conversation_state
from .telegram_setting import _run_wrapper_setup_flow


@Client.on_callback_query(filters.regex(pattern=r"^providerPanel"))
async def provider_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        buttons = []
        # Always show Apple Music button
        buttons.append([
            InlineKeyboardButton("🍎 Apple Music", callback_data="appleP")
        ])
        
        # Apple-only build: hide other providers
            
        buttons += [
            [InlineKeyboardButton(lang.s.MAIN_MENU_BUTTON, callback_data="main_menu")],
            [InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")]
        ]
        
        await edit_message(
            cb.message,
            lang.s.PROVIDERS_PANEL,
            InlineKeyboardMarkup(buttons)
        )


#----------------
# APPLE MUSIC
#----------------
@Client.on_callback_query(filters.regex(pattern=r"^appleP"))
async def apple_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        formats = {
            'alac': 'ALAC',
            'atmos': 'Dolby Atmos'
        }
        current = Config.APPLE_DEFAULT_FORMAT
        formats[current] += ' ✅'
        
        await edit_message(
            cb.message,
            "🍎 **Apple Music Settings**\n\n"
            "Use the buttons below to configure formats, quality, and manage the Wrapper service.\n\n"
            "**Available Formats:**\n"
            "- ALAC: Apple Lossless Audio Codec\n"
            "- Dolby Atmos: Spatial audio experience\n\n"
            "**Current Default Format:**",
            apple_button(formats)
        )


@Client.on_callback_query(filters.regex(pattern=r"^appleF"))
async def apple_format_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        format_type = cb.data.split('_')[1]
        # Update configuration
        set_db.set_variable('APPLE_DEFAULT_FORMAT', format_type)
        Config.APPLE_DEFAULT_FORMAT = format_type
        await apple_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^appleQ"))
async def apple_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        qualities = {
            'alac': ['192000', '256000', '320000'],
            'atmos': ['2768', '3072', '3456']
        }
        current_format = Config.APPLE_DEFAULT_FORMAT
        current_quality = getattr(Config, f'APPLE_{current_format.upper()}_QUALITY')
        
        # Create quality buttons
        buttons = []
        for quality in qualities[current_format]:
            label = f"{quality} kbps"
            if quality == current_quality:
                label += " ✅"
            buttons.append([InlineKeyboardButton(label, callback_data=f"appleSQ_{current_format}_{quality}")])
        
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="appleP")])
        
        await edit_message(
            cb.message,
            f"⚙️ **{current_format.upper()} Quality Settings**\n\n"
            "Select the maximum quality for downloads:",
            InlineKeyboardMarkup(buttons)
        )


@Client.on_callback_query(filters.regex(pattern=r"^appleSQ"))
async def apple_set_quality_cb(c, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        _, format_type, quality = cb.data.split('_')
        # Update configuration
        set_db.set_variable(f'APPLE_{format_type.upper()}_QUALITY', quality)
        setattr(Config, f'APPLE_{format_type.upper()}_QUALITY', quality)
        await apple_quality_cb(c, cb)


# Apple Wrapper: Stop with confirmation
@Client.on_callback_query(filters.regex(pattern=r"^appleStop$"))
async def apple_wrapper_stop_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        # Ask for confirmation
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Stop", callback_data="appleStopConfirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="appleP")]
        ])
        await edit_message(cb.message, "Are you sure you want to stop the Wrapper?", buttons)


@Client.on_callback_query(filters.regex(pattern=r"^appleStopConfirm$"))
async def apple_wrapper_stop_confirm_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        from config import Config as Cfg
        import asyncio
        await c.answer_callback_query(cb.id, "Stopping wrapper...", show_alert=False)
        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash", Cfg.APPLE_WRAPPER_STOP_PATH,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode(errors='ignore')
            err = stderr.decode(errors='ignore')
            text = "⏹️ Wrapper stop result:\n\n" + (out.strip() or err.strip() or "Done.")
        except Exception as e:
            text = f"❌ Failed to stop wrapper: {e}"
        await edit_message(cb.message, text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="appleP")]]))


# Apple Wrapper: Setup flow entry (asks for username then password)
@Client.on_callback_query(filters.regex(pattern=r"^appleSetup$"))
async def apple_wrapper_setup_cb(c: Client, cb: CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        # Explain flow
        await edit_message(cb.message, "We'll set up the Wrapper. Please send your Apple ID username.\n\nYou can cancel anytime by sending /cancel.", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="appleP")]]))
        # Mark state for this user
        await conversation_state.start(cb.from_user.id, "apple_setup_username", {"chat_id": cb.message.chat.id, "msg_id": cb.message.id})


# Redundant, dedicated text handler to ensure wrapper flow always responds
@Client.on_message(filters.text & ~filters.command(["start", "settings", "download", "auth", "ban", "log", "cancel"]))
async def apple_wrapper_text_inputs(c: Client, msg: Message):
    state = await conversation_state.get(msg.from_user.id)
    if not state:
        return
    stage = state.get("stage")
    data = state.get("data", {})
    if stage == "apple_setup_username":
        await conversation_state.update(msg.from_user.id, stage="apple_setup_password", username=msg.text.strip())
        await send_message(msg, "Now send your Apple ID password. You can cancel with /cancel")
        return
    if stage == "apple_setup_password":
        await conversation_state.update(msg.from_user.id, stage="apple_setup_running", password=msg.text.strip())
        await send_message(msg, "Running setup... If 2FA is required, I'll ask for it.")
        import asyncio as _asyncio
        _asyncio.create_task(_run_wrapper_setup_flow(c, msg))
        return
    # Let other modules handle other stages
    return


# Apple-only build: remove Qobuz/Tidal handlers