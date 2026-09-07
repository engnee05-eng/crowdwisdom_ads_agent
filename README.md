# CrowdWisdomTrading Video Ads Agent

An AI multi-agent pipeline that automatically generates video ads for [crowdwisdomtrading.com](https://crowdwisdomtrading.com).

## What This Does

```
Agent 1 (Scraper)  →  Agent 2 (Analyzer)  →  Agent 3 (Scripts)  →  Agent 4 (Video)
   Apify                  Hermes-3 LLM          Tavily + Exa           MoviePy
```

1. **Agent 1** scrapes top trading ads from the Meta Ads Library (last 30 days)
2. **Agent 2** extracts pain points, ICP, and winning patterns using the LLM
3. **Agent 3** writes 3 different 30–60 sec video ad scripts with storyboards
4. **Agent 4** produces actual `.mp4` video files from the scripts

## Output Files

| File | Description |
|------|-------------|
| `outputs/top_ads.json` | Top 20 Meta ads found in the trading niche |
| `outputs/marketing_insights.json` | Pain points, ICP, creative patterns |
| `outputs/ad_scripts.json` | 3 full storyboarded ad scripts |
| `outputs/videos/ad_A.mp4` | Pain/Problem ad (30–60 sec) |
| `outputs/videos/ad_B.mp4` | Social Proof/Data ad (30–60 sec) |
| `outputs/videos/ad_C.mp4` | Pattern Interrupt ad (30–60 sec) |

## Setup

### 1. Install FFmpeg (required for video)
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html), add to PATH
- **Mac:** `brew install ffmpeg`
- **Ubuntu:** `sudo apt install ffmpeg`

### 2. Install Python dependencies
```bash
cd crowdwisdom_ads_agent
pip install -r requirements.txt
```

### 3. Set up API keys
```bash
# Copy the template
cp .env.example .env

# Edit .env and add your keys:
# - OPENROUTER_API_KEY  → https://openrouter.ai  (free tier)
# - APIFY_API_KEY       → https://apify.com      (free tier)
# - TAVILY_API_KEY      → https://tavily.com     (free tier)
# - EXA_API_KEY         → https://exa.ai         (free tier)
# - PEXELS_API_KEY      → https://pexels.com/api (free)
```

### 4. Run

```bash
# Check your API keys work (no cost, no scraping)
python main.py --dry-run

# Run the full pipeline
python main.py
```

## File Structure (Easy to Learn)

```
crowdwisdom_ads_agent/
│
├── main.py                 ← START HERE — runs all 4 agents
├── config.py               ← all settings and API keys
│
├── agent_1_scraper.py      ← scrapes Meta Ads via Apify
├── agent_2_analyzer.py     ← analyzes ads with LLM (Hermes-3)
├── agent_3_scriptwriter.py ← writes 3 scripts using Tavily/Exa
├── agent_4_video.py        ← generates .mp4 videos with MoviePy
│
├── requirements.txt        ← pip install -r requirements.txt
├── .env.example            ← copy to .env and add your keys
│
└── outputs/                ← all results saved here
    ├── top_ads.json
    ├── marketing_insights.json
    ├── ad_scripts.json
    └── videos/
        ├── ad_A.mp4
        ├── ad_B.mp4
        └── ad_C.mp4
```

## How Each Agent Works

### Agent 1 — Scraper (`agent_1_scraper.py`)
- Uses Apify's `facebook-ads-scraper` actor
- Searches for 8 keywords in the trading niche
- Picks the top 20 ads (sorted by days running = more days = more profitable)
- **Has fallback mock data** if Apify fails

### Agent 2 — Analyzer (`agent_2_analyzer.py`)
- Reads `top_ads.json`
- Sends all ad text to Hermes-3 LLM via OpenRouter
- Extracts: pain points, ICP profile, winning patterns, top hooks
- **Has fallback insights** if LLM fails

### Agent 3 — Script Writer (`agent_3_scriptwriter.py`)
- Searches web with Tavily + Exa for current trader pain content
- Uses LLM to write 3 distinct scripts (Pain, Social Proof, Pattern Interrupt)
- Injects real CWT data (16,564 traders, 74.1% win rate, etc.)
- **Has fallback scripts** if LLM fails

### Agent 4 — Video Producer (`agent_4_video.py`)
- Downloads stock footage from Pexels (free)
- Generates voiceover with gTTS (Google TTS — free)
- Creates branded text overlays with Pillow
- Stitches everything with MoviePy + FFmpeg

## API Keys Summary (All Free Tiers)

| Key | Where to Get | Free Tier |
|-----|-------------|-----------|
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) | Free credits on signup |
| `APIFY_API_KEY` | [apify.com](https://apify.com) | $5 free monthly credit |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) | 1,000 searches/month free |
| `EXA_API_KEY` | [exa.ai](https://exa.ai) | 1,000 searches/month free |
| `PEXELS_API_KEY` | [pexels.com/api](https://pexels.com/api) | Unlimited free |

## LLM Used: NousResearch Hermes-3 (via OpenRouter)

This project uses **Hermes-3** — the "Hermes agent framework" referenced in the brief — a function-calling and structured-output optimized model by NousResearch. It's available free on OpenRouter.
