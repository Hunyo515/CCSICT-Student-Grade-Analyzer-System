# CCSICT Student Grade Analyzer

The active implementation follows the supplied six-page SRS, with the university workflow amendments in WORKFLOW.md. See [SRS_COMPLIANCE.md](SRS_COMPLIANCE.md) for requirement mapping, grading interpretations, and verification.

## Main workflows

- Admin: searchable/paginated subject, faculty and student records; class assignments; academic terms; dashboard and school analytics.
- Subject curricula: BSDSA (2023–2024) plus supplied BSCS, BSIT, BSIS and BLIS (2021–2022) curricula, grouped by year and semester, including Midyear as Summer. Retained PDF sources, specialization tracks and source discrepancy notes are available in each program. The four-program import adds 224 verified course rows without overwriting existing subjects; nine-unit practicum/internship courses are supported in Oracle and subject editing. Import checks, backups and source transcriptions are under audit/program-curricula.
- Faculty: Lecture/Laboratory split, weighted components, score grid, CSV preview/import/export, direct grade publication, class analytics, and Top Performers.
- Grade entry: edit component titles, component percentages, blank-by-default activity dates, highest possible scores, and student scores directly in the worksheet, then Save sheet. Use the + button beside Export CSV to add a component, the compact header editor to change its title or percentage, and + Add beside the component Total heading to append an activity column. The Add action saves pending scores in the same transaction and keeps numbering sequential. Dialog saves include pending worksheet scores in the same transaction; Cancel/Escape discards only dialog edits. The record uses a monochrome grid with readable numbered activity headings and no assessment-key panel. New HPS cells start blank. Active editable records follow the reference class-record calculation: PS = total raw scores / total HPS × 100; WS = rounded PS × component percentage (rounded to two decimals), with semester percentage summing WS. Individual activity percentages are not shown. Published and historical records retain their saved calculation basis and ISU grade equivalents. Excel score ranges can be pasted; Enter/Shift+Enter moves vertically. HPS edits validate search-hidden students and save denominators with scores in one transaction. Missing scores contribute zero. Faculty see In progress provisional grades from configured activities while HPS or allocations are unfinished; final publication still requires valid setup. Activities with scores cannot be removed by reducing the count.
- Student: registration, upcoming-term EnlistMe, own published grades, unit-weighted Overall Average, own rank, and personal analytics.
- Shared: in-app notifications and admin email OTP; faculty/student password login, generated initial credentials, and first-login password change.

The interface uses Segoe UI and brown navigation with a black-and-white class record, with consistent controls, component-edit dialogs, confirmation dialogs, and responsive navigation.

## Run locally

Follow [LOCAL_SETUP.md](LOCAL_SETUP.md) to configure Gmail locally, then run:

```powershell
.\venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000/. After changing configuration, restart the existing project server with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restart_local.ps1
```

## Current tests

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\venv\Scripts\python.exe tests\oracle_srs_check.py --database
.\venv\Scripts\python.exe tests\oracle_srs_smoke.py
.\venv\Scripts\python.exe tests\browser_srs.py
```

Oracle acceptance fixtures roll back. Browser fixtures are isolated synthetic applications and do not send email. Evidence and pre-change source snapshot are in audit/srs-alignment.

## Scope and history

Teachers publish directly. Missing scores contribute zero while remaining unrecorded in storage. CSV confirmation commits valid rows and reports skipped invalid rows. Existing publication history and academic data are retained. Self-registered students can sign in immediately with their email address or Student ID and password. Registration offers an optional random password suggestion. Only administrators require email OTP.

FINAL_BLUEPRINT.md, REBUILD_STATUS.md, and older browser scripts describe superseded proposals. SRS_COMPLIANCE.md is the controlling current implementation document.

Automated backups and self-service password reset remain outside the SRS product scope. Existing operator backup/recovery tools are retained. Local verification is not a certification of institutional grading policy, production load, or database restoration.
