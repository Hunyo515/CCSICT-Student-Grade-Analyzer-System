<<<<<<< HEAD
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
=======
# CCT Score — Student Grade Analyzer

Flask + Oracle DB implementation of the full Student Grade Analyzer system
from the Figma design: Admin, Faculty, and Student portals. Built to match
the design system 1:1: colors, typography (Lexend/Inter), card and table
styling, sidebar navigation, modals, pagination, and — for Admin
Analytics — the exact chart layout from the Figma frame.

## Scope of this build

✅ Shared foundation: role select screen, role-aware login/logout, session auth
✅ Admin portal, fully wired to Oracle:
  - Dashboard (live stat cards + recent activity feed)
  - Subjects Catalog (search, paginate, add, edit, delete)
  - Faculty Members (search, add, edit, delete, assign course load)
  - Students Registry (search, filter by year/section/program, paginate, add, edit, delete)
  - Settings (school-term management, admin profile/password)
  - Analytics: rebuilt pixel-for-pixel against the Figma
    "admin-analytics-enhanced" frame — 6 live panels: Enrollment by Program
    (horizontal bars), Enrollment by Year Level (vertical bars), Enrollment
    by Subject & Sex (grouped bars), Student Distribution by Sex (donut),
    Regular vs Irregular Students (donut + per-program breakdown table),
    and Class Average per Subject (vertical bars, computed from real
    weighted grades). All figures are queried live — nothing is hardcoded.

