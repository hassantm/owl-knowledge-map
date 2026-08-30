"""
Unit tests for prompts.py — prompt construction.
No database required.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'enrichment'))

from prompts import build_enrichment_prompt


class TestBuildEnrichmentPrompt:

    def test_concept_term_in_prompt(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4, 5])
        assert 'empire' in prompt

    def test_subjects_in_prompt(self):
        prompt = build_enrichment_prompt('trade route', ['History', 'Geography'], [5])
        assert 'History' in prompt
        assert 'Geography' in prompt

    def test_years_in_prompt(self):
        prompt = build_enrichment_prompt('irrigation', ['Geography'], [3, 4, 5])
        assert '3' in prompt
        assert '4' in prompt
        assert '5' in prompt

    def test_years_sorted_in_prompt(self):
        # Years should appear in ascending order regardless of input order
        prompt = build_enrichment_prompt('dynasty', ['History'], [6, 3, 5])
        idx_3 = prompt.index('3')
        idx_6 = prompt.index('6')
        assert idx_3 < idx_6

    def test_prompt_requests_json_output(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'json' in prompt.lower() or 'JSON' in prompt

    def test_prompt_requires_definition_field(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'definition' in prompt

    def test_prompt_requires_etymology_field(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'etymology' in prompt

    def test_prompt_requires_word_family_field(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'word_family' in prompt

    def test_prompt_requires_register_field(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'register' in prompt

    def test_prompt_requires_tier_field(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'tier' in prompt

    def test_prompt_names_all_four_valid_registers(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        for register in ('subject-specific', 'formal academic', 'technical', 'general formal'):
            assert register in prompt, f"Expected register '{register}' listed in prompt"

    def test_prompt_mentions_tier_guidance(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        # Tier 1/2/3 should be explained
        assert '1' in prompt and '2' in prompt and '3' in prompt

    def test_prompt_mentions_ks2(self):
        prompt = build_enrichment_prompt('empire', ['History'], [4])
        assert 'KS2' in prompt or 'Key Stage 2' in prompt

    def test_prompt_returns_string(self):
        result = build_enrichment_prompt('trade', ['History'], [3])
        assert isinstance(result, str)
        assert len(result) > 100

    def test_single_subject_works(self):
        prompt = build_enrichment_prompt('monsoon', ['Geography'], [5])
        assert 'Geography' in prompt

    def test_multiple_subjects_comma_separated(self):
        prompt = build_enrichment_prompt('evidence', ['History', 'Geography', 'Religion'], [3, 4, 5, 6])
        # All three subjects should appear
        assert 'History' in prompt
        assert 'Geography' in prompt
        assert 'Religion' in prompt
