"""
Unit tests for enrich.py validation logic.
No database required — pure function tests.
"""

import pytest

# validate_enrichment is a pure function; import it directly once the file exists.
# Until enrichment/enrich.py is created, these tests will fail with ImportError,
# which is the correct signal that the module hasn't been built yet.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'enrichment'))

from enrich import validate_enrichment


VALID = {
    'definition':  'A territory controlled by a single ruler or state.',
    'etymology':   'From Latin imperium, meaning power or command.',
    'word_family': ['empire', 'imperial', 'imperialism', 'emperor'],
    'register':    'subject-specific',
    'tier':        3,
}


class TestValidateEnrichment:

    def test_valid_data_passes(self):
        ok, reason = validate_enrichment(VALID)
        assert ok is True
        assert reason == ''

    def test_all_four_registers_accepted(self):
        for register in ('subject-specific', 'formal academic', 'technical', 'general formal'):
            data = {**VALID, 'register': register}
            ok, _ = validate_enrichment(data)
            assert ok, f"register '{register}' should be valid"

    def test_all_three_tiers_accepted(self):
        for tier in (1, 2, 3):
            data = {**VALID, 'tier': tier}
            ok, _ = validate_enrichment(data)
            assert ok, f"tier {tier} should be valid"

    def test_missing_definition_fails(self):
        data = {k: v for k, v in VALID.items() if k != 'definition'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'definition' in reason

    def test_missing_etymology_fails(self):
        data = {k: v for k, v in VALID.items() if k != 'etymology'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'etymology' in reason

    def test_missing_word_family_fails(self):
        data = {k: v for k, v in VALID.items() if k != 'word_family'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'word_family' in reason

    def test_missing_register_fails(self):
        data = {k: v for k, v in VALID.items() if k != 'register'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'register' in reason

    def test_missing_tier_fails(self):
        data = {k: v for k, v in VALID.items() if k != 'tier'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'tier' in reason

    def test_invalid_register_fails(self):
        data = {**VALID, 'register': 'conversational'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'register' in reason.lower()

    def test_invalid_tier_zero_fails(self):
        data = {**VALID, 'tier': 0}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'tier' in reason.lower()

    def test_invalid_tier_four_fails(self):
        data = {**VALID, 'tier': 4}
        ok, reason = validate_enrichment(data)
        assert ok is False

    def test_tier_as_string_fails(self):
        data = {**VALID, 'tier': '2'}
        ok, reason = validate_enrichment(data)
        assert ok is False

    def test_word_family_as_string_fails(self):
        data = {**VALID, 'word_family': 'empire, imperial'}
        ok, reason = validate_enrichment(data)
        assert ok is False
        assert 'word_family' in reason

    def test_word_family_empty_list_passes(self):
        # An empty word family is valid — some terms have no related forms
        data = {**VALID, 'word_family': []}
        ok, _ = validate_enrichment(data)
        assert ok is True

    def test_empty_dict_fails(self):
        ok, reason = validate_enrichment({})
        assert ok is False
        assert 'Missing fields' in reason
