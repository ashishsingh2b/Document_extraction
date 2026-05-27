# TODO - invoice_ai_service fixes

- [x] Step 1: Fix `SpatialExtractor` crash (`find_right_of` missing) so annotation + extraction can run end-to-end.
- [ ] Step 2: Remove/disable unsafe prefill heuristics in `scripts/annotate_helper.py` that can assign wrong fields (invoice_number/amount swaps). Replace with conservative logic.
- [ ] Step 3: Improve extraction+mapping safety: require label-confidence + keyword proximity before writing to normalized fields; prevent cross-field contamination.
- [ ] Step 4: Add regression tests using the provided sample invoice formats (at least 4: invoice 1,2,3,4 / plus others) to ensure correct extraction and no wrong mapping.
- [ ] Step 5: Run tests / quick evaluation script and update status docs.

