# SRS analytics

The active service is app/srs_grading.py. Admin views cover program/year/subject enrollment, sex distribution, regular/irregular counts, and published class averages. Faculty views cover recorded component averages, weighted grade distribution, entry completion, and class Top Performers. Student views expose only their own published subject/type results, unit-weighted average, and own cohort rank.

Missing scores contribute zero to weighted grades under SRS business rule 7, while the underlying record stays missing. Component averages are explicitly labeled as recorded-score means. Two-tier weights, normalization, two-decimal half-up rounding, and competition ranking are consistent across the gradebook, reports, and CSV export. Existing published legacy totals remain preserved.

Reporting uses five bulk queries for working classes and at most one additional publication-history query when published classes exist. Student render contexts omit peer rows and scores. See SRS_COMPLIANCE.md for exact interpretation and tests/browser_srs.py for current UI acceptance.
