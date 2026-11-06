> Superseded: the current implementation follows the supplied SRS plus email OTP. See SRS_COMPLIANCE.md and LOCAL_SETUP.md.

# Rebuild delivery status

Implemented locally, 27 October 2026. The application is a teacher-centered Grade Analyzer using the existing brown identity, Segoe UI, Flask/Jinja, and Oracle. This is a tested local-project implementation; institutional grading approval, real email delivery, and an operational restore rehearsal are separate readiness steps.

## Delivered

- Shared responsive brown styling, simplified role navigation, reusable workspace controls, keyboard score-entry progression, unsaved-change warnings, and show/hide password.
- Password plus mandatory email OTP. Single-use five-minute challenges, per-account limits, five attempts per challenge, resend cooldown, credential/email change invalidation, and no pre-OTP academic session. Gmail configuration uses a local hidden prompt.
- Program curriculum folders and subject CRUD/archival; student/teacher management; class creation with one responsible teacher; current-term sections and historical main-section membership.
- Immediate student joining by code, including cross-section/program/year students. No approval queue. Prerequisites show an advisory notice; source notes are not presented as verified prerequisite completion. Joining closes on submission/publication.
- Teacher class workspace: Gradebook, Grading setup, Analytics, Class details. Teacher-created categories total 100%; assessments have individual maximum scores. Equal-percentage and total-points averaging are explicit options. Category changes with scores show a draft-result preview.
- Numeric scores distinguish zero from missing. Server validation, finite two-decimal bounds, class ownership checks, atomic score updates, stale-form protection, and protected deletion of scored assessments.
- Excel .xlsx template with class/revision/assessment metadata. Numeric uploads, roster matching by ID, validation, change preview, confirmation, atomic draft import, stale-preview rejection, and formula rejection. Blank cells retain existing scores. Imports do not release or publish grades.
- Explicit Save draft / Save and release. Students read immutable released values; subsequent private edits remain private. A later publication supersedes an older assessment release for the displayed approved result.
- Frozen final submissions, administrator return/publication, and authorized corrections retaining the prior publication. Legacy faculty write endpoints are blocked; old bookmarks route to the current workspace.
- Teacher assessment means, score distributions, and completion visualizations. Student score-percentage indicators and published breakdowns. Admin enrollment/submission summaries and reports using latest immutable publications, including while a correction is being prepared.
- Additive database migration, pre-migration logical snapshot, legacy-publication preservation utility, local setup/recovery instructions, and existing Oracle Data Pump backup/recovery tooling.

## Verification

Run from the `system` directory:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\venv\Scripts\python.exe tests\oracle_rebuild_check.py --database
.\venv\Scripts\python.exe tests\oracle_rebuild_smoke.py
.\venv\Scripts\python.exe tests\browser_rebuild.py
```

- 72 automated unit/security/calculation tests passed.
- 20 real Oracle workflow checks passed; all academic fixtures rolled back.
- 26 read-only real-Oracle route checks passed.
- 84 populated browser page checks passed at 1440, 768, 375, and 320 pixels, plus locked-gradebook and password-visibility checks. Final screenshot reruns update `audit/rebuild/browser-results.json`.

Oracle checks exercise joining, duplicate protection, category calculations (90% equal versus 88% points), release privacy, category edit preview, Excel preview/import/replay, formula rejection, policy requirements, submission locks, administrator return/resubmission/publication, student visibility, and preservation during corrections. Synthetic browser tests are not production-load measurements.

Earlier browser suites describe the previous interface; use browser_rebuild.py for current acceptance. Existing unit tests retain legacy pure-function coverage but verify current route redirects and mandatory email verification.

## Local setup still required

Run `venv\Scripts\python.exe scripts\configure_gmail.py` in your own terminal. Enter your Gmail address and Google App Password at the prompts; never send them through chat. If a login account has an old or unreachable email, run `scripts\set_account_email.py USERNAME` and enter its verified address. Restart after Gmail setup. LOCAL_SETUP.md has full instructions and official Google references.

SMTP credentials were not supplied and no real Gmail login code was sent during development. Email delivery errors fail closed; no demo OTP bypass exists. Test-only authenticated fixture routes exist only in the isolated test applications.

## Academic and deployment limits

- Final submission requires an administrator to record an approved whole-percentage rounding rule. The available choices are nearest whole percentage with .5 upward or round down; neither is silently chosen. Confirm departmental policy before using either.
- Release one requires complete numeric records. INC, exemption, withdrawal-grade conventions, and institutional completion procedures remain policy-dependent extensions; never substitute zero for them. GWA and predictive analytics are excluded.
- Existing subjects without a program remain unclassified. Resolve the eight legacy records and BSDSA source ambiguities with the academic owner rather than guessing.
- Existing published records, if present, can be preserved as labeled legacy snapshots; the migration does not fabricate administrator approval or recalculate their equivalents.
- This local configuration binds to 127.0.0.1 with HTTP-compatible cookies. Campus deployment requires HTTPS/secure cookies, a restricted runtime database account, verified database constraints/indexes, an agreed load target, and operational ownership. The preflight reports these conditions honestly.
- Data Pump clients are installed, but wallet/directory setup, scheduled backups, and an actual isolated restore rehearsal have not been completed by this task. The migration JSON snapshot does not replace a verified Oracle backup. Follow BACKUP_RECOVERY.md before real institutional use.
