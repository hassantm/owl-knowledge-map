"""
Shared helpers for authored vocab lists (Phase 2, 2026-10-03).

List files live in data/phase2/lists/<unit_id>_<slug>.txt (gitignored: they
are OWL curriculum content). Format:
    #! source / date / file metadata
    # Chapter N[: title]
    entry
    entry
Entries are kept exactly as authored.
"""

import re
from pathlib import Path

from lemminflect import getAllLemmas, getAllLemmasOOV

LISTS_DIR = Path('data/phase2/lists')


def norm(term: str) -> str:
    """Lower-case, straight apostrophes, single spaces."""
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


def parse_list_file(path: Path) -> dict:
    """Return {'meta': [...], 'entries': [(chapter or None, entry), ...]}."""
    meta, entries, chapter = [], [], None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#!'):
            meta.append(line[2:].strip())
        elif line.startswith('#'):
            chapter = line.lstrip('#').strip()
        else:
            entries.append((chapter, line))
    return {'meta': meta, 'entries': entries}


def list_files() -> dict[int, Path]:
    """unit_id -> list file."""
    out = {}
    for p in sorted(LISTS_DIR.glob('*.txt')):
        m = re.match(r'(\d+)_', p.name)
        if m:
            out[int(m.group(1))] = p
    return out


class ConceptIndex:
    """Resolve a list entry to a live concept: exact term, then authored form, then base form."""

    def __init__(self, cur):
        cur.execute("SELECT concept_id, term FROM concepts WHERE merged_into IS NULL")
        rows = cur.fetchall()
        get = (lambda r, k, i: r[k]) if rows and isinstance(rows[0], dict) else (lambda r, k, i: r[i])
        self.terms = {cid: t for cid, t in ((get(r, 'concept_id', 0), get(r, 'term', 1)) for r in rows)}
        self.by_norm, self.by_key = {}, {}
        for cid, t in sorted(self.terms.items()):
            self.by_norm.setdefault(norm(t), cid)
            self.by_key.setdefault(base_key(t), cid)
        cur.execute("""SELECT f.concept_id, f.form FROM concept_forms f JOIN concepts c USING (concept_id)
                       WHERE c.merged_into IS NULL AND f.kind = 'authored'""")
        for r in cur.fetchall():
            cid, form = get(r, 'concept_id', 0), get(r, 'form', 1)
            self.by_norm.setdefault(norm(form), cid)
            self.by_key.setdefault(base_key(form), cid)

    def resolve(self, entry: str):
        """(concept_id or None, how) where how is 'exact', 'base form' or 'none'."""
        cid = self.by_norm.get(norm(entry))
        if cid:
            return cid, 'exact'
        cid = self.by_key.get(base_key(entry))
        if cid:
            return cid, 'base form'
        return None, 'none'
