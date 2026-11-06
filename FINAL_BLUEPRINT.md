> Superseded: the current implementation follows the supplied SRS plus email OTP. See SRS_COMPLIANCE.md and LOCAL_SETUP.md.

# CCSICT system — Final project blueprint

## Final execution scope — teacher-centered Grade Analyzer

This section is the latest controlling scope. It overrides broader features proposed below where they conflict. Implementation has not started under this blueprint.

### Purpose

Replace repetitive spreadsheet grade processing with a teacher-centered gradebook, consistent calculations, useful descriptive analytics, and transparent student results. Keep administrative functions limited to academic setup, account management, class assignment, and final-grade review. Deliver one complete, manageable release rather than an extensive student information system.

### Confirmed product decisions

- Campus-only access, existing brown theme, Segoe UI, and shared minimalist components.
- Eight-character minimum passwords plus mandatory email OTP for all roles. Codes expire, are single use, and have resend/attempt limits. Campus email delivery and verified-account recovery must work before launch.
- One curriculum per program, with curriculum subjects shown inside program folders.
- Admin creates each term's subject class and assigns exactly one responsible teacher.
- Teacher shares a class code; an active verified student confirms the class and joins immediately. No administrator approval queue. Cross-section joining preserves the student's main section. Prerequisites warn only.
- Teacher enters or imports scores, submits final grades, and administrator returns or publishes them.
- Teachers may create named grading categories for each class and allocate the final 100% among them.

### Release-one screens

| Role | Screens and responsibilities |
|---|---|
| Admin | Overview; Academics (program curricula and sections); People (students/teachers); Classes; Grade Review; Reports |
| Teacher | My Classes; class workspace with Gradebook, Analytics, Class details; Submissions |
| Student | My Subjects with Join class; released score details; Grade History |

Account controls use the profile menu. Restricted administrative Settings handles terms and operational configuration. Do not create separate curriculum-guide, teacher-assignment, enrollment-directory, or join-approval modules. Class details contains roster and code controls.

### Core journey

Admin creates class → teacher shares code → student joins → teacher creates categories and assessments → teacher enters/imports scores → teacher releases assessment results → teacher submits final grades → admin reviews and publishes → student sees final result.

Score-release default proposed for implementation review: Save draft keeps edits private; Save and release makes selected assessment results immediately visible to the relevant students. Final grades remain private until admin publication. This release choice has been recommended but not explicitly confirmed by the user. Avoid provisional overall standings in release one. Unreleased edits to previously released scores must not leak to students; retain the last released values until an explicit subsequent release.

### Weighted category grading

Each category has a unique name within the class and a positive percentage weight. Teacher can add categories such as Laboratory, Examinations, Quizzes, Activities, Attendance, or Projects. Show the allocated total while configuring. Require exactly 100% before a scheme becomes active for released calculations or final submission; a partially configured draft is allowed.

Each assessment belongs to exactly one category and has a title and positive maximum score. Each student score is between zero and that maximum. Blank means unrecorded, not zero. Attendance is entered as an assessment score if used; a daily attendance module is out of scope.

For a category result C on a 0–100 scale and category weight W, contribution = C × W / 100. Final percentage = sum of category contributions. Example: category results of 90, 80, 85, 95, and 100 with weights 30, 30, 20, 10, and 10 produce 87.5%.

The institution must choose one aggregation rule for release one:
- Equal assessment weighting: C = mean(100 × score / maximum) across included assessments.
- Points weighting: C = 100 × sum(scores) / sum(maximums).

These methods are not interchangeable. Scores 18/20, 40/50, and 30/30 yield 90% with equal assessment weighting and 88% with points weighting. Do not implement a hidden default or average raw scores with unequal maximums. No individual-assessment percentage weights or arbitrary formula editor in release one.

Use decimal arithmetic and the approved rounding policy. Report incomplete calculations explicitly; do not silently renormalize category weights when a category has no scores. Missing/exempt/special outcomes and final submission rules require approved policy. Use the ISU equivalence table referenced below, with academic confirmation of fractional conversion boundaries and any amendments. GWA remains out of scope until its inclusion rules are approved.

