# repo-retrospective Commands

Quick reference for the repo-retrospective skill.

## Modes

| Mode | Purpose | Token Budget |
|------|---------|--------------|
| `full` | Complete retrospective (all 5 phases) | ~30-40K |
| `quick` | Verification audit only | ~15-20K |
| `coverage` | Gap analysis (ONBOARD vs X-Ray) | ~15-20K |
| `actionability` | Usability test only | ~10-15K |

---

## Usage Examples

### Full Retrospective

```bash
@repo_retrospective full \
  --onboard examples/KOSMOS_ONBOARD_v2.md \
  --xray examples/kosmos_xray_output_v31.md \
  --codebase /mnt/c/python/kosmos
```

### Quick Verification

```bash
@repo_retrospective quick \
  --onboard examples/KOSMOS_ONBOARD_v2.md \
  --codebase /mnt/c/python/kosmos
```

### Coverage Analysis

```bash
@repo_retrospective coverage \
  --onboard examples/KOSMOS_ONBOARD_v2.md \
  --xray examples/kosmos_xray_output_v31.md
```

### Actionability Test

```bash
@repo_retrospective actionability \
  --onboard examples/KOSMOS_ONBOARD_v2.md
```

---

## Required Inputs by Mode

| Mode | ONBOARD | X-Ray | Codebase |
|------|---------|-------|----------|
| `full` | Required | Required | Required |
| `quick` | Required | — | Required |
| `coverage` | Required | Required | — |
| `actionability` | Required | — | — |

---

## Output Location

Reports are written to the same directory as the ONBOARD document:

```
examples/
├── KOSMOS_ONBOARD_v2.md
└── KOSMOS_RETROSPECTIVE.md  ← Generated report
```

Or specify custom output:

```bash
@repo_retrospective full ... --output reports/RETROSPECTIVE.md
```

---

## Quick Checks

### Verify a single claim

```bash
# In conversation, ask:
"Can you verify the claim at line 245 of ONBOARD.md about exponential backoff?"
```

### Check coverage of specific X-Ray section

```bash
# In conversation, ask:
"Check if the Data Models section from X-Ray is adequately covered in ONBOARD"
```

### Test specific actionability question

```bash
# In conversation, ask:
"Using only ONBOARD.md, can you explain how to add a new agent?"
```

---

## Verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| **Ship It** | High quality, ready to use | Commit |
| **Needs Minor Fixes** | Good but has 1-3 issues | Fix and commit |
| **Needs Significant Rework** | Critical problems | Re-run repo_xray |

---

## Integration

Typical workflow:

```bash
# 1. Generate X-Ray scan
python xray.py /path/to/code --output both --out analysis

# 2. Run repo_xray agent to create ONBOARD
@repo_xray analyze

# 3. Run retrospective to QA the ONBOARD
@repo_retrospective full \
  --onboard analysis/ONBOARD.md \
  --xray analysis/xray.md \
  --codebase /path/to/code

# 4. Fix any issues identified

# 5. Ship both documents
```
