class EN(object):
    __language__ = 'en'
#----------------
#
# BASICS
#
#----------------
    WELCOME_MSG = "Hello {}"
    DOWNLOADING = 'Downloading........'
    DOWNLOAD_PROGRESS = """
<b>╭─ Progress
│
├ {0}
│
├ Done : <code>{1} / {2}</code>
│
├ Title : <code>{3}</code>
│
╰─ Type : <code>{4}</code></b>
"""
    UPLOADING = 'Uploading........'
    ZIPPING = 'Zipping........'
    TASK_COMPLETED = "Download Finished"




#----------------
#
# SETTINGS PANEL
#
#----------------
    INIT_SETTINGS_PANEL = '<b>Welcome to Bot Settings</b>'
    LANGUAGE_PANEL = 'Select bot language here'
    CORE_PANEL = 'Edit main settings here'
    PROVIDERS_PANEL = 'Configure each platform seperartelty'
    RCLONE_PANEL = '<b>Rclone Settings</b>'
    RCLONE_STATUS = 'Status: {}'
    RCLONE = 'Rclone'
    RCLONE_UPLOAD_PATH = 'Upload Path: {}'
    RCLONE_REMOTE_BROWSE = '🗂️ Browse Remotes'
    RCLONE_SET_UPLOAD_PATH = '📂 Set Upload Path'
    RCLONE_IMPORT_CONF = '📥 Import rclone.conf'
    RCLONE_COPY = '📄 Cloud → Cloud Copy'
    RCLONE_MOVE = '📦 Cloud → Cloud Move'
    RCLONE_BACK = '🔙 Back'
    RCLONE_SEND_CONF = 'Please send your rclone.conf file here.'
    RCLONE_CONF_SAVED = '✅ rclone.conf saved.'
    RCLONE_DEST_SET = '✅ Upload path set to {}'
    RCLONE_BROWSE_HEADER = '<b>Browsing:</b> {}'
    RCLONE_BROWSE_NEXT = 'Next ▶️'
    RCLONE_BROWSE_PREV = '◀️ Prev'
    RCLONE_BROWSE_UP = '⬆️ Up'
    RCLONE_SELECT_THIS = 'Select this folder'
    RCLONE_PICK_SOURCE = 'Pick source'
    RCLONE_PICK_DEST = 'Pick destination'
    RCLONE_OP_IN_PROGRESS = 'Operation running...'
    RCLONE_OP_DONE = '✅ Operation completed.'
    RCLONE_OP_FAILED = '❌ Operation failed: {}'

    

    TELEGRAM_PANEL = """
<b>Telegram Settings</b>

Admins : {2}
Auth Users : {3}
Auth Chats : {4}
"""
    BAN_AUTH_FORMAT = 'Use /command {userid}'
    BAN_ID = 'Removed {}'
    USER_DOEST_EXIST = "This ID doesn't exist"
    USER_EXIST = 'This ID already exist'
    AUTH_ID = 'Successfully Authed'





#----------------
#
# BUTTONS
#
#----------------
    MAIN_MENU_BUTTON = 'MAIN MENU'
    CLOSE_BUTTON = 'CLOSE'
    PROVIDERS = 'PROVIDERS'
    TELEGRAM = 'Telegram'
    CORE = 'CORE'
    


    BOT_PUBLIC = 'Bot Public - {}'
    BOT_LANGUAGE = 'Language'
    ANTI_SPAM = 'Anit Spam - {}'
    LANGUAGE = 'Language'
    QUALITY = 'Quality'
    AUTHORIZATION = "Authorizations"

    POST_ART_BUT = "Art Poster : {}"
    SORT_PLAYLIST = 'Sort Playlist : {}'
    DISABLE_SORT_LINK = 'Disable Sort Link : {}'
    PLAYLIST_CONC_BUT = "Playlist Batch Download : {}"
    PLAYLIST_ZIP = 'Zip Playlist : {}'
    ARTIST_BATCH_BUT = 'Artist Batch Upload : {}'
    ARTIST_ZIP = 'Zip Artist : {}'
    ALBUM_ZIP = 'Zip Album : {}'





    RCLONE_LINK = 'Direct Link'
    INDEX_LINK = 'Index Link'
#----------------
#
# ERRORS
#
#----------------
    ERR_NO_LINK = 'No link found :('
    ERR_LINK_RECOGNITION = "Sorry, couldn't recognise the given link."


#----------------
#
# ERRORS
#
#----------------

#----------------
#
# TRACK & ALBUM POSTS
#
#----------------
    ALBUM_TEMPLATE = """
🎶 <b>Title :</b> {title}
👤 <b>Artist :</b> {artist}
📅 <b>Release Date :</b> {date}
🔢 <b>Total Tracks :</b> {totaltracks}
📀 <b>Total Volumes :</b> {totalvolume}
💫 <b>Quality :</b> {quality}
📡 <b>Provider :</b> {provider}
🔞 <b>Explicit :</b> {explicit}
"""

    PLAYLIST_TEMPLATE = """
🎶 <b>Title :</b> {title}
🔢 <b>Total Tracks :</b> {totaltracks}
💫 <b>Quality :</b> {quality}
📡 <b>Provider :</b> {provider}
"""

    SIMPLE_TITLE = """
Name : {0}
Type : {1}
Provider : {2}
"""

    ARTIST_TEMPLATE = """
👤 <b>Artist :</b> {artist}
💫 <b>Quality :</b> {quality}
📡 <b>Provider :</b> {provider}
"""