Categories containing scores cannot be deleted through normal CRUD; preserve data and require an explicit corrective workflow. Weight changes preview their impact before confirmation and record history. Submission freezes the scheme, roster, scores, and calculated outcomes. Submitted/published schemes cannot be edited directly. Final corrections create a new reviewed revision without overwriting the prior publication.

### Excel import/export

Support one downloadable .xlsx template per class and assessment configuration. Initial template: a protected-by-convention roster with Student ID, Student Name, and assessment columns; a metadata sheet identifies class, template revision, assessment IDs, category, and maximum score. Server validation—not worksheet protection—enforces integrity. Teachers download a fresh template after changing assessments.

Flow: download → fill scores → upload → validate → preview new/changed/invalid entries → confirm. Match exclusively by student ID against the class roster. Reject unknown/duplicate students, duplicate assessment columns, stale/wrong-class templates, out-of-range values, and formula cells in score inputs; request numeric values. Do not execute spreadsheet macros or formulas. An import never creates students, enrollments, categories, or assessments implicitly.

Blank import cells leave existing scores unchanged; clearing a score is an explicit gradebook action. Display this rule in the template and preview. Confirm all valid changes atomically after resolving blocking errors, with a fresh revision check and audit event. Repeated uploads cannot create duplicate score rows. Imports save drafts and never auto-release or publish results. Export scores and calculation breakdowns under the same role permissions as the screen. Sanitize text export cells against spreadsheet formula interpretation.

Flexible arbitrary spreadsheet mapping, multiple workbook formats, macros, and spreadsheet formula compatibility are deferred.

### Data-science and analytics contribution

Release one uses descriptive analytics and transparent calculation, not predictive models. The technical contribution includes input quality checks, normalization, missing-data handling, reproducible aggregation, and role-appropriate visual communication.

Teacher Analytics contains three focused views:
1. Assessment distribution: normalized percentage histogram with sample count, missing count, mean, and median; for tiny groups use a readable score table instead of suggesting a meaningful distribution.
2. Assessment comparison: mean normalized percentage by assessment, grouped or filtered by category, with recorded counts. Do not claim assessment difficulty or learning gains solely from score differences.
3. Completion: recorded versus missing scores by assessment, linked to the gradebook. A recorded zero counts as recorded.

Teacher category/final breakdowns remain available as a calculation table. Student views show their own released score/max/percentage and published final/category contributions. Admin sees submission progress and scoped enrollment/published outcome reports. Student trends are deferred until approved comparable metrics exist. Do not expose classmates' grades or class rankings to students.

Every view identifies class/term, data state (working, released, or published), denominator, and exclusions. Missing is never included as zero without an explicit recorded zero. No item analysis without question-level data, automatic student risk prediction, teacher ranking, or causal claims.

### Minimal technical design

Retain a modular Flask/Jinja application and Oracle. Central services handle enrollment, scoring, calculation, import, submission/publication, and authentication. All screens and exports use the same calculation rules. Keep shared brown CSS components and limited JavaScript; no SPA migration is needed merely for visual modernization.

Data entities: users, email OTP challenges, students, teachers, programs, curriculum subjects/prerequisites, terms, sections/membership, classes/codes, enrollments, categories, assessments, scores, released-score revisions, frozen submissions/results, review/publication decisions, corrections, and audit history. Use stable identifiers, uniqueness constraints, transactions, and revision checks. Include import provenance in audit records without building a separate import-management product.

Validate all fields in the browser and server, with database enforcement for critical relationships. Verify role and record ownership for every endpoint/export. Keep passwords, OTPs, and SMTP secrets out of logs. Restrict sensitive record deletion; preserve historical academic data. Backup database, required files, configuration, and key-recovery material through appropriate protected processes and demonstrate restoration before launch.

### Design deliverables before feature development

