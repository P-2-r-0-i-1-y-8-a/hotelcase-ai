# HotelCase AI — End-to-End Local MVP

**A working demonstration of hotel revenue reconciliation, LangGraph investigation, audit workflow and evidence packet generation.** All bundled transactions are synthetic. No real credit cards, customer names or confidential hotel information are included.

## Features

- Streamlit dashboard with property filtering, KPI cards and exception queue
- CSV import for PMS reservations, captured payments and OTA settlements
- Deterministic USD-only accounting using Python integer cents, NOT LLM arithmetic
- Clear distinction between HOTEL-collected funds and OTA-collected net settlements
- Flags shortfalls, overcollection, pending settlements, policy-review cases, and duplicate transaction IDs
- LangGraph StateGraph: retrieve source records → validate financial facts → route to review / clear → optional local Ollama summary
- Persistent local SQLite review states and append-only **application-level** audit records
- Reviewer approval required before **manual** dispute preparation; no automated submissions
- PDF evidence packets and CSV/JSON exports
- Unit tests covering reconciliation, dirty data, approval, audit, graph routing and PDF creation

## Quick start (Windows PowerShell)

Keep the project in a short folder to avoid Windows PyTorch long-path issues. This project **does not install torch**.

```powershell
cd C:\HotelCaseAI
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8507
```

Open **http://localhost:8507**. On subsequent days, simply `cd C:\HotelCaseAI`, activate `.venv`, and run the Streamlit command again. Stop with `Ctrl+C`.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8507
```

For a local LLM explanation (optional), install Ollama, run `ollama pull llama3.2:3b`, start Ollama, then toggle **Optional local Ollama narration** in the sidebar. Without Ollama, the LangGraph workflow remains functional and produces rule-grounded recommendations. Ollama narration is limited to supplied facts and cannot modify financial totals.

## Automated verification

```powershell
python -m pytest -q
```

## Demonstration workflow

1. Open **Overview** to inspect synthetic exception counts and unverified shortfall amounts.
2. Open **Exceptions & Cases** to filter the queue and record a review decision.
3. Open **LangGraph Investigation**, select `HC-1001` and click **Run LangGraph investigation**.
4. Expand graph checks/source records; download a PDF evidence packet.
5. Inspect **Audit Trail** to see creation, investigation and review events.
6. Download sample CSV templates from the sidebar, edit **synthetic** examples and re-upload to simulate changing records.

### Example synthetic cases

- `HC-1001`: hotel-managed $100 shortfall
- `HC-1002`: OTA-managed net settlement reconciles after $75 commission
- `HC-1004`: pending hotel payment (not classified as confirmed loss)
- `HC-1005`: OTA refund + commission netting
- `HC-1006`: $20 overcollection; investigate potential refund
- `HC-1007`, `HC-1011`: cancellation/no-show policy reviews
- `HC-1008`: pending OTA settlement
- `HC-1013`: duplicate payment ID, excluded from totals pending review

## CSV formats

The files `data/reservations.csv`, `data/payments.csv`, and `data/settlements.csv` are your templates. Fields:

**Reservations:** `reservation_id,property_id,channel,payment_responsibility,booking_status,gross_amount,approved_refund,adjustment,ota_commission,currency,response_deadline`

**Payments:** `payment_id,reservation_id,amount,status,currency,processed_at` (a successful row uses `CAPTURED`)

**Settlements:** `settlement_id,reservation_id,amount,status,currency,settled_at` (a successful row uses `SETTLED`)

This is a simplified accounting model, not a full hotel folio or processor ledger. Gross, adjustments, refund and commission fields must be interpreted consistently. In production the settlement model must be checked against the contract, processor fees, taxes and accounting basis.

## Architecture

```text
synthetic PMS / payment / OTA CSVs
           |
      schema validation
           |
   deterministic reconciliation
           |
   exception queue + SQLite state
           |
   LangGraph investigation
      +-- retrieve source evidence
      +-- validate numeric facts
      +-- route review or clear
      +-- optional Ollama narration
           |
    human case-review workflow
           |
   PDF packet + audit + exports
```

## Safety and production limitations

- **NO OTA/PMS connectivity**, web scraping, bank processing, external chargeback filing, payment capture or automated refund.
- All data are synthetic. **Never upload card numbers, CVVs, guest PII or real hotel records** into this demo.
- Reviewer identity is a label, **not authentication**. SQLite audit records are application-level and can be modified by someone with local disk access.
- The response-deadline field is supplied data, **not validated** against any OTA, processor or legal deadline.
- Differences are **unverified accounting exceptions**; not proven recoverable revenue or legal entitlement.
- Duplicate transaction IDs are excluded entirely from monetary totals, pending validation; do not use those totals as accounting truth.
- Uploaded data replace sample files only in the running session. Case states are keyed by reservation ID in SQLite; do not mix independent hotels/workspaces in the same database. If source category/amount changes, review state resets, but other nonfinancial source changes are not version-controlled in this demo.
- For production: add property tenancy, RBAC, authentication, encryption, ingestion provenance, permissions, immutable evidence storage, ledger-level reconciliation, policy validation, idempotency keys, source snapshots, workflow review controls and comprehensive security audits.

## Layout

```
app.py
requirements.txt
hotelcase/
  agent.py
  reconciliation.py
  storage.py
  evidence.py
  sample_data.py
data/
  reservations.csv
  payments.csv
  settlements.csv
tests/
  test_reconciliation.py
  test_storage_agent_evidence.py
```

Created for education and local product validation, not production financial operations.
