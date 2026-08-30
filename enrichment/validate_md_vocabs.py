"""
Parse markdown vocab files for 5 Geography units and validate their occurrences.

For each unit:
  1. Sets vocab_list_path on the units table row
  2. Parses terms from the markdown file
  3. Updates validation_status on occurrences:
       matched   → term found in vocab list (case-insensitive)
       unmatched → term not found; candidate for deletion
"""

import re
from pathlib import Path
from db import get_connection

VOCAB_DIR = Path(__file__).parent.parent / "data" / "Vocab"

UNIT_VOCAB_MAP = [
    {
        "unit_id": 2,
        "file": "Y3 - Geography - Mountains - vocab.md",
    },
    {
        "unit_id": 3,
        "file": "Y3 Spring1 Geography settlements vocab.md",
    },
    {
        "unit_id": 8,
        "file": "Y4 Autumn 2 Population - Vocab.md",
    },
    {
        "unit_id": 16,
        "file": "Y5 - Spring 2 - North and South America - Vocab.md",
    },
    {
        "unit_id": 18,
        "file": "Y5-summer2-geography-interconnectedAmazon-vocab.md",
    },
]


def parse_vocab_terms(path: Path) -> set[str]:
    """Extract all vocab terms from a markdown file, ignoring chapter headers."""
    terms = set()
    for line in path.read_text().splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        if re.match(r"^#+\s", stripped) or re.match(r"^Chapter\s+\d+", stripped, re.IGNORECASE):
            continue
        if re.match(r"^—", stripped):
            continue
        terms.add(stripped.lower())
    return terms


def run():
    conn = get_connection()
    cur = conn.cursor()

    total_matched = 0
    total_unmatched = 0

    for entry in UNIT_VOCAB_MAP:
        vocab_path = VOCAB_DIR / entry["file"]
        rel_path = f"data/Vocab/{entry['file']}"

        cur.execute(
            "UPDATE units SET vocab_list_path = %s WHERE unit_id = %s",
            (rel_path, entry["unit_id"]),
        )

        terms = parse_vocab_terms(vocab_path)

        cur.execute(
            """SELECT o.occurrence_id, c.term
               FROM occurrences o
               JOIN concepts c ON o.concept_id = c.concept_id
               WHERE o.unit_id = %s""",
            (entry["unit_id"],),
        )
        rows = cur.fetchall()

        matched = unmatched = 0
        for row in rows:
            occ_id = row["occurrence_id"]
            term = row["term"].lower().strip()
            if term in terms:
                status = "matched"
                matched += 1
            else:
                status = "unmatched"
                unmatched += 1
            cur.execute(
                """UPDATE occurrences
                   SET validation_status = %s,
                       vocab_source = %s,
                       vocab_match_type = %s
                 WHERE occurrence_id = %s""",
                (
                    status,
                    rel_path,
                    "exact" if status == "matched" else None,
                    occ_id,
                ),
            )

        cur.execute(
            "SELECT unit FROM units WHERE unit_id = %s", (entry["unit_id"],)
        )
        unit_name = cur.fetchone()["unit"]
        print(f"{unit_name}: {matched} matched, {unmatched} unmatched")
        total_matched += matched
        total_unmatched += unmatched

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nTotal: {total_matched} matched, {total_unmatched} unmatched")
    if total_unmatched:
        print("Review unmatched with:")
        print("  SELECT o.term, u.unit FROM occurrences o JOIN units u ON o.unit_id=u.unit_id")
        print("  WHERE o.validation_status = 'unmatched' ORDER BY u.unit, o.term;")


if __name__ == "__main__":
    run()
