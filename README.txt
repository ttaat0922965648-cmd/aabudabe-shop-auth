# Aabudabe Shop — Discord one-time access codes

## How it works
1. User launches `Aabudabe_Shop.bat`; Windows requests administrator permission first, then the app creates a request ID through the API.
2. The bot DMs the configured owner with the request ID.
3. Owner replies in the bot DM: `!approve REQUESTID`
4. The bot DMs the owner a random one-time code.
5. Owner shares that code with the user. The code expires after 15 minutes by default and can be used once.
6. After verification, the original Aabudabe Shop menu and optimization actions continue.

## Important setup
This is a source starter, not a hosted service. You must deploy `server.py` to a public HTTPS host and set that URL in the BAT file. Do not distribute the BAT until this is configured.

### 1. Create a Discord bot
- In Discord Developer Portal, create an application and add a Bot.
- Enable **Message Content Intent** for prefix commands.
- Invite the bot with permission to read/send messages.
- Keep the bot token private. Never put it in the BAT file or share it with users.
- Get your Discord User ID (enable Developer Mode, right-click your profile, Copy User ID).

### 2. Configure server
- Copy `.env.example` to `.env`.
- Set `DISCORD_BOT_TOKEN` and `OWNER_DISCORD_ID`.
- Install Python 3.11+ then run:
  ```sh
  pip install -r requirements.txt
  python server.py
  ```
- Deploy behind HTTPS (for example, a Python host with a persistent disk). Keep the SQLite database persistent.
- For production, configure HTTPS and request rate limiting at the hosting/reverse-proxy layer.

### 3. Configure client
Open `Aabudabe_Shop.bat` in Notepad and replace:
`https://YOUR-SERVER-DOMAIN.example`
with your real HTTPS server URL (no trailing slash).

### 4. Owner approval
When you receive a DM containing a request ID, reply to the bot in that DM:
`!approve ABCDEF123456`
The bot sends the code only to the configured owner. Share it with the intended user yourself.

## Security notes
- Codes are random, expire, and are consumed once.
- The bot only accepts approvals from the configured owner ID and only in DMs.
- The client is a BAT file and can be edited by end users; this gate is an access check, not strong DRM. A determined user can modify a local BAT. For stronger protection, move sensitive functionality to a server-side application.
- Do not expose port 8000 directly without HTTPS/reverse proxy. Add host-level rate limiting before public use.
