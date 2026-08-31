#!/usr/bin/env python3
"""
OWL Style Corpus Statistics
===========================
Derives the quantitative evidence base for the Opening Worlds house style
guide from units.booklet_content.

Booklet text is extracted from PPTX and carries a lot of non-prose furniture:
margin line numbers used for shared reading, page numbers, image credits and
Wikimedia URLs. Roughly three quarters of non-empty lines are furniture rather
than prose, so every metric here runs over cleaned text (see clean_page).

Analyses:
  size          corpus size by subject; pages, tokens, words, sentences
  sentences     mean/median sentence length by year and by subject
  tone          direct address, question and exclamation rates, connectives
  orthography   British spelling, quote style, dashes, spacing
  structure     contents pages, chapter headings, recurring furniture

Run:
  python src/style_corpus_stats.py                      # run all
  python src/style_corpus_stats.py --analysis sentences
  python src/style_corpus_stats.py --subject Religion
  python src/style_corpus_stats.py --json /tmp/stats.json

Findings from the first run are written up in
docs/20260830_house_style_guide_feasibility.md.

Created: 2026-08-30
"""

import argparse
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_connection  # noqa: E402

# Lines that are extraction furniture rather than booklet prose.
_FURNITURE_MARKERS = (
    "wikimedia", "http", "File:", "Image by", "Photo by",
    "creativecommons", "Opening Worlds Ltd", "Pixabay",
)
# A line that is only digits, whitespace and punctuation: margin line numbers
# and page numbers.
_NUMERIC_ONLY_RE = re.compile(r"^[\d\s.,]+$")

# "1. The mighty River Indus" — the numbered chapter heading pattern.
_CHAPTER_HEADING_RE = re.compile(r"^\s*(\d{1,2})\.\s+([A-Z][^\n]{3,70})$", re.M)

# "murti (mer-tee)" — the house pronunciation gloss.
_PRONUNCIATION_RE = re.compile(r"\([a-z]+[-–][a-z]+")


def fetch_booklets(subject=None, year=None):
    """Return booklet rows, optionally filtered by subject and/or year."""
    sql = """
        SELECT subject, year, term, unit, booklet_content
        FROM units
        WHERE booklet_content IS NOT NULL
    """
    params = []
    if subject:
        sql += " AND subject = %s"
        params.append(subject)
    if year:
        sql += " AND year = %s"
        params.append(year)
    sql += " ORDER BY subject, year, term"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def clean_page(text):
    """Strip extraction furniture from one page, returning prose only."""
    kept = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or _NUMERIC_ONLY_RE.match(s):
            continue
        if any(marker in s for marker in _FURNITURE_MARKERS):
            continue
        kept.append(s)
    return " ".join(kept)


def unit_prose(row):
    """Cleaned prose for a whole unit."""
    pages = row["booklet_content"]["pages"]
    return " ".join(clean_page(p["text"]) for p in pages.values())


