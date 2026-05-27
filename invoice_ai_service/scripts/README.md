# Scripts

| Script | Usage |
|--------|--------|
| `train_model.py` | `python scripts/train_model.py` — train XGBoost routing model |
| | `python scripts/train_model.py --evaluate-only` — inspect `models/v1` |
| | `python scripts/train_model.py --predict --file path/to.pdf` |
| `test_accuracy.py` | Run field accuracy vs `training_data/annotated/labels.json` |
| `generate_report.py` | Generate `logs/accuracy_report.txt` |
| `annotate_helper.py` | Interactive labels for files in `training_data/raw/` |
| `build_ocr_cache.py` | OCR all PDFs in `raw/` → `ocr_cache/` |
| `eval_ocr_cache.py` | Table of extractions from cache (no PDF runtime) |

Run from `invoice_ai_service/` with venv active and `pip install -r requirements.txt`.

See **`END_TO_END_GUIDE.md`** for the full phased workflow.

### Run all tests (venv + install + validate)

```bash
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh
```

Or only validation (after deps installed):

```bash
python scripts/e2e_validate.py
pytest tests/ -v -m "not integration"
```
