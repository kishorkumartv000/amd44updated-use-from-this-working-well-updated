import asyncio
import os
from typing import List, Dict, Any
import uuid
import signal
from asyncio.subprocess import Process
from dataclasses import dataclass
from contextlib import suppress

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import bot.helpers.translations as lang
from ..helpers.message import edit_message, send_message, check_user, fetch_user_details
from ..helpers.state import conversation_state
from ..helpers.database.pg_impl import set_db
from ..settings import bot_set
from config import Config
from bot.logger import LOGGER
from bot.tgclient import aio

PAGE_SIZE = 10

# Track long-running tasks for cancel
ACTIVE_TASKS: Dict[str, Dict[str, any]] = {}

@dataclass
class RunningTask:
    task_id: str
    process: Process | None
    chat_id: int
    message_id: int
    user_id: int
    op: str


def _rclone_main_buttons():
    dest = Config.RCLONE_DEST or "Not set"
    status = "ON" if bot_set.rclone else "OFF"
    buttons = [
        [InlineKeyboardButton(lang.s.RCLONE_IMPORT_CONF, callback_data="rcl_import")],
    ]
    # Show delete conf button if a config exists
    if os.path.exists("/workspace/rclone.conf") or os.path.exists("rclone.conf"):
        buttons.append([InlineKeyboardButton(lang.s.RCLONE_DELETE_CONF, callback_data="rcl_del_conf")])
    # Core actions
    buttons.append([InlineKeyboardButton(lang.s.RCLONE_SET_UPLOAD_PATH, callback_data="rcl_set_path")])
    buttons.append([InlineKeyboardButton(lang.s.RCLONE_REMOTE_BROWSE, callback_data="rcl_browse")])
    buttons.append([
        InlineKeyboardButton(lang.s.RCLONE_COPY, callback_data="rcl_copy"),
        InlineKeyboardButton(lang.s.RCLONE_MOVE, callback_data="rcl_move"),
    ])
    # Mount controls
    buttons.append([
        InlineKeyboardButton(lang.s.RCLONE_MOUNT, callback_data="rcl_mount"),
        InlineKeyboardButton(lang.s.RCLONE_UNMOUNT, callback_data="rcl_unmount"),
    ])
    # New features
    buttons.append([
        InlineKeyboardButton(lang.s.RCLONE_MYFILES, callback_data="rcl_myfiles"),
        InlineKeyboardButton(lang.s.RCLONE_LEECH, callback_data="rcl_leech"),
    ])
    buttons.append([
        InlineKeyboardButton(lang.s.RCLONE_SYNC, callback_data="rcl_sync"),
        InlineKeyboardButton(lang.s.RCLONE_MULTI, callback_data="rcl_multi"),
    ])
    buttons.append([
        InlineKeyboardButton(lang.s.RCLONE_FLAGS, callback_data="rcl_flags"),
        InlineKeyboardButton(lang.s.RCLONE_SERVE, callback_data="rcl_serve"),
    ])
    # Footer
    buttons.append([InlineKeyboardButton(lang.s.MAIN_MENU_BUTTON, callback_data="main_menu")])
    buttons.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])

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


def _get_config_arg() -> str:
    # Prefer explicit Config if it exists on disk
    candidates = []
    try:
        if getattr(Config, "RCLONE_CONFIG", None) and os.path.exists(Config.RCLONE_CONFIG):
            candidates.append(Config.RCLONE_CONFIG)
    except Exception:
        pass
    candidates.extend(["/workspace/rclone.conf", "rclone.conf"])
    for p in candidates:
        try:
            if p and os.path.exists(p):
                return f'--config "{p}"'
        except Exception:
            continue
    return ""


def _state_data(state: Dict) -> Dict:
    if not state:
        return {}
    if isinstance(state, dict) and "data" in state and isinstance(state["data"], dict):
        return state["data"]
    return state


async def _list_remotes() -> List[str]:
    cfg = _get_config_arg()
    code, out, err = await _run(f"rclone listremotes {cfg}")
    if code != 0:
        LOGGER.error(f"rclone listremotes failed: {err}")
        return []
    # Ensure trailing ':' per remote
    remotes = []
    for r in out.splitlines():
        r = r.strip()
        if not r:
            continue
        if not r.endswith(":"):
            r = r + ":"
        remotes.append(r)
    return remotes


