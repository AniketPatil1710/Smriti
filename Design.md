# Design — Smriti

## Direction

The subject is *memory* — a codebase's present state layered over the history that produced it. The visual language comes from **manuscript strata**: ink on aged paper, later hands writing over earlier ones, marginalia annotating the main text.

This gives the interface one honest structural idea: **the two indexes are two inks.** Code retrieval is slate blue, history retrieval is ochre. That distinction appears everywhere — citation chips, source markers, the signature element — so a user can see at a glance whether an answer came from the code or from the story behind it. Nothing else in the UI is allowed to be colourful.

Dark ground, warm foreground. Developer tools live on dark screens, but the text is paper-warm rather than cold grey, which keeps the manuscript association alive without costuming.

## Color tokens

```css
:root {
  --ink:        #15161C;  /* page ground */
  --ink-raised: #1D1F27;  /* cards, input, code blocks */
  --rule:       #2C2F3A;  /* hairlines, borders */
  --vellum:     #E8E2D5;  /* primary text — warm, not white */
  --vellum-dim: #8A8779;  /* secondary text, timestamps, metadata */
  --code:       #7FA8CC;  /* CODE INDEX — citations, chips, markers */
  --history:    #C99A4B;  /* HISTORY INDEX — commits, PRs, "why" answers */
  --alert:      #C4685E;  /* errors only */
}
```

Two accents, each with a fixed meaning. Never use `--code` or `--history` decoratively — if it's blue, it came from a file; if it's ochre, it came from a commit. That rule is what makes the palette informative rather than pretty.

## Typography

| Role | Face | Use |
|---|---|---|
| Display | **Fraunces** (variable, `wght 600`, `SOFT 40`, `WONK 1`) | Product name, empty state, section headers. Used sparingly — it's characterful and gets tiresome at small sizes. |
| Body | **IBM Plex Sans** | Answers, labels, everything conversational. |
| Devanagari | **IBM Plex Sans Devanagari** | स्मृति in the header — same family, so the two scripts sit together properly instead of clashing. |
| Mono | **IBM Plex Mono** | Code chunks, file paths, line numbers, commit SHAs. |

The Plex family covering Latin, Devanagari, and mono is the reason for choosing it — the name renders in the same voice as the interface.

**Scale** (1.25 ratio): 12 / 14 / 16 / 20 / 25 / 31 / 39 px. Body 16px, line-height 1.6. Mono 14px, line-height 1.5. Display at 31 or 39.

Sentence case throughout. No uppercase headers except metadata eyebrows at 12px with 0.08em tracking.

## Layout

```
┌────────────────────────────────────────────────────┐
│  स्मृति  Smriti          fastapi · 3,847 chunks     │  header, 64px, hairline below
├────────────────────────────────────────────────────┤
│                                                    │
│   ┌──┐                                             │
│   │▓ │  Where is token validation handled?         │  user message — right, quiet
│   └──┘                                             │
│                                                    │
│   ┌──┐                                             │
│   │▒▒│  Token validation lives in                   │  answer — left, full width
│   │▓ │  `src/auth/tokens.py`, in `validate_token`   │
│   │▒▒│  ...                                         │
│   └──┘                                             │
│    ▲                                               │
│    └─ STRATA BAR                                   │
│                                                    │
│   [ tokens.py:42–78 ]  [ #4821 retry fix ]         │  citation chips: blue / ochre
│                                                    │
├────────────────────────────────────────────────────┤
│  Ask about this codebase…                    [ ↵ ] │  input, sticky bottom
└────────────────────────────────────────────────────┘
```

Single column, max-width 760px, centered. Conversation scrolls, input is fixed. No sidebar — a file tree would compete with the answer for attention and the agent already navigates for you.

## Signature element: the strata bar

A 4px vertical bar on the left edge of every answer, segmented in proportion to where that answer's sources came from — blue for code chunks, ochre for history records. An answer drawn entirely from source files is a solid blue rule. An answer about *why* something exists shows a thick ochre band.

It's the memory metaphor made literal: you see the sediment of each answer before you read a word of it. Hovering a segment highlights the matching citation chips below.

This is the one bold thing in the design. Everything else stays quiet so it lands.

## Components

**Citation chip.** Mono 12px, 1px border in the source's colour, 4px radius, transparent background. Code chips read `tokens.py:42–78`; history chips read `#4821 retry fix` or `a3f9c21`. Click expands the chunk inline in a `--ink-raised` block. Hover fills at 12% opacity.

**Code block.** `--ink-raised`, 1px `--rule` border, mono 14px, line numbers in `--vellum-dim` on the left. No syntax highlighting library — one more dependency for marginal gain. Path and line range as a 12px mono eyebrow above.

**Input.** `--ink-raised`, 1px `--rule`, 6px radius, 14px padding. Focus: border to `--code`, no glow. Placeholder in `--vellum-dim`.

**Thinking state.** The agent takes 5–15 seconds, so show what it's doing rather than a spinner: `searching code…` → `reading tokens.py…` → `checking history…`, mono 13px in `--vellum-dim`, each line replacing the last. Streaming the tool trace is more reassuring than any animation, and it also demonstrates the ReAct loop to anyone watching your demo.

**Empty state.** Display face, one line: *What do you want to know about this codebase?* Below it, three example questions as clickable chips — one lookup, one conceptual, one "why". The third one teaches the feature nobody expects.

## Motion

Almost none, deliberately.

- Answers fade in over 150ms, no slide
- Citation expansion: height transition, 200ms `ease-out`
- Thinking-state lines cross-fade at 100ms
- Strata bar draws top-to-bottom over 300ms as the answer streams — the one flourish

`prefers-reduced-motion: reduce` disables all of it.

## Quality floor

Responsive to 380px (chips wrap, max-width becomes 100% minus 32px gutters). Visible keyboard focus on every interactive element — 2px `--code` outline, 2px offset. Enter sends, Shift+Enter newlines. Contrast: `--vellum` on `--ink` is roughly 12:1; `--vellum-dim` is used only at 14px and above.

## Voice

Plain and specific. The interface never apologizes and never pads.

- Empty: *What do you want to know about this codebase?*
- Indexing: *Indexing fastapi — 1,203 of 3,847 files*
- No results: *Nothing in this codebase matches that. Try naming a file or function.*
- Error: *Couldn't reach the model. Check your API key in .env.*
- Iteration cap: *Stopped after 6 steps. Here's what I found so far.*

Never "Oops!", never "I'm sorry", never an exclamation mark.
