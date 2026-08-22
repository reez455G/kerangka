---
name: verify-fixed-canvas-html-deck
description: "Use when QA-ing a single-file HTML deck built from a locked-canvas template (e.g. deck-open-slide-canvas, deck-swiss-international, deck-guizang-editorial) that forbids overflow and requires keyboard slide navigation — verifies no-overflow, nav clamping, and motion in a real headless browser."
---

## When to use
After generating a single-file HTML deck from any "locked canvas, no overflow" template skill (fixed px canvas like 1920x1080, `transform: scale()` to fit viewport, `<section class="slide" data-slide-id="n">` per page, keyboard ←/→ nav with hash sync). These templates have a hard rule against scrollbars/overflow that is easy to violate with dense text and easy to miss by eye alone.

## Procedure
1. Open the file with the `browser` tool: `action: open`, `url: file://<absolute-path>`. If the first call times out waiting for the WS endpoint, just retry once — it's a transient cold-start issue, not a real failure.
2. For every slide, assert no overflow by comparing the inner content wrapper's `scrollWidth`/`scrollHeight` against the canvas's fixed dimensions (e.g. 1920x1080). Do this via `tab.evaluate` reading `getComputedStyle`/`scrollWidth`/`scrollHeight` of `.slide.active > div` (or equivalent inner wrapper) — never eyeball it only.
3. Drive navigation with `tab.press('ArrowRight'/'ArrowLeft')` repeatedly from slide 1 through the last slide, checking overflow at each stop. Then press once more past the last slide and confirm the active slide id is clamped (does not advance past max, does not go below 1).
4. If the template specifies motion (entrance animation, background pulse, etc.), confirm it's actually wired up: `getComputedStyle(el).animationName` and `.animationDuration` on the relevant elements after navigating to a slide — don't just trust the CSS source.
5. Screenshot each slide (`tab.screenshot({ selector: '.slide.active' })`) and visually confirm: single visual hierarchy per slide (no two equal-weight text blocks side by side unless in an explicit equal-weight grid), palette/type-scale consistency, no clipped text.
6. Close the tab when done (`action: close`).

## Why this matters
Regular screenshot-only QA misses off-canvas overflow that's clipped by `overflow:hidden` and invisible in a screenshot — you have to read `scrollWidth`/`scrollHeight` programmatically to catch it. Keyboard-clamp bugs (nav past last/first slide) are also invisible in a static screenshot and need an actual press-through.
