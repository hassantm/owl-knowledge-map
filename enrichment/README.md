● All 2,928 approved. Here's a spot-check query you can run any time to sample across subjects, years and tiers — good for a quick
  sanity pass:

  ```sql
  SELECT c.term, c.definition, c.tier, c.register, c.word_family,
        c.etymology, u.subject, u.year
 FROM concepts c
  JOIN occurrences o ON o.concept_id = c.concept_id
 JOIN units u ON o.unit_id = u.unit_id
  WHERE o.is_introduction = 1
  ORDER BY random()
  LIMIT 20;                                                                       ```

  Run it a few times to get a spread. If you spot a pattern that's consistently off (e.g. tier assignments for a particular
  register), let me know and we can fix it in bulk. What's next — shall I update the todos and then look at the Anvil integration?

● From the enrichment prompt/spec, tiers follow Beck's vocabulary framework adapted for KS2:

  - Tier 1 — Common everyday words that most children already know (hill, town, cattle)
  - Tier 2 — High-frequency academic words that appear across subjects and are central to educated discourse (significant, evidence,
  settlement, adapted, diverse) — the most pedagogically valuable tier for the curriculum
  - Tier 3 — Subject-specific technical terms used within a particular discipline (favelado, conurbation, monotheism, Eisteddfod)

  The key judgement call is Tier 2 vs Tier 3 — some terms feel domain-specific but are actually doing broader academic work (e.g.
  empire is History-specific on the surface but Counsell uses it as a cross-subject schema). Those are the ones most worth
  spot-checking.