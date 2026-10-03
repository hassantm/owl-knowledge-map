#!/usr/bin/env python3
"""
Align every unit's introductions with its current authored vocab list
(Phase 2, 2026-10-03). See docs/20261003_method_reset_plan.md.

Lists come from data/phase2/lists/<unit_id>_*.txt (fetched from Dropbox;
compare_vocab_lists.py reports the drift this script resolves). Per unit:
  - each list entry resolves to a concept (exact, authored form, base form,
    or wording variant); entries with no concept get a new concept;
  - introductions not on the list are removed (gap-fill will count the word
    as a recurrence if the booklet still uses it);
  - listed concepts without an introduction get one, promoting an existing
    recurrence in the unit where there is one;
  - authored_term and vocab_source record the list's exact form and file.

Dry run by default (rolls back). Pass --write to commit.

    python3 src/align_vocab_lists.py
    python3 src/align_vocab_lists.py --write
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402
from phase2_concept_hygiene import Hygiene  # noqa: E402
from vocab_lists import ConceptIndex, base_key, list_files, norm, parse_list_file  # noqa: E402

# The current list words an existing concept differently (reviewed 2026-10-03):
# list entry -> existing concept term. The entry is recorded as an authored form.
SAME_AS = {
    'trapping of power': 'trappings of power',
    'savannah': 'savanna',
    'Gaugalmela': 'Gaugamela',             # typo in the list
    'Battle of Marathon': 'Marathon',
}
# Typos in the list for new concepts: kept as authored, matched by the correct spelling too.
TYPO_FORMS = {
    'unleavened bred': 'unleavened bread',
    'veni, vedi, vici': 'veni, vidi, vici',
}

LIST_INTRO = """vocab_source IS DISTINCT FROM 'booklet_gap_fill'
                AND (vocab_source IS NOT NULL OR is_introduction = 1)"""


class Aligner(Hygiene):

    def source_file(self, parsed):
        for m in parsed['meta']:
            if m.startswith('file:'):
                return m.split(':', 1)[1].strip().split(' (')[0]
        return None

    def map_same_as(self):
        for entry, existing in SAME_AS.items():
            self.q("SELECT concept_id FROM concepts WHERE merged_into IS NULL AND term = %s", (existing,))
            row = self.cur.fetchone()
            if not row:
                raise RuntimeError(f'SAME_AS target missing: {existing}')
            self.add_form(row['concept_id'], entry, source='current vocab list wording')

    def align_unit(self, unit_id, path, index):
        parsed = parse_list_file(path)
        source = self.source_file(parsed) or path.name
        self.q("SELECT subject FROM units WHERE unit_id = %s", (unit_id,))
        subject = self.cur.fetchone()['subject']

        by_key = {}
        for _, e in parsed['entries']:
            by_key.setdefault(base_key(e), []).append(e)
        wanted, created = {}, []
        for key, forms in by_key.items():
            cid = next((c for c in (index.resolve(f)[0] for f in forms) if c), None)
            if cid is None:
                cid = self.create_concept(next((f for f in forms if norm(f) == key), forms[0]), subject)
                created.append(forms[0])
                index.terms[cid] = forms[0]
                index.by_norm.setdefault(norm(forms[0]), cid)
                index.by_key.setdefault(key, cid)
            wanted.setdefault(cid, forms[0])
            for f in forms:
                self.add_form(cid, f, source=source)
                if f in TYPO_FORMS:
                    self.add_form(cid, TYPO_FORMS[f], source=f'correct spelling of list typo "{f}"')

        self.q(f"""SELECT o.occurrence_id, o.concept_id, coalesce(o.authored_term, c.term) AS authored_term
                   FROM occurrences o JOIN concepts c USING (concept_id)
                   WHERE o.unit_id = %s AND {LIST_INTRO.replace('vocab_source', 'o.vocab_source').replace('is_introduction', 'o.is_introduction')}""", (unit_id,))
        current = self.cur.fetchall()
        drop = [r for r in current if r['concept_id'] not in wanted]
        ids = [r['occurrence_id'] for r in drop]
        # rows a confirmed edge points at are demoted to recurrences (migration 009), not deleted
        self.q("""UPDATE occurrences SET is_introduction = 0, vocab_source = 'list_removed'
                  WHERE occurrence_id = ANY(%s)
                    AND occurrence_id IN (SELECT from_occurrence FROM edges UNION SELECT to_occurrence FROM edges)
                  RETURNING occurrence_id, (SELECT term FROM concepts c WHERE c.concept_id = occurrences.concept_id) AS authored_term""", (ids,))
        demoted = self.cur.fetchall()
        for d in demoted:
            self.note(f"unit {unit_id}: '{d['authored_term']}' kept as a recurrence (edge-referenced)")
        rest = [i for i in ids if i not in {d['occurrence_id'] for d in demoted}]
        if rest:
            self.delete_occurrences("occurrence_id = ANY(%s)", (rest,), label=f'unit {unit_id} off-list intros')
        have = {r['concept_id'] for r in current if r['concept_id'] in wanted}

        added, promoted, reform = [], [], 0
        for cid, entry in wanted.items():
            if cid in have:
                self.q(f"""UPDATE occurrences SET vocab_source = %s, authored_term = %s, is_introduction = 1
                           WHERE unit_id = %s AND concept_id = %s AND {LIST_INTRO}
                             AND (authored_term IS DISTINCT FROM %s OR vocab_source IS DISTINCT FROM %s
                                  OR is_introduction <> 1)""",
                       (source, entry, unit_id, cid, entry, source))
                reform += self.cur.rowcount
                continue
            self.q("""UPDATE occurrences SET is_introduction = 1, vocab_source = %s, authored_term = %s
                      WHERE occurrence_id = (SELECT min(occurrence_id) FROM occurrences
                                             WHERE unit_id = %s AND concept_id = %s)
                      RETURNING occurrence_id""", (source, entry, unit_id, cid))
            if self.cur.fetchone():
                promoted.append(entry)
                continue
            page, chapter, ctx = self.find_context(unit_id, entry)
            self.q("""INSERT INTO occurrences (concept_id, unit_id, subject, year, term, unit, chapter,
                          slide_number, is_introduction, term_in_context, vocab_source, authored_term)
                      SELECT %s, unit_id, subject, year, term, unit, %s, %s, 1, %s, %s, %s
                      FROM units WHERE unit_id = %s""",
                   (cid, chapter, page, ctx, source, entry, unit_id))
            added.append(entry)

        if drop or added or promoted or created:
            self.note(f"unit {unit_id}: -{len(drop)} off-list ({', '.join(r['authored_term'] or '?' for r in drop) or 'none'}); "
                      f"+{len(added) + len(promoted)} intros ({', '.join(added + [p + '*' for p in promoted]) or 'none'}); "
                      f"{len(created)} new concepts; {reform} rows re-sourced")
        return dict(dropped=len(drop), added=len(added), promoted=len(promoted), created=len(created), reformed=reform)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='commit the changes (default: dry run, rolled back)')
    args = ap.parse_args()

    conn = get_connection()
    a = Aligner(conn)
    try:
        print('before:', a.summary())
        a.q("SELECT pg_get_viewdef('v_occurrences') LIKE '%list_removed%' AS present")
        if not a.cur.fetchone()['present']:
            a.q(open('migrations/009_list_removed_recurrences.sql').read())
            print('applied migration 009 (inside this transaction)')
        a.map_same_as()
        index = ConceptIndex(a.cur)
        totals = {}
        for unit_id, path in list_files().items():
            for k, v in a.align_unit(unit_id, path, index).items():
                totals[k] = totals.get(k, 0) + v
        a.dedupe()
        after = a.summary()
        print('totals:', totals, '(* = promoted recurrence)')
        print('after: ', after)
        if after['dup_pairs'] or after['nonlist_intros']:
            raise RuntimeError('duplicates or non-list introductions remain')
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
