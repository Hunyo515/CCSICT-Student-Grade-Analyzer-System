> November 2 faculty amendment: My Classes now owns the semester-specific class list. Open Gradebook uses a grouped class-record worksheet with faculty-defined component/activity weights (each level totals 100%), highest possible scores, normalized percentages, and weighted semester results. New/unpublished classes use the FLEXIBLE model. Published historical models are retained. ISU numerical grades use the published Student Manual bands; component weights remain faculty-controlled. This amendment supersedes the earlier fixed Lecture/Laboratory UI and grading-policy statements below.

> Current university amendments (27 October 2026): program curriculum folders; generated initial faculty/student credentials; first-login password change; university ID/contact/email/section validation; admin-only email OTP; upcoming-term EnlistMe replacing code joining and admin enrollment; read-only term filtering including All. These explicit user instructions supersede the corresponding original SRS behavior. See WORKFLOW.md.

# Student Grade Analyzer — SRS implementation and acceptance

Baseline: `srs-student-grade-analyzer.pdf`, six pages, supplied by the project owner. The owner's later instruction selects this SRS over conflicting rebuild proposals, with email OTP retained. This document maps the current implementation; earlier FINAL_BLUEPRINT.md and REBUILD_STATUS.md describe superseded workflows.

## Active scope

Admin manages subjects, faculty, students, classes, and terms. Faculty configures weighted Lecture/Laboratory components, enters or imports CSV scores, publishes directly, and reviews class analytics/rankings. Students self-register, join using a teacher code, and see their own published grades, average, rank, and analytics. Shared in-app notifications and email-OTP sign-in remain enabled.

Admin grade approval, arbitrary category schemes, Excel upload, and pre-publication score release are not active SRS workflows. Their existing history remains preserved; their previous write endpoints are blocked. An existing class in a previous Submitted/Returned state can be saved by its responsible teacher into In Progress without deleting its revision history.

## Functional traceability

| SRS requirement | Current implementation | Acceptance evidence |
|---|---|---|
| 3.1.1 Role-specific login | Admin, Faculty, Student login screens | Security unit tests; browser login checks |
| 3.1.2 Student registration | Registration creates an active student account with optional random password suggestion | Registration and real Oracle browser tests |
| 3.1.3 Reject invalid/deactivated/wrong-role login | Active account/profile checks, password verification, role checks | Security and session tests |
| 3.1.4 Role and record separation | Route guards, teacher ownership, published-only student queries; peer grades omitted from student render context | SRS access/calculation tests and Oracle checks |
| 3.1.5 Admin-assisted password reset | Neutral reset-request response and administrator in-app notification | Existing auth workflow and security tests |
| 3.2.1 Admin dashboard | Active student/faculty account counts, active catalog count, term grade-entry count, recent activity | Real-Oracle pages and browser checks |
| 3.2.2 Record CRUD/search | Paginated searchable subject catalog; faculty/student search, add, edit, archive/deactivate/delete protections | Existing workflow tests; live route and browser checks |
| 3.2.3 Assign faculty and student sections | Admin class assignment with generated code; student section editing and roster assignment | Oracle class creation, duplicate checks, existing admin tests |
| 3.2.4 Terms | Term creation/activation, one-active-term unique index; active-term editing | Existing term validation and live checks |
| 3.2.5 Admin analytics | Program/year/subject enrollment, sex distribution, regular/irregular counts and program breakdown, published class averages | Browser populated/empty pages; scoped bulk reporting |
| 3.3.1 Faculty dashboard | Assigned class cards, Draft/In Progress/Published labels | Browser pages and live Oracle checks |
| 3.3.2 Weighted components and score grid | Named components under Lecture/Laboratory, editable weights, score maxima, keyboard-friendly entry | SRS calculation and Oracle checks |
| 3.3.3 Lecture/Laboratory split | Editable split, running total, within-portion weights and final contribution | Browser weighting screen; calculation tests |
| 3.3.4 CSV import | UTF-8 CSV preview, per-row reasons, explicit valid-row confirmation, revision and ownership recheck | Oracle valid/invalid import and replay checks |
| 3.3.5 CSV export | Current score percentages, totals, letters, state; formula-safe text | Oracle CSV export and unit sanitization tests |
| 3.3.6 Teacher publication | Direct teacher publication; affected student notifications; explicit reopen hides drafts | Oracle publication, notification, and privacy checks |
| 3.3.7 Join controls amendment | Code controls retired; admin opens upcoming-term enlistment and prepares curriculum classes | Oracle university acceptance and browser EnlistMe checks |
| 3.3.8 Class analytics and Top Performers | Component means, grade distribution, completion, ranked class results | Calculation and browser checks |
| 3.4.1 Student dashboard | Published unit-weighted average, enrollment count, own rank, recent published items | Browser populated/empty pages; calculation tests |
| 3.4.2 Enrollment amendment | EnlistMe lists all current-term curriculum subjects by program/year/semester with checkboxes, including subjects without faculty. Checked subjects create/reuse section classes; later faculty assignment preserves enrollments/grades. | Oracle current-term acceptance and responsive browser checks |
| 3.4.3 Published grade detail | Own score/weight/contribution breakdown, total, letter, pass/at-risk indicator | Oracle own-grade checks and browser pages |
| 3.4.4 Average and rank | Unit-weighted percentages over published classes; competition rank within program/section | Weighted-average/tie unit tests and Oracle checks |
| 3.4.5 Personal analytics | Published subject performance and assessment-type means | Browser checks and published-query tests |
| 3.5 In-app notification feed | Owned feed, unread count, individual/all read actions; account/enrollment/publication events | Existing ownership tests; Oracle publication notification check |
| OTP amendment | Admin password followed by emailed single-use code; faculty/student password login; expiry/limits/resend cooldown | OTP unit tests, admin OTP and direct faculty/student login tests; Gmail setup pending |

