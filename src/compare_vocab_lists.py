#!/usr/bin/env python3
"""
Compare each unit's current authored vocab list with its introductions in the
database (Phase 2, 2026-10-03). Read-only.

For every unit with a list file in data/phase2/lists/, reports:
  on list, not introduced here   -> promote recurrence / add introduction / new concept
  introduced here, not on list   -> remove introduction
  on list as a different form    -> authored form changed (e.g. 'succeed' -> 'succeeds')

Writes data/phase2/list_drift.csv and prints a per-unit summary.

    python3 src/compare_vocab_lists.py
"""

import csv
import sys
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402
from vocab_lists import ConceptIndex, list_files, norm, parse_list_file  # noqa: E402

OUT = 'data/phase2/list_drift.csv'


def main():
    conn = get_connection()
    conn.set_session(readonly=True)
    cur = conn.cursor()
    index = ConceptIndex(cur)
    cur.execute("SELECT unit_id, subject, year, term, unit FROM units")
    units = {r['unit_id']: r for r in cur.fetchall()}

    rows, summary = [], []
    for unit_id, path in list_files().items():
        u = units[unit_id]
        parsed = parse_list_file(path)
        listed = {}                                   # concept_id (or 'new:<entry>') -> (entry, chapter, how)
        for chapter, entry in parsed['entries']:
            cid, how = index.resolve(entry)
            listed.setdefault(cid or f'new:{norm(entry)}', (entry, chapter, how))

        cur.execute("""SELECT concept_id, concept_term, authored_term, is_introduction
                       FROM v_occurrences WHERE unit_id = %s""", (unit_id,))
        occ = cur.fetchall()
        intro = {r['concept_id']: r for r in occ if r['is_introduction']}
        recur = {r['concept_id'] for r in occ if not r['is_introduction']}

        def row(kind, action, concept_id, term, authored, list_entry, chapter, how):
            rows.append(dict(unit_id=unit_id, subject=u['subject'], year=u['year'], term_period=u['term'],
                             unit=u['unit'], kind=kind, proposed_action=action, concept_id=concept_id or '',
                             concept_term=term or '', db_authored_term=authored or '', list_entry=list_entry or '',
                             list_chapter=chapter or '', matched_by=how or ''))

        for key, (entry, chapter, how) in listed.items():
            if isinstance(key, str):
                row('on list, no concept', 'create concept + introduction', None, None, None, entry, chapter, how)
            elif key not in intro:
                action = 'promote recurrence to introduction' if key in recur else 'add introduction'
                row('on list, not introduced here', action, key, index.terms.get(key), None, entry, chapter, how)
            elif norm(intro[key]['authored_term'] or intro[key]['concept_term']) != norm(entry):
                row('authored form differs', 'update authored_term', key, index.terms.get(key),
                    intro[key]['authored_term'], entry, chapter, how)
        for cid, r in intro.items():
            if cid not in listed:
                row('introduced here, not on list', 'remove introduction', cid, r['concept_term'],
                    r['authored_term'], None, None, None)

        kinds = Counter(r['kind'] for r in rows if r['unit_id'] == unit_id)
        summary.append((unit_id, u['subject'], u['unit'], len(parsed['entries']), len(intro), kinds))

    with open(OUT, 'w', newline='') as f:
        fields = ['unit_id', 'subject', 'year', 'term_period', 'unit', 'kind', 'proposed_action', 'concept_id',
                  'concept_term', 'db_authored_term', 'list_entry', 'list_chapter', 'matched_by']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"{'unit':>4}  {'subject':<9} {'unit name':<36} {'list':>4} {'db':>4}  add  new  remove  form")
    for unit_id, subject, name, n_list, n_db, k in summary:
        add = k['on list, not introduced here']
        print(f"{unit_id:>4}  {subject:<9} {name[:36]:<36} {n_list:>4} {n_db:>4}  {add:>3}  {k['on list, no concept']:>3}"
              f"  {k['introduced here, not on list']:>6}  {k['authored form differs']:>4}")
    total = Counter(r['kind'] for r in rows)
    print(f'\n{len(summary)} units compared; {dict(total)}; written to {OUT}')
    conn.close()


if __name__ == '__main__':
    sys.exit(main())
