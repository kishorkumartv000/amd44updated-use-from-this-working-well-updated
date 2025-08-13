import asyncio
import os
from typing import List, Dict

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import bot.helpers.translations as lang
from ..helpers.message import edit_message, send_message, check_user, fetch_user_details
from ..helpers.state import conversation_state
from ..helpers.database.pg_impl import set_db
from ..settings import bot_set
from config import Config
from bot.logger import LOGGER

PAGE_SIZE = 10


def _rclone_main_buttons():
    dest = Config.RCLONE_DEST or "Not set"
    status = "ON" if bot_set.rclone else "OFF"
    buttons = [
        [InlineKeyboardButton(lang.s.RCLONE_IMPORT_CONF, callback_data="rcl_import")],
        [InlineKeyboardButton(lang.s.RCLONE_SET_UPLOAD_PATH, callback_data="rcl_set_path")],
        [InlineKeyboardButton(lang.s.RCLONE_REMOTE_BROWSE, callback_data="rcl_browse")],
        [
            InlineKeyboardButton(lang.s.RCLONE_COPY, callback_data="rcl_copy"),
            InlineKeyboardButton(lang.s.RCLONE_MOVE, callback_data="rcl_move"),
        ],
        [InlineKeyboardButton(lang.s.MAIN_MENU_BUTTON, callback_data="main_menu")],
        [InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")],
    ]
    header = f"{lang.s.RCLONE_PANEL}\n{lang.s.RCLONE_STATUS.format(status)}\n{lang.s.RCLONE_UPLOAD_PATH.format(dest)}"
    return header, InlineKeyboardMarkup(buttons)


async def _run(cmd: str) -> (int, str, str):
    task = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await task.communicate()
    return task.returncode, out.decode().strip(), err.decode().strip()


async def _list_remotes() -> List[str]:
    code, out, err = await _run("rclone listremotes --config ./rclone.conf")
    if code != 0:
        LOGGER.error(f"rclone listremotes failed: {err}")
        return []
    # Output ends with ':' per remote
    remotes = [r.strip() for r in out.splitlines() if r.strip()]
    return remotes


async def _list_items(remote: str, path: str) -> List[Dict[str, str]]:
    base = f"{remote}{path}" if path else remote
    # Directories
    code_d, out_d, err_d = await _run(f'rclone lsf --dirs-only --config ./rclone.conf "{base}"')
    # Files
    code_f, out_f, err_f = await _run(f'rclone lsf --files-only --config ./rclone.conf "{base}"')
    items: List[Dict[str, str]] = []
    if code_d == 0 and out_d:
        for line in out_d.splitlines():
            name = line.strip().rstrip('/')
            if name:
                items.append({"name": name, "type": "dir"})
    if code_f == 0 and out_f:
        for line in out_f.splitlines():
            name = line.strip()
            if name:
                items.append({"name": name, "type": "file"})
    if code_d != 0 and err_d:
        LOGGER.debug(f"lsf dirs error: {err_d}")
    if code_f != 0 and err_f:
        LOGGER.debug(f"lsf files error: {err_f}")
    return items


def _build_browser_keyboard(state: Dict) -> InlineKeyboardMarkup:
    items: List[Dict[str, str]] = state.get("items", [])
    page: int = state.get("page", 0)
    mode: str = state.get("rcl_mode", "browse")
    remote: str = state.get("remote", "")
    path: str = state.get("path", "")

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = items[start:end]

    kb: List[List[InlineKeyboardButton]] = []
    for idx, it in enumerate(page_items, start=start):
        prefix = "📁 " if it["type"] == "dir" else "📄 "
        data = f"rcl_open:{idx}" if it["type"] == "dir" else f"rcl_file:{idx}"
        kb.append([InlineKeyboardButton(prefix + it["name"], callback_data=data)])

    nav: List[InlineKeyboardButton] = []
    if path:
        nav.append(InlineKeyboardButton(lang.s.RCLONE_BROWSE_UP, callback_data="rcl_up"))
    if page > 0:
        nav.append(InlineKeyboardButton(lang.s.RCLONE_BROWSE_PREV, callback_data="rcl_prev"))
    if end < len(items):
        nav.append(InlineKeyboardButton(lang.s.RCLONE_BROWSE_NEXT, callback_data="rcl_next"))
    if nav:
        kb.append(nav)

    # Selection controls depending on mode
    if mode in ("set_path", "copy_src", "move_src", "copy_dst", "move_dst"):
        kb.append([InlineKeyboardButton(lang.s.RCLONE_SELECT_THIS, callback_data="rcl_select_here")])

    # Footer
    kb.append([InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")])
    kb.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])

    return InlineKeyboardMarkup(kb)


async def _show_remote_picker(cb_or_msg, mode: str):
    remotes = await _list_remotes()
    rows = [[InlineKeyboardButton(r, callback_data=f"rcl_pick_remote:{r}")] for r in remotes]
    rows.append([InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")])
    rows.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])
    markup = InlineKeyboardMarkup(rows)
    text = f"{lang.s.RCLONE_PANEL}\n{lang.s.RCLONE_PICK_SOURCE if mode in ('copy_src','move_src') else (lang.s.RCLONE_PICK_DEST if mode in ('copy_dst','move_dst') else lang.s.RCLONE_SET_UPLOAD_PATH)}"
    if isinstance(cb_or_msg, CallbackQuery):
        await edit_message(cb_or_msg.message, text, markup)
    else:
        await send_message(cb_or_msg, text, markup=markup)


async def _enter_browser(c: Client, cb: CallbackQuery, remote: str):
    state = await conversation_state.get(cb.from_user.id) or {}
    mode = state.get("rcl_mode", "browse")
    path = ""
    items = await _list_items(remote, path)
    await conversation_state.update(cb.from_user.id, rcl_mode=mode, remote=remote, path=path, items=items, page=0)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{path}")
    await edit_message(cb.message, header, _build_browser_keyboard(await conversation_state.get(cb.from_user.id)))


@Client.on_callback_query(filters.regex(pattern=r"^rclonePanel$"))
async def rclone_panel(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    header, kb = _rclone_main_buttons()
    await edit_message(cb.message, header, kb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_back$"))
async def rcl_back(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    # back to main rclone panel
    await conversation_state.clear(cb.from_user.id)
    header, kb = _rclone_main_buttons()
    await edit_message(cb.message, header, kb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_import$"))
async def rcl_import(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_import_conf", data={})
    await edit_message(cb.message, lang.s.RCLONE_SEND_CONF, InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")]]))


@Client.on_message(filters.document & ~filters.command(["start","settings","download","auth","ban","log","cancel"]))
async def rclone_handle_conf(c: Client, msg: Message):
    state = await conversation_state.get(msg.from_user.id)
    if not state or state.get("stage") != "rclone_import_conf":
        return
    # Download the sent file
    doc = msg.document
    try:
        dest_path = "/workspace/rclone.conf"
        await c.download_media(message=msg, file_name=dest_path)
        # Ensure bot recognizes rclone
        bot_set.rclone = True
        await conversation_state.clear(msg.from_user.id)
        await send_message(msg, lang.s.RCLONE_CONF_SAVED)
    except Exception as e:
        await send_message(msg, f"Failed to save rclone.conf: {e}")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_set_path$"))
async def rcl_set_path(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "set_path"})
    await _show_remote_picker(cb, mode="set_path")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_browse$"))
async def rcl_browse(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "browse"})
    await _show_remote_picker(cb, mode="browse")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_copy$"))
async def rcl_copy(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "copy_src"})
    await _show_remote_picker(cb, mode="copy_src")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_move$"))
async def rcl_move(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "move_src"})
    await _show_remote_picker(cb, mode="move_src")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_pick_remote:(.+)$"))
async def rcl_pick_remote(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    remote = cb.data.split(":", 1)[1]
    await _enter_browser(c, cb, remote)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_up$"))
async def rcl_up(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    remote = state.get("remote", "")
    path = state.get("path", "")
    if not remote:
        await _show_remote_picker(cb, mode=state.get("rcl_mode", "browse"))
        return
    # Go up
    new_path = "" if not path or path.strip("/") == "" else "/".join(path.strip("/").split("/")[:-1])
    if new_path:
        new_path = "/" + new_path + "/"
    items = await _list_items(remote, new_path)
    await conversation_state.update(cb.from_user.id, path=new_path, items=items, page=0)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{new_path}")
    await edit_message(cb.message, header, _build_browser_keyboard(await conversation_state.get(cb.from_user.id)))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_next$"))
async def rcl_next(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    page = state.get("page", 0) + 1
    await conversation_state.update(cb.from_user.id, page=page)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{state.get('remote','')}{state.get('path','')}")
    await edit_message(cb.message, header, _build_browser_keyboard(await conversation_state.get(cb.from_user.id)))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_prev$"))
async def rcl_prev(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    page = max(0, state.get("page", 0) - 1)
    await conversation_state.update(cb.from_user.id, page=page)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{state.get('remote','')}{state.get('path','')}")
    await edit_message(cb.message, header, _build_browser_keyboard(await conversation_state.get(cb.from_user.id)))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_open:(\d+)$"))
async def rcl_open_dir(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    idx = int(cb.data.split(":")[1])
    items = state.get("items", [])
    if idx < 0 or idx >= len(items):
        return
    it = items[idx]
    if it.get("type") != "dir":
        return
    remote = state.get("remote", "")
    path = state.get("path", "") or "/"
    new_path = f"{path}{it['name']}/" if path else f"/{it['name']}/"
    new_items = await _list_items(remote, new_path)
    await conversation_state.update(cb.from_user.id, path=new_path, items=new_items, page=0)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{new_path}")
    await edit_message(cb.message, header, _build_browser_keyboard(await conversation_state.get(cb.from_user.id)))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_file:(\d+)$"))
async def rcl_select_file(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    mode = state.get("rcl_mode", "browse")
    if mode not in ("copy_src", "move_src"):
        return
    idx = int(cb.data.split(":")[1])
    items = state.get("items", [])
    if idx < 0 or idx >= len(items):
        return
    it = items[idx]
    if it.get("type") != "file":
        return
    remote = state.get("remote", "")
    path = state.get("path", "") or "/"
    src = f"{remote}{path}{it['name']}"
    op = "copy" if mode == "copy_src" else "move"
    # Next: pick destination
    await conversation_state.update(cb.from_user.id, rcl_mode=f"{op}_dst", src=src)
    await _show_remote_picker(cb, mode=f"{op}_dst")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_select_here$"))
async def rcl_select_here(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    mode = state.get("rcl_mode", "browse")
    remote = state.get("remote", "")
    path = state.get("path", "")
    current = f"{remote}{path}" if path else remote

    if mode == "set_path":
        # Persist upload path
        set_db.set_variable('RCLONE_DEST', current)
        Config.RCLONE_DEST = current
        await send_message(cb.message, lang.s.RCLONE_DEST_SET.format(current))
        # Back to rclone panel
        await rcl_back(c, cb)
        return

    if mode in ("copy_dst", "move_dst"):
        src = state.get("src")
        if not src:
            await rcl_back(c, cb)
            return
        op = "copy" if mode == "copy_dst" else "move"
        await send_message(cb.message, lang.s.RCLONE_OP_IN_PROGRESS)
        code, out, err = await _run(f'rclone {op} --config ./rclone.conf "{src}" "{current}" -P')
        if code == 0:
            await send_message(cb.message, lang.s.RCLONE_OP_DONE)
        else:
            await send_message(cb.message, lang.s.RCLONE_OP_FAILED.format(err or out))
        await rcl_back(c, cb)
        return


@Client.on_callback_query(filters.regex(pattern=r"^rcl_back$"))
async def rcl_back_dup(c: Client, cb: CallbackQuery):
    # alias, already handled above but keep safe
    await rcl_back(c, cb)