
# Project-Siesta
![GitHub Repo stars](https://img.shields.io/github/stars/vinayak-7-0-3/Project-Siesta?style=for-the-badge)
![GitHub forks](https://img.shields.io/github/forks/vinayak-7-0-3/Project-Siesta?style=for-the-badge)
![Docker Pulls](https://img.shields.io/docker/pulls/weebzbots/project-siesta?style=for-the-badge)
[![Static Badge](https://img.shields.io/badge/support-pink?style=for-the-badge)](https://t.me/weebzgroup)

AIO Bot for your music needs on Telegram.

Note: This is not a music streaming / VC Bot

## FEATURES

**Currently the project is in early development stage and features are incomplete**

Feels free to check the repo and report bugs / features

**A complete guide for ~~downloading~~ (coughs..) ehmm.... can be found [here](https://rentry.org/project-siesta)**

## INSTALLATION


#### 1) LOCAL DEPLOYMENT

**Requirements**
- Python>=3.10 (3.12 recommended) 
- Git installed (optional)
- Rclone (optional)
- ffmpeg (optional)

**Steps**
- Git clone (or download) the repo
- Create virtual environment and run
```
virtualenv -p python3 VENV
. ./VENV/bin/activate
```
- Edit and fill out the essentials environment variables in `sample.env` (refer [here](#variables-info))
- Rename `sample.env` to `.env`
- Finally run
```
pip install -r requirements.txt
python -m bot
```

#### 2) USING DOCKER (Manual Build)
**Requirements**
- Git installed (optional)
- Of course Docker installed (how would ya do docker method without docker  🤷‍)

**Steps**
- Git clone (or download) the repo
- Fill out the required variables in `sample.env` (refer [here](#variables-info))
- Build the image using the Docker build command
```
sudo docker build . -t project-siesta
```
- Now run the created Docker image
```
sudo docker run -d --env-file sample.env --name siesta project-siesta
```
- At this point your bot will be running (if everything correct)

#### 3) USING DOCKER (Prebuilt Image)

Premade Docker Images are available at Dockerhub repo `weebzbots/project-siesta`
These images are made using GitHub Actions
- Supported architectures
	- `arm64`
	- `amd64`
- Build Tags
	- `latest` - Latest stable releases from main branch
	- `beta` - Latest beta releases from beta branch (early feature testing)
	- `<commit-hash>` - You can use specific commit hash for specific versions

**Requirements**
- Of course Docker installed (how would ya do docker method without docker  🤷‍)

**Steps**
- Pull the Docker image
```
sudo docker pull weebzcloud/project-siesta
```
- Somewhere in your server, create a `.env` file with required variables (refer [here](#variables-info))
- Run the image
```
sudo docker run -d --env-file .env --name siesta project-siesta
```
- At this point your bot will be running (if everything correct)

## VARIABLES INFO

#### ESSENTIAL VARIABLES
- `TG_BOT_TOKEN` - Telegeam bot token (get it from [BotFather](https://t.me/BotFather))
- `APP_ID` - Your Telegram APP ID (get it from my.telegram.org) `(int)`
- `API_HASH` - Your Telegram APP HASH (get it from my.telegram.org) `(str)`
- `DATABASE_URL` - Postgres database URL (self hosted or any service) `(str)`
- `BOT_USERNAME` - Your Telegram Bot username (with or without `@`) `(str)`
- `ADMINS` - List of Admin users for the Bot (seperated by space) `(str)`

#### OPTIONAL VARIABLES
- `DOWNLOAD_BASE_DIR` - Downloads folder for the bot (folder is inside the working directory of bot) `(str)`
- `LOCAL_STORAGE` - Folder (full path needed) where you want to store the downloaded file the server itself rather than uploading `(str)`
- `RCLONE_CONFIG` - Rclone config as text or URL to file (can ignore this if you add file manually to root of repo) `(str)`
- `RCLONE_DEST` - Rclone destination as `remote-name:folder-in-remote` `(str)`
- `INDEX_LINK` - If index link needed for Rclone uploads (testes with alist) (no trailing slashes `/` ) `(str)`
- `MAX_WORKERS` - Multithreading limit (kind of more speed) `(int)`
- `TRACK_NAME_FORMAT` - Naming format for tracks (check [metadata](https://github.com/vinayak-7-0-3/Project-Siesta/blob/2bbea8572d660a92bb182a360e91791583f4523b/bot/helpers/metadata.py#L16) section for tags supported) `(str)`
- `PLAYLIST_NAME_FORMAT` - Similar to `TRACK_NAME_FORMAT` but for Playlists (Note: all tags might not be available) `(str)`

## Rclone Features and Usage

The bot includes a full Rclone integration accessible from Telegram.

- Location: `Settings -> Rclone`
- Requirements:
  - A working `rclone.conf` with at least one remote configured
  - rclone binary is bundled in Docker image; for local runs install rclone (`apt install rclone`)

### What you can do

- Import rclone.conf from Telegram
  - Tap `📥 Import rclone.conf` and send your `rclone.conf` file to the bot
  - The file is saved and used automatically; no restarts needed

- Set upload path (destination) from Telegram
  - Tap `📂 Set Upload Path`
  - Pick a remote, browse to the desired folder, tap `Select this folder`
  - Destination is saved in the database and used for future Rclone uploads
  - You can still set `RCLONE_DEST` via env; Telegram setting overrides it at runtime

- Browse Rclone remotes
  - Tap `🗂️ Browse Remotes`
  - Navigate folders with `⬆️ Up`, `◀️ Prev`, `Next ▶️`
  - View both folders and files as buttons

- Cloud → Cloud copy/move
  - Tap `📄 Cloud → Cloud Copy` or `📦 Cloud → Cloud Move`
  - Pick a source remote/file, then pick destination remote/folder
  - The bot runs `rclone copy`/`rclone move` with progress in the background

### How uploads work with Rclone

- In `/settings -> CORE`, set `Upload` to `RCLONE` (visible once `rclone.conf` is present)
- When a download finishes, the bot constructs a relative path and requests a share link using:
  - `rclone link --config <detected_config_path> "<RCLONE_DEST>/<relative_path>"` (detected_config_path = `/workspace/rclone.conf` if present, else `./rclone.conf`)
- If `INDEX_LINK` is set, an Index URL is also produced
- Link return options in CORE settings:
  - `False`: No links
  - `Index`: Only Index link
  - `RCLONE`: Only Rclone link
  - `Both`: Both links

### Where files are stored

- `rclone.conf` path: `/workspace/rclone.conf` preferred; falls back to `./rclone.conf` if present
- Destination: `RCLONE_DEST` stored in DB (overrides `.env` at runtime)

### Troubleshooting

- No remotes shown: Verify your `rclone.conf` contains remotes (e.g., run `rclone listremotes` locally)
- Copy/Move fails: Check both source and destination are accessible by your remote and you have permissions
- Links are empty: Ensure `RCLONE_LINK_OPTIONS` in CORE settings is `RCLONE` or `Both`
- Index link wrong: Ensure `INDEX_LINK` has no trailing `/`

### Mounted remote browsing and server-side copy/move

- New: In `Settings -> Rclone` you can:
  - Browse your rclone remotes and navigate folders with paging
  - Set the upload destination path directly from Telegram
  - Perform cloud→cloud Copy/Move using rclone
  - Mount and unmount remotes (container must allow FUSE)

### Manual install inside a running container (for mounting)

If you are testing inside a container and need to enable rclone mount manually without rebuilding:

```bash
# Install FUSE and dependencies (Debian/Ubuntu base)
apt-get update && apt-get install -y fuse3 pkg-config libfuse3-3 ca-certificates

# Allow fuse mounts inside the container (requires privileged caps at run)
# When starting the container, add:
#   --cap-add SYS_ADMIN --device /dev/fuse --security-opt apparmor:unconfined

# Verify rclone exists
rclone version

# Optional: check that fuse is available
ls -l /dev/fuse
```

Run-time flags required at container start to allow mounting:

- `--cap-add SYS_ADMIN`
- `--device /dev/fuse`
- `--security-opt apparmor:unconfined` (or equivalent SELinux/AppArmor relaxations)

Example run command:

```bash
docker run -d \
  --env-file .env \
  --name siesta \
  --cap-add SYS_ADMIN \
  --device /dev/fuse \
  --security-opt apparmor:unconfined \
  project-siesta
```

Notes:
- rclone config path detection prefers `/workspace/rclone.conf`, then `./rclone.conf`, or `Config.RCLONE_CONFIG` if it points to an existing file.
- If mounts still fail, ensure the host kernel supports FUSE and the container runtime allows it.

### Additional Rclone features in this build

- My Files manager
  - Open: Settings -> Rclone -> 📂 My Files
  - Pick a remote, then browse. Use Folder Options to:
    - 🔍 Search: enter a query to find files/folders (recursive)
    - 📏 Size: show size of current path
    - ℹ️ Remote Usage: show remote quota/usage (rclone about)
    - 📁 Make Folder: create a subfolder in current directory
    - ↪️ Rename Item: send `old|new` to rename item in current directory
    - 🗑️ Delete Empty Dirs: delete empty directories below current path
    - 🧹 Dedupe (Drive): resolve duplicate objects on Google Drive remotes

- Remote → Local (Leech)
  - Open: Settings -> Rclone -> 📥 Remote → Local (Leech)
  - Pick a remote, select a file or folder; the bot runs `rclone copy` to local storage under `${LOCAL_STORAGE}/{user_id}/leech`.
  - Progress and Cancel: progress appears inline; tap Cancel to stop.

- Sync (source → destination identical)
  - Open: Settings -> Rclone -> 🔁 Sync (Dangerous)
  - Pick source remote/folder, then pick destination remote/folder
  - You will be asked to confirm; sync will modify destination to match source (may delete)
  - Advanced flag “Server-side across configs” can be toggled in Advanced Flags
  - Progress and Cancel supported

- Multi-remote Mirror
  - Open: Settings -> Rclone -> 📡 Multi-remote Mirror
  - Select one or more destination remotes, then choose a source remote/folder
  - The bot mirrors source to each selected destination sequentially

- Serve HTTP/WebDAV (optional)
  - Toggle availability in Advanced Flags (OFF by default)
  - Open: Settings -> Rclone -> 🌐 Serve (Optional)
  - Pick remote, then send a TCP port (e.g., 8080)
  - Choose Start HTTP or Start WebDAV; the bot starts `rclone serve` with that remote
  - Stop via “Stop Serve” button
  - Requires container/network permissions and open ports

- Advanced Rclone Flags
  - Open: Settings -> Rclone -> ⚙️ Advanced Flags
  - Options:
    - Toggle “Server-side across configs”: enables `--server-side-across-configs` for sync (where supported)
    - Set Copy Flags / Upload Flags / Download Flags: accept comma-separated flags like `--fast-list,--no-modtime`
    - Clear each set to reset
  - Benefits:
    - Server-side copy/sync reduces egress and speeds up transfers within providers
    - `--fast-list` and `--no-modtime` can improve list performance and reduce API calls
    - Tailor behavior for provider quirks and performance

- Remote Search
  - Available within My Files -> 🔍 Search
  - Enter a query; first 10 matches are listed. Selecting a result opens its parent directory in the browser

- Progress + Cancel for long ops
  - Copy/Move/Leech/Sync/Mirror show a live “Transferred:” line
  - A Cancel button allows stopping the active rclone process

---

## CREDITS
- OrpheusDL - https://github.com/yarrm80s/orpheusdl
- Streamrip - https://github.com/nathom/streamrip
- yaronzz - Tidal-Media-Downloader - https://github.com/yaronzz/Tidal-Media-Downloader
- vitiko98 - qobuz-dl - https://github.com/vitiko98/qobuz-dl

## Support Me ❤️
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I7FWQZ4)

TON - `UQBBPkWSnbMWXrM6P-pb96wYxQzLjZ2hhuYfsO-N2pVmznCG`

## Apple Wrapper Controls (Apple Music)

- **Location**: `Settings -> Providers -> Apple Music`
- **Buttons**:
  - `🧩 Setup Wrapper`: Starts an interactive setup that asks for your Apple ID username and password, then runs the wrapper setup script with those credentials. If 2FA is required, the bot will detect it and prompt you to send the 2FA code, then continues automatically.
  - `⏹️ Stop Wrapper`: Stops any running wrapper process. Includes a confirmation step to prevent accidental taps.

### How Setup Works
1. Tap `🧩 Setup Wrapper`.
2. Send your Apple ID username when asked.
3. Send your Apple ID password when asked.
4. The bot runs the setup script with `USERNAME` and `PASSWORD` exported in the environment, equivalent to:
   ```bash
   USERNAME="your_username" PASSWORD="your_password" /usr/src/app/downloader/setup_wrapper.sh
   ```
5. If the wrapper requests 2FA, you will see a prompt. Send the 2FA code as a normal message within 3 minutes.
6. On success, you'll get a confirmation. On failure, the last part of the script output is shown for debugging.

### How Stop Works
- Tap `⏹️ Stop Wrapper` -> Confirm. The bot runs:
  ```bash
  /usr/src/app/downloader/stop_wrapper.sh
  ```
- It kills wrapper processes and frees ports 10020/20020.

### Configuration
- Override script paths with env vars if needed:
  - `APPLE_WRAPPER_SETUP_PATH` (default `/usr/src/app/downloader/setup_wrapper.sh`)
  - `APPLE_WRAPPER_STOP_PATH` (default `/usr/src/app/downloader/stop_wrapper.sh`)

### Notes & Security
- Credentials are only used to start the setup process and are not stored by the bot.
- You can cancel the flow any time by sending `/cancel`.
- If 2FA prompt does not appear (rare), setup continues and completes automatically.

## Commands and Usage

These commands work in any chat where the bot is present. Copy-paste directly into Telegram.

- /start: Show welcome message
- /help: Show available commands
- /settings: Open settings panel
- /download <url> [--options]: Start a download for a supported provider
This build is Apple Music–only. Qobuz, Tidal, and Deezer integrations have been removed. Use Apple Music links like `https://music.apple.com/...`.
  - Examples:
    - ```
/download https://music.apple.com/…
    ```
    - ```
/download --alac-max 192000 https://music.apple.com/…
    ```
    - Reply to a message containing the link and send:
      ```
/download --atmos
      ```
  - On start, the bot replies with a Task ID. Use it to manage the task.
- /cancel <task_id>: Cancel a specific running task by its ID
  - Example:
    ```
/cancel ab12cd34
    ```
- /cancel_all: Cancel all your running tasks (download, zipping, uploading)
  - Example:
    ```
/cancel_all
    ```
- /status: Show real-time status for your ongoing tasks (downloading, zipping, uploading, uptime). Designed to be lightweight and non-blocking, so it won’t interrupt active tasks.
  - Example:
    ```
/status
    ```
- /history (alias /downloads): Show your personal download history with title, artist, type, quality, and date.
  - Example:
    ```
/history
    ```

### What happens on cancel
- The bot stops the active step (downloading, zipping, uploading)
- Any partial files/archives are cleaned up automatically
- The progress message is updated to indicate cancellation

### Realtime system usage in progress
- Progress messages now include CPU, RAM, and Disk usage to help monitor server load while tasks run.

## Apple Music Config (config.yaml) via Telegram

Admins can view and edit `/root/amalac/config.yaml` in real time. Changes are written safely with a backup created each time.

Path override: set env `APPLE_CONFIG_YAML_PATH` to a different file if needed.

### Commands

- /config or /cfg: Show quick help and path
- /config_show [keys...]: Show current values for a curated list or specific keys
- /config_get <key>: Show current value of a key (sensitive values are masked)
- /config_set <key> <value>: Set key to value (with validation where applicable)
- /config_toggle <bool-key>: Toggle a boolean key between true/false

### Supported Keys and Validation

- Choice keys:
  - lrc-type: lyrics | syllable-lyrics
  - lrc-format: lrc | ttml
  - cover-format: jpg | png | original
  - mv-audio-type: atmos | ac3 | aac
- Boolean keys:
  - embed-lrc
  - save-lrc-file
  - save-artist-cover
  - save-animated-artwork
  - emby-animated-artwork
  - embed-cover
  - dl-albumcover-for-playlist
- Integer keys:
  - mv-max (e.g., 2160)
- Sensitive keys (masked in outputs; will be auto-quoted on set):
  - media-user-token
  - authorization-token

Other common keys you can set directly with /config_set:
- cover-size (e.g., `5000x5000`)
- alac-save-folder, atmos-save-folder, aac-save-folder (folders are auto-created if missing)
- alac-max, atmos-max, aac-type, storefront, language

### Examples

```text
/config_show
/config_get storefront
/config_set storefront in
/config_set lrc-type lyrics
/config_set lrc-format lrc
/config_toggle embed-lrc
/config_toggle save-artist-cover
/config_set cover-format png
/config_set cover-size 5000x5000
/config_set mv-audio-type atmos
/config_set mv-max 2160
/config_set media-user-token "<your_token_here>"
/config_set alac-save-folder "/usr/src/app/bot/DOWNLOADS/5329535193/Apple Music/alac"
```

Note: If the Apple downloader runs persistently, restart it after updating critical values (tokens, formats) so it reloads the file.

## BotFather command list (copy-paste)

```text
start - Start the bot
help - Show help
settings - Open settings panel
download - Start a download
cancel - Cancel a running task by ID
cancel_all - Cancel all your running tasks
status - Show status of ongoing tasks
history - Show your download history
config - Config help for Apple Music YAML
config_show - Show config values (or specific keys)
config_get - Get a single config value
config_set - Set a config value
config_toggle - Toggle a boolean config value
log - Get the bot log
auth - Authorize a user or chat
ban - Ban a user or chat
```