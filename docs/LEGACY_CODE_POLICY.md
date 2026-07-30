# Legacy Code Policy

- V1 trading logic is frozen and is not a design source for V2.
- Existing code may be inspected only for infrastructure reuse, data compatibility and migration risks.
- New indicators, regime, scoring, setup, lifecycle and evidence logic must live under `v2/`.
- Changes to V1 production files require an explicit compatibility reason and a complete-file review.
- Partial-file replacement is prohibited.
