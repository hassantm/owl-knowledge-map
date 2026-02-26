# Audit Review Guide — `term_audit_enriched.csv`

Open `output/term_audit_enriched.csv` in Excel or Numbers. Fill in the `decision` column. Leave blank to skip (no action taken).

---

## Decision values by issue type

| `issue_type` | Valid decisions | Meaning |
|---|---|---|
| `missed_from_extraction` | `add` | Term found unbolded in PPTX — insert into DB as a non-introduction occurrence |
| `missed_from_extraction` | `skip` / blank | Ignore — don't add to DB |
| `potential_noise` | `keep` | Confirm it's a valid concept — marks `validation_status = confirmed` |
| `potential_noise` | `delete` | Remove from DB; orphan concepts cleaned up automatically |
| `potential_noise` | `skip` / blank | No action |
| `high_priority_review` | `keep` | Same as above |
| `high_priority_review` | `delete` | Same as above |
| `high_priority_review` | `skip` / blank | No action |

---

## Key columns to check when deciding

**For `missed_from_extraction` rows:**
- `appears_unbolded` — `True` means the term was found in the PPTX text (unbolded). `False` means genuinely absent. Only set `add` if this is `True`.
- `unbolded_slides` — which slides it appears on
- `unbolded_context` — the surrounding paragraph text to judge whether it's conceptual

**For `potential_noise` and `high_priority_review` rows:**
- `occurrence_id` — pre-filled; required for delete/keep to work
- `term` — the extracted bold text
- `context` — the paragraph it came from
- `review_reason` — why it was flagged (`short_term`, `potential_heading`, `all_caps`)

---

## After filling in decisions

```bash
python src/apply_audit_decisions.py
```

Prints a summary (N deleted, N confirmed, N added) and writes a full audit trail to `output/audit_decisions_log.csv`.

Safe to re-run — all operations are idempotent.
