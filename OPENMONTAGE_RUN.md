# Final-video workflow (OpenMontage)

The local MoviePy export is a fast proof-of-concept preview. The assessment
submission should use OpenMontage for the final 30–60 second renders so it can
retrieve/generate real motion footage, mix music and narration, and enforce its
slideshow-risk quality gate.

## 1. Set up OpenMontage once

```powershell
git clone https://github.com/calesthio/OpenMontage.git
cd OpenMontage
make setup
```

Follow OpenMontage's Windows setup instructions if `make` is unavailable.

## 2. Run this project's research and script agents

```powershell
python main.py
```

This writes these reviewable inputs for every route:

- `outputs/productions/<route>/creative_brief.json`
- `outputs/productions/<route>/screenplay.md`
- `outputs/productions/<route>/OPENMONTAGE_PROMPT.md`

## 3. Produce the final cut

Open the cloned OpenMontage repository in your coding agent. Paste the content
of `OPENMONTAGE_PROMPT.md` as the production brief. Choose the real-footage or
motion-generation pipeline; do not choose an image-only slideshow pipeline.

Before accepting a render, require these pass conditions:

1. 30–60 seconds, 1080×1920 vertical.
2. At least five distinct moving shots; no repeated still frame as the primary visual.
3. Natural neural voice with background score ducked under narration.
4. Text only as brief emphasis captions—never the main visual.
5. OpenMontage post-render and slideshow-risk checks pass.

Save the approved MP4s to `outputs/videos/` as `ad_A.mp4`, `ad_B.mp4`, and
`ad_C.mp4`.
