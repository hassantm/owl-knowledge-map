#!/usr/bin/env python3
"""
Vocabulary List Validator

Parses authoritative vocab list .docx files and validates extracted terms
against them. Assigns confidence scores and validation status to each term.

Created: 2026-02-24
"""

import re
from difflib import SequenceMatcher
from pathlib import Path

from docx import Document


# =============================================================================
# VOCAB LIST DISCOVERY
# =============================================================================

def find_vocab_list(pptx_path: str) -> str | None:
    """
    Find the authoritative vocab list .docx for a booklet file.

    Search strategy:
    1. Get unit folder (parent.parent of pptx)
    2. Find sibling folders containing 'vocab' in the name
    3. Recurse into them for .docx files
    4. Exclude A-Z alphabetical variants (chapter-ordered only)
    5. Return the most recently modified file

    Created: 2026-02-24

    Args:
        pptx_path: Full path to PPTX booklet file

    Returns:
        Absolute path to best vocab .docx, or None if not found
    """
    unit_folder = Path(pptx_path).parent.parent

    # 2026-02-24: Two passes — prefer chapter-ordered, fall back to A-Z
    az_files = []
    chapter_files = []

    for child in unit_folder.iterdir():
        if not child.is_dir():
            continue
        if 'vocab' not in child.name.lower():
            continue
        for docx_file in child.rglob('*.docx'):
            if docx_file.name.startswith('.') or docx_file.name.startswith('~$'):
                continue
            name_lower = docx_file.name.lower()
            # 2026-02-24: Only accept files with 'vocab' in the filename
            # (filters out stray commercial/admin docs in vocab folders)
            if 'vocab' not in name_lower:
                continue
            if name_lower.startswith('a-z') or ' a-z' in name_lower or '_a-z' in name_lower:
                az_files.append(docx_file)
            else:
                chapter_files.append(docx_file)

    candidates = chapter_files if chapter_files else az_files
    if not candidates:
        return None

    return str(max(candidates, key=lambda f: f.stat().st_mtime))


# =============================================================================
# VOCAB LIST PARSING
# =============================================================================

def parse_vocab_docx(docx_path: str) -> dict:
    """
    Parse a vocabulary list .docx into structured data.

    Chapter headings are detected by text pattern (^Chapter N), regardless
    of paragraph style, since style names differ across documents.

    Created: 2026-02-24

    Args:
        docx_path: Path to vocab list .docx file

    Returns:
        {
            'chapters': {'1': ['term1', 'term2'], '2': ['term3', ...]},
            'all_terms': ['term1', 'term2', ...],
            'metadata': {
                'source_path': str,
                'total_terms': int,
                'chapter_count': int
            }
        }
    """
    doc = Document(docx_path)

    chapters = {}
    current_chapter = '0'  # Terms before first heading go into chapter '0'
    chapter_pattern = re.compile(r'^Chapter\s+(\d+)', re.IGNORECASE)

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Check for chapter heading
        chapter_match = chapter_pattern.match(text)
        if chapter_match:
            current_chapter = chapter_match.group(1)
            if current_chapter not in chapters:
                chapters[current_chapter] = []
            continue

        # Skip the document title (first non-empty paragraph if chapter '0' still empty)
        if current_chapter == '0' and not chapters.get('0'):
            # Heuristic: if text is long and looks like a title, skip it
            if len(text) > 40 or para.style.name in ('Title', 'Heading 1', 'Heading 2'):
                continue

        # Everything else is a vocabulary term
        if current_chapter not in chapters:
            chapters[current_chapter] = []
        chapters[current_chapter].append(text)

    # Remove chapter '0' if empty
    if '0' in chapters and not chapters['0']:
        del chapters['0']

    all_terms = [term for terms in chapters.values() for term in terms]

    return {
        'chapters': chapters,
        'all_terms': all_terms,
        'metadata': {
            'source_path': str(docx_path),
            'total_terms': len(all_terms),
            'chapter_count': len(chapters)
        }
    }


# =============================================================================
# TERM MATCHING
# =============================================================================

