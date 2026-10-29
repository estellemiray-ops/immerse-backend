# Immerse — backend

FastAPI + Postgres. Handles accounts, pulling/aligning YouTube subtitles, word
lessons, the flashcard scheduler, story generation, translation, grammar
checking, book recommendations, chat, and real Mandarin TTS audio. This is
the piece your phone app talks to.

## What's real here (not a mock)

- **AI**: [Groq](https://groq.com) — a free API serving open-source models
  (`qwen/qwen3-32b` for text, `whisper-large-v3-turbo` for audio). No credit
  card required.
- **Captions**: `youtube-transcript-api` pulls YouTube's captions, but only
  if they're **creator-uploaded** — YouTube's own auto-captions are
  frequently wrong on tones/word-boundaries, so this app skips them and
  falls through to Whisper instead, which is more reliable.
- **No-caption fallback**: `yt-dlp` downloads audio, Groq's hosted Whisper
  transcribes it. Runs for most videos, since most don't have creator captions.
- **Lessons, alignment, story writing, chat, translation, grammar checking,
  book recommendations**: Groq (`qwen/qwen3-32b`).
- **Pronunciation audio**: `edge-tts` — a real neural Mandarin voice, free,
  no key needed at all.
- **Flashcards**: an actual SM-2-style spaced repetition scheduler, same
  family of algorithm as Anki.
- **Accounts**: email/password with JWT, so your library lives on the
  server, not just one device.
- **Hosting**: Render (free web service) + Neon (free, permanent Postgres).
  Both genuinely free, no card, no trial clock.

## 1. Get a Groq API key (free, no credit card)

1. **console.groq.com** → sign up
2. **console.groq.com/keys** → Create API Key → name it → Submit
3. Copy it (`gsk_...`) somewhere safe — shown only once

## 2. Create a free Postgres database on Neon (free, no credit card)

Render's *own* free database expires after 30 days and gets deleted — not
something you want for a library you're building up over months. Neon's free
tier is permanent instead, so the database lives here and the backend (on
Render) just connects to it.

1. Go to **neon.tech** → sign up (no card)
2. Create a project (any name/region)
3. On the project dashboard, find the **connection string** — looks like
   `postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require`
4. Copy the whole thing — you'll paste it into Render in step 4 as `DATABASE_URL`

## 3. Create a Render account (free, no credit card)

1. Go to **render.com** → sign up with GitHub (easiest, since you'll deploy
   straight from a repo)

## 4. Push this folder to GitHub, then deploy on Render

```bash
cd immerse-backend
git init
git add .
git commit -m "Immerse backend"
```

Create a new empty repo at **github.com/new** (e.g. `immerse-backend`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/immerse-backend.git
git branch -M main
git push -u origin main
```

Then on Render:

1. Dashboard → **New** → **Blueprint** → connect the `immerse-backend` repo.
   Render reads `render.yaml` and sets up the web service automatically
   (it builds from the included `Dockerfile`, which also installs `ffmpeg`
   for the Whisper fallback path).
2. It'll prompt you for the three secret env vars it found in `render.yaml`:
   - `GROQ_API_KEY` = the key from step 1
   - `JWT_SECRET` = a random string — generate one with
     `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `DATABASE_URL` = the Neon connection string from step 2
3. Deploy. First build takes a few minutes (installing ffmpeg + dependencies).
4. Once live, Render gives you a URL like `immerse-backend.onrender.com` —
   **this is your API's base URL**, needed for the mobile app next.
5. Visit `https://YOUR-DOMAIN/health` — should show `{"status":"ok"}`.
6. Visit `https://YOUR-DOMAIN/docs` for interactive API docs.

### The one real tradeoff of free hosting

Render's free web service **sleeps after 15 minutes with no traffic**, and
takes ~30–60 seconds to wake up on the next request. For a personal app this
just means: the first thing you do after not using Immerse for a while will
feel slow for one request, then it's normal speed again. Nothing to fix —
just worth knowing so it doesn't look broken. (Neon's database does something
similar — auto-suspends after 5 min idle, wakes automatically in under a
second, no action needed.)

## Local development (optional)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY at least
uvicorn app.main:app --reload
```

Without `DATABASE_URL` set, it falls back to a local SQLite file
(`immerse.db`) — fine for development only.

## A note on the open-source model choice

`qwen/qwen3-32b` was picked for Chinese-language quality. If quality ever
feels off, two alternatives (set `GROQ_MODEL` as a Render env var):
- `deepseek-r1-distill-llama-70b` — also strong at Chinese, slower
- `llama-3.3-70b-versatile` — faster, weaker Chinese, more consistent
  strict-JSON output

## API surface

| Endpoint | What it does |
|---|---|
| `POST /auth/register`, `/auth/login` | account creation / login → JWT |
| `POST /videos` | `{youtube_url}` → fetches + aligns subtitles, returns tappable lines |
| `GET /videos`, `/videos/{id}` | revisit previously processed videos |
| `POST /words/learnt` | tap a word → mark yellow |
| `POST /words/lesson` | long-press a word → full mini-lesson |
| `POST /words/save` | Save button → lavender + adds SRS cards |
| `GET /words` | full library |
| `GET /review/queue` | cards due right now, across all 4 types |
| `POST /review/grade` | `{zh, card_type, grade}` → reschedules |
| `POST /story/generate` | writes a story from your library |
| `POST /chat` | `{channel: "partner"\|"tutor", message}` |
| `POST /translate` | `{text}` in English → tappable Mandarin translation |
| `POST /grammar/check` | `{text}` in Mandarin → corrected + explanation |
| `GET /books/recommendations` | once you've saved 30+ words, suggests real books |
| `GET /tts?text=...` | streams mp3 audio of the pronunciation |

Next up: the React Native (Expo) app that talks to this API.
