# Synthetic document samples

These small PDFs contain fictional values and are watermarked **SYNTHETIC TEST SAMPLE - NOT A GOVERNMENT CERTIFICATE**. They are for local or staging upload tests only; never use them as procurement evidence.

Regenerate the files from the repository root with:

```powershell
python backend/testdata/sample_documents/generate_samples.py
```

## Files

- `valid_gst_certificate.pdf`, `valid_pan_certificate.pdf`, and `valid_udyam_certificate.pdf` contain mutually consistent sample details based on the local demo bidder profile.
- `mismatched_gst_certificate.pdf` uses a different GSTIN/PAN to exercise identity discrepancy and manual review.
- To test missing mandatory coverage, create a test draft for a tender requiring GST and PAN, upload only `valid_pan_certificate.pdf`, then run verification. The bid form normally blocks submission until mandatory files are selected; this authenticated API flow exercises the server-side verification result without weakening that UI guard. Run it against a local or staging database only, and replace the tender reference/category with an active tender that requires both document types:

  ```powershell
  $api = 'http://localhost:8000/api'
  $login = Invoke-RestMethod -Method Post -Uri "$api/auth/login" -ContentType 'application/json' -Body (@{ email = 'bidder@bharatsetu.gov.in'; password = '<local bidder password>' } | ConvertTo-Json)
  $headers = @{ Authorization = "Bearer $($login.access_token)" }
  $bid = Invoke-RestMethod -Method Post -Uri "$api/bids" -Headers $headers -ContentType 'application/json' -Body (@{ tender_id = '<active tender reference>'; vendor_name = 'TechCorp India Pvt Ltd'; category = '<tender category>'; bid_amount = '120000' } | ConvertTo-Json)
  Invoke-RestMethod -Method Post -Uri "$api/bids/$($bid.id)/documents" -Headers $headers -Form @{ file = Get-Item 'backend/testdata/sample_documents/valid_pan_certificate.pdf'; document_type = 'PAN' }
  Invoke-RestMethod -Method Post -Uri "$api/bids/$($bid.id)/verify" -Headers $headers
  ```

## Test in the app

1. Start the backend in local mode with `LLM_PROVIDER=gemini`, `GEMINI_API_KEY` configured, and `GEMINI_MODEL=gemini-2.5-flash` (or the model configured for the environment). Keep `STORAGE_BACKEND=local` for local tests; production credentials must never be placed in this folder or committed.
2. Sign in as an authorized bidder whose profile matches the valid sample values. In the bidder portal, choose **Start a Bid / Upload Documents**, select a tender, then attach the corresponding sample in its document checklist. Existing bids also expose per-requirement upload controls under **My Bids**.
3. Submit and run verification. Review extracted fields in **My Documents** and requirement findings, discrepancy actions, and the officer review summary in **My Bids**. Use the mismatch sample for a discrepancy; replace or omit the required file to exercise remediation and missing-document coverage.

For a local dev server, from the repository root:

```powershell
$env:ENVIRONMENT = 'development'
$env:LLM_PROVIDER = 'gemini'
$env:GEMINI_API_KEY = '<your test key>'
$env:GEMINI_MODEL = 'gemini-2.5-flash'
$env:STORAGE_BACKEND = 'local'
python -m uvicorn app.main:app --app-dir backend --reload
```

Run the frontend separately with `cd Frontend; npm run dev`. API credentials and tokens are kept in the environment and browser session, not in the sample files.