def _normalise(text: str) -> str:
    """Strip punctuation and collapse whitespace for normalised matching."""
    text = re.sub(r'[.,;:!?\'"()\[\]{}]', '', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


def match_term(extracted: str, vocab_terms: list) -> dict:
    """
    Match an extracted term against a list of vocab terms.

    Three-tier matching:
    1. Exact (case-insensitive)
    2. Normalised (punctuation stripped, whitespace collapsed)
    3. Fuzzy (difflib SequenceMatcher, threshold 0.9)

    Created: 2026-02-24

    Args:
        extracted: Extracted term from booklet
        vocab_terms: List of authoritative vocab terms

    Returns:
        {
            'matched': bool,
            'match_type': 'exact' | 'normalised' | 'fuzzy' | 'none',
            'confidence': float (0.0–1.0),
            'vocab_term': str | None
        }
    """
    extracted_lower = extracted.lower()
    extracted_norm = _normalise(extracted)

    for vocab_term in vocab_terms:
        # Tier 1: Exact (case-insensitive)
        if extracted_lower == vocab_term.lower():
            return {
                'matched': True,
                'match_type': 'exact',
                'confidence': 1.0,
                'vocab_term': vocab_term
            }

    for vocab_term in vocab_terms:
        # Tier 2: Normalised
        if extracted_norm == _normalise(vocab_term):
            return {
                'matched': True,
                'match_type': 'normalised',
                'confidence': 0.95,
                'vocab_term': vocab_term
            }

    for vocab_term in vocab_terms:
        # Tier 3: Fuzzy
        ratio = SequenceMatcher(None, extracted_lower, vocab_term.lower()).ratio()
        if ratio >= 0.9:
            return {
                'matched': True,
                'match_type': 'fuzzy',
                'confidence': round(ratio * 0.85, 3),  # Scale to max ~0.85
                'vocab_term': vocab_term
            }

    return {
        'matched': False,
        'match_type': 'none',
        'confidence': 0.0,
        'vocab_term': None
    }


# =============================================================================
# VALIDATION
# =============================================================================

def validate_extraction(extraction_results: dict, vocab_path: str) -> dict:
    """
    Enrich extraction results with validation metadata from vocab list.

    Validation categories:
    - 'confirmed'            : In vocab, not flagged by Stage 1
    - 'confirmed_with_flag'  : In vocab, but flagged by Stage 1
    - 'potential_noise'      : Not in vocab, not flagged by Stage 1
    - 'high_priority_review' : Not in vocab AND flagged by Stage 1

    Modifies extraction_results['terms'] in-place, adding to each term:
    - validation_status, vocab_confidence, vocab_match_type, vocab_source

    Also adds extraction_results['validation_stats'].

    Created: 2026-02-24

    Args:
        extraction_results: Output from extract_stage1.extract_bold_runs()
        vocab_path: Path to vocab .docx

    Returns:
        Enriched extraction_results dict
    """
    vocab_data = parse_vocab_docx(vocab_path)
    vocab_terms = vocab_data['all_terms']
    vocab_source = str(Path(vocab_path).name)

    confirmed = 0
    potential_noise = 0
    missed_terms = []

    for term_data in extraction_results['terms']:
        result = match_term(term_data['term'], vocab_terms)

        if result['matched']:
            status = 'confirmed_with_flag' if term_data['flagged'] else 'confirmed'
            confirmed += 1
        else:
            status = 'high_priority_review' if term_data['flagged'] else 'potential_noise'
            potential_noise += 1

        term_data['validation_status'] = status
        term_data['vocab_confidence'] = result['confidence']
        term_data['vocab_match_type'] = result['match_type']
        term_data['vocab_source'] = vocab_source

    # Find terms in vocab that weren't extracted
    extracted_lower = {t['term'].lower() for t in extraction_results['terms']}
    extracted_norm = {_normalise(t['term']) for t in extraction_results['terms']}

    for vocab_term in vocab_terms:
        if vocab_term.lower() not in extracted_lower and _normalise(vocab_term) not in extracted_norm:
            missed_terms.append(vocab_term)

    extraction_results['validation_stats'] = {
        'vocab_list': vocab_source,
        'vocab_terms_total': vocab_data['metadata']['total_terms'],
        'extracted_confirmed': confirmed,
        'extracted_noise': potential_noise,
        'missed_terms': missed_terms
    }

    return extraction_results
