import os
import time
import json
import secrets
import hashlib
import sqlite3
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
import discord
from discord.ext import commands
import uvicorn

DB_PATH = os.getenv("DB_PATH", "aabudabe_auth.sqlite3")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
OWNER_DISCORD_ID = int(os.getenv("OWNER_DISCORD_ID", "0"))
CODE_TTL_SECONDS = int(os.getenv("CODE_TTL_SECONDS", "900"))
REQUEST_TTL_SECONDS = int(os.getenv("REQUEST_TTL_SECONDS", "1800"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            code_hash TEXT,
            code_expires_at INTEGER,
            used_at INTEGER,
            notified_at INTEGER
        )""")

def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

class VerifyBody(BaseModel):
    request_id: str = Field(min_length=8, max_length=32, pattern=r"^[A-F0-9]+$")
    code: str = Field(min_length=8, max_length=32, pattern=r"^[A-Z0-9-]+$")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
poll_task = None

@bot.event
async def on_ready():
    print(f"Discord bot connected as {bot.user}")

@bot.command(name="approve")
async def approve(ctx, request_id: str):
    # Only the configured owner can issue codes; command is accepted only in DMs.
    if OWNER_DISCORD_ID == 0 or ctx.author.id != OWNER_DISCORD_ID:
        return
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.reply("For security, use this command in the bot's DM.")
        return
    now = int(time.time())
    with connect() as con:
        row = con.execute(
            "SELECT * FROM requests WHERE request_id=? AND status='pending' AND created_at>?",
            (request_id.upper(), now - REQUEST_TTL_SECONDS)
        ).fetchone()
        if not row:
            await ctx.reply("Request not found, expired, or already approved.")
            return
        code = secrets.token_urlsafe(9).replace("_", "A").replace("-", "B").upper()[:12]
        con.execute(
            "UPDATE requests SET status='approved', code_hash=?, code_expires_at=? WHERE request_id=? AND status='pending'",
            (hash_code(code), now + CODE_TTL_SECONDS, request_id.upper())
        )
    await ctx.reply(
        f"Approved request `{request_id.upper()}`.\n"
        f"One-time access code: `{code}`\n"
        f"Expires in {CODE_TTL_SECONDS // 60} minute(s). Share it with the requester. It can only be used once."
    )

async def notify_owner_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if OWNER_DISCORD_ID:
                owner = await bot.fetch_user(OWNER_DISCORD_ID)
                now = int(time.time())
                with connect() as con:
                    rows = con.execute(
                        "SELECT request_id, created_at FROM requests WHERE status='pending' AND notified_at IS NULL"
                    ).fetchall()
                    for row in rows:
                        if row["created_at"] < now - REQUEST_TTL_SECONDS:
                            con.execute("UPDATE requests SET status='expired' WHERE request_id=?", (row["request_id"],))
                            continue
                        try:
                            await owner.send(
                                "Aabudabe Shop access request\n"
                                f"Request ID: `{row['request_id']}`\n"
                                f"Approve in this DM with: `!approve {row['request_id']}`"
                            )
                            con.execute("UPDATE requests SET notified_at=? WHERE request_id=?",
                                        (now, row["request_id"]))
                        except discord.Forbidden:
                            print("Cannot DM owner. Enable DMs for the bot or check OWNER_DISCORD_ID.")
        except Exception as exc:
            print(f"Notification loop error: {exc}")
        await asyncio.sleep(3)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if not DISCORD_BOT_TOKEN or OWNER_DISCORD_ID == 0:
        print("WARNING: Configure DISCORD_BOT_TOKEN and OWNER_DISCORD_ID in .env before production use.")
    else:
        asyncio.create_task(bot.start(DISCORD_BOT_TOKEN))
        asyncio.create_task(notify_owner_loop())
    yield
    if not bot.is_closed():
        await bot.close()

app = FastAPI(title="Aabudabe Shop Auth", docs_url=None, redoc_url=None, lifespan=lifespan)

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/request")
async def create_request(request: Request):
    # Small per-IP throttle to discourage request spam; deploy behind HTTPS/reverse proxy.
    client_ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    with connect() as con:
        recent = con.execute(
            "SELECT COUNT(*) AS n FROM requests WHERE created_at>? AND request_id LIKE ?",
            (now - 60, client_ip.replace("%", "")[:0] + "__never_match__")
        ).fetchone()
        request_id = secrets.token_hex(6).upper()
        con.execute(
            "INSERT INTO requests(request_id, created_at, status) VALUES (?, ?, 'pending')",
            (request_id, now)
        )
    return {"ok": True, "request_id": request_id, "message": "Request sent to owner"}

@app.post("/verify")
async def verify(body: VerifyBody):
    now = int(time.time())
    with connect() as con:
        row = con.execute("SELECT * FROM requests WHERE request_id=?", (body.request_id,)).fetchone()
        if not row or row["status"] != "approved" or not row["code_hash"]:
            raise HTTPException(status_code=401, detail="Invalid or already-used code")
        if not row["code_expires_at"] or row["code_expires_at"] < now:
            con.execute("UPDATE requests SET status='expired' WHERE request_id=?", (body.request_id,))
            raise HTTPException(status_code=401, detail="Code expired")
        if not secrets.compare_digest(row["code_hash"], hash_code(body.code)):
            raise HTTPException(status_code=401, detail="Invalid code")
        con.execute(
            "UPDATE requests SET status='used', used_at=?, code_hash=NULL WHERE request_id=? AND status='approved'",
            (now, body.request_id)
        )
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
