#!/usr/bin/env python3
"""
Batch Content Ingestion

Walks the Dropbox folder structure and ingests lesson and booklet content
for every unit found, matching each folder to its unit_id in the database.

Expected folder structure:
  <dropbox-root>/
    HEP History/
      Year 5 Hist/
        Y5 Hist Autumn 1 Baghdad/
          Y5 Hist Autumn 1 Booklet.pptx      ← glob *Booklet*.pptx
          Y5 Autumn 1 Baghdad Powerpoints/   ← glob *Powerpoints*/
            Lesson 1.pptx
            ...

Usage:
    python batch_ingest.py --dropbox-root "/path/to/Haringey Counsell Shared Items"
    python batch_ingest.py --dropbox-root "/path/to/..." --dry-run
    python batch_ingest.py --dropbox-root "/path/to/..." --force
    python batch_ingest.py --dropbox-root "/path/to/..." --unit "Baghdad"
"""

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from content_ingestion import ingest_booklet, ingest_lesson
from db import get_connection

load_dotenv()

SUBJECT_MAP = {
    "hist":     "History",
    "history":  "History",
    "geog":     "Geography",
    "geography":"Geography",
    "relig":    "Religion",
    "religion": "Religion",
    "re":       "Religion",
}

# Matches: Y5 Hist Autumn 1 Baghdad
#          Y3 Religion Autumn 1 Hindu Stories_I Rama and Sita
#          Y4 Geog Spring 2 Climate and Biomes
_UNIT_FOLDER_RE = re.compile(
    r"^Y(\d+)\s+(Hist(?:ory)?|Geog(?:raphy)?|Relig(?:ion)?|RE)\s+(Autumn|Spring|Summer)\s+(\d+)\s+(.+)$",
    re.IGNORECASE,
)

# Fallback for Religion folders with no subject word: "Y6 Autumn 1 Sikhism 1 The teaching of the gurus"
_UNIT_FOLDER_RE_NO_SUBJ = re.compile(
    r"^Y(\d+)\s+(Autumn|Spring|Summer)\s+(\d+)\s+(.+)$",
    re.IGNORECASE,
)


def parse_unit_folder(name: str, inferred_subject: str | None = None) -> dict | None:
    """Parse a unit folder name into metadata, or return None if it doesn't match."""
    m = _UNIT_FOLDER_RE.match(name.strip())
    if m:
        year, subj_abbr, term_word, term_num, unit_name = m.groups()
        return {
            "year":    int(year),
            "subject": SUBJECT_MAP.get(subj_abbr.lower(), subj_abbr),
            "term":    f"{term_word.capitalize()}{term_num}",
            "unit":    unit_name.strip(),
        }
    # Fallback: no subject word in folder name — use inferred_subject if provided
    m2 = _UNIT_FOLDER_RE_NO_SUBJ.match(name.strip())
    if m2 and inferred_subject:
        year, term_word, term_num, unit_name = m2.groups()
        return {
            "year":    int(year),
            "subject": inferred_subject,
            "term":    f"{term_word.capitalize()}{term_num}",
            "unit":    unit_name.strip(),
        }
    return None


