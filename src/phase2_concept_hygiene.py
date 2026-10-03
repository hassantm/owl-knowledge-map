#!/usr/bin/env python3
"""
Phase 2 concept hygiene (2026-10-03). See docs/20261003_method_reset_plan.md.

Applies, in one transaction:
  1. Seeds concept_forms with every concept's authored term, and backfills
     occurrences.authored_term for introductions.
  2. Removes the 24 bold-only introductions (23 + the letterless "–") from the 2026-10-02 Sikhism 1
     extraction, and the fragment concepts it created (ids 3502-3518).
  3. Repairs truncated terms ("urret" -> "turret") and merges truncations whose
     repaired form already exists ("lexandria" -> "Alexandria").
  4. Fixes fragments: "the Davidic" -> "the Davidic line"; collapses whitespace.
  5. Merges concepts that are forms of one base word, per the reviewed
     data/phase2/merge_review.csv (decision = merge).
  6. Aligns introductions for units 9, 44 and 50 with their current Dropbox
     vocab lists (data/phase2/lists/).
  7. Removes duplicate occurrences created by the merges, repointing any edges.

Dry run by default (rolls back). Pass --write to commit.
Requires migrations/008_concept_forms_and_merges.sql.

Run from the repo root:
    python3 src/phase2_concept_hygiene.py
    python3 src/phase2_concept_hygiene.py --write
"""

import argparse
import csv
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402
from gap_fill_occurrences import build_pattern, clean_page_text, detect_chapter_from_page  # noqa: E402
from lemminflect import getAllLemmas, getAllLemmasOOV  # noqa: E402

PHASE2 = Path('data/phase2')

BOLD_ONLY_UNIT = 61
FRAGMENT_CONCEPTS = range(3502, 3519)          # created by the 2026-10-02 Sikhism 1 extraction

TRUNCATION_RENAMES = {1141: 'turret', 1200: 'contemporaries', 1269: 'browsing',
                      1604: 'groynes', 2855: 'extreme', 2867: 'Buddha'}
TRUNCATION_MERGES = {290: 299, 2569: 3358, 3062: 1898}   # lexandria, hurch, renched
FRAGMENT_MERGES = {2413: 3208}                           # the Davidic -> the Davidic line

UNIT_LISTS = {
    50: ('50_family_of_jesus.txt', 'A-Z - Y4 Autumn 1 Family of Jesus Core vocab.docx'),
    44: ('44_rama_and_sita.txt', 'Y3 Spring 1 A Hindu Story_ Rama and Sita Core Vocab.pdf'),
    9:  ('9_coastal_processes.txt', 'Y4 Spring 1 Coastal Processes and Landforms Core vocab.pdf'),
}
FUSED_CONCEPTS = {2136: ['Hindus', 'Hinduism']}           # "Hindus.   Hinduism"


def norm(term: str) -> str:
    return ' '.join(term.replace('’', "'").split()).lower()


def base_key(term: str) -> str:
    """Normalised term with its head (last) word reduced to its base form: 'succeeds' -> 'succeed'."""
    words = norm(term).split(' ')
    lemmas = getAllLemmas(words[-1]) or getAllLemmasOOV(words[-1], upos='NOUN')
    for pos in ('NOUN', 'PROPN', 'VERB', 'ADJ'):
        if pos in lemmas:
            words[-1] = lemmas[pos][0].lower()
            break
    return ' '.join(words)


