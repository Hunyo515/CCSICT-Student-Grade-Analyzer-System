# Pre-launch audit — 25 October 2026

**Decision: NOT READY FOR LAUNCH.** Local defects listed below were repaired and
regression-tested, but live Oracle, SMTP, migration, recovery, TLS and production
capacity checks cannot be completed without test services. The user confirmed
that no Oracle test database or SMTP test inbox is available. Passing fixture
checks is not certification of a deployed application.

## Verified local results

- **38 automated tests passed** (see `audit/unit-tests.txt`).
- **84 empty-data browser checks and 61 populated/browser-security checks passed**
  at 1440, 375 and 320 pixels, with no detected root horizontal overflow,
  JavaScript errors or broken registered-route links in the final runs.
- Slow-network registration completed in about **15.3 seconds** with a cold cache,
  400 ms latency and 50 KB/s download cap. Offline navigation produced the browser's
  connection error and no false success. These are local simulations, not field measurements.
- **24 concurrent OTP verification attempts produced exactly one success**;
  the parallel five-attempt limiter admitted exactly five attempts.
- **36 fixture dashboard requests across 12 workers returned 200**, with independent
  sessions. See measured fixture timings in `audit/concurrent-users.json`.
- **15 pinned production packages** returned no known advisories in the final scan.
- Scoped common-secret-pattern scan returned **zero matches** after cleanup.
- Readiness preflight correctly **failed** because required services/secrets are absent.

## Scope and evidence

Reviewed the Flask application factory, configuration, password/session handling,
all five route modules, database helpers, grading and notification helpers,
all templates, shared CSS, schema/seed/migrations, dependencies, password reset,
and backup/recovery scripts. There is no separate REST API or external business
API in this source: the application uses server-rendered Flask GET/POST routes,
Oracle, and SMTP. External Google Fonts imports were removed so rendering does
not depend on that service.

Evidence in `audit/`:

- `unit-tests.txt`: reproducible unit, integration and concurrency test results.
- `route-results.json`: authenticated empty-data page responses; expected redirects
  for an absent CSV preview and 404 for an absent export assignment are intentional.
- `browser-results.json`: real headless Edge checks at 1440, 375 and 320 pixels,
  empty data, route links, JavaScript errors, modal/tab checks, slow and offline conditions.
- `browser-populated-results.json`: populated faculty/student pages and stored
  confirmation-text injection regression in a real browser, using SQL fixtures.
- PNG screenshots: representative desktop/mobile pages and the student form.
- `concurrent-users.json`: 36 fixture dashboard requests across 12 workers with
  independent sessions; this does not measure Oracle throughput.
- `dependencies-before.json` and `dependencies-after.json`: package advisory scans.
  Initial direct pins had Flask and python-dotenv advisories; a subsequent scan
  also identified the Windows-specific Werkzeug safe_join advisory. Final pins
  have no known advisories returned by the scanner at audit time. This is not a
  guarantee that undisclosed vulnerabilities do not exist.

## Critical/high-priority defects repaired

| Finding and impact | Repair | Verification / limit |
|---|---|---|
| Student grades, analytics and recent assessments exposed draft scores before publication. | Require PUBLISHED in these paths; hide the draft total and grade banner. | Tests prove draft scores are not read; populated and empty pages render. Oracle predicates still require live integration testing. |
| Existing signed cookies retained access after account disablement, password reset, or logout. | Server-side expiring/revocable session tokens; check active account, password fingerprint, role and linked profile on each authenticated request; revoke on logout. | Disabled accounts, changed credentials and replayed logged-out tokens are rejected. |
| Pending OTP could authenticate after a password reset. | Bind pending login to the password fingerprint and recheck active role/account after OTP. | Authentication flow and password/session tests cover the new binding; real mail delivery remains untested. |
| Student self-registration could claim an identity and gain immediate access; named peer grades were exposed by rankings. | New registrations remain INACTIVE pending administrator identity verification; display only the student's own named class standing. | Registration test confirms inactive user/student inserts; route review confirms only the own-entry list reaches the ranking template. |
| Database-backed text was interpolated into JavaScript confirmation strings. Quotes could break the dialog or execute code. | Store text in escaped data-confirm attributes and pass it as a string to confirm(), never as generated JavaScript. | Static regression plus browser payload test. |
| Concurrent grade edits could silently overwrite each other; changing a published score/weight left corrections publicly visible. | Lock the class row, use revision tokens, reject stale edits with 409, return modified grades/weights to IN_PROGRESS, require explicit publication. | Stale revisions fail before writes; row-lock behavior must be tested on Oracle after migration 009. |
| CSV cells could execute spreadsheet formulas when staff opened exported files. | Escape formula-prefixed text and sanitize download filenames; private exports receive no-store. | Formula-prefix tests; populated export route responds successfully. |
| Declared dependencies included known vulnerabilities; the environment differed from requirements.txt. | Pin the tested production dependency graph; Flask 3.1.3, Werkzeug 3.1.9, python-dotenv 1.2.2; add Waitress. | Final package-advisory scan reports no known vulnerabilities. |
| Schema setup silently dropped existing academic tables. | Fresh schema creation now fails on conflicts instead of dropping data; upgrades use a separate migration. | Source inspection; migration has NOT been run against Oracle. |
| Administrative deletions could cascade through academic history. | Reject deletion of students with enrollments, teachers/subjects with classes, and classes with enrollments; retain/deactivate instead. | Guard review; database-side concurrency/integrity requires staging validation. |
| Application defaults encouraged using the schema owner at runtime. | Supply a separate runtime DML grant script and ORACLE_SCHEMA support, plus read-only privilege checks. | SQL/config review only. Actual account grants and network exposure are UNKNOWN. |