✅ Faculty portal, fully wired to Oracle:
  - Dashboard (welcome banner, stat cards, "My Subjects" cards with live status)
  - Grade Entry: weighted grade-components setup (add/remove, live allocation
    total), a spreadsheet-style gradebook grid with inline score editing,
    Save Draft / Publish Grades workflow (drives the dashboard's status dots)
  - CSV import: upload → validated preview (valid rows vs. skipped rows with
    reasons) → confirm before anything is written
  - CSV export: one-click download of the current gradebook with computed
    weighted totals and letter grades
  - Analytics: component averages and grade-distribution bars, computed live
    from actual scores
  - Top Performers: ranked honor roll with trophies for the top 3, using the
    same weighted-grade formula (verified against the design's sample bands:
    93.2%→A, 89.4%→B+, 87.8%→B+, 76.4%→C+, 63%→D)

✅ Student portal, fully wired to Oracle:
  - Self-service Registration (creates a student account directly, no admin
    step needed) and a "Register" link on the Student login screen
  - Dashboard: welcome banner, overall average / subjects enrolled / class
    rank stat cards, "My Subjects" cards, "Recent Assessments" feed of the
    latest graded items across all subjects
  - My Grades: per-subject breakdown with a component-level table (Quiz /
    Exam / Assignment / Project type badges), missed items flagged in red,
    a weighted-total + letter-grade banner with a PASSED / AT RISK badge
  - Profile: personal info card + enrollment status + list of enrolled
    subjects with units
  - Analytics: performance-by-subject and performance-by-assessment-type
    bar breakdowns, computed live from the student's own scores
  - My Rank: a rank card plus a class leaderboard (ranked by overall
    average among classmates sharing the same section), with the student's
    own row highlighted

  Grading model: a student's "overall average" is a **credit-weighted**
  mean of their weighted-total score across every subject where the teacher
  has clicked **Publish Grades** — each subject's percentage is weighted by
  its `units` (a 3-unit subject counts 3x more than a 1-unit subject), the
  same way a GPA works. Draft/in-progress subjects are excluded so students
  never see grades before the teacher finalizes them. The class leaderboard
  in My Rank uses the same number, computed per classmate (same
  `students.section`).

## 1. Set up Oracle

Point the app at your Oracle instance via environment variables (see
`.env.example`). Defaults match what you gave me:

```
ORACLE_HOST=localhost
ORACLE_PORT=1521
ORACLE_SERVICE=XEPDB1
ORACLE_USER=student
ORACLE_PASSWORD=1j2u3n4e
```

Create the schema and seed sample data (matches the sample rows in the
Figma mockups) by running, as the `student` schema owner:

```bash
sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/schema.sql
sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/seed.sql
```

> Already ran `schema.sql` before this update? Apply the migrations in order:
> ```bash
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/002_faculty_portal.sql
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/003_analytics_support.sql
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/004_class_join_codes.sql
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/005_grade_weighting.sql
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/006_notifications.sql
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/007_curriculum_guide.sql
> sqlplus student/1j2u3n4e@localhost:1521/XEPDB1 @db/migrations/008_flexible_grade_weighting.sql
> ```
> Migration 003 adds `students.sex` and `students.enrollment_type`
> (Regular/Irregular), which the new Admin Analytics screen depends on.

The seed data includes a faculty login (`e.cruz`) pre-assigned to teach
CS101 / BSCS 1A with grade components, enrolled students, sample scores,
and the section marked **PUBLISHED** — so a student in that section
(`j.delacruz`) has a fully populated Student portal (dashboard, grades,
rank, analytics) right after you reset its password.

> The password hashes in `seed.sql` are placeholders. After seeding, set a
> real password for the admin account:
> ```bash
> python scripts/reset_password.py admin password123
> ```
> Do this for any other seeded users you want to log in as, e.g.:
> ```bash
> python scripts/reset_password.py e.cruz password123
> python scripts/reset_password.py j.delacruz password123
> ```

## 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`oracledb` runs in **thin mode** by default — no Oracle Instant Client
installation needed.

## 3. Run

```bash
cp .env.example .env      # edit if your Oracle connection differs
python run.py
```

Visit http://localhost:5000 — you'll land on the Select Role screen.
Choose **Admin**, log in with `admin` / `password123` (or whatever you set),
and you're in the dashboard.

## Project layout

```
cct_score/
├── app/
│   ├── __init__.py        # app factory
│   ├── db.py               # Oracle connection pool + query helpers
│   ├── auth.py              # password hashing + @login_required
│   ├── grading.py            # weighted-total, letter-grade, component-type helpers
│   ├── routes/
│   │   ├── auth.py           # select role / login / logout / student registration
│   │   ├── admin.py          # all admin CRUD + analytics routes
│   │   ├── faculty.py        # dashboard, grade entry, CSV import/export, analytics, rankings
│   │   └── student.py        # dashboard, grades, profile, analytics, my rank
│   ├── templates/
│   │   ├── auth/              # select_role, login, registration, coming_soon
│   │   ├── admin/              # _layout (sidebar/topbar shell) + 6 pages
│   │   ├── faculty/            # _layout + 5 pages (dashboard, grade_entry, csv_preview, analytics, top_performers)
│   │   └── student/            # _layout + 5 pages (dashboard, grades, profile, analytics, my_rank)
│   └── static/css/            # main.css (shared design system), auth.css
├── db/
│   ├── schema.sql
│   ├── seed.sql
│   └── migrations/
│       ├── 002_faculty_portal.sql
│       └── 003_analytics_support.sql
├── scripts/reset_password.py
├── config.py
├── requirements.txt
└── run.py
```

## Design fidelity notes

- Every screen list below was built directly against the Figma node data
  (colors, spacing, font weights, component structure pulled from the file):
  Select Role, Login (all 3 roles), Admin Dashboard/Subjects/Teachers/Students,
  **Admin Analytics** (`admin-analytics-enhanced` — pixel-matched: horizontal
  bars, vertical bars, grouped bar chart, two donut charts with live
  conic-gradient percentages, and the irregular-students breakdown table),
  Faculty Dashboard/Grade Entry/Top Performers, Student Dashboard/Grades/
  Profile/My Rank, and Student Registration.
- Faculty Analytics and Student Analytics reuse the shared design system
  (cards, sidebar, bar-chart pattern) but weren't pixel-matched against a
  specific Figma analytics frame — flag it if you want either tightened
  the same way Admin Analytics was.
- Icons are hand-built inline SVGs in the Lucide style used throughout the
  design (not the exact source files, since those are Figma-exported
  assets) — visually equivalent, fully themeable via `currentColor`.

## Next steps

- Wire the "3" notification-bell badge on the Student topbar to real
  notification data (currently a static design element)
- Add password-reset / forgot-password flows (currently placeholder links)
- Pixel-match Faculty Analytics and Student Analytics against their own
  Figma frames the same way Admin Analytics was tightened
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