def lookup_unit_id(meta: dict) -> int | None:
    """Look up unit_id in the database for parsed folder metadata.

    Tries exact match first, then falls back to checking whether the DB unit name
    is contained within the folder-parsed unit name (handles cases like
    'Sikhism 1 The teaching of the gurus' matching DB entry 'The teaching of the gurus').
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Exact match
            cur.execute("""
                SELECT unit_id, unit FROM units
                WHERE year = %s AND subject = %s AND term = %s
                  AND unit ILIKE %s
            """, (meta["year"], meta["subject"], meta["term"], meta["unit"]))
            row = cur.fetchone()
            if row:
                return row["unit_id"]
            # Fallback: DB unit name is a substring of the parsed folder name
            cur.execute("""
                SELECT unit_id, unit FROM units
                WHERE year = %s AND subject = %s AND term = %s
            """, (meta["year"], meta["subject"], meta["term"]))
            candidates = cur.fetchall()
            for candidate in candidates:
                if candidate["unit"].lower() in meta["unit"].lower():
                    return candidate["unit_id"]
    finally:
        conn.close()
    return None


def is_already_ingested(unit_id: int) -> tuple[bool, bool]:
    """Return (has_lesson, has_booklet) for a unit."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    lesson_content IS NOT NULL  AS has_lesson,
                    booklet_content IS NOT NULL AS has_booklet
                FROM units WHERE unit_id = %s
            """, (unit_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return False, False
    return row["has_lesson"], row["has_booklet"]


def infer_subject_from_path(path: Path) -> str | None:
    """Infer subject from any part of the folder path (e.g. 'HEP Religion' → 'Religion')."""
    for part in path.parts:
        for key, subj in SUBJECT_MAP.items():
            if key in part.lower():
                return subj
    return None


def find_unit_folders(dropbox_root: Path) -> list[tuple[Path, str | None]]:
    """Walk the dropbox root and return (folder, inferred_subject) pairs matching the unit name pattern."""
    results = []
    for p in dropbox_root.rglob("*"):
        if not p.is_dir():
            continue
        inferred = infer_subject_from_path(p)
        if parse_unit_folder(p.name, inferred):
            results.append((p, inferred))
    return results


def find_booklet(unit_dir: Path) -> Path | None:
    """Find the booklet PPTX inside the *Booklet* subfolder."""
    booklet_dirs = [
        p for p in unit_dir.iterdir()
        if p.is_dir() and "booklet" in p.name.lower()
    ]
    if not booklet_dirs:
        return None
    matches = list(booklet_dirs[0].glob("*.pptx"))
    return matches[0] if len(matches) == 1 else None


def find_lesson_dir(unit_dir: Path) -> Path | None:
    """Find the Powerpoints or Lessons subfolder containing the lesson PPTXs."""
    matches = [
        p for p in unit_dir.iterdir()
        if p.is_dir() and ("powerpoint" in p.name.lower() or "lesson" in p.name.lower())
    ]
    return matches[0] if len(matches) >= 1 else None


def ingest_unit(unit_dir: Path, unit_id: int, meta: dict, model: str,
                force: bool, dry_run: bool,
                story_icon_hashes: set[str] | None = None) -> dict:
    """
    Ingest lesson and booklet for one unit. Returns a status dict.
    """
    has_lesson, has_booklet = is_already_ingested(unit_id)

    booklet_path = find_booklet(unit_dir)
    lesson_dir   = find_lesson_dir(unit_dir)

    status = {
        "unit_id":     unit_id,
        "unit":        meta["unit"],
        "lesson":      None,
        "booklet":     None,
        "skipped":     [],
        "errors":      [],
    }

    if lesson_dir:
        if has_lesson and not force:
            status["skipped"].append("lesson (already ingested, use --force to re-ingest)")
        else:
            try:
                ingest_lesson(str(lesson_dir), unit_id, model, dry_run=dry_run,
                              story_icon_hashes=story_icon_hashes)
                status["lesson"] = str(lesson_dir.name)
            except Exception as e:
                status["errors"].append(f"lesson: {e}")
    else:
        status["errors"].append("no *Powerpoints* subfolder found")

    if booklet_path:
        if has_booklet and not force:
            status["skipped"].append("booklet (already ingested, use --force to re-ingest)")
        else:
            try:
                ingest_booklet(str(booklet_path), unit_id, model, dry_run=dry_run)
                status["booklet"] = booklet_path.name
            except Exception as e:
                status["errors"].append(f"booklet: {e}")
    else:
        status["errors"].append("no *Booklet*.pptx found")

    return status


def main():
    parser = argparse.ArgumentParser(
        description="Batch-ingest lesson and booklet content for all curriculum units",
    )
    parser.add_argument("--dropbox-root", required=True, action="append", dest="dropbox_roots",
                        metavar="PATH",
                        help="Subject root folder (e.g. 'HEP History/'). Can be repeated.")
    parser.add_argument("--model",    default="claude-sonnet-4-6")
    parser.add_argument("--force",    action="store_true",
                        help="Re-ingest even if content is already present")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Parse and report without writing to the database")
    parser.add_argument("--unit",     help="Only process units whose name contains this string")
    parser.add_argument("--story-icon-hash", action="append", dest="story_icon_hashes",
                        metavar="MD5",
                        help="MD5 hash of the story icon (can repeat). "
                             "Use find_story_icon.py to extract from a known story slide.")
    args = parser.parse_args()

    unit_folders = []
    for root_str in args.dropbox_roots:
        root = Path(root_str)
        if not root.exists():
            print(f"ERROR: path not found: {root}")
            return 1
        unit_folders.extend(find_unit_folders(root))
    if not unit_folders:
        print("No unit folders found. Check the --dropbox-root path.")
        return 1

    if args.unit:
        unit_folders = [(f, s) for f, s in unit_folders if args.unit.lower() in f.name.lower()]

    unit_folders.sort(key=lambda t: t[0].name)
    print(f"Found {len(unit_folders)} unit folder(s)\n")

    icon_hashes = set(args.story_icon_hashes) if args.story_icon_hashes else None
    ok, skipped, failed, unmatched = [], [], [], []

    for unit_dir, inferred_subject in unit_folders:
        meta = parse_unit_folder(unit_dir.name, inferred_subject)
        unit_id = lookup_unit_id(meta)

        if unit_id is None:
            print(f"  [NO DB MATCH] {unit_dir.name}")
            unmatched.append(unit_dir.name)
            continue

        print(f"  [{meta['subject']} Y{meta['year']} {meta['term']}] {meta['unit']} "
              f"(unit_id={unit_id})")

        status = ingest_unit(unit_dir, unit_id, meta, args.model, args.force, args.dry_run,
                             icon_hashes)

        for s in status["skipped"]:
            print(f"    skip: {s}")
            skipped.append(unit_dir.name)

        for e in status["errors"]:
            print(f"    ERROR: {e}")
            failed.append(f"{unit_dir.name}: {e}")

        if status["lesson"]:
            print(f"    lesson:  {status['lesson']}")
        if status["booklet"]:
            print(f"    booklet: {status['booklet']}")

        if not status["errors"] and not status["skipped"]:
            ok.append(unit_dir.name)

    print(f"\n--- Summary ---")
    print(f"  Ingested:  {len(ok)}")
    print(f"  Skipped:   {len(skipped)}")
    print(f"  No DB match: {len(unmatched)}")
    print(f"  Errors:    {len(failed)}")

    if unmatched:
        print("\nUnmatched folders (not in DB):")
        for u in unmatched:
            print(f"  {u}")

    if failed:
        print("\nErrors:")
        for f in failed:
            print(f"  {f}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