## Additional functional/reliability fixes

- Empty student analytics passed an empty list to the GPA function and crashed.
  It now uses the same credit-weighted published average as the dashboard.
- Student pass/fail used 60 while faculty/export and dashboard used 75. Displays
  now consistently use 75, the existing faculty cutoff. The school must confirm
  this grading policy before release; this audit does not set academic policy.
- Clearing a score input previously left the old grade intact. Blank entries now
  remove the submitted score, with ownership and revision checks.
- Saved percentages now update max_score to 100; existing scores with other maxima
  display normalized percentages before editing.
- CSV previews are server-side, owner-bound and expire; confirmation rechecks
  class revision/membership. Duplicate headers, duplicate student/component pairs,
  surplus columns, nonfinite/out-of-range scores and more than 10,000 rows fail.
  A malformed/oversized CSV produces a controlled 400/413 response.
- Component names are unique per class so CSV matching is unambiguous; migration
  009 must validate existing data before the unique index can be applied.
- Term activation validates the requested term and serializes the change; a unique
  index prevents multiple active terms. Creating a class without a term now gives
  an actionable conflict rather than a null-reference crash.
- Class codes now use cryptographic randomness, are generated only by POST,
  are throttled when joining, and cannot enroll a student into an inactive term.
- Account-setting changes require the current password. Password reset uses a
  masked terminal prompt rather than placing the new password in command history.
- Logout is a CSRF-protected POST. Notification links are loaded from the owned
  database record and checked for unsafe redirects instead of trusting form input.
- Errors render without retrying failed database queries through the navigation
  context processor. Database failures return a generic 503 without SQL details;
  a failed commit never returns a success confirmation.
- Oracle pool waits and individual calls have bounded timeouts. The entry point
  runs Waitress on localhost rather than the Flask development server.
- Class rankings bulk-load published scores instead of querying per student and
  subject; weighted-average and tie-ranking tests were added, with supporting indexes.
- UTF-8 notification/activity truncation now respects database byte limits;
  notification failures are logged by type rather than silently swallowed.
- Non-ASCII CSRF tokens no longer produce a server exception.
- Corrected username generation limits and curriculum-program validation.
- Added no-store responses for authenticated content, CSP, frame protection,
  content-type protection and restricted browser permissions. CSP still allows
  inline scripts/styles because existing templates use inline event handlers;
  further nonce-based refactoring would be defense-in-depth.
- Removed the embedded example database password from schema instructions,
  explicitly disabled demo seed passwords, and added ignore rules for secrets,
  local security databases, environments and dumps. No live API keys were found
  by the scoped source scan; external stores/history were not available to inspect.
- Added small-screen navigation/form/table rules; fixed clipped registration,
  Settings negative margins, populated faculty pages, and scrollable grade tables.
  Added submission feedback and duplicate-submit prevention for slow connections.
- Recovery now checks that the target schema exists and is empty via SQL*Plus
  before import. Missing metadata privileges fail closed. No backup/restore was run.

## Flow coverage and limits