One brown style sheet and reusable component set; a compact screen map; connected prototypes for login/OTP, class creation, code join, gradebook/category setup, import preview, analytics, grade review, and student results. Show realistic populated, empty, invalid, and unavailable states. Review keyboard score entry, copy/paste, safe save behavior, mobile results, and accessible tables. No redundant hero text or decorative charts.

### Implementation order and acceptance

1. Confirm grading aggregation, rounding, missing outcomes, score release, and campus SMTP details; inventory existing data and create reference calculation fixtures.
2. Build shared brown UI, verified accounts, email OTP, and essential academic setup.
3. Build class creation, teacher assignment, code controls, and immediate student enrollment.
4. Build categories, assessments, grade entry, and the approved calculation service.
5. Build the fixed Excel template, preview/validation, transactional import, and release of student scores.
6. Build immutable final submission, administrator return/publication, and reviewed corrections.
7. Build the three teacher analytics views and essential student/admin reporting.
8. Rehearse migration and recovery; run role/security, concurrent-write, accessibility, realistic-load, and end-to-end acceptance tests; pilot and train before cutover.

Acceptance evidence: manually verified grading examples including the 90% versus 88% distinction; Excel preview matches committed changes and leaves no partial writes on error; student release privacy; automatic joining with duplicate prevention; frozen submission integrity; OTP expiry/reuse/attempt-limit checks; chart-to-record reconciliation; historical migration reconciliation; and demonstrated backup restoration. Evaluate usability with representative teachers completing grade entry, import, correction, and submission tasks, recording completion time, errors, and feedback. Compare against a defined equivalent spreadsheet task if making efficiency claims; do not promise measured improvement before evaluation.

### Decisions still required before their dependent features

1. Professor's category aggregation: equal assessment percentages or total points.
2. Approved category weighting constraints, ISU fractional rounding, and handling of missing/exempt/INC records.
3. Confirm Save draft / Save and release for student score visibility.
4. Campus SMTP credentials/sender, identity verification, hosting/support ownership, and backup commitments.

The remaining sections are supporting detail only where consistent with this final execution scope.

Decision baseline: 27 October 2026. Status: planning, before implementation.
This is the controlling product specification. It supersedes conflicting choices in REBUILD_PLAN.md, particularly green branding, enrollment approval requests, and authentication proposals. REBUILD_PLAN.md supplies supporting migration and engineering detail where consistent with this blueprint.

## 1. Product and scope

A minimalist campus-only departmental web application for administrators, teachers, and students. It manages program curricula, class assignments, immediate code-based enrollment, teacher grade submission, administrator publication, and descriptive academic reports.

Keep existing academic data. Use Flask/Jinja, Oracle, reusable CSS, and focused JavaScript unless implementation discovery identifies a documented reason to change. Avoid unnecessary frameworks, microservices, and duplicate modules. Deployment uses a managed campus server and internal HTTPS. Outbound email delivery is required even though application access is campus-only.

Exclude billing, admissions, attendance, timetable optimization, learning management, predictive student scoring, official transcript issuance, and a native mobile application from release one. Departmental publication does not imply registrar certification.

## 2. Confirmed rules

- Retain the old brown identity and use Segoe UI globally.
- Minimum password length is eight characters, plus mandatory email OTP at login for all three roles.
- One curriculum per program; preserve historical subject metadata and results.
- Admin chooses a curriculum subject, term, class section, and exactly one responsible teacher.
- A teacher's program affiliation is descriptive; teaching responsibility belongs to specific classes.
- Students enter a teacher-shared class code and join immediately after confirming the class details. No enrollment approval queue.
- Main-section membership and class enrollment are separate. Cross-section joining does not change the student's main section.
- Prerequisites warn only; missing or unverifiable prerequisite evidence does not block joining.
- Admin bulk enrollment remains an optional shortcut in the same class roster interface.
- Teachers submit grades. Only authorized academic administrators publish them.
- All roles use the same terminology, components, colors, and validation patterns.

## 3. Navigation

