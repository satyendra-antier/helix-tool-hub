# Tool Hub

One shell, pluggable tool modules. Video Scraper + Market Depth Analyzer included.

## Quick Start

```bash
cd tool-hub
cp .env.example .env   # add your API keys
chmod +x start.sh
./start.sh
```

Open **http://localhost:3000**

## Services

| Service | Port | Description |
|---------|------|-------------|
| Web (Hub) | 3000 | Next.js dashboard + tool host |
| Video Scraper API | 8001 | FastAPI — yt-dlp + OpenAI |
| Market Depth API | 8002 | FastAPI — real data scoring |
| Lead Intelligence API | 8003 | FastAPI — lead discovery & pipeline |
| Postgres | internal | Shared database |
| Redis | internal | Job queue backing |

## Commands

```bash
./start.sh          # build & start all services
./start.sh down     # stop stack
./start.sh logs     # tail logs
./start.sh restart  # restart services
```

## Adding a New Tool

1. Create `modules/your-tool/manifest.json`
2. Add `frontend/` and `backend/` folders
3. Register frontend in `apps/web/components/tool-host.tsx`
4. Restart — card appears on dashboard automatically

## Required API Keys

- **OPENAI_API_KEY** — all modules (gpt-5-mini for text, whisper-1 for transcription)
- **GITHUB_TOKEN** — Market Depth developer momentum
- **ADZUNA_APP_ID / ADZUNA_APP_KEY** — Market Depth hiring demand (optional, falls back to RemoteOK)