async def _list_items(remote: str, path: str) -> List[Dict[str, str]]:
    # Normalize base: for root, use just remote (no '/'), otherwise strip leading '/'
    norm_path = (path or "").strip("/")
    base = remote if norm_path == "" else f"{remote}{norm_path}/"
    cfg = _get_config_arg()
    # Directories
    code_d, out_d, err_d = await _run(f'rclone lsf --dirs-only {cfg} "{base}"')
    # Files
    code_f, out_f, err_f = await _run(f'rclone lsf --files-only {cfg} "{base}"')
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
    # Accept either full conversation state or the nested data dict
    if isinstance(state, dict) and "data" in state and isinstance(state["data"], dict):
        state = state["data"]
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
    if mode in ("myfiles", "leech_src", "sync_src", "sync_dst", "multi_src"):
        # In these modes, selecting current folder is meaningful
        kb.append([InlineKeyboardButton(lang.s.RCLONE_SELECT_THIS, callback_data="rcl_select_here")])

    # MyFiles folder options
    if mode == "myfiles":
        kb.append([
            InlineKeyboardButton(lang.s.RCLONE_FOLDER_OPTIONS, callback_data="rcl_folder_opts"),
            InlineKeyboardButton(lang.s.RCLONE_SEARCH, callback_data="rcl_search"),
        ])

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
    text = f"{lang.s.RCLONE_PANEL}\n" + (
        lang.s.RCLONE_PICK_SOURCE if mode in ('copy_src','move_src') else (
            lang.s.RCLONE_PICK_DEST if mode in ('copy_dst','move_dst') else (
                lang.s.RCLONE_PICK_MOUNT if mode == 'mount' else lang.s.RCLONE_SET_UPLOAD_PATH
            )
        )
    )
    if isinstance(cb_or_msg, CallbackQuery):
        await edit_message(cb_or_msg.message, text, markup)
    else:
        await send_message(cb_or_msg, text, markup=markup)


def _get_mount_dir(remote: str) -> str:
    remote_name = remote.rstrip(':').replace('/', '_')
    return f"/workspace/mnt/{remote_name}"


async def _list_active_mounts() -> List[str]:
    mounts: List[str] = []
    try:
        if os.path.exists('/proc/mounts'):
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3:
                        mount_point = parts[1]
                        fs_type = parts[2]
                        if mount_point.startswith('/workspace/mnt/') and 'fuse' in fs_type:
                            mounts.append(mount_point)
    except Exception as e:
        LOGGER.debug(f"Failed to parse mounts: {e}")
    # Fallback: include existing dirs
    try:
        if os.path.isdir('/workspace/mnt'):
            for name in os.listdir('/workspace/mnt'):
                path = os.path.join('/workspace/mnt', name)
                if os.path.isdir(path) and path not in mounts:
                    mounts.append(path)
    except Exception:
        pass
    return mounts


async def _unmount_path(path: str) -> (bool, str):
    for cmd in [f'fusermount -u "{path}"', f'fusermount3 -u "{path}"', f'umount -l "{path}"']:
        code, out, err = await _run(cmd)
        if code == 0:
            return True, ''
        last_err = err or out
    return False, last_err


async def _enter_browser(c: Client, cb: CallbackQuery, remote: str):
    state = await conversation_state.get(cb.from_user.id) or {}
    mode = _state_data(state).get("rcl_mode", "browse")
    # Start at root (empty path)
    path = ""
    items = await _list_items(remote, path)
    await conversation_state.update(cb.from_user.id, rcl_mode=mode, remote=remote, path=path, items=items, page=0)
    new_state = await conversation_state.get(cb.from_user.id)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{path or '/'}")
    await edit_message(cb.message, header, _build_browser_keyboard(new_state))


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


@Client.on_callback_query(filters.regex(pattern=r"^rcl_del_conf$"))
async def rcl_del_conf(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    removed_any = False
    for path in ["/workspace/rclone.conf", "rclone.conf"]:
        try:
            if os.path.exists(path):
                os.remove(path)
                removed_any = True
        except Exception as e:
            LOGGER.error(f"Failed to delete {path}: {e}")
    # Reset state
    bot_set.rclone = False
    if Config.RCLONE_DEST:
        Config.RCLONE_DEST = None
        try:
            set_db.set_variable('RCLONE_DEST', '')
        except Exception:
            pass
    # If upload mode was RCLONE, fallback to Local
    try:
        if getattr(bot_set, 'upload_mode', 'Local') == 'RCLONE':
            bot_set.upload_mode = 'Local'
            set_db.set_variable('UPLOAD_MODE', 'Local')
    except Exception:
        pass
    await send_message(cb.message, lang.s.RCLONE_CONF_DELETED if removed_any else lang.s.RCLONE_CONF_DELETE_FAILED)
    await rcl_back(c, cb)


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


@Client.on_callback_query(filters.regex(pattern=r"^rcl_myfiles$"))
async def rcl_myfiles(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "myfiles"})
    await _show_remote_picker(cb, mode="browse")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_leech$"))
