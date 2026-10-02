"""
CrowdWisdomTrading Video Ads Agent
===================================
Run: python main.py

3 files only:
  .env.example  -> copy to .env and add your API keys
  requirements.txt -> pip install -r requirements.txt
  main.py       -> this file, does everything

Pipeline:
  Agent 1: Scrape top Meta ads (Apify)
  Agent 2: Extract pain points (LLM - Hermes-3 via OpenRouter)
  Agent 3: Write 3 ad scripts (Tavily + Exa + LLM)
  Agent 4: Generate polished vertical video ads (MoviePy + gTTS + Pillow)
"""

# ── Standard library ─────────────────────────────────────────────────────────
import os, json, sys, textwrap, urllib.request, math, asyncio
from datetime import datetime, timedelta
from pathlib import Path

# ── Third-party ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
from openai import OpenAI  # type: ignore
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from openmontage_handoff import write_production_package

load_dotenv()
console = Console()

# =============================================================================
# SECTION 1 — CONFIG 
# =============================================================================

LLM_KEY      = os.getenv("OPENROUTER_API_KEY", "")
LLM_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL    = "nousresearch/hermes-3-llama-3.1-405b:free"

APIFY_KEY  = os.getenv("APIFY_API_KEY", "")
TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")
EXA_KEY    = os.getenv("EXA_API_KEY", "")
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")

OUT_DIR    = Path("outputs")
VIDEOS_DIR = OUT_DIR / "videos"
TEMP_DIR   = OUT_DIR / "temp"
BUILTIN_BROLLS = [
    Path("assets") / "cinematic-trader.png",
    Path("assets") / "cinematic-phone.png",
    Path("assets") / "cinematic-success.png",
]

# Real CrowdWisdomTrading facts — injected into every ad script
CWT = {
    "traders":  "16,564",
    "win_rate": "74.1%",
    "time":     "5 minutes",
    "saved":    "100+ hours weekly",
    "price":    "$29.99/month",
    "free":     "20 free predictions, no credit card",
    "url":      "crowdwisdomtrading.com",
}

# Brand colours (dark blue + gold)
BG    = (10, 14, 26)
GOLD  = (255, 196, 57)
WHITE = (255, 255, 255)
GREEN = (0, 212, 132)


# =============================================================================
# SECTION 2 — LLM HELPER 
# =============================================================================

def ask_llm(system: str, user: str, temperature: float = 0.5):
    """Call Hermes-3 via OpenRouter and return parsed JSON (or raw string)."""
    # A short timeout keeps the demo pipeline progressing to its offline fallbacks
    # when a school/work proxy blocks the external provider.
    client = OpenAI(api_key=LLM_KEY, base_url=LLM_BASE_URL, timeout=20.0, max_retries=0)
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            temperature=temperature,
            max_tokens=3000,
        )
        text = resp.choices[0].message.content.strip()
        # strip markdown fences if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception as e:
        console.print(f"[yellow]WARNING: LLM call failed: {e}[/yellow]")
        return {}


# =============================================================================
# SECTION 3 — AGENT 1: SCRAPE TOP ADS (Apify)
# =============================================================================

def agent1_scrape_ads() -> list[dict]:
    """Scrape Meta Ads Library for top trading ads via Apify."""
    console.print("\n[bold cyan]Agent 1: Scraping Meta Ads Library...[/bold cyan]")

    if not APIFY_KEY:
        console.print("  [yellow]No Apify key — using mock ads[/yellow]")
        return _mock_ads()

    try:
        from apify_client import ApifyClient  # type: ignore
        client = ApifyClient(APIFY_KEY)
        run = client.actor("apify/facebook-ads-scraper").call(run_input={
            "searchTerms": ["trading signals", "stock picks", "crowd wisdom trading"],
            "activeStatus": "ACTIVE",
            "country": "US",
            "maxResults": 20,
        })
        ads = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            start = item.get("startDate", "")
            try:
                days = (datetime.now() - datetime.fromisoformat(start.replace("Z",""))).days
            except Exception:
                days = 0
            ads.append({
                "advertiser": item.get("pageName", ""),
                "text":       item.get("adCreativeBody", ""),
                "cta":        item.get("ctaText", ""),
                "days":       days,
            })
        ads.sort(key=lambda x: x["days"], reverse=True)
        result = ads[:20]
    except Exception as e:
        console.print(f"  [yellow]Apify error: {e} — using mock data[/yellow]")
        result = _mock_ads()

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "top_ads.json").write_text(json.dumps(result, indent=2))
    console.print(f"  OK: {len(result)} ads saved to outputs/top_ads.json")
    return result


