import bot.helpers.translations as lang

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from ..settings import bot_set
from ..helpers.translations import lang_available
from ..helpers.buttons.settings import *
from ..helpers.database.pg_impl import set_db
from ..helpers.message import edit_message, check_user, send_message, fetch_user_details
from ..helpers.state import conversation_state
from config import Config
import asyncio
import os


@Client.on_callback_query(filters.regex(pattern=r"^tgPanel"))
async def tg_cb(c, cb:CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        await edit_message(
            cb.message, 
            lang.s.TELEGRAM_PANEL.format(
                bot_set.bot_public,
                bot_set.bot_lang,
                len(bot_set.admins),
                len(bot_set.auth_users),
                len(bot_set.auth_chats),
                bot_set.upload_mode
            ),
            markup=tg_button()
        )


@Client.on_callback_query(filters.regex(pattern=r"^botPublic"))
async def bot_public_cb(client, cb:CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        bot_set.bot_public = False if bot_set.bot_public else True
        set_db.set_variable('BOT_PUBLIC', bot_set.bot_public)
        try:
            await tg_cb(client, cb)
        except:
            pass


@Client.on_callback_query(filters.regex(pattern=r"^antiSpam"))
async def anti_spam_cb(client, cb:CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        anti = ['OFF', 'USER', 'CHAT+']
        current = anti.index(bot_set.anti_spam)
        nexti = (current + 1) % 3
        bot_set.anti_spam = anti[nexti]
        set_db.set_variable('ANTI_SPAM', anti[nexti])
        try:
            await tg_cb(client, cb)
        except:
            pass


@Client.on_callback_query(filters.regex(pattern=r"^vidUploadType$"))
async def video_upload_type_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    bot_set.video_as_document = not bot_set.video_as_document
    set_db.set_variable('VIDEO_AS_DOCUMENT', bot_set.video_as_document)
    await tg_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^audUploadType$"))
async def audio_upload_type_cb(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    bot_set.audio_as_document = not bot_set.audio_as_document
    set_db.set_variable('AUDIO_AS_DOCUMENT', bot_set.audio_as_document)
    await tg_cb(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^langPanel"))
async def language_panel_cb(client, cb:CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        current = bot_set.bot_lang
        await edit_message(
            cb.message,
            lang.s.LANGUAGE_PANEL,
            language_buttons(lang_available, current)
        )


@Client.on_callback_query(filters.regex(pattern=r"^langSet"))
async def set_language_cb(client, cb:CallbackQuery):
    if await check_user(cb.from_user.id, restricted=True):
        to_set = cb.data.split('_')[1]
        bot_set.bot_lang = to_set
        set_db.set_variable('BOT_LANGUAGE', to_set)
        bot_set.set_language()
        try:
            await language_panel_cb(client, cb)
        except:
            pass


@Client.on_message(filters.text & ~filters.command(["start", "settings", "download", "auth", "ban", "log", "cancel"]))
async def handle_text_input(c: Client, msg: Message):
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
        # Start the setup process and monitor for 2FA
        asyncio.create_task(_run_wrapper_setup_flow(c, msg))
        return

    if stage == "apple_setup_need_2fa":
        code = msg.text.strip()
        await conversation_state.update(msg.from_user.id, stage="apple_setup_running", twofa=code)
        await send_message(msg, "Received 2FA code. Continuing...")
        # Signal the running process to consume 2FA code
        _pending = data.get("_pending_2fa")
        if _pending and not _pending.done():
            _pending.set_result(code)
        return

@Client.on_message(filters.command(["cancel"]))
async def cancel_flow(c: Client, msg: Message):
    await conversation_state.clear(msg.from_user.id)
    await send_message(msg, "Cancelled current operation.")

async def _run_wrapper_setup_flow(c: Client, msg: Message):
    user_id = msg.from_user.id
    state = await conversation_state.get(user_id)
    if not state:
        return
    data = state.get("data", {})
    username = data.get("username")
    password = data.get("password")

    try:
        # Launch the setup script with environment vars
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", Config.APPLE_WRAPPER_SETUP_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE,
            env={**os.environ, "USERNAME": username, "PASSWORD": password},
        )

        pending_2fa_future = None  # type: asyncio.Future | None
        buffer = ""
        while True:
            chunk = await proc.stdout.read(1024)
            if not chunk:
                break
            text = chunk.decode(errors='ignore')
            buffer += text
            # Detect 2FA prompt in output
            if "2FA" in text or "2fa" in text or "2FA code" in text:
                if not pending_2fa_future:
                    pending_2fa_future = asyncio.get_event_loop().create_future()
                    await conversation_state.update(user_id, stage="apple_setup_need_2fa", _pending_2fa=pending_2fa_future)
                    await send_message(msg, "Please send your 2FA code.")
                    # Wait for user to respond, with timeout
                    try:
                        code = await asyncio.wait_for(pending_2fa_future, timeout=180)
                    except asyncio.TimeoutError:
                        await send_message(msg, "2FA timed out. Cancelling setup.")
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        await conversation_state.clear(user_id)
                        return
                    # Write code to process stdin with newline
                    if proc.stdin is not None:
                        proc.stdin.write((code + "\n").encode())
                        await proc.stdin.drain()

        rc = await proc.wait()
        if rc == 0:
            await send_message(msg, "✅ Wrapper setup completed.")
        else:
            await send_message(msg, f"❌ Wrapper setup failed. Exit code {rc}.\n\nOutput:\n{buffer[-2000:]}")
    except Exception as e:
        await send_message(msg, f"❌ Error running setup: {e}")
    finally:
        await conversation_state.clear(user_id)
