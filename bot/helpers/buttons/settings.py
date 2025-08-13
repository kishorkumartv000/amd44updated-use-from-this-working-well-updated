import bot.helpers.translations as lang
from bot.settings import bot_set
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config

main_button = [[InlineKeyboardButton(text=lang.s.MAIN_MENU_BUTTON, callback_data="main_menu")]]
close_button = [[InlineKeyboardButton(text=lang.s.CLOSE_BUTTON, callback_data="close")]]

def main_menu():
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=lang.s.CORE,
                callback_data='corePanel'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.TELEGRAM,
                callback_data='tgPanel'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.PROVIDERS,
                callback_data='providerPanel'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.RCLONE,
                callback_data='rclonePanel'
            )
        ]
    ]
    inline_keyboard += close_button
    return InlineKeyboardMarkup(inline_keyboard)

def providers_button():
    inline_keyboard = []
    
    # Always show Apple Music button
    inline_keyboard.append([
        InlineKeyboardButton("🍎 Apple Music", callback_data="appleP")
    ])
    
    # Apple-only build: hide other providers
    
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

def tg_button():
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=lang.s.BOT_PUBLIC.format(bot_set.bot_public),
                callback_data='botPublic'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.ANTI_SPAM.format(bot_set.anti_spam),
                callback_data='antiSpam'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.LANGUAGE,
                callback_data='langPanel'
            )
        ]
    ]

    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

def core_buttons():
    inline_keyboard = []

    if bot_set.rclone:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"Return Link : {bot_set.link_options}",
                    callback_data='linkOption'
                )
            ]
        )

    inline_keyboard += [
        [
            InlineKeyboardButton(
                text=f"Upload : {bot_set.upload_mode}",
                callback_data='upload'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.SORT_PLAYLIST.format(bot_set.playlist_sort),
                callback_data='sortPlay'
            ),
            InlineKeyboardButton(
                text=lang.s.DISABLE_SORT_LINK.format(bot_set.disable_sort_link),
                callback_data='sortLinkPlay'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.PLAYLIST_ZIP.format(bot_set.playlist_zip),
                callback_data='playZip'
            ),
            InlineKeyboardButton(
                text=lang.s.PLAYLIST_CONC_BUT.format(bot_set.playlist_conc),
                callback_data='playCONC'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.ARTIST_BATCH_BUT.format(bot_set.artist_batch),
                callback_data='artBATCH'
            ),
            InlineKeyboardButton(
                text=lang.s.ARTIST_ZIP.format(bot_set.artist_zip),
                callback_data='artZip'
            )
        ],
        [
            InlineKeyboardButton(
                text=lang.s.ALBUM_ZIP.format(bot_set.album_zip),
                callback_data='albZip'
            ),
            InlineKeyboardButton(
                text=lang.s.POST_ART_BUT.format(bot_set.art_poster),
                callback_data='albArt'
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Video Upload: {'Document' if bot_set.video_as_document else 'Media'}",
                callback_data='vidUploadType'
            ),
            InlineKeyboardButton(
                text=f"Audio Upload: {'Document' if bot_set.audio_as_document else 'Audio'}",
                callback_data='audUploadType'
            )
        ]
    ]
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

def language_buttons(languages, selected):
    inline_keyboard = []
    for item in languages:
        text = f"{item.__language__} ✅" if item.__language__ == selected else item.__language__
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=text.upper(),
                    callback_data=f'langSet_{item.__language__}'
                )
            ]
        )
    inline_keyboard += main_button + close_button
    return InlineKeyboardMarkup(inline_keyboard)

# Apple Music specific buttons
def apple_button(formats):
    """Create buttons for Apple Music settings"""
    buttons = []
    for fmt, label in formats.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"appleF_{fmt}")])
    buttons.append([InlineKeyboardButton("Quality Settings", callback_data="appleQ")])
    # Wrapper controls
    buttons.append([
        InlineKeyboardButton("🧩 Setup Wrapper", callback_data="appleSetup"),
        InlineKeyboardButton("⏹️ Stop Wrapper", callback_data="appleStop")
    ])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="providerPanel")])
    return InlineKeyboardMarkup(buttons)