| Area | Verified locally | Still requires real staging services |
|---|---|---|
| Login / OTP / logout | Real bcrypt verification with fake SMTP transport; all roles; expiry, replay, five-attempt lockout; logout revocation; CSRF; controlled delivery timeout. | STARTTLS negotiation, SMTP credentials, recipient delivery/spam handling, sender domain configuration. |
| Sign-up / account administration | Required/invalid fields; inactive registration inserts and password hashing; status/reset invalidation; page/form rendering. | Unique/FK constraints, transaction durability, actual approval workflow and real account email data. |
| Academic CRUD / enrollment | Role guards, form validation, populated/empty route rendering, safe errors and history-deletion guards. | Apply and test schema, identities, foreign keys, grants and rollback across full create/edit/assign/delete workflows. |
| Grades / weighting / import/export | Draft privacy, weighted math, stale revision rejection, score clearing, CSV validation/safety, published page rendering. | Concurrent Oracle writers, commit failure/reconnect cases, actual CSV persistence and publication notifications. |
| Notifications / recovery requests | Owned-record scoping and safe redirect code; notification byte limits. | Actual Oracle storage and administrator response. Forgot-password remains an administrator-assisted reset, not an automated email-reset link. |
| Browser/mobile | Edge at desktop and phone widths, populated/empty states, link resolution, JS errors, modal/settings interactions. | Real devices, Safari/Firefox, screen-reader usability and school-sized datasets. |
| Network/concurrency | Real browser throttling and offline failure; 24 competing OTP consumes allow one success; parallel limiter cannot exceed five; 36 independent fixture page requests. | Production latency/loss, interrupted writes, campus NAT/proxy configuration, Oracle pool saturation and realistic sustained load. |
| Backup/recovery | Command validation, source-target separation, empty-target check, runbook and dry run. | Successful dump, encrypted off-host copy, scheduled jobs/alerts and measured restoration with row/grade/identity verification. |

No networked application API was discovered beyond the Flask routes. API-like
POSTs are protected by server role/record checks, CSRF and validation; this is not
an audit of a separate API gateway, database firewall or hosting provider.

## Remaining launch blockers — do not skip

1. **Configure an isolated Oracle staging database and apply the correct schema or
   migrations through 009.** Run preflight, verify constraints/indexes/identities,
   all CRUD and grade workflows, rollback and row-lock behavior with two writers.
   Existing bad data can cause migration failure; Oracle DDL commits individually.
2. **Configure and test SMTP with a controlled inbox.** Confirm OTP delivery,
   expiry/retry behavior, wrong/unavailable recipients and mail-server outages.
   Ensure every active account has a verified, controlled email address.
3. **Provide real deployment secrets and infrastructure.** The local preflight
   reports missing SECRET_KEY, Oracle password and SMTP host/sender. Verify HTTPS,
   secure cookies, host/proxy configuration, filesystem permissions, database
   firewall rules and least-privilege runtime grants. Rotate any previously used
   example database password; this audit cannot know whether it was deployed.
4. **Rehearse backup and recovery on a separate database.** No successful backup,
   restore, schedule, retention/off-host verification or recovery time is evidenced.
5. **Run a production-like load/failure test.** Fixture timings cannot establish
   capacity. Exercise realistic students, subjects and CSV sizes, simultaneous
   saving/publishing, timeouts and connection loss. Tune pool/worker/rate limits
   based on measured results. Current SQLite security storage supports one
   application host, not multiple independent hosts.
6. **Confirm operational/academic policy.** Identity approval, 75% pass threshold,
   authorized staff access, privacy/retention, administrator-assisted password
   recovery and the republish-after-correction workflow require school sign-off.

## Reproduce

From `system` using the configured virtual environment:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe tests/browser_audit.py
.\venv\Scripts\python.exe tests/browser_audit.py --populated
.\venv\Scripts\python.exe -m pip_audit -r requirements.txt --no-deps --disable-pip
.\venv\Scripts\python.exe scripts/preflight.py --database
```

Browser tests require Microsoft Edge and create only a temporary localhost fixture
server. Test-only login routes exist exclusively in `tests/audit_fixture.py` and
are never registered by `run.py` or `create_app()` in production. They bypass real
identity solely to render fixture pages. The separate authentication tests exercise
the actual password/OTP/session flow with fake SMTP transport.

## Post-audit authentication change

After this audit, email OTP sign-in was removed at the user's request. SMTP
configuration is no longer required for login, and successful password
authentication now creates a protected session directly after checking the
selected role and active account status. The OTP-specific audit results and
SMTP deployment blocker above describe the earlier audited version and no
longer apply. Password-only login is less secure than multi-factor
authentication; retain the active-account checks, rate limits, CSRF protection,
HTTPS, and strong unique passwords.
