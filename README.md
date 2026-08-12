# Nova — Your Own AI Assistant

A general-purpose AI assistant, open to anyone, with per-user memory. Powered
by Google's Gemini API under the hood — this app provides the sign-up/login,
chat interface, and memory system; Gemini handles the actual language
understanding.

## How memory works

Every message the user sends is scanned for durable facts worth remembering
(name, preferences, ongoing projects, etc.). Those get stored per-user and
injected into future conversations — so the assistant "remembers" a user
across sessions, similar to how this works in mainstream AI assistants.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Add your Gemini API key to `.env` (free at https://aistudio.google.com/apikey).
Without a key, the app runs in demo mode with placeholder replies so you can
test the full sign-up/chat flow first.

```bash
python app.py
```

Visit `http://localhost:5000`

## Renaming your assistant

Change `ASSISTANT_NAME` in `.env` to whatever you want it called.

## Structure

```
nova-assistant/
├── app.py                  # Flask app, auth, chat, memory logic
├── requirements.txt
├── Procfile                 # For deployment (Render/Railway)
├── .env.example
├── templates/
│   ├── base.html
│   ├── signup.html
│   ├── login.html
│   └── chat.html
└── static/
    ├── css/style.css
    └── js/chat.js
```

## Deploying

Same as gh-data-link — push to Render or Railway, connect this repo, add
your `GEMINI_API_KEY` and `SECRET_KEY` as environment variables, deploy.