def sentences(text):
    """Split into sentences, discarding single-word fragments."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in parts if len(s.strip().split()) > 1]


def analyse_size(rows):
    by_subject = defaultdict(lambda: {"units": 0, "pages": 0, "tokens": 0,
                                      "words": 0, "sentences": 0})
    for row in rows:
        bc = row["booklet_content"]
        prose = unit_prose(row)
        agg = by_subject[row["subject"]]
        agg["units"] += 1
        agg["pages"] += bc["page_count"]
        agg["tokens"] += bc["total_token_count"]
        agg["words"] += len(prose.split())
        agg["sentences"] += len(sentences(prose))

    print("\n=== Corpus size (cleaned prose) ===\n")
    print(f"{'Subject':<12}{'Units':>7}{'Pages':>8}{'Tokens':>10}"
          f"{'Words':>10}{'Sentences':>11}")
    totals = Counter()
    for subject, agg in sorted(by_subject.items()):
        print(f"{subject:<12}{agg['units']:>7}{agg['pages']:>8}"
              f"{agg['tokens']:>10}{agg['words']:>10}{agg['sentences']:>11}")
        totals.update(agg)
    print(f"{'TOTAL':<12}{totals['units']:>7}{totals['pages']:>8}"
          f"{totals['tokens']:>10}{totals['words']:>10}{totals['sentences']:>11}")
    return {"by_subject": dict(by_subject), "totals": dict(totals)}


def analyse_sentences(rows):
    by_year, by_subject, per_unit = defaultdict(list), defaultdict(list), []
    for row in rows:
        prose = unit_prose(row)
        lengths = [len(s.split()) for s in sentences(prose)]
        if not lengths:
            continue
        by_year[row["year"]] += lengths
        by_subject[row["subject"]] += lengths
        words = prose.split()
        long_words = sum(1 for w in words if len(w) >= 9)
        per_unit.append({
            "year": row["year"], "subject": row["subject"], "unit": row["unit"],
            "sentences": len(lengths), "mean": round(st.mean(lengths), 1),
            "long_word_pct": round(100 * long_words / max(1, len(words)), 1),
        })

    print("\n=== Sentence length by unit ===\n")
    for u in sorted(per_unit, key=lambda x: (x["year"], x["subject"])):
        print(f"  Y{u['year']} {u['subject'][:4]:<5}{u['unit'][:30]:<32}"
              f"n={u['sentences']:>5}  mean={u['mean']:>5}  "
              f"9+ chars={u['long_word_pct']:>5}%")

    print("\n=== Sentence length by year ===\n")
    print("  The Y3->Y6 gradient is the basis for the per-year pitch bands.")
    for year in sorted(by_year):
        lengths = by_year[year]
        print(f"  Year {year}: mean {st.mean(lengths):>5.1f} words, "
              f"median {st.median(lengths):>4}, n={len(lengths)}")

    print("\n=== Sentence length by subject ===\n")
    for subject in sorted(by_subject):
        lengths = by_subject[subject]
        print(f"  {subject:<12} mean {st.mean(lengths):>5.1f} words, "
              f"n={len(lengths)}")

    return {
        "per_unit": per_unit,
        "by_year": {y: round(st.mean(v), 1) for y, v in by_year.items()},
        "by_subject": {s: round(st.mean(v), 1) for s, v in by_subject.items()},
    }


def analyse_tone(rows):
    prose = " ".join(unit_prose(r) for r in rows)
    sents = sentences(prose)

    questions = sum(1 for s in sents if s.rstrip().endswith("?"))
    exclamations = sum(1 for s in sents if s.rstrip().endswith("!"))

    def count_word(word):
        return len(re.findall(r"\b" + re.escape(word) + r"\b", prose))

    address = {w: count_word(w) for w in
               ("you", "You", "we", "We", "children", "pupils")}
    # Sentence-initial connectives the house voice sanctions, against the
    # formal ones it avoids.
    connectives = {p: len(re.findall(re.escape(p), prose)) for p in
                   ("But ", "So ", "Now ", "However", "Moreover", "Indeed",
                    "Of course", "Perhaps", "Let’s", "Let us",
                    "Do you remember", "Can you see", "Look at", "Imagine")}

    print("\n=== Tone and voice ===\n")
    print(f"  Sentences: {len(sents)}")
    print(f"  Questions:    {questions:>6}  ({100*questions/len(sents):.1f}%)")
    print(f"  Exclamations: {exclamations:>6}  "
          f"({100*exclamations/len(sents):.1f}%)")
    print("\n  Direct address (the reader is addressed, not described):")
    for word, n in address.items():
        print(f"    {word:<12}{n:>6}")
    print("\n  Connectives and prompts:")
    for phrase, n in sorted(connectives.items(), key=lambda x: -x[1]):
        print(f"    {phrase.strip():<18}{n:>6}")
    print(f"\n  Pronunciation glosses e.g. 'murti (mer-tee)': "
          f"{len(_PRONUNCIATION_RE.findall(prose))}")

    return {"sentences": len(sents), "questions": questions,
            "exclamations": exclamations, "address": address,
            "connectives": connectives}


def analyse_orthography(rows):
    prose = " ".join(unit_prose(r) for r in rows)

    # Stems, counted with inflections: 'colourful' and 'civilisations' are
    # as much evidence of British spelling as the bare lemma. Pairs are
    # ordered (house preference, variant to avoid).
    stem_pairs = [("colour", "color"), ("realis", "realiz"),
                  ("organis", "organiz"), ("centre", "center"),
                  ("civilis", "civiliz")]
    # Pairs where inflection would cross-match, so whole words only:
    # 'toward' is a prefix of 'towards', 'practice' of 'practices'.
    word_pairs = [("towards", "toward"), ("while", "whilst"),
                  ("practise", "practice")]

    print("\n=== Orthography ===\n")
    print("  British/American and house preferences.")
    print("  Stems count inflected forms (colour -> colours, colourful);")
    print("  the last three are whole-word to avoid cross-matching.\n")
    spelling = {}
    for a, b in stem_pairs + word_pairs:
        bound = r"\w*" if (a, b) in stem_pairs else r"\b"
        na = len(re.findall(r"\b" + a + bound, prose, re.I))
        nb = len(re.findall(r"\b" + b + bound, prose, re.I))
        spelling[f"{a}/{b}"] = [na, nb]
        print(f"    {a:<14}{na:>5}   vs   {b:<14}{nb:>5}")

    punctuation = {
        "curly apostrophe": prose.count("’"),
        "straight apostrophe": prose.count("'"),
        "em dash": prose.count("—"),
        "en dash": prose.count("–"),
        "double space after full stop": len(re.findall(r"\.  ", prose)),
        "curly double quotes": len(re.findall(r"[“”]", prose)),
        "comma before 'and'": len(re.findall(r",\s+and\b", prose)),
    }
    print("\n  Punctuation:\n")
    for label, n in punctuation.items():
        print(f"    {label:<32}{n:>6}")
    print("\n  Note: 'comma before and' mixes true serial commas with clause")
    print("  joins. Needs manual review before becoming a rule.")

    return {"spelling": spelling, "punctuation": punctuation}


def analyse_structure(rows):
    all_text = "\n".join(p["text"] for r in rows
                         for p in r["booklet_content"]["pages"].values())

    total_lines = furniture_lines = 0
    pages = pages_with_page_number = 0
    headings = Counter()
    for row in rows:
        for _, page in sorted(row["booklet_content"]["pages"].items(),
                              key=lambda x: int(x[0])):
            pages += 1
            text = page["text"]
            for m in _CHAPTER_HEADING_RE.finditer(text):
                headings[m.group(2).strip()] += 1
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for s in lines:
                total_lines += 1
                if _NUMERIC_ONLY_RE.match(s) or any(
                        m in s for m in _FURNITURE_MARKERS):
                    furniture_lines += 1
            if lines and lines[-1].isdigit():
                pages_with_page_number += 1

    print("\n=== Structure ===\n")
    print(f"  Pages: {pages}")
    print(f"  Non-empty lines: {total_lines}, of which furniture: "
          f"{furniture_lines} ({100*furniture_lines/total_lines:.1f}%)")
    print(f"  Pages ending in a bare page number: {pages_with_page_number}")
    print(f"  Numbered chapter headings detected: {sum(headings.values())}")

    print("\n  Recurring furniture:\n")
    patterns = {
        "copyright line": r"©\d{4} Opening Worlds",
        "Glossary": r"\bGlossary\b",
        "Key words / word bank": r"\b(Key words|Word bank|New words)\b",
        "Did you know": r"Did you know",
        "Remember": r"\bRemember\b",
    }
    furniture = {}
    for label, pattern in patterns.items():
        n = len(re.findall(pattern, all_text))
        furniture[label] = n
        print(f"    {label:<26}{n:>6}")
    print("\n  Zero glossary/word-bank hits: vocabulary lives outside the")
    print("  booklet, in the Core vocab documents and the concepts table.")

    return {"pages": pages, "total_lines": total_lines,
            "furniture_lines": furniture_lines,
            "chapter_headings": sum(headings.values()),
            "furniture": furniture}


ANALYSES = {
    "size": analyse_size,
    "sentences": analyse_sentences,
    "tone": analyse_tone,
    "orthography": analyse_orthography,
    "structure": analyse_structure,
}


def main():
    parser = argparse.ArgumentParser(
        description="Quantify Opening Worlds house style from booklet text",
    )
    parser.add_argument("--analysis", choices=sorted(ANALYSES),
                        help="Run one analysis (default: all)")
    parser.add_argument("--subject", help="Limit to one subject")
    parser.add_argument("--year", type=int, help="Limit to one year group")
    parser.add_argument("--json", metavar="PATH",
                        help="Also write results as JSON")
    args = parser.parse_args()

    rows = fetch_booklets(args.subject, args.year)
    if not rows:
        print("No units with booklet_content matched.", file=sys.stderr)
        return 1
    print(f"Loaded {len(rows)} units with booklet content.")

    chosen = [args.analysis] if args.analysis else list(ANALYSES)
    results = {name: ANALYSES[name](rows) for name in chosen}

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, default=str))
        print(f"\nJSON written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