def _mock_ads() -> list[dict]:
    return [
        {"advertiser": "TradeAlerts Pro",
         "text": "🚨 Stop losing on bad trades. 78% win rate AI signals. Try FREE 7 days.",
         "cta": "Get Free Signals", "days": 28},
        {"advertiser": "SmartTrader",
         "text": "I spent 3 HOURS daily researching stocks. Now 10 minutes. Better trades.",
         "cta": "See Free Picks", "days": 21},
        {"advertiser": "Wall Street Insider",
         "text": "What if 10,000 pros told you what to buy BEFORE the market opened?",
         "cta": "Join Free", "days": 14},
        {"advertiser": "SignalPro",
         "text": "Conflicting gurus ruining your trades? One clear signal. Every week.",
         "cta": "Start Free", "days": 10},
    ]


# =============================================================================
# SECTION 4 — AGENT 2: ANALYZE ADS (Hermes-3 LLM)
# =============================================================================

def agent2_analyze(ads: list[dict]) -> dict:
    """Use LLM to extract pain points, ICP, and winning patterns from the ads."""
    console.print("\n[bold magenta]Agent 2: Analyzing ads with Hermes-3...[/bold magenta]")

    ads_block = "\n".join([f"- {a['advertiser']}: {a['text']} | CTA: {a['cta']}" for a in ads])

    result = ask_llm(
        system="You are an expert marketing analyst. Return only valid JSON.",
        user=f"""Analyze these trading ads and return JSON with this exact structure:
{{
  "pain_points": ["pain 1", "pain 2", "pain 3"],
  "icp": "one sentence description of the ideal customer",
  "top_hooks": ["hook 1", "hook 2", "hook 3"],
  "winning_pattern": "what makes these ads work (1-2 sentences)"
}}

Ads:
{ads_block}

Also consider CrowdWisdomTrading: {CWT['traders']} traders, {CWT['win_rate']} win rate.""",
        temperature=0.3,
    )

    if not result:
        result = {
            "pain_points": [
                "Spending 5-10 hours on research with no clear trade plan",
                "Conflicting signals from YouTube gurus and analysts",
                "Emotional FOMO-driven trades that lose money",
            ],
            "icp": "Active retail trader aged 28-45 who trades part-time but wants professional-level insights",
            "top_hooks": [
                "What if 16,564 traders told you exactly what to buy this week?",
                "Stop spending 10 hours researching. Get your plan in 5 minutes.",
                "The market moves. Do you know where the pros are positioned?",
            ],
            "winning_pattern": "Lead with a relatable pain, show a dramatic contrast, close with a specific proof number and zero-risk CTA.",
        }

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "marketing_insights.json").write_text(json.dumps(result, indent=2))
    console.print("  OK: Insights saved to outputs/marketing_insights.json")
    return result


# =============================================================================
# SECTION 5 — AGENT 3: WRITE 3 AD SCRIPTS (Tavily + Exa + LLM)
# =============================================================================

