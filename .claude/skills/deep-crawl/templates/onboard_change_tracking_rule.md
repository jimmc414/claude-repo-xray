# Onboarding Document Change Tracking

Paste this rule into the CLAUDE.md of any repo that has a docs/DEEP_ONBOARD.md.
Phase 6 of the deep crawl injects this automatically for new crawls. This
template is for repos that already have DEEP_ONBOARD.md but haven't been
re-crawled with the updated Phase 6.

---

## Rule text (copy below this line into CLAUDE.md)

### Onboarding Document Change Tracking

If you modify code that may affect claims in docs/DEEP_ONBOARD.md, append to docs/.onboard_changes.log:

    {ISO_TIMESTAMP} | {FILE:LINE} | {SECTION_PATH} | {BRIEF_DESCRIPTION}

Section path uses document headings: `{## Section}` or `{## Section} / {### Subsection}`.

Examples:

    2026-04-01T14:23:00Z | executor.py:617 | Gotchas / Process Management | Changed timeout from SIGALRM to asyncio.wait_for
    2026-04-01T14:30:00Z | api_router.py:45 | Critical Paths / API Request | Added rate limiting middleware
    2026-04-01T14:40:00Z | config.py:12 | Configuration Surface | New REDIS_URL env var required

Do not manually edit DEEP_ONBOARD.md — it is a generated artifact maintained by the deep crawl pipeline.
