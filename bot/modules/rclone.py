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
    if mode not in ("copy_src", "move_src"):
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


@Client.on_callback_query(filters.regex(pattern=r"^rcl_back$"))
async def rcl_back_dup(c: Client, cb: CallbackQuery):
    # alias, already handled above but keep safe
    await rcl_back(c, cb)