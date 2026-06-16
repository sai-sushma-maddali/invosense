# Invoice Extraction Module

Standalone Python module that turns an invoice image into an `ExtractedInvoice`
(Contract 1) JSON object using a Groq vision LLM routed through the
**TrueFoundry AI Gateway**. Has no dependency on other project modules.

## What it does

`extraction.run(image_bytes, invoice_id) -> ExtractedInvoice`

1. Encodes the image as a base64 data URI.
2. Calls a Groq vision model via the TrueFoundry gateway (OpenAI-compatible),
   so usage/cost are logged centrally.
3. Prompts for **JSON only** with: `company, gst_id, invoice_no, date`
   (`YYYY-MM-DD`), `taxable` (subtotal before tax), `tax`, `total`.
4. Safely parses + normalizes the response (date -> `YYYY-MM-DD`, amounts ->
   float).
5. Scores 0-1 confidence per field (GST id regex, date parses, and the
   `total == taxable + tax` identity), blended with model certainty if present.
6. Optionally attaches `{field: [x, y, w, h]}` word boxes via pytesseract.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in real values
```

`.env`:

```
TFY_GATEWAY_URL=https://gateway.truefoundry.ai
TFY_API_KEY=...
TFY_MODEL=groq-main/llama-3.2-90b-vision-preview   # copy exact id from Playground
```

## Usage

```python
from extraction import run

with open("invoices/X51007262330.jpg", "rb") as f:
    result = run(f.read(), invoice_id="X51007262330")

print(result.to_json())
```

## Evaluation (field-level F1)

Runs over the 10 sample receipts and compares to the SROIE ground truth:

```bash
python -m eval.run_eval --invoices "invoices" --ground-truth "ground truth" --target 0.9
```

Per-image Contract-1 JSON is written to `out/`, and a per-field
precision/recall/F1 table plus macro/micro F1 is printed. Only fields present
in each ground-truth file are scored, so the stock SROIE GT
(`company`/`date`/`total`) and an extended 7-field GT both work.

## Optional: word boxes

Requires the `tesseract` binary installed on the system. Enable with
`run(..., with_boxes=True)` or `--with-boxes` in the eval harness. Degrades
gracefully to no boxes if tesseract is unavailable.

## Offline smoke test

Verifies the contract, normalization, confidence and F1 plumbing without
network or credentials:

```bash
python -m tests.smoke_test
```

## Files

- `extraction/contract.py` - `ExtractedInvoice` (Contract 1).
- `extraction/gateway.py` - TrueFoundry/OpenAI client + image encoding.
- `extraction/prompt.py` - vision prompt + safe JSON parsing.
- `extraction/normalize.py` - date/amount/text normalization.
- `extraction/confidence.py` - per-field 0-1 scoring.
- `extraction/boxes.py` - optional pytesseract word boxes.
- `extraction/extract.py` - `run()` orchestration.
- `eval/run_eval.py` - F1 evaluation harness.
