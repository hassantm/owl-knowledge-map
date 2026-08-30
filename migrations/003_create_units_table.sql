-- Migration 003: Create units table
--
-- Promotes the implicit unit dimension (previously only in occurrences rows)
-- into a first-class table. Gives us a canonical unit list, a place to store
-- vocab_list_path per unit, and a clean FK from occurrences.
--
-- subject/year/term/unit are intentionally kept on occurrences as denormalised
-- convenience columns — uplink.py filters heavily on them and a JOIN to units
-- on every query would add complexity with no real benefit.

CREATE TABLE IF NOT EXISTS units (
    unit_id         serial      PRIMARY KEY,
    subject         text        NOT NULL,
    year            integer     NOT NULL,
    term            text        NOT NULL,
    unit            text        NOT NULL,
    vocab_list_path text,
    CONSTRAINT units_unique UNIQUE (subject, year, term, unit)
);

-- Populate from existing occurrences data
INSERT INTO units (subject, year, term, unit)
SELECT DISTINCT subject, year, term, unit
FROM occurrences
ORDER BY subject, year, term, unit
ON CONFLICT DO NOTHING;

-- Add FK column to occurrences
ALTER TABLE occurrences
    ADD COLUMN IF NOT EXISTS unit_id integer REFERENCES units(unit_id);

-- Back-fill unit_id on all existing rows
UPDATE occurrences o
SET unit_id = u.unit_id
FROM units u
WHERE o.subject = u.subject
  AND o.year    = u.year
  AND o.term    = u.term
  AND o.unit    = u.unit;

-- Enforce NOT NULL now that all rows are filled
ALTER TABLE occurrences
    ALTER COLUMN unit_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_occurrences_unit_id ON occurrences(unit_id);