class Hygiene:
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
        self.log = []

    def q(self, sql, params=None):
        self.cur.execute(sql, params)
        return self.cur

    def note(self, msg):
        self.log.append(msg)
        print('  ' + msg)

    # -- helpers -------------------------------------------------------------

    def add_form(self, concept_id, form, kind='authored', status='approved', source=None):
        self.q("""INSERT INTO concept_forms (concept_id, form, kind, status, source)
                  VALUES (%s, %s, %s, %s, %s)
                  ON CONFLICT (concept_id, lower(form)) DO NOTHING""",
               (concept_id, form, kind, status, source))

    def merge(self, from_id, into_id, why):
        """Soft-merge from_id into into_id: move occurrences and forms, mark merged_into."""
        if from_id == into_id:
            return
        self.q("UPDATE occurrences SET concept_id = %s WHERE concept_id = %s", (into_id, from_id))
        moved = self.cur.rowcount
        self.q("""INSERT INTO concept_forms (concept_id, form, kind, status, source)
                  SELECT %s, form, kind, status, coalesce(source, '') || ' (merged from ' || %s || ')'
                  FROM concept_forms WHERE concept_id = %s
                  ON CONFLICT (concept_id, lower(form)) DO NOTHING""", (into_id, str(from_id), from_id))
        self.q("DELETE FROM concept_forms WHERE concept_id = %s", (from_id,))
        self.q("UPDATE concepts SET merged_into = %s WHERE concept_id = %s", (into_id, from_id))
        self.q("UPDATE concepts SET merged_into = %s WHERE merged_into = %s", (into_id, from_id))
        return moved

    def delete_occurrences(self, where, params, expect=None, label=''):
        self.q(f"SELECT occurrence_id FROM occurrences WHERE {where}", params)
        ids = [r['occurrence_id'] for r in self.cur.fetchall()]
        if expect is not None and len(ids) != expect:
            raise RuntimeError(f'{label}: expected {expect} rows, found {len(ids)}')
        if ids:
            self.q("SELECT count(*) n FROM edges WHERE from_occurrence = ANY(%s) OR to_occurrence = ANY(%s)", (ids, ids))
            if self.cur.fetchone()['n']:
                raise RuntimeError(f'{label}: edges reference rows to be deleted')
            self.q("DELETE FROM occurrences WHERE occurrence_id = ANY(%s)", (ids,))
        return len(ids)

    def delete_concepts(self, ids, label=''):
        ids = list(ids)
        self.q("SELECT count(*) n FROM occurrences WHERE concept_id = ANY(%s)", (ids,))
        if self.cur.fetchone()['n']:
            raise RuntimeError(f'{label}: concepts still have occurrences')
        self.q("DELETE FROM co_occurrences WHERE concept_a_id = ANY(%s) OR concept_b_id = ANY(%s)", (ids, ids))
        self.q("DELETE FROM concept_forms WHERE concept_id = ANY(%s)", (ids,))
        self.q("DELETE FROM concepts WHERE concept_id = ANY(%s)", (ids,))
        return self.cur.rowcount

    def concept_by_term(self, term):
        self.q("""SELECT concept_id FROM concepts WHERE merged_into IS NULL
                  AND lower(regexp_replace(replace(term, '’', ''''), '\\s+', ' ', 'g')) = %s
                  ORDER BY concept_id LIMIT 1""", (norm(term),))
        row = self.cur.fetchone()
        if row:
            return row['concept_id']
        self.q("""SELECT concept_id FROM concept_forms f JOIN concepts c USING (concept_id)
                  WHERE c.merged_into IS NULL AND f.kind = 'authored'
                  AND lower(regexp_replace(replace(f.form, '’', ''''), '\\s+', ' ', 'g')) = %s
                  ORDER BY concept_id LIMIT 1""", (norm(term),))
        row = self.cur.fetchone()
        if row:
            return row['concept_id']
        # fall back to base form, so a list's 'succeeds' finds the concept 'succeed'
        key = base_key(term)
        self.q("SELECT concept_id, term FROM concepts WHERE merged_into IS NULL ORDER BY concept_id")
        for r in self.cur.fetchall():
            if base_key(r['term']) == key:
                return r['concept_id']
        return None

    def create_concept(self, term, subject):
        self.q("INSERT INTO concepts (term, subject_area) VALUES (%s, %s) RETURNING concept_id", (term, subject))
        cid = self.cur.fetchone()['concept_id']
        self.add_form(cid, term, source='vocab list')
        return cid

    def find_context(self, unit_id, term):
        """First match of term in the unit's cleaned booklet text: (page, chapter, snippet)."""
        self.q("SELECT booklet_content->'pages' AS pages FROM units WHERE unit_id = %s", (unit_id,))
        pages = self.cur.fetchone()['pages'] or {}
        pat = build_pattern(term)
        chapter = None
        for num in sorted(pages, key=int):
            text = clean_page_text(pages[num].get('text') or '')
            chapter = detect_chapter_from_page(text) or chapter
            m = pat.search(text)
            if m:
                s, e = max(0, m.start() - 60), min(len(text), m.end() + 60)
                return int(num), chapter, ' '.join(text[s:e].split())
        return None, None, None

    # -- steps ---------------------------------------------------------------

    def seed_forms(self):
        self.q("""INSERT INTO concept_forms (concept_id, form, kind, status, source)
                  SELECT concept_id, term, 'authored', 'approved', 'concepts.term' FROM concepts
                  ON CONFLICT (concept_id, lower(form)) DO NOTHING""")
        self.note(f'seeded {self.cur.rowcount} authored forms')
        self.q("""UPDATE occurrences o SET authored_term = c.term FROM concepts c
                  WHERE c.concept_id = o.concept_id AND o.authored_term IS NULL
                    AND o.is_introduction = 1
                    AND o.vocab_source IS DISTINCT FROM 'booklet_gap_fill'""")
        self.note(f'backfilled authored_term on {self.cur.rowcount} introductions')

    def remove_bold_only(self):
        n = self.delete_occurrences("unit_id = %s AND vocab_source = 'bold_extraction'",
                                    (BOLD_ONLY_UNIT,), expect=24, label='bold-only intros')  # 23 + the letterless '–'
        m = self.delete_occurrences("concept_id = ANY(%s)", (list(FRAGMENT_CONCEPTS),), label='fragment concept rows')
        c = self.delete_concepts(FRAGMENT_CONCEPTS, label='fragment concepts')
        self.note(f'removed {n} bold-only introductions, {m} other rows and {c} fragment concepts')

    def repair_truncations(self):
        for cid, term in TRUNCATION_RENAMES.items():
            self.q("SELECT term FROM concepts WHERE concept_id = %s", (cid,))
            old = self.cur.fetchone()['term']
            self.q("UPDATE concepts SET term = %s WHERE concept_id = %s", (term, cid))
            self.q("UPDATE occurrences SET authored_term = %s WHERE concept_id = %s AND authored_term = %s", (term, cid, old))
            self.q("DELETE FROM concept_forms WHERE concept_id = %s AND form = %s", (cid, old))
            self.add_form(cid, term, source='truncation repair')
        for src, dst in {**TRUNCATION_MERGES, **FRAGMENT_MERGES}.items():
            self.q("SELECT term FROM concepts WHERE concept_id = %s", (dst,))
            good = self.cur.fetchone()['term']
            self.q("UPDATE occurrences SET authored_term = %s WHERE concept_id = %s AND authored_term IS NOT NULL", (good, src))
            self.q("DELETE FROM concept_forms WHERE concept_id = %s", (src,))
            self.merge(src, dst, 'truncation/fragment')
        self.q("""UPDATE concepts SET term = regexp_replace(term, '\\s{2,}', ' ', 'g')
                  WHERE term ~ '\\s{2,}' AND concept_id NOT IN (SELECT unnest(%s))""", (list(FUSED_CONCEPTS),))
        self.note(f'repaired {len(TRUNCATION_RENAMES)} truncated terms, merged {len(TRUNCATION_MERGES) + len(FRAGMENT_MERGES)} truncations/fragments, collapsed whitespace in {self.cur.rowcount} terms')

    def merge_base_forms(self):
        rows = list(csv.DictReader(open(PHASE2 / 'merge_review.csv')))
        merged = 0
        for r in rows:
            if r['decision'] == 'merge' and r['role'].startswith('merge into'):
                into = int(r['role'].split()[-1])
                self.merge(int(r['concept_id']), into, 'base form')
                merged += 1
        self.note(f'merged {merged} concepts into their base-form concept')

    def align_units(self):
        for unit_id, (fname, source_file) in UNIT_LISTS.items():
            entries = [l.strip() for l in open(PHASE2 / 'lists' / fname) if l.strip()]
            self.q("SELECT subject FROM units WHERE unit_id = %s", (unit_id,))
            subject = self.cur.fetchone()['subject']

            # fused concepts: split into their parts before matching
            for fused, parts in FUSED_CONCEPTS.items():
                self.q("SELECT 1 FROM occurrences WHERE concept_id = %s AND unit_id = %s", (fused, unit_id))
                if self.cur.fetchone():
                    self.delete_occurrences("concept_id = %s", (fused,), label='fused concept rows')
                    self.delete_concepts([fused], label='fused concept')
                    self.note(f'unit {unit_id}: removed fused concept {fused}; parts {parts} come from the list')

            # group entries that are forms of one word ('deposit', 'depositing'); a new concept
            # takes the entry that is the base form itself, if the list has one
            by_key = {}
            for e in entries:
                by_key.setdefault(base_key(e), []).append(e)
            wanted = {}                     # concept_id -> authored entry
            for key, forms in by_key.items():
                cid = next((c for c in map(self.concept_by_term, forms) if c), None)
                if cid is None:
                    cid = self.create_concept(next((f for f in forms if norm(f) == key), forms[0]), subject)
                wanted.setdefault(cid, forms[0])
                for f in forms:
                    self.add_form(cid, f, source=source_file)

            self.q("""SELECT occurrence_id, concept_id FROM occurrences
                      WHERE unit_id = %s AND is_introduction = 1
                        AND vocab_source IS DISTINCT FROM 'booklet_gap_fill'""", (unit_id,))
            current = self.cur.fetchall()
            drop = [r['occurrence_id'] for r in current if r['concept_id'] not in wanted]
            self.q("SELECT string_agg(coalesce(authored_term, '?'), ', ') t FROM occurrences WHERE occurrence_id = ANY(%s)", (drop,))
            dropped_terms = self.cur.fetchone()['t']
            if drop:
                self.delete_occurrences("occurrence_id = ANY(%s)", (drop,), label=f'unit {unit_id} off-list intros')
            have = {r['concept_id'] for r in current if r['concept_id'] in wanted}

            added = []
            for cid, entry in wanted.items():
                if cid in have:
                    self.q("""UPDATE occurrences SET vocab_source = %s, authored_term = %s
                              WHERE unit_id = %s AND concept_id = %s AND is_introduction = 1
                                AND vocab_source IS DISTINCT FROM 'booklet_gap_fill'""",
                           (source_file, entry, unit_id, cid))
                    continue
                # promote an existing recurrence in this unit, else insert a new introduction
                self.q("""UPDATE occurrences SET is_introduction = 1, vocab_source = %s, authored_term = %s
                          WHERE occurrence_id = (SELECT min(occurrence_id) FROM occurrences
                                                 WHERE unit_id = %s AND concept_id = %s)
                          RETURNING occurrence_id""", (source_file, entry, unit_id, cid))
                if self.cur.fetchone():
                    added.append(entry + ' (promoted recurrence)')
                    continue
                page, chapter, ctx = self.find_context(unit_id, entry)
                self.q("""INSERT INTO occurrences (concept_id, unit_id, subject, year, term, unit, chapter,
                              slide_number, is_introduction, term_in_context, vocab_source, authored_term)
                          SELECT %s, unit_id, subject, year, term, unit, %s, %s, 1, %s, %s, %s
                          FROM units WHERE unit_id = %s""",
                       (cid, chapter, page, ctx, source_file, entry, unit_id))
                added.append(entry)
            self.note(f'unit {unit_id}: {len(entries)} list entries; dropped {len(drop)} off-list intros '
                      f'({dropped_terms or "none"}); added {len(added)} ({", ".join(added) or "none"})')

    def dedupe(self):
        """After merges a concept can have several rows in one unit. Keep one intro
        (lowest id) if any, else the lowest-id recurrence; repoint edges to the survivor."""
        self.q("""
            WITH ranked AS (
                SELECT occurrence_id, concept_id, unit_id,
                       first_value(occurrence_id) OVER w AS keep_id,
                       row_number() OVER w AS rn
                FROM occurrences
                WINDOW w AS (PARTITION BY concept_id, unit_id
                             ORDER BY (is_introduction = 1 AND vocab_source IS DISTINCT FROM 'booklet_gap_fill') DESC,
                                      occurrence_id)
            )
            SELECT occurrence_id, keep_id FROM ranked WHERE rn > 1""")
        dupes = self.cur.fetchall()
        for d in dupes:
            self.q("UPDATE edges SET from_occurrence = %s WHERE from_occurrence = %s", (d['keep_id'], d['occurrence_id']))
            self.q("UPDATE edges SET to_occurrence = %s WHERE to_occurrence = %s", (d['keep_id'], d['occurrence_id']))
        if dupes:
            self.q("DELETE FROM occurrences WHERE occurrence_id = ANY(%s)", ([d['occurrence_id'] for d in dupes],))
        self.note(f'removed {len(dupes)} duplicate rows created by merges')

    def summary(self):
        self.q("""SELECT (SELECT count(*) FROM concepts WHERE merged_into IS NULL) live_concepts,
                         (SELECT count(*) FROM concepts WHERE merged_into IS NOT NULL) merged_concepts,
                         (SELECT count(*) FROM occurrences) occurrences,
                         (SELECT count(*) FROM v_occurrences) v_occurrences,
                         (SELECT count(*) FROM v_occurrences WHERE is_introduction) intros,
                         (SELECT count(*) FROM concept_forms) forms,
                         (SELECT count(*) FROM edges) edges,
                         (SELECT count(*) FROM (SELECT 1 FROM occurrences GROUP BY concept_id, unit_id HAVING count(*) > 1) d) dup_pairs,
                         (SELECT count(*) FROM v_occurrences WHERE intro_source IN ('bold_only','unsourced') AND is_introduction) nonlist_intros""")
        return dict(self.cur.fetchone())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='commit the changes (default: dry run, rolled back)')
    args = ap.parse_args()

    conn = get_connection()
    h = Hygiene(conn)
    try:
        # Apply migration 008 in the same transaction if absent, so a dry run tests it too.
        h.q("SELECT to_regclass('public.concept_forms') IS NOT NULL AS present")
        if not h.cur.fetchone()['present']:
            h.q(Path('migrations/008_concept_forms_and_merges.sql').read_text())
            print('applied migration 008 (inside this transaction)')
        print('before:', h.summary())
        h.seed_forms()
        h.remove_bold_only()
        h.repair_truncations()
        h.merge_base_forms()
        h.align_units()
        h.dedupe()
        after = h.summary()
        print('after: ', after)
        if after['dup_pairs']:
            raise RuntimeError('duplicate (concept, unit) pairs remain')
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