| Role | Main navigation | Contents |
|---|---|---|
| Admin | Overview | Pending grade reviews, setup issues, limited summaries |
| Admin | Academics | Program folders, curriculum subjects, sections by term |
| Admin | People | Students and Teachers tabs; records and account management |
| Admin | Classes | Offerings, responsible teacher, class roster and history |
| Admin | Grade Review | Submitted revisions, return feedback, publication |
| Admin | Reports | Detailed enrollment, workload, and academic analysis |
| Teacher | My Classes | Class roster, code controls, assessment setup, gradebook |
| Teacher | Submissions | Submitted, returned, and published class revisions |
| Student | My Subjects | Joined classes, Join class action, published subject details |
| Student | Grade History | Published results across terms and approved summaries |

Put Account and Logout in the profile menu. Restrict administrative Settings to authorized users at the bottom of navigation. Teacher and student landing pages include relevant summaries; do not add duplicate Dashboard and Analytics destinations. Notifications use one shared header control.

## 4. End-to-end operation

### Academic preparation
Admin creates the term, maintains program curricula, creates sections, and verifies people/account records. Programs display as folders under Academics; opening a folder shows subjects by year and semester. Subjects support create, read, edit, archive, restore, and deletion only when unused. Preserve BSDSA source material and reconcile source ambiguities explicitly.

### Class setup
Admin opens Classes → Create class → selects program curriculum subject → term → section → responsible teacher. Prevent duplicate offerings for the same curriculum subject, section, and term regardless of teacher. One teacher may handle several classes, including approved cross-program assignments. Teacher replacement is audited and preserves history.

### Joining by code
The system generates a random unique class code. The assigned teacher can copy it, close/open joining, and regenerate it. Old codes stop working after regeneration; existing enrollments remain.

Student selects Join class, enters the code, sees subject/teacher/section/term and any prerequisite warnings, then confirms Join. The system immediately creates enrollment and displays success; the teacher's next roster load includes the student. No admin approval or pending membership state.

Require an active verified account, active class/term, open joining, and an editable roster. Block duplicate enrollment in the same curriculum subject and term, invalid/expired codes, and submitted/published rosters. Do not impose hidden same-section or prerequisite restrictions. Apply reasonable attempt limits to code lookup. Returning a submission does not automatically reopen joining; the teacher explicitly reopens it if appropriate.

Use the same enrollment service for student joining and admin bulk enrollment. Repeated clicks and concurrent requests create only one membership. Leaving, transferring, or removing students with academic records must use a controlled administrative action that preserves grades and history. Do not expose destructive self-removal after grade recording.

### Grading
Teacher opens the class, configures an approved assessment scheme, enters scores, validates, and submits. Use Draft → Submitted → Published; an administrator may Return a submission for correction and resubmission.

Submission freezes the roster, subject units, grading policy, weights, scores, and calculated outcomes. Admin reviews that exact revision and either returns it with a reason or publishes. No silent admin score editing. Students see only their own published data. Grade corrections create a new reviewed revision and retain the prior publication until replacement is approved. Audit teacher, reviewer, timestamps, reasons, and revision references.

## 5. Login, OTP, and accounts

User-entered password minimum: eight characters, per the explicit requirement. Allow long passphrases and password managers; reject common/compromised values using an appropriate locally available list. Do not silently truncate passwords or require arbitrary symbol combinations. Store passwords with an appropriate salted password hash. Show/Hide password is available and hidden by default.

Login: username/password → six-digit email OTP → authenticated role home. Password verification alone grants no academic access. Describe this accurately as email two-step verification; do not claim phishing-resistant MFA or standards assurance that it does not provide.

Proposed OTP defaults: expires after five minutes, at most five failed attempts per challenge, resend cooldown of 60 seconds, and single use. Resend invalidates the prior code. Add account-level and network-aware limits across new challenges so resend cannot reset the guessing budget. Campus users may share an IP, so avoid a blanket IP lockout that disables the entire department.

Use cryptographically generated codes, securely keyed code verification storage, short-lived challenges bound to the login session/account/purpose, and no plaintext OTP logs. Store mail credentials outside source. Mask the destination email on screen. Allow code paste. Display delivery failure and retry options without bypassing verification. Keep server clocks synchronized.

