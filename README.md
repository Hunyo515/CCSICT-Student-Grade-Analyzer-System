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
