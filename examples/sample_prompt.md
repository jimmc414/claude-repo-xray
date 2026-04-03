# Sample Onboarding Prompt

Copy and adapt this prompt when starting a new AI session with your generated output files.

Replace the placeholder values with your actual filenames and codebase path. The scanner names output files based on your `--out` flag (e.g., `python xray.py . --output both --out ./analysis` produces `analysis.md` and `analysis.json`). The deep crawl produces `DEEP_ONBOARD.md` in its working directory.

---

## Both phases (X-Ray + Deep Crawl)

```
I'm providing two reference documents for this codebase:

1. <your_project>_XRAY.md — A deterministic structural scan of the codebase
   covering architecture, dependency graph, complexity hotspots, git risk
   signals, side effects, security concerns, and investigation targets.

2. <your_project>_DEEP_ONBOARD.md — A comprehensive onboarding document with
   verified [FACT] code citations covering critical paths, module behavior,
   error handling patterns, shared state, gotchas, change playbooks, and
   extension points.

Use these documents to orient yourself before reading or modifying any code.
When the documents reference specific files and line numbers, trust those as
your starting points but verify current state since code may have changed
since generation.

The codebase is located at: /path/to/your/project

My task: [describe what you want the AI to do]
```

## Phase 1 only (X-Ray scan)

```
I'm providing a structural scan of this codebase:

1. <your_project>_XRAY.md — A deterministic scan covering architecture,
   dependency graph, complexity hotspots, git risk signals, side effects,
   and security concerns.

Use this document to orient yourself before reading or modifying any code.
The scan provides structural signals (what exists, how it connects, where
complexity lives) but not behavioral details (why code works the way it does).
For behavioral questions, read the source files directly.

The codebase is located at: /path/to/your/project

My task: [describe what you want the AI to do]
```

---

## Tips

- **Attach the files** — don't paste their contents into the prompt. Most AI interfaces support file attachments, which preserves formatting and avoids token waste in your message.
- **Be specific about your task** — "fix the bug in the payment flow" works better than "help me with this codebase" because the AI can use the documents to navigate directly to the relevant modules.
- **Mention staleness if relevant** — if significant code changes have happened since generation, tell the AI: "These docs were generated on [date]. The auth module has been refactored since then — verify before relying on that section."
