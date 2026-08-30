-- Migration 001: Add vocabulary enrichment columns to concepts table
-- Safe to re-run: uses IF NOT EXISTS / IF NOT EXISTS patterns

ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS definition         text,
    ADD COLUMN IF NOT EXISTS etymology          text,
    ADD COLUMN IF NOT EXISTS word_family        text[],
    ADD COLUMN IF NOT EXISTS register           text
        CHECK (register IN (
            'subject-specific',
            'formal academic',
            'technical',
            'general formal'
        )),
    ADD COLUMN IF NOT EXISTS tier               integer
        CHECK (tier IN (1, 2, 3)),
    ADD COLUMN IF NOT EXISTS enrichment_status  text
        NOT NULL DEFAULT 'pending'
        CHECK (enrichment_status IN (
            'pending',
            'generated',
            'approved',
            'rejected'
        )),
    ADD COLUMN IF NOT EXISTS enrichment_notes   text,
    ADD COLUMN IF NOT EXISTS enriched_at        timestamptz,
    ADD COLUMN IF NOT EXISTS enriched_by        text DEFAULT 'claude-batch';
