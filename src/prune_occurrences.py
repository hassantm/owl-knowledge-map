#!/usr/bin/env python3
"""
Delete occurrence rows that the inclusion rule (v_occurrences) excludes
(Phase 3, 2026-10-03). See docs/20261003_method_reset_plan.md.

Rows fall outside the view when they are recurrences before the concept's
first introduction in curriculum order, belong to a concept that is on no
current vocab list, or belong to a merged or letterless concept. They are
invisible to every consumer, but they block gap-fill (which skips concept/unit
pairs that already have a row) and inflate raw counts.

Rows referenced by a confirmed edge are never deleted; they are reported
for the edge re-check.

Dry run by default (rolls back). Pass --write to commit.

    python3 src/prune_occurrences.py
    python3 src/prune_occurrences.py --write
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402

OUTSIDE_VIEW = """
    SELECT o.occurrence_id FROM occurrences o
    WHERE NOT EXISTS (SELECT 1 FROM v_occurrences v WHERE v.occurrence_id = o.occurrence_id)
"""
EDGE_REFS = "SELECT from_occurrence FROM edges UNION SELECT to_occurrence FROM edges"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='commit the deletion (default: dry run, rolled back)')
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"""SELECT o.occurrence_id, c.term, u.unit FROM occurrences o
                        JOIN concepts c USING (concept_id) JOIN units u USING (unit_id)
                        WHERE o.occurrence_id IN ({OUTSIDE_VIEW}) AND o.occurrence_id IN ({EDGE_REFS})""")
        kept = cur.fetchall()
        cur.execute(f"""DELETE FROM occurrences
                        WHERE occurrence_id IN ({OUTSIDE_VIEW}) AND occurrence_id NOT IN ({EDGE_REFS})""")
        deleted = cur.rowcount
        cur.execute("SELECT count(*) n FROM occurrences")
        remaining = cur.fetchone()['n']
        cur.execute("SELECT count(*) n FROM v_occurrences")
        in_view = cur.fetchone()['n']
        print(f'deleted {deleted} rows outside the inclusion rule; {remaining} rows remain, {in_view} in v_occurrences')
        for k in kept:
            print(f"  kept (edge-referenced): occurrence {k['occurrence_id']} '{k['term']}' in {k['unit']}")
        if args.write:
            conn.commit()
            print('COMMITTED')
        else:
            conn.rollback()
            print('DRY RUN: rolled back')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
