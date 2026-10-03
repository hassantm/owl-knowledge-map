#!/usr/bin/env python3
"""
Generate inflected forms for every concept and stage them for review
(Phase 2, 2026-10-03). See docs/20261003_method_reset_plan.md.

  python3 src/generate_inflections.py            # write data/phase2/inflection_review.csv (read-only on the DB)
  python3 src/generate_inflections.py --load     # dry run: load reviewed decisions into concept_forms
  python3 src/generate_inflections.py --load --write

Generation: the head (last) word of each concept is inflected with lemminflect -
noun plurals and verb forms; adjective comparatives are skipped, as are function
words ("stood for" does not yield "fors"). A form is dropped if it is already a
form of the concept, or is the term or authored form of another concept (so
concepts kept separate, e.g. 'forced'/'forces', stay apart).

Only forms that would add a recurrence are staged: the form appears in the
cleaned booklet text of a unit at or after the concept's first introduction,
where the concept is not already recorded. Each row shows that impact and an
example context. Risk: low = regular plural of a known noun (pre-approved);
medium = verb form, out-of-vocabulary guess or capitalised name; high = a plural
whose meaning can differ from the singular ('goods', 'arms').

Review by editing the decision column (approve / reject). --load records every
row in concept_forms as kind 'inflection' with status approved or rejected.
"""

import argparse
import csv
import re
import sys
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402
from gap_fill_occurrences import build_pattern, clean_page_text, curriculum_pos  # noqa: E402
from lemminflect import getAllInflections, getAllInflectionsOOV, getAllLemmas, getAllLemmasOOV  # noqa: E402
from vocab_lists import norm  # noqa: E402

OUT = 'data/phase2/inflection_review.csv'

FUNCTION_WORDS = {
    'a', 'an', 'the', 'of', 'to', 'in', 'on', 'at', 'by', 'for', 'with', 'from', 'up', 'down', 'out', 'off',
    'over', 'into', 'onto', 'upon', 'about', 'as', 'and', 'or', 'but', 'nor', 'so', 'than', 'that', 'this',
    'is', 'was', 'be', 'it', 'its', 'his', 'her', 'their', 'our', 'my', 'your', 'all', 'no', 'not', 'one',
    'fro', 'away', 'back', 'through', 'against', 'between', 'under', 'within', 'without',
}
# plurals whose meaning can differ from the singular
SENSE_SHIFT = {'goods', 'customs', 'arms', 'remains', 'manners', 'forces', 'quarters', 'spirits', 'letters',
               'papers', 'grounds', 'means', 'works', 'troops', 'ashes', 'riches', 'clothes', 'savings',
               'belongings', 'premises', 'damages', 'glasses', 'irons', 'looks', 'minutes', 'orders', 'pains',
               'parts', 'regards', 'terms', 'rights', 'sands', 'waters', 'heavens', 'times', 'lines', 'arts',
               'humanities', 'letters', 'colours', 'stocks', 'tops', 'grains', 'spectacles', 'surroundings'}
TAGS = {'NNS': 'plural', 'VBD': 'past', 'VBN': 'past participle', 'VBG': '-ing', 'VBZ': '-s (verb)'}


def generate(term: str):
    """Yield (form, tag, oov) for inflections of the term's head word."""
    words = term.split(' ')
    head = words[-1]
    if head.lower() in FUNCTION_WORDS or not re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", head):
        return
    lemmas = getAllLemmas(head.lower())
    oov = not lemmas
    if oov:
        if head[:1].isupper():                  # unknown capitalised word: a name; don't guess
            return
        lemmas = getAllLemmasOOV(head.lower(), upos='NOUN')
    for pos, lems in lemmas.items():
        if pos not in ('NOUN', 'VERB'):
            continue
        for lemma in lems:
            infl = getAllInflections(lemma, upos=pos) or getAllInflectionsOOV(lemma, upos=pos)
            for tag, forms in infl.items():
                if tag not in TAGS:
                    continue
                for f in forms:
                    if head[:1].isupper():
                        f = f[:1].upper() + f[1:]
                    yield ' '.join(words[:-1] + [f]), tag, oov


