# Demonstration video reference

## Status

A recording link is intentionally left as a placeholder because the repository should not ship a
large binary video. Record the walkthrough below and replace this line with the final URL:

```text
Recording: TBD - add the hosted video URL here
```

The script and expected output in this document are the canonical demonstration reference.

## Recording setup

1. Start from a clean repository and a clean Docker volume:

   ```bash
   docker compose down -v
   docker compose up --build -d
   ```

2. Open <http://localhost:8000> at 1280x800 or larger.

3. Run `bash scripts/demo.sh` in a terminal for the API-only path, or click through the UI while the
   terminal shows `docker compose logs -f receipt-ai`.

## Storyboard

| Time | Scene | What to show |
| --- | --- | --- |
| 0:00 | Context | Repository root, `README.md`, `knowledge.txt`, and the phase branches |
| 0:30 | Architecture | `docs/architecture.md` diagram, data flow, and storage boundaries |
| 1:00 | 100k analysis | `make analyze`, then `reports/insights.json` and `docs/figures/` |
| 1:30 | 2M streaming | `make stream`, point at the 58.7 MB RSS and 17.57 s numbers in `docs/benchmark-results.md` |
| 2:00 | Vector DB | `pytest tests/test_vector_similarity.py tests/test_vector_store.py`, show `docs/vector-index.md` |
| 2:30 | Upload | Drop a receipt image, show OCR metadata, warnings, and the editable review form |
| 3:15 | Save | Save the receipt and show it appear under History with insights |
| 3:45 | Ask | Ask the three required questions and show the answer, tool call, and evidence |
| 4:30 | Container | `bash scripts/verify_docker.sh`, mention the health check and persistence restart |
| 5:00 | CI | Show `.github/workflows/ci.yml`, the lint, test, and container build jobs |
| 5:30 | Tests | Run `pytest -q` and show the passing suite |
| 5:45 | Close | Requirements mapping, limitations, and what would change at production scale |

## Required questions to ask on camera

Use the Ask page or the API:

```bash
curl -sS -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What food did I buy yesterday?"}' | python3 -m json.tool

curl -sS -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Give me total expenses for food on 20 June"}' | python3 -m json.tool

curl -sS -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Where did I buy hamburger from last 7 days?"}' | python3 -m json.tool
```

If today is not near the receipt date, include `as_of` so relative dates are deterministic:

```json
{"question": "What food did I buy yesterday?", "as_of": "2026-10-29"}
```

## Expected demo output

`bash scripts/demo.sh` prints a receipt upload, a save confirmation, and the three answers. A healthy
run looks like this:

```text
Uploaded receipt #1 for GREEN BOWL on 2026-10-28 with 3 items totaling 31.35 USD
Saved receipt #1 and indexed it for retrieval

Q: What food did I buy yesterday?
A: You bought food 2026-10-28. Receipts: GREEN BOWL on 2026-10-28: Hamburger x2, Fries x1, ...
   engine=rules found=True tool=get_purchases_by_date evidence_rows=1

Q: Where did I buy hamburger from last 7 days?
A: You bought hamburger from GREEN BOWL on 2026-10-28 (20.00 USD).
   engine=rules found=True tool=find_merchant_by_item evidence_rows=1
```

The script sets `OPENAI_API_KEY` to empty by default so the demo is deterministic and offline. Set
`DEMO_LLM=1` to exercise a configured OpenAI-compatible model instead.

## What to call out

- The model never sees SQL. It sees three typed tools.
- Every answer carries normalized arguments and evidence rows.
- The empty-result path is explicit, not hallucinated.
- The container health check and volume restart prove the local deployment is real.
- The 2M pipeline is measured, not asserted.