Recommended account provisioning: admin creates/imports verified identities and sends activation to the registered address. Users establish a password and verify the address before first access. A student cannot create an active identity by merely claiming a student ID. Email changes require verified authorization and verification of the new address. Lost-email recovery requires documented identity checking; temporary recovery cannot become a permanent OTP bypass. Invalidate relevant sessions after password reset or account recovery.

Integrate an approved campus SMTP relay or transactional email service. Test actual campus delivery, delays, expiry, sender configuration, and delivery failure. Campus IT must supply the sending account and connectivity. No SMS or authenticator-app workflow is included in this release.

## 6. Grading policy boundary

Use the ISU grade-equivalence table already sourced in REBUILD_PLAN.md. Before implementing conversions, the academic owner must confirm current applicability, assessment weights, rounding of fractional percentages, special outcomes, and average inclusion rules. Never guess how a value such as 94.5 converts.

Use one decimal-based calculation service across grade entry, submission, reports, and exports. Zero differs from missing; INC is a special outcome rather than numeric zero. Policy revisions do not recalculate prior publications. Label percentage averages accurately; show GWA only after its institutional rules are confirmed. Test approved worked examples and every grade boundary.

## 7. Global GUI

Preserve existing theme tokens: brown primary #8A6D3B, darker hover #785D31, warm canvas #F7F5F0, dark text #2E2E2E, muted text #6E6E6E, and white surfaces. Validate actual contrast for text, focus, buttons, and charts; use a darker brown variant where necessary. Use neutral form fields instead of unrelated blue decoration. Semantic error/warning/success colors remain available with text labels.

Segoe UI throughout; approximately 16px body text, clear heading hierarchy, consistent 4/8px spacing, modest corners, restrained shadows. One icon family with labels. No external font dependency, decorative gradients, or oversized introductory banners.

Desktop uses a stable sidebar and compact header. Mobile uses a collapsible navigation drawer, stacked forms, and scrollable data tables. Gradebooks prioritize readable columns and stable student row identity over squeezing every column onto a phone.

Shared components: app shell, header, term selector, buttons, fields/errors, filters, tabs, paginated tables, badges, confirmations, notifications, empty states, and chart/table pairs. Every screen covers empty, loading, saved, validation error, forbidden, stale revision, and service failure where relevant. Do not show backend implementation details in normal user flows.

One main action per screen/task. Dedicated pages for complex edits; dialogs for brief confirmation. Preserve filters and safe form input on errors. Avoid repeating the same figure in a metric card, chart, and table unless the table is the accessible alternative. No repeated curriculum module, teacher-assignment module, join-request queue, or separate enrollment directory.

## 8. Input and data validation

Validate in the browser for feedback, on the server for enforcement, and in database constraints for critical invariants. Centralize rules so bulk imports and ordinary forms behave consistently. Allow real names with spaces, accents, apostrophes, and hyphens. Use approved identifier formats, length limits, supported enum values, relational checks, and uniqueness rules.

Check score bounds, positive maximums, complete weight totals, valid curriculum references, active teachers, term state, duplicate enrollment, and permitted workflow transitions. Imports require bounded file sizes/formats, a preview, row-level errors, and atomic confirmation. All SQL is parameterized; rendered input is escaped. Validation must not be mistaken for authorization.

## 9. Meaningful visualizations

Admin overview: submissions awaiting review, enrollment by program/year, and class-size or submission-state summaries. Teacher landing: class completion progress and assessment/result distributions with links to missing entries. Student landing/history: published subject results and term trends, plus curriculum completion where recognition data is verified.

Aim for two to four useful visualizations per relevant screen, not a mandatory chart quota. Use consistent scales, labels, term filters, counts, and missing-data coverage. Separate operational completion from academic achievement. Do not rank teacher quality using class grades or imply causal improvement from unlike cohorts. Students never see classmates' grades. Reports and exports retain the same access scope as screens.

## 10. Records and engineering

