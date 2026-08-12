"""
A general-purpose AI assistant with per-user memory.
Powered by Google's Gemini API under the hood.

Users sign up, chat with the assistant, and the assistant remembers
key facts about them across sessions (stored in SQLite, injected into
the prompt on each new message).
"""

import os
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")

DB_PATH = os.environ.get("DB_PATH", "assistant.db")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

ASSISTANT_NAME = os.environ.get("ASSISTANT_NAME", "Nova")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            fact TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ---------- Auth ----------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()

        if not email or not password:
            return render_template("signup.html", error="Email and password required")

        conn = get_db()
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            return render_template("signup.html", error="An account with that email already exists")

        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, generate_password_hash(password), name, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

        session["user_id"] = user_id
        session["name"] = name
        return redirect(url_for("chat"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("chat"))

        return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Chat ----------

@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("chat"))
    return redirect(url_for("login"))


@app.route("/chat")
def chat():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conn = get_db()
    history = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE user_id = ? ORDER BY id ASC",
        (session["user_id"],),
    ).fetchall()
    conn.close()

    return render_template(
        "chat.html",
        assistant_name=ASSISTANT_NAME,
        name=session.get("name") or "there",
        history=[dict(h) for h in history],
    )


def get_user_memory(user_id):
    conn = get_db()
    facts = conn.execute(
        "SELECT fact FROM memory WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,)
    ).fetchall()
    conn.close()
    return [f["fact"] for f in facts]


def save_memory_fact(user_id, fact):
    conn = get_db()
    conn.execute(
        "INSERT INTO memory (user_id, fact, created_at) VALUES (?, ?, ?)",
        (user_id, fact, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_recent_messages(user_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


def save_message(user_id, role, content):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


@app.route("/api/message", methods=["POST"])
def api_message():
    if not session.get("user_id"):
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    save_message(user_id, "user", user_message)

    if not GEMINI_API_KEY or not GENAI_AVAILABLE:
        reply = (
            "[DEMO MODE] No Gemini API key configured yet, so I can't "
            "generate a real reply. Add GEMINI_API_KEY to .env to enable "
            f"live responses. You said: \"{user_message}\""
        )
        save_message(user_id, "assistant", reply)
        return jsonify({"reply": reply})

    # Build context: known facts about this user + recent conversation
    memory_facts = get_user_memory(user_id)
    recent = get_recent_messages(user_id, limit=10)

    system_context = f"You are {ASSISTANT_NAME}, a helpful, warm AI assistant."
    if memory_facts:
        system_context += "\n\nThings you know about this user from past conversations:\n"
        system_context += "\n".join(f"- {fact}" for fact in memory_facts)

    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    prompt = f"{system_context}\n\nConversation so far:\n{conversation}\n\nRespond as {ASSISTANT_NAME}:"

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        reply = response.text
    except Exception as e:
        reply = f"Sorry, I ran into an error generating a response: {e}"

    save_message(user_id, "assistant", reply)

    # Very simple memory extraction: ask the model if anything worth
    # remembering long-term was said. Kept lightweight/best-effort.
    try:
        extract_prompt = (
            f"The user just said: \"{user_message}\"\n"
            "If this contains a durable fact worth remembering about the "
            "user for future conversations (their name, preferences, job, "
            "ongoing projects, etc.), reply with just that fact in one "
            "short sentence. If there's nothing worth remembering, reply "
            "with exactly: NONE"
        )
        model = genai.GenerativeModel("gemini-2.5-flash")
        extract_response = model.generate_content(extract_prompt)
        fact = extract_response.text.strip()
        if fact and fact.upper() != "NONE":
            save_memory_fact(user_id, fact)
    except Exception:
        pass  # memory extraction is best-effort, never block the chat reply

    return jsonify({"reply": reply})


init_db()

if __name__ == "__main__":
    app.run(debug=True)
