"""Create reviewable OpenMontage production packages from an agent storyboard.

OpenMontage is agent-first: the package below is the exact creative contract an
OpenMontage session consumes. Keeping it in a small module makes the handoff
auditable without hiding the marketing logic in a third-party tool.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_production_package(script: dict, insights: dict, output_root: Path) -> Path:
    """Write one screenplay, shot list and OpenMontage prompt per creative route."""
    ad_type = script.get("type", "ad").replace(" ", "_")
    package = output_root / "productions" / ad_type
    package.mkdir(parents=True, exist_ok=True)

    scenes = script.get("scenes", [])
    duration = sum(int(scene.get("seconds", 0)) for scene in scenes) + 8
    creative = {
        "format": "Instagram Reels / TikTok, vertical 9:16, 1080x1920",
        "duration_target_seconds": max(30, min(60, duration)),
        "delivery_promise": "cinematic, motion-led ad with real footage; never a text-ad or slideshow",
        "voice_direction": "warm, intimate US English narrator; restrained, confident, never announcer-like",
        "music_direction": "minimal pulsing cinematic score, subtle market-ticker texture, mixed under narration",
        "creative_route": ad_type,
        "hook": script.get("hook", ""),
        "cta": script.get("cta", ""),
        "marketing_insight": insights.get("winning_pattern", ""),
        "scenes": scenes,
    }
    (package / "creative_brief.json").write_text(json.dumps(creative, indent=2), encoding="utf-8")

    shot_lines = []
    for scene in scenes:
        shot_lines.append(
            f"{scene.get('num', '?')}. {scene.get('seconds', 0)}s | "
            f"Visual: {scene.get('visual', '')}\n"
            f"   Narration: {scene.get('voiceover', '')}\n"
            f"   On-screen copy: {scene.get('text_on_screen') or 'None'}"
        )
    screenplay = "\n\n".join(shot_lines)
    (package / "screenplay.md").write_text(
        f"# {ad_type.replace('_', ' ').title()}\n\n"
        f"Hook: {script.get('hook', '')}\n\n{screenplay}\n\nCTA: {script.get('cta', '')}\n",
        encoding="utf-8",
    )

    prompt = f"""Create a {creative['duration_target_seconds']}-second vertical 9:16 cinematic performance ad for CrowdWisdomTrading.

This is a motion-led film, not a slide deck. Use real stock footage where possible: hands, screens, late-night research, quiet confidence, city light, and authentic trader environments. Every scene needs distinct shot intent and camera movement. Use cuts, match cuts, push-ins, and sound design; never hold a static text card for more than a beat.

Audience: active retail traders overwhelmed by conflicting signals and research overload.
Creative route: {ad_type}. Hook: {script.get('hook', '')}
Voice: warm, intimate US English, natural pacing. Music: cinematic pulse under narration; duck it under speech.
Hard rules: no fake trading-app UI, no unverified claims, no talking avatar, no generic corporate stock montage, no PowerPoint dashboards, no all-text scenes. Captions are limited to short emphasis phrases and must never repeat the full narration.

Storyboards:
{screenplay}

End on this CTA, integrated over a moving final shot: {script.get('cta', '')}.
Run OpenMontage's quality gates. Reject the render if the slideshow-risk check is critical, narration is silent/robotic, clips repeat, or the result is shorter than 30 seconds.
"""
    (package / "OPENMONTAGE_PROMPT.md").write_text(prompt, encoding="utf-8")
    return package