async def rcl_leech(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "leech_src"})
    await _show_remote_picker(cb, mode="browse")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_sync$"))
async def rcl_sync(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "sync_src"})
    await _show_remote_picker(cb, mode="browse")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_multi$"))
async def rcl_multi(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    # Start with selecting multiple destination remotes
    remotes = await _list_remotes()
    # Store selection state
    await conversation_state.start(cb.from_user.id, stage="rclone_multi", data={"rcl_mode": "multi_select", "targets": set()})
    rows: List[List[InlineKeyboardButton]] = []
    for r in remotes:
        rows.append([InlineKeyboardButton(f"⬜ {r}", callback_data=f"rcl_multi_toggle:{r}")])
    rows.append([InlineKeyboardButton("Next ▶️", callback_data="rcl_multi_next")])
    rows.append([InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")])
    rows.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])
    await edit_message(cb.message, "Select destination remotes (toggle):", InlineKeyboardMarkup(rows))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_multi_toggle:(.+)$"))
async def rcl_multi_toggle(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    chosen = cb.data.split(":", 1)[1]
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    targets: set = data.get("targets") or set()
    if chosen in targets:
        targets.remove(chosen)
    else:
        targets.add(chosen)
    await conversation_state.update(cb.from_user.id, targets=targets)
    # Re-render selection list
    remotes = await _list_remotes()
    rows: List[List[InlineKeyboardButton]] = []
    for r in remotes:
        mark = "✅" if r in targets else "⬜"
        rows.append([InlineKeyboardButton(f"{mark} {r}", callback_data=f"rcl_multi_toggle:{r}")])
    rows.append([InlineKeyboardButton("Next ▶️", callback_data="rcl_multi_next")])
    rows.append([InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")])
    rows.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])
    await edit_message(cb.message, "Select destination remotes (toggle):", InlineKeyboardMarkup(rows))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_multi_next$"))
async def rcl_multi_next(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    targets: set = data.get("targets") or set()
    if not targets:
        await cb.answer("Select at least one remote", show_alert=True)
        return
    # Next: pick source remote/folder
    await conversation_state.update(cb.from_user.id, rcl_mode="multi_src")
    await _show_remote_picker(cb, mode="browse")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_flags$"))
async def rcl_flags(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    # Show flags panel
    text = lang.s.RCLONE_FLAGS_PANEL.format(
        bot_set.rclone_server_side,
        bot_set.rclone_copy_flags or "-",
        bot_set.rclone_upload_flags or "-",
        bot_set.rclone_download_flags or "-",
    )
    kb = [
        [InlineKeyboardButton(lang.s.RCLONE_TOGGLE_SERVER_SIDE.format(bot_set.rclone_server_side), callback_data="rcl_flag_toggle:ssac")],
        [InlineKeyboardButton(lang.s.RCLONE_SET_COPY_FLAGS, callback_data="rcl_flag_set:copy"), InlineKeyboardButton(lang.s.RCLONE_CLEAR_COPY_FLAGS, callback_data="rcl_flag_clear:copy")],
        [InlineKeyboardButton(lang.s.RCLONE_SET_UPLOAD_FLAGS, callback_data="rcl_flag_set:upload"), InlineKeyboardButton(lang.s.RCLONE_CLEAR_UPLOAD_FLAGS, callback_data="rcl_flag_clear:upload")],
        [InlineKeyboardButton(lang.s.RCLONE_SET_DOWNLOAD_FLAGS, callback_data="rcl_flag_set:download"), InlineKeyboardButton(lang.s.RCLONE_CLEAR_DOWNLOAD_FLAGS, callback_data="rcl_flag_clear:download")],
        [InlineKeyboardButton(lang.s.RCLONE_TOGGLE_SERVE.format(bot_set.rclone_serve_enabled), callback_data="rcl_flag_toggle:serve")],
        [InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")],
        [InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")],
    ]
    await edit_message(cb.message, text, InlineKeyboardMarkup(kb))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_flag_toggle:(.+)$"))
async def rcl_flag_toggle(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    what = cb.data.split(":", 1)[1]
    if what == "ssac":
        bot_set.rclone_server_side = not bot_set.rclone_server_side
        set_db.set_variable('RCLONE_SERVER_SIDE', bot_set.rclone_server_side)
    elif what == "serve":
        bot_set.rclone_serve_enabled = not bot_set.rclone_serve_enabled
        set_db.set_variable('RCLONE_SERVE_ENABLED', bot_set.rclone_serve_enabled)
    await rcl_flags(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_flag_set:(.+)$"))
async def rcl_flag_set(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    which = cb.data.split(":", 1)[1]
    await conversation_state.start(cb.from_user.id, stage="rclone_flags_input", data={"which": which})
    await edit_message(cb.message, lang.s.RCLONE_SEND_FLAGS_TEXT, InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")]]))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_flag_clear:(.+)$"))
async def rcl_flag_clear(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    which = cb.data.split(":", 1)[1]
    if which == 'copy':
        bot_set.rclone_copy_flags = ''
        set_db.set_variable('RCLONE_COPY_FLAGS', '')
    elif which == 'upload':
        bot_set.rclone_upload_flags = ''
        set_db.set_variable('RCLONE_UPLOAD_FLAGS', '')
    elif which == 'download':
        bot_set.rclone_download_flags = ''
        set_db.set_variable('RCLONE_DOWNLOAD_FLAGS', '')
    await rcl_flags(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_serve$"))
async def rcl_serve(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    if not getattr(bot_set, 'rclone_serve_enabled', False):
        await send_message(cb.message, "Serve is disabled. Enable in Advanced Flags.")
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "serve"})
    await _show_remote_picker(cb, mode="browse")


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


@Client.on_callback_query(filters.regex(pattern=r"^rcl_mount$"))
async def rcl_mount(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.start(cb.from_user.id, stage="rclone_browse", data={"rcl_mode": "mount"})
    await _show_remote_picker(cb, mode="mount")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_unmount$"))
async def rcl_unmount(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    mounts = await _list_active_mounts()
    if not mounts:
        await send_message(cb.message, lang.s.RCLONE_NO_MOUNTS)
        return
    # Save to state and show picker
    await conversation_state.start(cb.from_user.id, stage="rclone_unmount", data={"mounts": mounts})
    rows = [[InlineKeyboardButton(m, callback_data=f"rcl_unmount_pick:{idx}")] for idx, m in enumerate(mounts)]
    rows.append([InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")])
    rows.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])
    await edit_message(cb.message, lang.s.RCLONE_UNMOUNT_PICK, InlineKeyboardMarkup(rows))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_unmount_pick:(\d+)$"))
async def rcl_unmount_pick(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    mounts: List[str] = data.get('mounts', [])
    idx = int(cb.data.split(":")[1])
    if idx < 0 or idx >= len(mounts):
        await rcl_back(c, cb)
        return
    target = mounts[idx]
    ok, err = await _unmount_path(target)
    if ok:
        await send_message(cb.message, lang.s.RCLONE_UNMOUNT_DONE.format(target))
    else:
        await send_message(cb.message, lang.s.RCLONE_UNMOUNT_FAIL.format(err))
    await rcl_back(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_pick_remote:(.+)$"))
async def rcl_pick_remote(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    remote = cb.data.split(":", 1)[1]
    # Ensure trailing colon for robustness
    if not remote.endswith(":"):
        remote = remote + ":"
    state = await conversation_state.get(cb.from_user.id) or {}
    mode = _state_data(state).get("rcl_mode", "browse")
    if mode == 'mount':
        mount_dir = _get_mount_dir(remote)
        try:
            os.makedirs(mount_dir, exist_ok=True)
        except Exception:
            pass
        cfg = _get_config_arg()
        cmd = f'rclone mount {cfg} "{remote}" "{mount_dir}" --daemon --vfs-cache-mode writes'
        code, out, err = await _run(cmd)
        if code == 0:
            await send_message(cb.message, lang.s.RCLONE_MOUNT_DONE.format(mount_dir))
        else:
            await send_message(cb.message, lang.s.RCLONE_MOUNT_FAIL.format(err or out))
        await rcl_back(c, cb)
        return
    if mode == 'serve':
        # After picking remote, ask for port
        await conversation_state.update(cb.from_user.id, remote=remote, path="/")
        await edit_message(cb.message, lang.s.RCLONE_ENTER_PORT, InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")]]))
        await conversation_state.set_stage(cb.from_user.id, "rclone_serve_port")
        return
    await _enter_browser(c, cb, remote)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_up$"))
async def rcl_up(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    remote = data.get("remote", "")
    path = data.get("path", "")
    if not remote:
        await _show_remote_picker(cb, mode=data.get("rcl_mode", "browse"))
        return
    # Go up
    new_path = "" if not path or path.strip("/") == "" else "/".join(path.strip("/").split("/")[:-1])
    if new_path:
        new_path = "/" + new_path + "/"
    items = await _list_items(remote, new_path)
    await conversation_state.update(cb.from_user.id, path=new_path, items=items, page=0)
    new_state = await conversation_state.get(cb.from_user.id)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{new_path or '/'}")
    await edit_message(cb.message, header, _build_browser_keyboard(new_state))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_next$"))
async def rcl_next(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    page = data.get("page", 0) + 1
    await conversation_state.update(cb.from_user.id, page=page)
    new_state = await conversation_state.get(cb.from_user.id)
    d = _state_data(new_state)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{d.get('remote','')}{d.get('path','')}")
    await edit_message(cb.message, header, _build_browser_keyboard(new_state))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_prev$"))
async def rcl_prev(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    page = max(0, data.get("page", 0) - 1)
    await conversation_state.update(cb.from_user.id, page=page)
    new_state = await conversation_state.get(cb.from_user.id)
    d = _state_data(new_state)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{d.get('remote','')}{d.get('path','')}")
    await edit_message(cb.message, header, _build_browser_keyboard(new_state))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_open:(\d+)$"))
async def rcl_open_dir(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    idx = int(cb.data.split(":")[1])
    items = data.get("items", [])
    if idx < 0 or idx >= len(items):
        return
    it = items[idx]
    if it.get("type") != "dir":
        return
    remote = data.get("remote", "")
    path = data.get("path", "")
    base_path = path or "/"
    new_path = f"{base_path}{it['name']}/" if base_path else f"/{it['name']}/"
    new_items = await _list_items(remote, new_path)
    await conversation_state.update(cb.from_user.id, path=new_path, items=new_items, page=0)
    new_state = await conversation_state.get(cb.from_user.id)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{new_path or '/'}")
    await edit_message(cb.message, header, _build_browser_keyboard(new_state))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_file:(\d+)$"))
async def rcl_select_file(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    mode = data.get("rcl_mode", "browse")
    if mode not in ("copy_src", "move_src", "leech_src"):
        return
    idx = int(cb.data.split(":")[1])
    items = data.get("items", [])
    if idx < 0 or idx >= len(items):
        return
    it = items[idx]
    if it.get("type") != "file":
        return
    remote = data.get("remote", "")
    path = data.get("path", "")
    norm_path = (path or "").strip("/")
    prefix = f"{remote}{norm_path}/" if norm_path else remote
    src = f"{prefix}{it['name']}"
    if mode == 'leech_src':
        await _start_leech(cb, src)
        return
    op = "copy" if mode == "copy_src" else "move"
    # Next: pick destination
    await conversation_state.update(cb.from_user.id, rcl_mode=f"{op}_dst", src=src)
    await _show_remote_picker(cb, mode=f"{op}_dst")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_select_here$"))
async def rcl_select_here(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    mode = data.get("rcl_mode", "browse")
    remote = data.get("remote", "")
    path = data.get("path", "")
    norm_path = (path or "").strip("/")
    current = f"{remote}{norm_path}" if norm_path else remote

    if mode == "set_path":
        # Persist upload path
        set_db.set_variable('RCLONE_DEST', current)
        Config.RCLONE_DEST = current
        await send_message(cb.message, lang.s.RCLONE_DEST_SET.format(current))
        # Back to rclone panel
        await rcl_back(c, cb)
        return

    if mode in ("copy_dst", "move_dst"):
        src = data.get("src")
        if not src:
            await rcl_back(c, cb)
            return
        op = "copy" if mode == "copy_dst" else "move"
        await send_message(cb.message, lang.s.RCLONE_OP_IN_PROGRESS)
        cfg = _get_config_arg()
        code, out, err = await _run(f'rclone {op} {cfg} "{src}" "{current}" -P')
        if code == 0:
            await send_message(cb.message, lang.s.RCLONE_OP_DONE)
        else:
            await send_message(cb.message, lang.s.RCLONE_OP_FAILED.format(err or out))
        await rcl_back(c, cb)
        return

    if mode == "leech_src":
        await _start_leech(cb, current)
        return

    if mode == "sync_src":
        # Save source and pick destination
        await conversation_state.update(cb.from_user.id, rcl_mode="sync_dst", src=current)
        await _show_remote_picker(cb, mode="copy_dst")
        return

    if mode == "sync_dst":
        src = data.get("src")
        dst = current
        if not src:
            await rcl_back(c, cb)
            return
        # Confirm destructive sync
        await conversation_state.update(cb.from_user.id, sync_src=src, sync_dst=dst)
        kb = [
            [InlineKeyboardButton(lang.s.RCLONE_YES, callback_data="rcl_sync_yes"), InlineKeyboardButton(lang.s.RCLONE_NO, callback_data="rcl_back")]
        ]
        await edit_message(cb.message, lang.s.RCLONE_SYNC_WARN, InlineKeyboardMarkup(kb))
        return

    if mode == "multi_src":
        # Mirror selected source to targets sequentially
        targets = data.get("targets") or []
        await _start_multi_mirror(cb, current, list(targets))
        return


async def _start_leech(cb: CallbackQuery, src: str):
    cfg = _get_config_arg()
    # Copy to local storage under leech/<user_id>
    base_local = os.path.join(Config.LOCAL_STORAGE, str(cb.from_user.id), "leech")
    os.makedirs(base_local, exist_ok=True)
    cmd = f'rclone copy {cfg} "{src}" "{base_local}" -P'
    await _run_with_progress(cb, cmd, f"Leeching to {base_local}")
    await send_message(cb.message, lang.s.RCLONE_OP_DONE)
    await rcl_back(aio, cb)  # type: ignore


async def _start_multi_mirror(cb: CallbackQuery, src: str, targets: List[str]):
    cfg = _get_config_arg()
    for dst_remote in targets:
        cmd = f'rclone copy {cfg} "{src}" "{dst_remote}" -P'
        await _run_with_progress(cb, cmd, f"Mirroring to {dst_remote}")
    await send_message(cb.message, lang.s.RCLONE_OP_DONE)
    await rcl_back(aio, cb)  # type: ignore


async def _run_with_progress(cb: CallbackQuery, cmd: str, title: str):
    user = await fetch_user_details(cb.message)
    # Start process
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    task_id = uuid.uuid4().hex[:8]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_CANCEL, callback_data=f"rcl_cancel:{task_id}")]])
    msg = await send_message(user, f"{title}\nStarted...", markup=kb)
    ACTIVE_TASKS[task_id] = {
        "proc": proc,
        "chat_id": user['chat_id'],
        "message_id": msg.id if msg else cb.message.id,
        "user_id": user['user_id'],
        "op": title,
    }
    # Stream progress
    buffer = ""
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode().strip()
        if 'Transferred:' in text:
            buffer = text
            try:
                await edit_message(cb.message, f"{title}\n{text}", kb)
            except Exception:
                pass
        await asyncio.sleep(0)
    with suppress(Exception):
        ACTIVE_TASKS.pop(task_id, None)
    await proc.wait()


@Client.on_callback_query(filters.regex(pattern=r"^rcl_cancel:(.+)$"))
async def rcl_cancel(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    task_id = cb.data.split(":", 1)[1]
    t = ACTIVE_TASKS.get(task_id)
    if not t:
        await cb.answer("No active task", show_alert=True)
        return
    proc: Process = t.get("proc")
    with suppress(Exception):
        proc.terminate()
    with suppress(Exception):
        ACTIVE_TASKS.pop(task_id, None)
    await cb.answer("Cancelled", show_alert=True)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_sync_yes$"))
async def rcl_sync_yes(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    src = data.get("sync_src")
    dst = data.get("sync_dst")
    if not src or not dst:
        await rcl_back(c, cb)
        return
    cfg = _get_config_arg()
    flags = " --server-side-across-configs" if getattr(bot_set, 'rclone_server_side', False) else ""
    cmd = f'rclone sync {cfg}{flags} "{src}" "{dst}" -P'
    await _run_with_progress(cb, cmd, f"Syncing {src} -> {dst}")
    await send_message(cb.message, lang.s.RCLONE_OP_DONE)
    await rcl_back(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_folder_opts$"))
async def rcl_folder_opts(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    kb = [
        [InlineKeyboardButton(lang.s.RCLONE_SIZE, callback_data="rcl_size"), InlineKeyboardButton(lang.s.RCLONE_ABOUT, callback_data="rcl_about")],
        [InlineKeyboardButton(lang.s.RCLONE_MKDIR, callback_data="rcl_mkdir"), InlineKeyboardButton(lang.s.RCLONE_RENAME, callback_data="rcl_rename")],
        [InlineKeyboardButton(lang.s.RCLONE_RMDIRS, callback_data="rcl_rmdirs"), InlineKeyboardButton(lang.s.RCLONE_DEDUPE, callback_data="rcl_dedupe")],
        [InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")],
        [InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")],
    ]
    await edit_message(cb.message, lang.s.RCLONE_FOLDER_OPTIONS, InlineKeyboardMarkup(kb))


def _current_remote_and_path(data: Dict) -> (str, str):
    remote = data.get("remote", "")
    path = data.get("path", "")
    norm_path = (path or "").strip("/")
    current = f"{remote}{norm_path}" if norm_path else remote
    return remote, current


@Client.on_callback_query(filters.regex(pattern=r"^rcl_size$"))
async def rcl_size(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    data = _state_data(await conversation_state.get(cb.from_user.id) or {})
    remote, current = _current_remote_and_path(data)
    cfg = _get_config_arg()
    code, out, err = await _run(f'rclone size {cfg} "{current}"')
    await send_message(cb.message, out if out else (err or "Failed"))
    await _enter_browser(c, cb, remote)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_about$"))
async def rcl_about(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    data = _state_data(await conversation_state.get(cb.from_user.id) or {})
    remote, current = _current_remote_and_path(data)
    # about works on remote, not path
    cfg = _get_config_arg()
    code, out, err = await _run(f'rclone about {cfg} "{remote}"')
    await send_message(cb.message, out if out else (err or "Failed"))
    await _enter_browser(c, cb, remote)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_mkdir$"))
async def rcl_mkdir(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.set_stage(cb.from_user.id, "rclone_mkdir_name")
    await edit_message(cb.message, lang.s.RCLONE_ENTER_DIRNAME, InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")]]))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_rename$"))
async def rcl_rename(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.set_stage(cb.from_user.id, "rclone_rename_text")
    await edit_message(cb.message, lang.s.RCLONE_ENTER_RENAME, InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")]]))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_rmdirs$"))
async def rcl_rmdirs(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    kb = [[InlineKeyboardButton(lang.s.RCLONE_YES, callback_data="rcl_rmdirs_yes"), InlineKeyboardButton(lang.s.RCLONE_NO, callback_data="rcl_back")]]
    await edit_message(cb.message, lang.s.RCLONE_CONFIRM, InlineKeyboardMarkup(kb))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_dedupe$"))
async def rcl_dedupe(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    kb = [[InlineKeyboardButton(lang.s.RCLONE_YES, callback_data="rcl_dedupe_yes"), InlineKeyboardButton(lang.s.RCLONE_NO, callback_data="rcl_back")]]
    await edit_message(cb.message, lang.s.RCLONE_CONFIRM, InlineKeyboardMarkup(kb))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_rmdirs_yes$"))
async def rcl_rmdirs_yes(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    data = _state_data(await conversation_state.get(cb.from_user.id) or {})
    _, current = _current_remote_and_path(data)
    cfg = _get_config_arg()
    code, out, err = await _run(f'rclone rmdirs {cfg} "{current}"')
    await send_message(cb.message, out if out else (err or "Done"))
    await rcl_back(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_dedupe_yes$"))
async def rcl_dedupe_yes(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    data = _state_data(await conversation_state.get(cb.from_user.id) or {})
    _, current = _current_remote_and_path(data)
    cfg = _get_config_arg()
    code, out, err = await _run(f'rclone dedupe {cfg} --dedupe-mode newest "{current}"')
    await send_message(cb.message, out if out else (err or "Done"))
    await rcl_back(c, cb)


@Client.on_callback_query(filters.regex(pattern=r"^rcl_search$"))
async def rcl_search(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    await conversation_state.set_stage(cb.from_user.id, "rclone_search_query")
    await edit_message(cb.message, lang.s.RCLONE_ENTER_QUERY, InlineKeyboardMarkup([[InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")]]))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_search_open:(\d+)$"))
async def rcl_search_open(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    results: List[Dict] = data.get("search_results", [])
    idx = int(cb.data.split(":")[1])
    if idx < 0 or idx >= len(results):
        return
    item = results[idx]
    name = item['name']
    # Navigate to parent directory of the result
    parent = name.rsplit('/', 1)[0] if '/' in name else ""
    new_path = "/" + parent + "/" if parent else "/"
    remote = data.get("remote", "")
    items = await _list_items(remote, new_path)
    await conversation_state.update(cb.from_user.id, path=new_path, items=items, page=0)
    new_state = await conversation_state.get(cb.from_user.id)
    header = lang.s.RCLONE_BROWSE_HEADER.format(f"{remote}{new_path or '/'}")
    await edit_message(cb.message, header, _build_browser_keyboard(new_state))


@Client.on_callback_query(filters.regex(pattern=r"^rcl_serve_http$"))
async def rcl_serve_http(c: Client, cb: CallbackQuery):
    await _start_serve(cb, protocol="http")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_serve_webdav$"))
async def rcl_serve_webdav(c: Client, cb: CallbackQuery):
    await _start_serve(cb, protocol="webdav")


@Client.on_callback_query(filters.regex(pattern=r"^rcl_serve_stop$"))
async def rcl_serve_stop(c: Client, cb: CallbackQuery):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    state = await conversation_state.get(cb.from_user.id) or {}
    data = _state_data(state)
    pid = data.get("serve_pid")
    if pid:
        with suppress(Exception):
            os.kill(int(pid), signal.SIGTERM)
        await send_message(cb.message, lang.s.RCLONE_SERVE_STOPPED)
    await rcl_back(c, cb)


async def _start_serve(cb: CallbackQuery, protocol: str):
    if not await check_user(cb.from_user.id, restricted=True):
        return
    data = _state_data(await conversation_state.get(cb.from_user.id) or {})
    remote = data.get("remote")
    port = data.get("port")
    if not remote or not port:
        await cb.answer("Missing remote/port", show_alert=True)
        return
    cfg = _get_config_arg()
    cmd = f'rclone serve {protocol} {cfg} "{remote}" --addr :{port}'
    proc = await asyncio.create_subprocess_shell(cmd)
    await conversation_state.update(cb.from_user.id, serve_pid=proc.pid)
    await send_message(cb.message, lang.s.RCLONE_SERVE_STARTED.format(remote, port))
    await rcl_back(aio, cb)  # type: ignore


@Client.on_callback_query(filters.regex(pattern=r"^rcl_back$"))
async def rcl_back_dup(c: Client, cb: CallbackQuery):
    # alias, already handled above but keep safe
    await rcl_back(c, cb)


@Client.on_message(filters.text & ~filters.command(["start","settings","download","auth","ban","log","cancel"]))
async def rclone_text_inputs(c: Client, msg: Message):
    state = await conversation_state.get(msg.from_user.id)
    if not state:
        return
    stage = state.get("stage")
    data = _state_data(state)
    cfg = _get_config_arg()
    if stage == "rclone_mkdir_name":
        _, current = _current_remote_and_path(data)
        name = msg.text.strip()
        code, out, err = await _run(f'rclone mkdir {cfg} "{current}/{name}"')
        await send_message(msg, out if out else (err or "Created"))
        await conversation_state.clear(msg.from_user.id)
    elif stage == "rclone_rename_text":
        _, current = _current_remote_and_path(data)
        try:
            old, new = [x.strip() for x in msg.text.split("|", 1)]
        except Exception:
            await send_message(msg, "Format: old|new")
            return
        code, out, err = await _run(f'rclone moveto {cfg} "{current}/{old}" "{current}/{new}"')
        await send_message(msg, out if out else (err or "Renamed"))
        await conversation_state.clear(msg.from_user.id)
    elif stage == "rclone_search_query":
        remote = data.get("remote", "")
        base = data.get("path", "")
        query = msg.text.strip().lower()
        target = f"{remote}{(base or '').strip('/')}/" if base else remote
        code, out, err = await _run(f'rclone lsjson {cfg} --fast-list --no-modtime --recursive "{target}"')
        results: List[Dict] = []
        if code == 0 and out:
            try:
                import json
                items = json.loads(out)
                for it in items:
                    name = it.get('Path') or it.get('Name')
                    if name and query in name.lower():
                        typ = 'dir' if it.get('IsDir') else ('dir' if str(name).endswith('/') else 'file')
                        results.append({"name": name, "type": typ})
            except Exception:
                pass
        # Show first 10 results as buttons that navigate to parent folder
        rows = []
        for i, r in enumerate(results[:10]):
            rows.append([InlineKeyboardButton(r["name"], callback_data=f"rcl_search_open:{i}")])
        await conversation_state.start(msg.from_user.id, stage="rclone_browse", data={"rcl_mode": "myfiles", "remote": remote, "path": base, "search_results": results})
        rows.append([InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")])
        rows.append([InlineKeyboardButton(lang.s.CLOSE_BUTTON, callback_data="close")])
        await send_message(msg, f"Found {len(results)} items (showing 10)", markup=InlineKeyboardMarkup(rows))
    elif stage == "rclone_flags_input":
        which = data.get("which")
        text = msg.text.strip()
        if which == 'copy':
            bot_set.rclone_copy_flags = text
            set_db.set_variable('RCLONE_COPY_FLAGS', text)
        elif which == 'upload':
            bot_set.rclone_upload_flags = text
            set_db.set_variable('RCLONE_UPLOAD_FLAGS', text)
        elif which == 'download':
            bot_set.rclone_download_flags = text
            set_db.set_variable('RCLONE_DOWNLOAD_FLAGS', text)
        await send_message(msg, "Saved")
        await conversation_state.clear(msg.from_user.id)
    elif stage == "rclone_serve_port":
        try:
            port = int(msg.text.strip())
        except Exception:
            await send_message(msg, "Invalid port")
            return
        await conversation_state.update(msg.from_user.id, port=port, stage="rclone_serve_ready")
        kb = [
            [InlineKeyboardButton(lang.s.RCLONE_SERVE_HTTP, callback_data="rcl_serve_http"), InlineKeyboardButton(lang.s.RCLONE_SERVE_WEBDAV, callback_data="rcl_serve_webdav")],
            [InlineKeyboardButton(lang.s.RCLONE_SERVE_STOP, callback_data="rcl_serve_stop")],
            [InlineKeyboardButton(lang.s.RCLONE_BACK, callback_data="rcl_back")],
        ]
        await send_message(msg, "Choose serve protocol:", markup=InlineKeyboardMarkup(kb))