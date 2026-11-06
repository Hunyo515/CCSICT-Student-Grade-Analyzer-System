# Local setup — SRS Student Grade Analyzer

Use a terminal in `C:\CCSICT Grade Analyzer\system`.

## 1. Configure Gmail email OTP

Enable Google 2-Step Verification and create a Google App Password: https://support.google.com/mail/answer/185833 . Then run:

```powershell
.\venv\Scripts\python.exe scripts\configure_gmail.py
```

Enter the Gmail sender address and App Password at the local prompts. Password entry is hidden. Never send the App Password through chat or commit `.env`. Gmail uses smtp.gmail.com:587 with STARTTLS. Internet access is required for email delivery, while the app remains local.

Administrator login codes go to the administrator account's registered email, which may differ from the sender. To bootstrap an existing account with an old/unreachable address, run:

```powershell
.\venv\Scripts\python.exe scripts\set_account_email.py USERNAME
```

Enter the verified address locally. Do not change someone else's address without verifying their identity. No real Gmail message was sent during automated testing.

## 2. Start or restart

```powershell
powershell -ExecutionPolicy Bypass -File scripts\restart_local.ps1
```

Open http://127.0.0.1:5000/. Administrators sign in with the role and password, then enter the six-digit email code. Faculty and students use their username and password. Admin-created student temporary passwords must be changed at first login. Faculty use their registered password and go directly to the dashboard. Codes expire after five minutes, are single use, and have attempt/resend limits. There is no OTP bypass. For a first foreground launch, use `.\venv\Scripts\python.exe run.py`.

## 3. Academic setup

Admin: Subjects → create/edit/search subjects. Faculty and Students → manage accounts. Settings → create/activate a term. Classes → assign a subject, faculty member, and section. For upcoming enrollment, create the next term in Settings, open its enlistment, and prepare its curriculum-matched Classes.

Students may register and sign in immediately using their email address or Student ID and password. Registration offers an optional randomly generated password. Faculty login and password recovery use the institutional email address. Faculty ID remains a record identifier. Admin-assisted password reset requests create an in-app notification.

## 4. Teacher workflow

Dashboard → Open gradebook → Grade weighting. Save the Lecture/Laboratory split. Add components with a within-portion percentage and maximum score. The portions total 100%; components within each positive-weight portion total 100% before publication. Draft allocations may be incomplete.

Existing components from prior schemes remain available for classification into Lecture/Laboratory. Existing scores and publication history are preserved. Unused previous categories remain historical metadata.

Students open EnlistMe, check the subjects they want from the current-term list matching their registered program, current year level, section, and semester, then click Enroll selected subjects. Only checked subjects are enrolled. Repeat submissions do not duplicate or remove enrollments. Subjects can be enrolled before a class or professor is assigned. Apply `venv/Scripts/python.exe scripts/migrate_unassigned_classes.py --apply` on existing installations first. Admin > Classes > Assign faculty attaches a professor later while preserving the enrollment. Enrollment code controls and admin roster enrollment are retired. See WORKFLOW.md.

Grade entry → enter scores and Save grades. Blank remains unrecorded and contributes zero to the weighted calculation, as specified by the SRS. Draft grades are private. Publish grades → confirm → enrolled students receive an in-app notification and can see results. Reopen for editing hides student results until republication.

## 5. CSV

Import CSV → Download CSV template. Required columns are id_number, component_name, score; optional max_score must match the gradebook component. Fill raw numeric scores using that component's displayed maximum. Upload, review valid/invalid rows, then confirm importing valid rows. Invalid rows are skipped with reasons; blanks do not clear an existing score. The entire valid batch commits atomically and stale previews are rejected.

Export CSV downloads normalized component percentages, calculated totals, letter grades, and class state. Dangerous spreadsheet text is escaped. These are UTF-8 CSV files, not .xlsx workbooks.

## 6. Analytics and rank

Faculty Analytics shows component averages, weighted grade distribution, and score-entry completion. Top Performers ranks only that teacher's selected class. Students see published subject/type analytics and their own rank, based on a unit-weighted average of published classes. Missing values contribute zero to weighted totals; component-average charts disclose recorded/missing counts. No percentage average is labeled GWA.

See SRS_COMPLIANCE.md for letter boundaries, rounding, tie handling, and scope notes. Tests use the SRS calculation service across screens and exports.

## Existing database and recovery

The prior additive schema migration remains required if the grade_versions and maximum-score fields are missing; never run db/schema.sql over existing tables. The university amendment adds first/middle/last names, must_change_password, enlistment_open, and one-open-enlistment uniqueness through scripts/migrate_rebuild.py --apply. The migration was applied locally after a logical snapshot; use the migration for another existing installation. Never recreate existing tables. Existing operator recovery documentation remains in BACKUP_RECOVERY.md, outside the current SRS feature scope. A real restore rehearsal and Gmail delivery verification are not implied by automated tests.

Faculty account deletion with academic history requires the additive migration `venv/Scripts/python.exe scripts/migrate_faculty_deletion.py --apply`. It saves a local backup, retains publication author names, and allows author account references to become null. The application detaches classes before deleting the faculty login.

Faculty grading revision: apply `venv/Scripts/python.exe scripts/migrate_flexible_grading.py --apply` on existing installations. It snapshots class/category/activity/score rows, enables flexible grading on unpublished classes, and preserves published models. My Classes is semester-specific. Open a gradebook and use Grading Settings to add components and activities; both levels must sum to 100% before publication. The workbook attachment supplies layout reference, while numerical grade bands follow the ISU Student Manual (https://isu.edu.ph/wp-content/uploads/2025/10/Student-Manual.pdf, grading system).