def agent3_write_scripts(insights: dict) -> list[dict]:
    """Search the web for context, then write 3 ad scripts with the LLM."""
    console.print("\n[bold green]Agent 3: Writing 3 ad scripts...[/bold green]")

    # Web research (optional — falls back gracefully if keys missing)
    research = _web_research()

    pain    = "\n".join(insights.get("pain_points", []))
    hooks   = "\n".join(insights.get("top_hooks", []))
    icp     = insights.get("icp", "active retail trader")

    # One LLM call → all 3 scripts at once
    scripts = ask_llm(
        system="You are an award-winning video ad scriptwriter. Return only valid JSON.",
        user=f"""Write 3 different 30-45 second video ad scripts for CrowdWisdomTrading.com.

PRODUCT FACTS (use exact numbers):
- {CWT['traders']} professional traders aggregated
- {CWT['win_rate']} tracked win rate (public)
- Saves {CWT['saved']} of research
- Results in {CWT['time']} per week
- {CWT['price']} — {CWT['free']}

TARGET VIEWER: {icp}
PAIN POINTS: {pain}
TOP HOOKS: {hooks}
RECENT RESEARCH: {research[:600]}

Return a JSON array of exactly 3 scripts. Each script object:
{{
  "type": "A_pain | B_social_proof | C_pattern_interrupt",
  "hook": "first 5 words that stop the scroll",
  "scenes": [
    {{
      "num": 1,
      "seconds": 8,
      "visual": "what viewer sees",
      "voiceover": "exact words spoken",
      "text_on_screen": "caption text or null"
    }}
  ],
  "cta": "final call to action",
  "why_it_works": "one sentence psychology explanation"
}}

Write 5-6 scenes per script. Make hooks UNFORGETTABLE.""",
        temperature=0.75,
    )

    # Fallback if LLM fails
    if not scripts:
        scripts = _cinematic_fallback_scripts()

    # If LLM returned a dict with a key instead of a list, unwrap it
    if isinstance(scripts, dict):
        scripts = list(scripts.values())[0] if scripts else _cinematic_fallback_scripts()

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "ad_scripts.json").write_text(
        json.dumps({"generated_at": datetime.now().isoformat(), "scripts": scripts}, indent=2)
    )
    console.print(f"  OK: {len(scripts)} scripts saved to outputs/ad_scripts.json")
    for s in scripts:
        console.print(f"     - {s.get('type','')}: \"{s.get('hook','')}\"")
    return scripts


