# Data governance and deployment gates

1. Maintain a data-source registry and store licence/attribution with every ingested dataset.
2. Never scrape sites in breach of terms or bypass access controls.
3. Do not combine datasets where licence terms conflict without legal review.
4. Remove direct personal identifiers; avoid owner/tenant data and sensitive household attributes.
5. Prevent target leakage: a feature timestamp must be at or before the valuation date.
6. Keep property-level records access-controlled; public output should be aggregated where re-identification risk exists.
7. Validate local currency, area unit, property type, tenure, tax treatment and transaction definition per jurisdiction.
8. Distinguish sale price, asking price, assessed value, circle/guidance rate, rent and modelled estimate.
9. Report uncertainty and abstain when data coverage is weak or out-of-distribution.
10. Do not use the system as a substitute for a certified appraisal or legal title verification.
