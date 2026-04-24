-- Migration 004: Add content storage columns to units table
--
-- Adds lesson and booklet JSONB content columns to the units table.
-- Each unit has one lesson PPTX (teacher-facing, with story slides and speaker notes)
-- and one booklet PPTX (pupil-facing reading material, used as the factual source).
-- Both live on the same units row since they belong to the same curriculum unit.
--
-- Content is stored as JSONB at extraction time with per-chunk token counts
-- so context assembly can budget tokens without re-calling the API at generation time.

ALTER TABLE units
    ADD COLUMN IF NOT EXISTS lesson_content               jsonb,
    ADD COLUMN IF NOT EXISTS lesson_content_stale         boolean     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS lesson_content_extracted_at  timestamptz,
    ADD COLUMN IF NOT EXISTS lesson_content_model         varchar(64),

    ADD COLUMN IF NOT EXISTS booklet_content              jsonb,
    ADD COLUMN IF NOT EXISTS booklet_content_stale        boolean     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS booklet_content_extracted_at timestamptz,
    ADD COLUMN IF NOT EXISTS booklet_content_model        varchar(64);

-- Index for staleness sweeps (only rows that need re-extraction)
CREATE INDEX IF NOT EXISTS idx_units_lesson_stale
    ON units (lesson_content_stale)
    WHERE lesson_content_stale = true;

CREATE INDEX IF NOT EXISTS idx_units_booklet_stale
    ON units (booklet_content_stale)
    WHERE booklet_content_stale = true;