def _web_research() -> str:
    """Try Tavily then Exa. Return research text (or built-in fallback)."""
    results = []

    if TAVILY_KEY:
        try:
            from tavily import TavilyClient  # type: ignore
            resp = TavilyClient(api_key=TAVILY_KEY).search(
                "retail trader research overload conflicting signals 2025", max_results=3
            )
            for r in resp.get("results", []):
                results.append(r.get("content", "")[:200])
            console.print("  Tavily: found research context")
        except Exception as e:
            console.print(f"  [yellow]Tavily: {e}[/yellow]")

    if EXA_KEY and not results:
        try:
            from exa_py import Exa  # type: ignore
            resp = Exa(api_key=EXA_KEY).search(
                "why retail traders lose money conflicting signals",
                num_results=3,
                start_published_date=(datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d"),
            )
            results = [r.title for r in resp.results]
            console.print("  Exa: found semantic context")
        except Exception as e:
            console.print(f"  [yellow]Exa: {e}[/yellow]")

    return "\n".join(results) if results else (
        "67% of traders struggle with conflicting signals. "
        "Average trader spends 8+ hours weekly on research. "
        "Emotional trading causes 30% of retail losses."
    )


def _cinematic_fallback_scripts() -> list[dict]:
    """Three 30-60 second film treatments used whenever the LLM is offline."""
    routes = [
        ("A_pain_to_clarity", "Your next trade should not start with panic.", "Get 20 free predictions", [
            ("Extreme close-up of a trader lit by fast-moving monitors at 11:47 PM; slow push-in.", "It is late. You have twelve tabs open. And somehow, you are less certain than when you started.", "Too much noise."),
            ("Phone vibrates beside cold coffee; laptop closes and the room falls quiet.", "The market is not short on opinions. It is short on clear conviction.", "Clear conviction."),
            ("Match cut to a calm morning commute, phone in hand, city light on glass.", "CrowdWisdom brings thousands of professional views into one focused signal.", "One focused signal."),
            ("Lateral shot of a composed trader checking a phone before market open.", "See the entry, the risk, and the target without giving up your evening to research.", "Less research. More clarity."),
            ("Warm sunrise as the trader walks away from the desk, relaxed.", "Make your next move with a plan, not a panic reaction.", "Trade with a plan."),
        ]),
        ("B_social_proof", "The market is loud. The crowd can be useful.", "Join 16,564 traders free", [
            ("Aerial night city; push toward one glowing trading screen.", "Every morning, thousands of traders ask the same question. What matters now?", "What matters now?"),
            ("Elegant match cuts: keyboards, trains, coffee, opening bell.", "On their own, every opinion is noise. Together, a pattern starts to appear.", "A pattern appears."),
            ("Charts resolve from blur to focus in a trader's glasses.", "CrowdWisdom distils the collective view of 16,564 professional traders into weekly ideas.", "16,564 professional views."),
            ("Quiet phone check in a sunlit cafe—no fake UI.", "Not a guru. Not a hot take. A transparent view of where conviction is building.", "Not another hot take."),
            ("Wide shot: trader walks confidently into a waking city.", "When the crowd sees something, you deserve to see it too.", "See the signal."),
        ]),
        ("C_pattern_interrupt", "Stop researching. Start deciding.", "See this week's free predictions", [
            ("Black frame, one notification sound, then smash cut to browser tabs in a tired face.", "Stop researching.", "STOP RESEARCHING."),
            ("Windows collapse in a practical edit, leaving one calm screen.", "Not because research does not matter. More tabs do not create better decisions.", "More tabs. Less clarity."),
            ("Camera circles a trader as morning light replaces monitor glow.", "A better decision starts with knowing what informed traders are already watching.", "Know what matters."),
            ("Phone placed face-down after a confident choice, then the trader steps outside.", "CrowdWisdom gives you a focused weekly view in minutes, so your time stays yours.", "Minutes, not hours."),
            ("Slow-motion street walk into warm daylight; music resolves.", "Stop chasing every opinion. Start deciding with clarity.", "Start deciding."),
        ]),
    ]
    return [
        {"type": ad_type, "hook": hook, "cta": cta,
         "why_it_works": "A cinematic emotional arc: tension, clarity, then confidence.",
         "scenes": [{"num": index + 1, "seconds": 7, "visual": visual,
                     "voiceover": voiceover, "text_on_screen": caption}
                    for index, (visual, voiceover, caption) in enumerate(beats)]}
        for ad_type, hook, cta, beats in routes
    ]


def _fallback_scripts() -> list[dict]:
    scene_base = [
        {"num":1,"seconds":5,"visual":"Stressed trader, multiple browser tabs open",
         "voiceover":"You've been doing this the hard way.","text_on_screen":None},
        {"num":2,"seconds":8,"visual":"Split screen: 50 tabs vs clean CWT dashboard",
         "voiceover":"Hours of YouTube. Conflicting gurus. Still no plan.",
         "text_on_screen":"Sound familiar?"},
        {"num":3,"seconds":7,"visual":"Animated counter: 16,564 trader profile icons appear",
         "voiceover":"16,564 professional traders already did the research for you.",
         "text_on_screen":"16,564 Pro Traders"},
        {"num":4,"seconds":6,"visual":"Trade card: AAPL — Entry $142, Stop $139, Target $151",
         "voiceover":"Clear entry, stop, and target. Every week. No guessing.",
         "text_on_screen":"Entry · Stop · Target"},
        {"num":5,"seconds":7,"visual":"74.1% badge animates in with green checkmarks",
         "voiceover":"74.1% win rate. Tracked. Public. Verifiable.",
         "text_on_screen":"74.1% Win Rate"},
        {"num":6,"seconds":7,"visual":"Person relaxing, phone shows CWT notification, smiling",
         "voiceover":"Start free. 20 predictions. No credit card.",
         "text_on_screen":"Start Free → crowdwisdomtrading.com"},
    ]
    return [
        {"type":"A_pain","hook":"You've been doing this wrong.",
         "scenes":scene_base,"cta":"Get 20 Free Predictions",
         "why_it_works":"Mirrors the viewer's frustration then delivers relief."},
        {"type":"B_social_proof","hook":"16,564 traders can't be wrong.",
         "scenes":scene_base,"cta":"Join 16,564 Pro Traders Free",
         "why_it_works":"Large credible numbers create instant social proof and FOMO."},
        {"type":"C_pattern_interrupt","hook":"Stop doing your own research.",
         "scenes":scene_base,"cta":"Let 16,564 Experts Do It For You",
         "why_it_works":"Contrarian opener causes a scroll-stop moment of curiosity."},
    ]


# =============================================================================
# SECTION 6 — AGENT 4: GENERATE VIDEOS (MoviePy + gTTS + Pillow)
# =============================================================================

def agent4_make_videos(scripts: list[dict], insights: dict | None = None) -> list[str]:
    """Turn each script into a real .mp4 video file."""
    console.print("\n[bold red]Agent 4: Generating video ads...[/bold red]")

    try:
        from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip  # type: ignore
        import numpy as np
    except ImportError:
        console.print("  [red]MoviePy not installed. Run: pip install moviepy[/red]")
        return []

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    output_paths = []
    for script in scripts:
        ad_type = script.get("type", "ad").split("_")[0].upper()
        out_path = str(VIDEOS_DIR / f"ad_{ad_type}.mp4")
        package = write_production_package(script, insights or {}, OUT_DIR)
        console.print(f"    OpenMontage package: {package}")
        console.print(f"\n  Building Ad {ad_type}: \"{script.get('hook','')}\"")
        try:
            _render_video(script, out_path)  # type: ignore
            output_paths.append(out_path)
            console.print(f"    OK: {out_path}")
        except Exception as e:
            console.print(f"    [red]Failed: {e}[/red]")
            console.print("    [dim]Tip: Install FFmpeg from ffmpeg.org and add it to PATH[/dim]")
    return output_paths


def _render_video(script: dict, out_path: str):
    """Build one video: title card + scene slides + voiceover + CTA card."""
    # pyrefly: ignore [missing-import]
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip

    # This is a quick local proof render. OpenMontage produces the final
    # 1080x1920 cinematic cut from the production package.
    W, H = 360, 640
    clips = []

    # 1 — Title card (3 sec)
    title_path = _make_title_img(script.get("hook",""), W, H)
    clips.append(ImageClip(title_path).with_duration(3))

    # 2 — One clip per scene
    for scene in script.get("scenes", []):
        dur = scene.get("seconds", 5)
        img = _make_cinematic_scene_img(scene, W, H)
        # Preview renderer: static clips encode quickly. The final production uses
        # OpenMontage motion footage and camera moves from the generated handoff.
        vc = ImageClip(img).with_duration(dur)

        # Voiceover
        audio = _make_audio(scene.get("voiceover",""), scene["num"], script["type"])
        if audio:
            trimmed = audio.subclipped(0, min(audio.duration, dur))
            vc = vc.with_audio(trimmed)

        clips.append(vc)

    # 3 — CTA card (5 sec)
    cta_path = _make_premium_cta_img(script.get("cta",""), W, H)
    clips.append(ImageClip(cta_path).with_duration(5))

    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(out_path, fps=12, codec="libx264", preset="ultrafast",
                          audio_codec="aac", logger=None)
    final.close()
    for c in clips:
        c.close()


# ── Image helpers (Pillow) ────────────────────────────────────────────────────

def _font(size: int, bold: bool = True):
    """Load a font, fall back to default if not found."""
    from PIL import ImageFont
    names = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"] if bold else [
        "arial.ttf", "Arial.ttf", "DejaVuSans.ttf"
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _brand_background(W: int, H: int):
    """A reusable dark-blue gradient, grid, and subtle gold glow."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            # Navy gradient plus a warm glow near the top-right corner.
            glow = max(0, 1 - math.hypot(x - W * .82, y - H * .16) / (W * .72))
            px[x, y] = (7 + int(18 * glow), 12 + int(14 * glow), 27 + int(10 * glow))
    draw = ImageDraw.Draw(img)
    for x in range(0, W, 90):
        draw.line((x, 0, x, H), fill=(20, 30, 52), width=1)
    for y in range(0, H, 90):
        draw.line((0, y, W, y), fill=(20, 30, 52), width=1)
    return img, draw


def _multiline(draw, xy, text: str, font, fill, width: int, **kwargs):
    """Draw centred, wrapped text. Keeping this helper makes the visual code easy to edit."""
    chars = max(10, width // max(1, int(font.size * .55)))
    draw.multiline_text(xy, textwrap.fill(str(text), chars), font=font, fill=fill,
                        anchor="mm", align="center", spacing=int(font.size * .22), **kwargs)


def _header(draw, W: int, label: str = "MARKET INTELLIGENCE"):
    draw.rounded_rectangle([58, 58, W - 58, 140], radius=28, fill=(14, 24, 45), outline=(45, 62, 94), width=2)
    draw.ellipse([82, 80, 112, 110], fill=GOLD)
    draw.text((130, 95), "CROWDWISDOM", font=_font(30), fill=WHITE, anchor="lm")
    draw.text((W - 82, 95), label, font=_font(21, bold=False), fill=(150, 164, 190), anchor="rm")


def _make_title_img(hook: str, W: int, H: int) -> str:
    """Scroll-stopping opening card with a repeatable brand treatment."""
    img, draw = _brand_background(W, H)
    _header(draw, W, "WEEKLY TRADE EDGE")
    draw.rounded_rectangle([70, H*.25, W-70, H*.72], radius=42, fill=(12, 22, 42), outline=(56, 76, 113), width=3)
    draw.rectangle([70, H*.25, 82, H*.72], fill=GOLD)
    draw.text((W//2, H*.34), "STOP SCROLLING", font=_font(30), fill=GOLD, anchor="mm")
    _multiline(draw, (W//2, H*.50), hook.upper(), _font(82), WHITE, int(W*.72))
    draw.text((W//2, H*.82), "Data-led picks. Clear conviction.", font=_font(35, False), fill=(177, 190, 215), anchor="mm")
    draw.text((W//2, H*.90), CWT["url"], font=_font(32), fill=GOLD, anchor="mm")
    path = str(TEMP_DIR / "title.png")
    img.save(path)
    return path


def _make_scene_img(scene: dict, W: int, H: int) -> str:
    """Dark slide for a scene — visual description + on-screen text."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Scene number (subtle)
    draw.text((60, 80), f"Scene {scene['num']}", font=_font(36), fill=(50, 60, 90))

    # Visual direction (dim, top area)
    vis = textwrap.fill(scene.get("visual", ""), 38)
    draw.text((W//2, H*0.30), vis, font=_font(38), fill=(130, 140, 170),
              anchor="mm", align="center")

    # Gold divider
    draw.line([(W*0.15, H*0.48), (W*0.85, H*0.48)], fill=GOLD, width=3)

    # Voiceover text (white, centre)
    vo = textwrap.fill(scene.get("voiceover", ""), 28)
    draw.text((W//2, H*0.60), vo, font=_font(58), fill=WHITE,
              anchor="mm", align="center")

    # On-screen text (gold banner, bottom)
    ost = scene.get("text_on_screen")
    if ost:
        draw.rounded_rectangle([80, H*0.80, W-80, H*0.88], radius=30, fill=GOLD)
        draw.text((W//2, H*0.84), ost, font=_font(52), fill=BG,
                  anchor="mm", align="center")

    path = str(TEMP_DIR / f"scene_{scene['num']}_{scene.get('num',0)}.png")
    img.save(path)
    return path


def _make_cta_img(cta: str, W: int, H: int) -> str:
    """Green CTA button card at the end."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([80, H*0.38, W-80, H*0.58], radius=50, fill=GREEN)
    draw.text((W//2, H*0.48), textwrap.fill(cta, 22), font=_font(64),
              fill=BG, anchor="mm", align="center")
    draw.text((W//2, H*0.68), CWT["url"], font=_font(50), fill=GOLD, anchor="mm")
    draw.text((W//2, H*0.78), CWT["free"], font=_font(38), fill=(160,160,160), anchor="mm")
    path = str(TEMP_DIR / "cta.png")
    img.save(path)
    return path


def _make_premium_scene_img(scene: dict, W: int, H: int) -> str:
    """Premium data visual plus a readable vertical-video subtitle layout."""
    img, draw = _brand_background(W, H)
    _header(draw, W, f"INSIGHT 0{scene.get('num', 1)}")
    draw.rounded_rectangle([70, H*.20, W-70, H*.51], radius=42, fill=(13, 25, 47), outline=(50, 70, 105), width=3)
    draw.text((110, H*.245), "MARKET CONSENSUS", font=_font(25, False), fill=(148, 164, 194))
    points = [(130, H*.43), (250, H*.38), (380, H*.41), (520, H*.32), (670, H*.35), (800, H*.27), (950, H*.29)]
    draw.line(points, fill=GREEN, width=9, joint="curve")
    for x, y in points:
        draw.ellipse([x-9, y-9, x+9, y+9], fill=WHITE, outline=GREEN, width=5)
    draw.rounded_rectangle([105, H*.455, 410, H*.495], radius=18, fill=(1, 72, 58))
    draw.text((258, H*.475), "LIVE SIGNALS", font=_font(22), fill=(183, 255, 229), anchor="mm")
    draw.text((W-115, H*.475), "74.1%", font=_font(42), fill=GOLD, anchor="rm")
    headline = (scene.get("text_on_screen") or "Clarity over noise").upper()
    _multiline(draw, (W//2, H*.61), headline, _font(66), WHITE, int(W*.78))
    draw.line([(W*.18, H*.70), (W*.82, H*.70)], fill=GOLD, width=5)
    _multiline(draw, (W//2, H*.79), scene.get("voiceover", ""), _font(37, False), (211, 220, 238), int(W*.78))
    draw.text((W//2, H*.93), "crowdwisdomtrading.com", font=_font(26, False), fill=(125, 143, 173), anchor="mm")
    path = str(TEMP_DIR / f"premium_scene_{scene['num']}.png")
    img.save(path)
    return path


def _make_premium_cta_img(cta: str, W: int, H: int) -> str:
    """High-contrast closing card with one unmistakable next action."""
    img, draw = _brand_background(W, H)
    _header(draw, W, "START FREE TODAY")
    draw.text((W//2, H*.30), "YOUR NEXT TRADE DESERVES", font=_font(29, False), fill=(166, 181, 207), anchor="mm")
    draw.text((W//2, H*.36), "A CLEARER PLAN", font=_font(64), fill=WHITE, anchor="mm")
    draw.rounded_rectangle([72, H*.45, W-72, H*.61], radius=45, fill=GREEN)
    _multiline(draw, (W//2, H*.53), cta.upper(), _font(54), BG, int(W*.72))
    draw.text((W//2, H*.70), CWT["free"].upper(), font=_font(34), fill=GOLD, anchor="mm")
    draw.text((W//2, H*.80), CWT["url"], font=_font(47), fill=WHITE, anchor="mm")
    draw.text((W//2, H*.88), "No credit card required", font=_font(28, False), fill=(156, 171, 198), anchor="mm")
    path = str(TEMP_DIR / "premium_cta.png")
    img.save(path)
    return path


def _make_cinematic_scene_img(scene: dict, W: int, H: int) -> str:
    """Cinematic local preview shot using varied, bundled b-roll—not dashboard slides."""
    from PIL import Image, ImageDraw
    source_path = BUILTIN_BROLLS[(int(scene.get("num", 1)) - 1) % len(BUILTIN_BROLLS)]
    if not source_path.exists():
        return _make_premium_scene_img(scene, W, H)
    source = Image.open(source_path).convert("RGB")
    scale = max(W / source.width, H / source.height)
    source = source.resize((round(source.width * scale), round(source.height * scale)))
    left, top = (source.width - W) // 2, (source.height - H) // 2
    image = source.crop((left, top, left + W, top + H)).convert("RGBA")
    image = Image.alpha_composite(image, Image.new("RGBA", (W, H), (3, 9, 20, 135))).convert("RGB")
    draw = ImageDraw.Draw(image)
    _header(draw, W, f"INSIGHT {int(scene.get('num', 1)):02d}")
    _multiline(draw, (W//2, H*.62), (scene.get("text_on_screen") or "Trade with clarity").upper(), _font(66), WHITE, int(W*.80))
    draw.rounded_rectangle([85, H*.73, W-85, H*.86], radius=30, fill=(8, 18, 36))
    _multiline(draw, (W//2, H*.795), scene.get("voiceover", ""), _font(35, False), (232, 238, 250), int(W*.72))
    draw.text((W//2, H*.91), CWT["url"], font=_font(27, False), fill=GOLD, anchor="mm")
    path = str(TEMP_DIR / f"cinematic_scene_{scene.get('num', 1)}.jpg")
    image.save(path, quality=94)
    return path


def _make_audio(text: str, num: int, script_type: str):
    """Generate an Edge neural voice; use gTTS only if neural TTS is unavailable."""
    if not text.strip():
        return None
    try:
        import edge_tts
        from moviepy import AudioFileClip  # type: ignore
        path = str(TEMP_DIR / f"vo_neural_{script_type}_{num}.mp3")
        if not Path(path).exists():
            asyncio.run(edge_tts.Communicate(text, voice="en-US-AndrewNeural", rate="+4%").save(path))
        return AudioFileClip(path)
    except Exception:
        try:
            from gtts import gTTS
            from moviepy import AudioFileClip  # type: ignore
            path = str(TEMP_DIR / f"vo_{script_type}_{num}.mp3")
            if not Path(path).exists():
                gTTS(text=text, lang="en").save(path)
            return AudioFileClip(path)
        except Exception:
            return None


# =============================================================================
# SECTION 7 — MAIN: KANBAN BOARD + PIPELINE
# =============================================================================

def show_board(statuses: dict):
    """Print a live Kanban board showing agent progress."""
    t = Table(box=box.ROUNDED, title="CrowdWisdomTrading Ads Agent",
              title_style="bold yellow", show_lines=True)
    t.add_column("Agent",  style="bold white", width=30)
    t.add_column("Status", width=14)
    t.add_column("Output", style="dim", width=36)

    icons = {"pending":"Pending","running":"Running","done":"Done","failed":"Failed"}
    colors = {"pending":"white","running":"yellow","done":"green","failed":"red"}
    outputs = {
        "1. Scraper":      "outputs/top_ads.json",
        "2. Analyzer":     "outputs/marketing_insights.json",
        "3. Script Writer":"outputs/ad_scripts.json",
        "4. Video":        "outputs/videos/ad_A/B/C.mp4",
    }
    for name, status in statuses.items():
        label = icons.get(status, "?")
        color = colors.get(status, "white")
        t.add_row(name, f"[{color}]{label}[/{color}]", outputs.get(name,""))
    console.print("\n", t)


def main():
    console.print(Panel(
        "[bold yellow]CrowdWisdomTrading[/bold yellow] Video Ads Agent\n\n"
        "[dim]Scrapes winning ads -> Analyzes pain points -> Writes scripts -> Makes videos[/dim]",
        border_style="yellow", padding=(1, 4)
    ))

    if not LLM_KEY:
        console.print("[bold red]ERROR: Set OPENROUTER_API_KEY in your .env file[/bold red]")
        console.print("Get a free key at: https://openrouter.ai")
        sys.exit(1)

    statuses = {"1. Scraper":"pending","2. Analyzer":"pending",
                "3. Script Writer":"pending","4. Video":"pending"}
    show_board(statuses)

    # Agent 1
    statuses["1. Scraper"] = "running"; show_board(statuses)
    ads = agent1_scrape_ads()
    statuses["1. Scraper"] = "done"; show_board(statuses)

    # Agent 2
    statuses["2. Analyzer"] = "running"; show_board(statuses)
    insights = agent2_analyze(ads)
    statuses["2. Analyzer"] = "done"; show_board(statuses)

    # Agent 3
    statuses["3. Script Writer"] = "running"; show_board(statuses)
    scripts = agent3_write_scripts(insights)
    statuses["3. Script Writer"] = "done"; show_board(statuses)

    # Agent 4
    statuses["4. Video"] = "running"; show_board(statuses)
    videos = agent4_make_videos(scripts, insights)
    statuses["4. Video"] = "done" if videos else "failed"; show_board(statuses)

    console.print(Panel(
        f"[bold green]Done![/bold green]\n\n"
        f"  Ads scraped:  {len(ads)}\n"
        f"  Scripts:      {len(scripts)}\n"
        f"  Videos:       {len(videos)}\n\n"
        + "\n".join(f"  - {v}" for v in videos),
        border_style="green", title="Results"
    ))


if __name__ == "__main__":
    main()