## Explicit interpretation of incomplete SRS details

- Missing score rows contribute zero to the weighted grade but stay unrecorded in storage. A recorded zero remains distinguishable. Component mean charts use recorded scores and display recorded/missing counts; weighted class totals follow the SRS zero-contribution rule.
- Each component weight is a percentage within Lecture or Laboratory. Final component contribution = component weight × portion weight / 100. Both portions sum to 100%; components in each positive-weight portion sum to 100% before publication. Draft setup can be incomplete. The SRS section 8 leaves strict enforcement open; enforcing it at publication is the documented implementation choice.
- Preserve the existing application's letter bands because the PDF does not supply a complete conversion table: A ≥90, B+ ≥85, B ≥80, C+ ≥75, C ≥70, D ≥60, otherwise F. The pass/at-risk reference is 75%. This is a percentage/letter model, not an ISU numeric-equivalent or official GWA implementation.
- Calculate with Decimal and round displayed final percentages to two decimals using half-up. Rank at the same displayed precision. Equal averages receive ranks 1,1,3. The SRS does not specify tie/rounding conventions; these choices are documented for academic review.
- Overall Average = sum(published class percentage × subject units) / sum(included units). Draft classes do not enter the denominator. Different published course loads can affect comparisons and are disclosed. Section identity includes program to avoid mixing similarly named sections from different programs. Students see only their own rank and cohort size, not classmates' individual grades.
- CSV requires id_number, component_name, score. Scores use the component maximum shown in the gradebook; optional max_score must match. Blank, unknown, invalid, and repeated student/component rows are shown as skipped; the first valid occurrence is accepted. All confirmed valid rows commit atomically. A class revision change invalidates the preview. Template CSV and computed gradebook CSV are separate downloads.
- Publication locks the score grid and closes enrollment. Teacher explicitly reopens for correction, which hides draft results until republication. Existing publication snapshots remain preserved.
- At the owner's October 29 request, new self-registrations are active immediately and support email address or Student ID login. Manually inactive accounts remain blocked. A real Oracle browser check verifies registration with suggested/custom passwords and both login identifiers.

## UI acceptance

Brown institutional identity, Segoe UI, consistent 42px primary/secondary controls, concise table actions, component editing in modal dialogs, native accessible confirmation dialogs, aligned forms, responsive metric cards, keyboard-focusable scroll regions, mobile navigation drawer, and unsaved score-entry warnings.

Screens are checked at 1440, 1024, 768, 375, and 320px with populated data, and desktop/mobile empty states. The browser suite also verifies publication confirmation/cancellation, component-edit dialogs, CSV panel, mobile drawer, score locks, and rendered CSRF fields.

## Verification commands

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\venv\Scripts\python.exe tests\oracle_srs_check.py --database
.\venv\Scripts\python.exe tests\oracle_srs_smoke.py
.\venv\Scripts\python.exe tests\browser_srs.py
```

Verified on 27 October 2026: 85 automated unit/security/calculation tests, 18 rollback-only Oracle workflow checks, 25 read-only real-Oracle page checks, and 144 populated/empty browser page checks with no JavaScript errors. Browser interactions additionally verify publication confirmation/cancellation, CSV panel, component modal, and mobile navigation.

Evidence is saved under `audit/srs-alignment`. Oracle academic fixtures roll back. Test sessions use isolated SQLite files; no test-only login route is registered by the real application. Gmail messages are not sent by these tests. Prior rebuild test scripts describe historical proposals and are not the active acceptance checklist.

## Local operation and limitations

Gmail sender configuration is still required through `scripts/configure_gmail.py`, using a Google App Password entered locally. Account delivery addresses can be set with `scripts/set_account_email.py USERNAME`. No OTP bypass is included. Restart with `scripts/restart_local.ps1` after configuring mail.

The local app uses Waitress rather than the SRS's older development-server description. Oracle and existing records are retained. No destructive schema migration was needed for SRS alignment. The pre-change source snapshot excludes `.env` and other environment secrets.

SRS section 8 items—automated backups and fully self-service password resets—remain outside the active product scope. Existing operator recovery scripts/documentation are preserved. Grade notifications remain in-app; email is used for login verification. Formal end-user acceptance and a real production-load/recovery certification are not implied by the automated checks.
