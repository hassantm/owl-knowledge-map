def build_enrichment_prompt(
    concept_term: str,
    subjects: list[str],
    years: list[int]
) -> str:
    subjects_str = ', '.join(subjects)
    years_str    = ', '.join(map(str, sorted(years)))

    return f"""You are enriching a vocabulary database for a KS2 humanities curriculum \
(ages 7–11) grounded in Core Knowledge principles (E.D. Hirsch). The curriculum \
covers history, geography and religion with a knowledge-rich, academically rigorous \
approach for primary school children in England.

CONCEPT: "{concept_term}"
SUBJECT CONTEXT: {subjects_str}
YEAR GROUPS WHERE IT APPEARS: {years_str}

Return ONLY a valid JSON object with exactly these fields. No preamble, no markdown \
fences, no trailing commas. The JSON must be parseable with json.loads():

{{
    "definition": "A clear, curriculum-appropriate definition written for a KS2 \
class teacher (not the pupil). 1–2 sentences. Should reflect the concept's meaning \
in the subject context given.",

    "etymology": "The word's origin — language it derives from, root meaning, and \
approximately when it entered English. 1–2 sentences. Accessible to a non-linguist.",

    "word_family": ["array", "of", "related", "word", "forms"],

    "register": "Exactly one of: subject-specific, formal academic, technical, \
general formal",

    "tier": 2
}}

Tier guidance:
- 1: Everyday conversational language (unlikely in this curriculum)
- 2: General academic vocabulary that appears across multiple subjects and \
disciplines (e.g. 'evidence', 'significant', 'process')
- 3: Subject-specific technical vocabulary tied to history, geography or religion \
(e.g. 'irrigation', 'dynasty', 'contour')
"""