Core data: accounts, people, programs, curriculum subjects, structured prerequisites, terms, sections, student-term membership, classes, teacher-assignment history, enrollments/events, assessment configuration, scores, immutable submissions/results, review/publication/correction records, notifications, OTP challenges, and audit events.

Use stable IDs and restricted deletion for referenced academic data. Separate main section from class section. Use revisions and database transactions for enrollment, score edits, submission, and publication. Verify permissions on every action and record, including exports. Preserve historical subject name/code/units in published snapshots. Failed database operations must roll back and show a clear retryable error, not fake empty data or partial success.

Keep application/domain/database layers separate enough to test without overengineering. Track schema migrations. Add indexes based on actual query needs. Keep deployment secrets outside the repository and essential assets local to support campus access without public asset services.

## 11. Backup, recovery, and operations

Automate Oracle backups and required document/configuration backups; retain encrypted copies on separate protected storage. Preserve encryption keys through a separately controlled recovery process. Define retention with the institution. A successful file copy is not evidence that Oracle data can be restored consistently.

Recovery targets from the earlier plan remain proposals: up to one hour data loss and four hours restoration, pending campus IT capability. Meet those through an appropriate database recovery strategy; nightly backups alone do not meet the one-hour loss target.

Test restoration on an isolated environment before launch and on a documented recurring schedule. Include app restart, database restore, mail configuration recovery, session/OTP invalidation, and reconciliation. Restore actions are technical maintenance operations restricted to designated staff. Admin Settings may display last backup status; ordinary admins should not have an unrestricted restore button.

Monitor application readiness, database availability, backup failures, email delivery failures, errors, and storage. Use support references and logs without exposing passwords, OTPs, or unnecessary student data. Assign campus IT primary and backup owners plus a grade-deadline escalation procedure.

## 12. Delivery and migration

1. Confirm grading examples, campus mail access, hosting ownership, and expected user/data volumes; inventory existing records.
2. Produce a brown design sheet, navigation map, and connected prototype: login/OTP, admin class setup, student code join, teacher gradebook, admin review, student results.
3. Build shared GUI, authentication, permission checks, and academic data foundations.
4. Build class creation, code controls, immediate student joining, and optional admin bulk enrollment.
5. Build the approved calculation engine, immutable submission, review/publication, and corrections.
6. Build reports, validation coverage, audit, email failure handling, backup and recovery operations.
7. Rehearse data migration, reconcile historical records, pilot representative users, and train staff.
8. Freeze old writes for cutover, back up, migrate/reconcile, verify, and launch under named support ownership.

Never infer missing historical program/section data. Reconcile legacy subjects and the BSDSA duplicate-code/source discrepancies with authorized staff. Preserve legacy published grades and provenance without fabricating admin approval or recalculating them under new rules. Maintain a rollback plan that accounts for any new-system writes. Do not delete or replace the existing system as part of planning.

## 13. Release acceptance

- Eight-character password policy and email OTP work end to end; expired, reused, wrong-session, and brute-forced codes are rejected.
- Resend/recovery/email-change paths do not bypass authentication. Delivery failure grants no session.
- Valid code joining immediately creates exactly one enrollment, including cross-section students, with no approval step.
- Warning-only prerequisites remain warnings. Closed enrollment and submitted/published rosters reject joining.
- Teachers cannot publish through either the UI or direct requests; students cannot access drafts or another student's data.
- Review publishes exactly the submitted revision; concurrent edits and duplicate clicks do not alter it.
- Calculations match institution-approved examples, including boundaries and special outcomes.
- All screens use the brown component system; keyboard, mobile, focus, contrast, and error recovery checks pass.
- Migration balances academic record counts and values; historical grades remain traceable.
- Campus mail delivery, realistic concurrent load, backup restoration, service restart, and incident ownership are demonstrated.

Remaining institution-owned decisions: precise grading calculation rules; authorized academic reviewers and correction evidence; actual student/class/concurrency volumes; SMTP/sender configuration; server ownership; backup retention/recovery commitments; and account identity-verification procedure. These are readiness gates, not reasons to add redundant screens.
