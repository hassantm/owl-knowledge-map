#!/usr/bin/env python3
"""
Load reviewed Phase 4 results into the database (2026-10-04).
See docs/20261003_method_reset_plan.md. Requires migration 010.

  --tags       data/phase4/concept_tags.csv       concept_id, concept_type, category, note
               -> concepts.concept_type / concept_category / concept_type_note
  --ambiguous  data/phase4/ambiguous_concepts.csv concept_id (one row per ambiguous concept)
               -> concepts.is_ambiguous
  --senses     data/phase4/sense_checks.csv       occurrence_id, sense_check, note
               -> occurrences.sense_check / sense_note ('different' drops out of v_occurrences)

Input files are gitignored working files (OWL content). Dry run by default
(rolls back); pass --write to commit.

    python3 src/load_phase4.py --tags
    python3 src/load_phase4.py --tags --ambiguous --senses --write
"""

import argparse
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402

DIR = Path('data/phase4')
# Decided 2026-10-04: subject-technical concepts (spur, headland, push factors, senate)
# are disciplinary concepts and count as transferable, so a one-off use shows as a
# reinforcement gap; unit_specific is for genuinely one-off structures, objects, species.
TYPES = {
    'transferable': {'ABSTRACT', 'DESCRIPTIVE', 'HUMAN', 'MORAL', 'PROCESS', 'VERBADJ', 'TECHNICAL'},
    'proper_noun': {'PROPER', 'SACRED', 'ACT'},
    'unit_specific': {'INFRA', 'LABEL', 'SPECIES'},
}
SENSES = {'same', 'different', 'unclear'}


def load_tags(cur):
    rows = list(csv.DictReader(open(DIR / 'concept_tags.csv')))
    bad = [r for r in rows if r['category'] not in TYPES.get(r['concept_type'], ())]
    if bad:
        raise SystemExit(f'{len(bad)} rows have an invalid type/category pair, e.g. {bad[0]}')
    cur.execute("SELECT DISTINCT concept_id FROM v_occurrences")
    live = {r['concept_id'] for r in cur.fetchall()}
    ids = {int(r['concept_id']) for r in rows}
    if live - ids:
        raise SystemExit(f'{len(live - ids)} concepts in the map have no tag, e.g. {sorted(live - ids)[:5]}')
    for r in rows:
        cur.execute("""UPDATE concepts SET concept_type = %s, concept_category = %s, concept_type_note = %s
                       WHERE concept_id = %s""",
                    (r['concept_type'], r['category'], r.get('note') or None, int(r['concept_id'])))
    print(f'tags: {len(rows)} concepts tagged')


def load_ambiguous(cur):
    ids = [int(r['concept_id']) for r in csv.DictReader(open(DIR / 'ambiguous_concepts.csv'))]
    cur.execute("UPDATE concepts SET is_ambiguous = (concept_id = ANY(%s))", (ids,))
    print(f'ambiguous: {len(ids)} concepts flagged')


def load_senses(cur):
    rows = list(csv.DictReader(open(DIR / 'sense_checks.csv')))
    bad = [r for r in rows if r['sense_check'] not in SENSES]
    if bad:
        raise SystemExit(f'{len(bad)} rows have an invalid sense_check, e.g. {bad[0]}')
    ids = [int(r['occurrence_id']) for r in rows]
    cur.execute("""SELECT count(*) AS n FROM occurrences WHERE occurrence_id = ANY(%s)
                   AND (vocab_source IS DISTINCT FROM 'booklet_gap_fill')""", (ids,))
    if cur.fetchone()['n']:
        raise SystemExit('sense checks apply to recurrences only; some rows are introductions')
    for r in rows:
        cur.execute("UPDATE occurrences SET sense_check = %s, sense_note = %s WHERE occurrence_id = %s",
                    (r['sense_check'], r.get('note') or None, int(r['occurrence_id'])))
    from collections import Counter
    print(f"senses: {len(rows)} recurrences checked {dict(Counter(r['sense_check'] for r in rows))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tags', action='store_true')
    ap.add_argument('--ambiguous', action='store_true')
    ap.add_argument('--senses', action='store_true')
    ap.add_argument('--write', action='store_true', help='commit (default: dry run, rolled back)')
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT to_regclass('public.v_occurrences') IS NOT NULL AND EXISTS ("
                    "SELECT 1 FROM information_schema.columns WHERE table_name = 'concepts' "
                    "AND column_name = 'concept_type') AS present")
        if not cur.fetchone()['present']:
            cur.execute(Path('migrations/010_concept_types_and_sense_checks.sql').read_text())
            print('applied migration 010 (inside this transaction)')
        if args.tags:
            load_tags(cur)
        if args.ambiguous:
            load_ambiguous(cur)
        if args.senses:
            load_senses(cur)
        cur.execute("SELECT count(*) AS n FROM v_occurrences")
        print('v_occurrences:', cur.fetchone()['n'])
        if args.write:
            conn.commit()
            print('COMMITTED')
        else:
            conn.rollback()
            print('DRY RUN: rolled back')
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