def build_review(conn):
    cur = conn.cursor()
    cur.execute("SELECT unit_id, year, term, unit, booklet_content->'pages' AS pages FROM units")
    units = []
    for r in cur.fetchall():
        text = '\n'.join(clean_page_text(p.get('text') or '') for p in (r['pages'] or {}).values())
        units.append(dict(unit_id=r['unit_id'], unit=r['unit'], pos=curriculum_pos(r['year'], r['term']),
                          text=text, lower=text.lower()))

    cur.execute("""SELECT c.concept_id, c.term, min(v.curriculum_pos) FILTER (WHERE v.is_introduction) first_pos,
                          array_agg(DISTINCT v.unit_id) unit_ids
                   FROM concepts c JOIN v_occurrences v USING (concept_id)
                   WHERE c.merged_into IS NULL GROUP BY 1, 2""")
    concepts = cur.fetchall()
    cur.execute("""SELECT f.concept_id, f.form FROM concept_forms f JOIN concepts c USING (concept_id)
                   WHERE c.merged_into IS NULL AND f.status <> 'rejected'""")
    forms_of = defaultdict(set)
    owner = {}
    for r in cur.fetchall():
        forms_of[r['concept_id']].add(norm(r['form']))
        owner.setdefault(norm(r['form']), r['concept_id'])
    for c in concepts:
        forms_of[c['concept_id']].add(norm(c['term']))
        owner.setdefault(norm(c['term']), c['concept_id'])

    rows, collisions = [], 0
    for c in concepts:
        seen = set()
        for form, tag, oov in generate(c['term']):
            k = norm(form)
            if k in seen or k in forms_of[c['concept_id']]:
                continue
            seen.add(k)
            if owner.get(k, c['concept_id']) != c['concept_id']:
                collisions += 1
                continue
            pat = build_pattern(form)
            new_units, example = [], ''
            for u in units:
                if u['pos'] < c['first_pos'] or u['unit_id'] in c['unit_ids'] or k not in u['lower']:
                    continue
                m = pat.search(u['text'])
                if m:
                    new_units.append(u['unit'])
                    if not example:
                        example = f"{u['unit']}: ..." + ' '.join(u['text'][max(0, m.start() - 70):m.end() + 70].split()) + '...'
            if not new_units:
                continue
            if k.split(' ')[-1] in SENSE_SHIFT:
                risk, why = 'high', 'plural may have a different meaning'
            elif tag != 'NNS':
                risk, why = 'medium', 'verb form'
            elif oov:
                risk, why = 'medium', 'word not in dictionary: plural is a guess'
            elif c['term'][:1].isupper():
                risk, why = 'medium', 'capitalised: name or title?'
            else:
                risk, why = 'low', 'regular plural'
            rows.append(dict(risk=risk, decision='approve' if risk == 'low' else 'review', concept_id=c['concept_id'],
                             concept=c['term'], form=form, form_type=TAGS[tag], reason=why,
                             new_units=len(new_units), units='; '.join(new_units), example=example[:260]))
    rows.sort(key=lambda r: ({'high': 0, 'medium': 1, 'low': 2}[r['risk']], r['concept'].lower(), r['form']))
    return rows, collisions


def load(conn, write):
    rows = list(csv.DictReader(open(OUT)))
    undecided = [r for r in rows if r['decision'] not in ('approve', 'reject')]
    if undecided:
        raise SystemExit(f'{len(undecided)} rows still need a decision (approve / reject)')
    cur = conn.cursor()
    for r in rows:
        status = 'approved' if r['decision'] == 'approve' else 'rejected'
        cur.execute("""INSERT INTO concept_forms (concept_id, form, kind, status, source)
                       VALUES (%s, %s, 'inflection', %s, 'lemminflect (reviewed 2026-10-03)')
                       ON CONFLICT (concept_id, lower(form)) DO UPDATE SET status = EXCLUDED.status""",
                    (int(r['concept_id']), r['form'], status))
    approved = sum(r['decision'] == 'approve' for r in rows)
    print(f'{approved} approved, {len(rows) - approved} rejected')
    if write:
        conn.commit()
        print('COMMITTED')
    else:
        conn.rollback()
        print('DRY RUN: rolled back')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--load', action='store_true', help='load reviewed decisions into concept_forms')
    ap.add_argument('--write', action='store_true', help='with --load: commit (default: dry run)')
    args = ap.parse_args()
    conn = get_connection()
    try:
        if args.load:
            return load(conn, args.write)
        conn.set_session(readonly=True)
        rows, collisions = build_review(conn)
        with open(OUT, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        from collections import Counter
        print(f"{len(rows)} forms would add recurrences; {collisions} forms skipped as another concept's term")
        print('by risk:', dict(Counter(r['risk'] for r in rows)))
        print('new recurrences:', sum(r['new_units'] for r in rows),
              {k: sum(r['new_units'] for r in rows if r['risk'] == k) for k in ('low', 'medium', 'high')})
        print(f'written to {OUT}')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
