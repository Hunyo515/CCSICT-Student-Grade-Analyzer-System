> Superseded: the current implementation follows the supplied SRS plus email OTP. See SRS_COMPLIANCE.md and LOCAL_SETUP.md.

# CCSICT Academic Records and Grade Analytics — Rebuild Plan

Superseded product decisions: use FINAL_BLUEPRINT.md (27 October 2026) as the controlling specification. In particular, retain brown branding, use eight-character minimum passwords with email OTP, immediate student joining by class code without approval, and the simplified navigation. The technical detail below remains background only where consistent with that blueprint.

Planning baseline: 26 October 2026. This document specifies a proposed replacement, not completed functionality or a production certification. Existing records must survive the transition.

## 1. Purpose and boundaries

Build a campus-only CCSICT departmental system for curriculum management, sections, classes, enrollment, assessment, administrator-reviewed grade publication, and descriptive analytics. Support administrators, teachers, and students with a shared visual language and role-specific tasks.

The departmental application must not claim to issue official transcripts, replace the registrar, or authorize institutional grade corrections unless the university expressly grants that responsibility. Billing, admissions, room scheduling, attendance tracking, learning materials, predictive risk scoring, and a mobile app are outside the first release.

Confirmed decisions:
- One curriculum per program for now; retain historical snapshots without adding a curriculum-version management interface.
- One responsible teacher per class. Reassignment preserves who previously taught and submitted records.
- Students have a term-specific main section and may take classes in other sections.
- Bulk enrollment by section with individual exceptions.
- Prerequisites WARN ONLY. They never block enrollment or require an override approval. Record which warnings were shown and acknowledged.
- Teachers submit grades; authorized administrators review and publish.
- Use ISU grading policy and Segoe UI throughout.
- Campus network access only; no public registration or public exposure is required by this plan.

## 2. Evidence and current gaps

Reviewed the current Oracle schema, workflow guide, authentication controls, and faculty publication routes. The existing system provides useful foundations, but the new requirements need structural changes:
- Faculty publication must become submission; publication moves to the administrator permission boundary.
- Section strings become section records and historical term memberships.
- Mutable grade rows need immutable submission and publication revisions.
- Current free-text prerequisite descriptions cannot reliably determine satisfaction; introduce structured relationships while retaining source notes.
- Cascading deletion of academic records must be replaced with restricted deletion and archive/withdrawal operations.
- Existing subject codes are not globally unique; preserve stable IDs and resolve the BSDSA source ambiguities explicitly.
- Existing SQLite security state is single-host. Keep that constraint explicit or consolidate it into Oracle before scaling to multiple hosts.

Do not carry forward the current database schema merely because existing screens depend on it. Migrate it deliberately with ID mappings and reconciliation.

## 3. Academic workflows

### Term setup
Create a term, verify programs and subjects, create sections, assign student main-section memberships, create classes, assign one teacher, preview enrollment, and open the term. One default working term is distinct from permissions to edit historical terms. Proposed term states: Planned, Open, Closed. Closure prevents ordinary edits; controlled correction workflows remain available.

### Curriculum
Subjects opens program folders directly. A folder shows subjects grouped by year and semester with code, title, units, lecture/laboratory units, and prerequisites. Support create, edit, archive, restore, and delete only unused records. Use structured prerequisites for courses and explicit notes for standing requirements; unresolved requirements show Unknown, not Satisfied. No recursive prerequisite enforcement is needed because the user selected warning-only behavior.

### Sections and enrollment
A student has at most one main section per term, but several class enrollments. Moving the main section does not automatically transfer class enrollment. Preview affected classes and let the admin choose changes.

Bulk preview shows eligible students, already enrolled students, subject conflicts, prerequisite warnings, and individual exceptions. Warning-only prerequisites do not remove students from the eligible list. Cross-program/year/section individual enrollment records a reason separately from prerequisite warnings. Confirm against a fresh revision; reject stale previews rather than silently changing the batch. Commit the batch atomically. A repeated confirmation must not create duplicates.

Prevent duplicate enrollment in the same curriculum subject and term across sections. Explicitly model approved subject equivalences before applying this rule across different program curricula. Preserve withdrawals and transfers as events rather than deleting academic history. Enrollment with grade records requires a controlled withdrawal/transfer process, never silent score deletion. Student class joining, if retained, creates a request for administrative enrollment rather than bypassing this workflow.

### Grade entry, review, and publication
Grade states: Draft → Submitted → Published; Submitted → Returned → Submitted. Publication applies to a specific immutable submission revision.

1. Teacher selects an assigned class and approved grading configuration.
2. Teacher records scores with explicit saves, validation, and an unsaved-change warning. Zero and missing are different values.
3. Submission checks roster revision, assessment configuration, completeness or permitted special outcomes, and calculation validity.
4. Submission freezes the roster, weights, raw scores, policy revision, calculated percentages, final equivalents, and relevant subject metadata for review.
5. Admin reviews the exact revision, returns it with a reason, or publishes it. Admin does not silently edit teacher scores.
6. Publication atomically records the decision and approved results. Students see only their own published results.
7. Teacher receives returned feedback or publication status through in-app notifications.

After publication, corrections create a new revision with a reason and any required institutional authorization reference. The prior published revision remains visible to authorized auditors. Do not withdraw a valid published record merely because a correction draft exists. Replacement publication supersedes it atomically. A technical administrator is not automatically an academic approving authority. Prohibit self-approval when a person holds both teaching and approving responsibilities.

## 4. Grading policy

Primary reference: [ISU Student Manual, section 18, printed page 24](https://isu.edu.ph/wp-content/uploads/2025/10/Student-Manual.pdf#page=25), accessed 26 October 2026. Campus academic authority must confirm applicability and any subsequent amendments.

| Published percentage band | Grade equivalent |
|---|---|
| 98–100 | 1.00 |
| 95–97 | 1.25 |
| 92–94 | 1.50 |
| 89–91 | 1.75 |
| 86–88 | 2.00 |
| 83–85 | 2.25 |
| 80–82 | 2.50 |
| 77–79 | 2.75 |
| 75–76 | 3.00 |
| 74 and below | 5.00 |

The manual also identifies INC as a distinct outcome. It must not be stored as numeric zero or automatically inferred from any missing score. Store special outcomes separately from numerical grades. Completion and correction workflows require institutional handling; do not implement silent scheduled grade changes from the manual alone.

Unresolved before grading implementation: percentage rounding at boundaries, assessment aggregation method, prelim/midterm/final contributions, lecture/laboratory weighting, permitted special outcomes, completion dates, and inclusion of NSTP/PE/repeats/transferred credits in averages. The published integer bands do not answer how 94.5 should be treated. Do not invent that rule.

Use decimal arithmetic, retain intermediate precision, and round only at the approved stage. One calculation service powers entry, review, exports, and analytics. Version grading configuration independently of the single-curriculum decision. Policy changes must not recalculate historical publications. Institution-approved worked examples become regression tests. GWA is unavailable until its inclusion rules are approved; a percentage average must never be labeled GWA.

## 5. Navigation and screen requirements

Admin: Overview; Academics; Students; Teachers; Sections; Classes; Grade Review; Reports; Settings.
Teacher: Overview; My Classes; Submissions; Reports; Account.
Student: Overview; My Subjects; Published Grades; Academic History; Account.

| Screen | Required functionality |
|---|---|
| Admin overview | Pending submissions, setup gaps, enrollment summaries, links to resolve issues |
| Academics | Program folders, curriculum tables, source document, subject CRUD and archival |
| Student directory/detail | Search and filters, profile, term membership, enrollment history, account state |
| Teacher directory/detail | Profile, class assignments, workload, account state |
| Sections | Term-specific sections, main-section members, membership change preview |
| Class directory/detail | Subject, term, one teacher, section; tabs for overview, roster, grades, history |
| Enrollment | Bulk preview, individual exception, warnings, conflicts, transfer/withdrawal history |
| Grade review | Queue, frozen submission detail, validation summary, return reason, publish confirmation |
| Teacher gradebook | Roster, assessment setup, score entry, validation, saved state, submit action |
| Student grades/history | Published results only, units, publication date, approved corrections and special outcomes |
| Reports | Scoped filters, denominators, accessible charts/tables, authorized exports |
| Settings | Terms, account permissions, grading configuration, audit search; technical operations restricted |

Every screen needs loading, empty, success, validation, forbidden, stale-edit, and service-unavailable behavior where applicable. Failed writes preserve safe user input without claiming success. A database outage returns a retryable service error with a support reference; it must never produce fabricated empty dashboards.

## 6. Global visual specification

Use a light interface, Segoe UI, neutral canvas, white surfaces, dark readable text, and one restrained institutional accent. Initial palette proposal: canvas #F6F7F9, text #17212B, primary #174B3B; validate all actual combinations during implementation. No external font downloads or decorative gradients.

Desktop: persistent approximately 240px sidebar; compact header with title, explicit term context, and account controls. Main content has predictable spacing and a readable width; large grade tables may use the available viewport. Mobile: collapsible navigation, stacked forms, readable detail screens, and horizontally scrollable grade tables with clear row identity.

Use a 4/8px spacing scale, 16px body text, 14px supporting text, approximately 1.5 body line height, modest corner radii, and restrained borders. Controls need generous touch targets. Confirm actual contrast, keyboard operation, focus visibility, and zoom behavior rather than relying on color choices alone.

Shared components: app shell, page header, term selector, action button, field/error pair, searchable select, filter bar, paginated table, status badge, empty state, confirmation dialog, notification, timeline, and chart/table pair. Prefer dedicated pages for complex editing. Use dialogs for short actions. Keep one dominant primary action per task. Destructive actions identify the record and consequences.

Prototype first: admin overview, class roster, teacher gradebook, administrator review, and student published results. Review these as one end-to-end journey before applying the design to every page.

## 7. Analytics

Admin: enrollment by program/year, class size, submission backlog, published outcome distribution, and teaching load defined as classes and assigned units unless a different workload formula is approved.
Teacher: completion by class, score distributions, assessment summaries, and a factual missing-record list.
Student: published grade history, subject-level results, and progress through the curriculum with recognized completions clearly distinguished from unverified credits.

Use bar charts for comparisons, stacked bars for workflow states, and term trends only with comparable definitions. Show counts, coverage, active filters, and update time. Missing is not zero. Use published outcomes for institutional academic reporting; teachers may see their own working data clearly labeled. No teacher quality rankings, causal claims, or predictive student labels in release one. Small groups and identifiable exports require appropriate access restrictions.

## 8. Logical data model

Core records: users and permissions; students; teachers; programs; curricula; curriculum_subjects; prerequisite relationships; academic_terms; sections; student_term_memberships; classes; teacher_assignment_history; enrollments and enrollment_events; grading_policies; assessment_categories; assessments; scores; grade_submissions; submission_results; review_decisions; publications; correction_requests; audit_events; notifications.

Relationships: program → one curriculum → many curriculum subjects; term → sections and classes; student + term → main-section membership; class → one curriculum subject, term, section, responsible teacher; student + class → enrollment; class → assessments; enrollment + assessment → score; class → immutable submission revisions → review decisions → publication.

Use stable surrogate IDs, foreign keys, uniqueness constraints, non-null critical fields, explicit status checks, and timestamps. Preserve historical subject name/code/units in published snapshots. Subject codes and titles are display metadata, not identity. Add structured equivalences only where institutionally verified. Keep archived records referentially intact. Deletion is restricted for academic records; user deactivation must not cascade into grades.

Protect concurrent score edits with revision checks. Lock and revalidate dependent rows during enrollment and publication. Enforce critical invariants at database and service boundaries, including duplicate classes/enrollments and one active publication per class scope. Audit events include actor, action, record, revision, reason, timestamp, and relevant before/after values; exclude passwords and session secrets.

## 9. Application architecture and campus operations

Use a modular Flask application with Jinja templates, shared CSS components, and limited JavaScript for interactive forms and charts. Retain Oracle unless campus IT identifies a concrete operational reason to change it. Separate route handling, permission checks, domain services, repositories, validation, and calculations. A modular monolith is sufficient; no microservices or separate SPA framework is required by the present scope.

Campus browsers → internal HTTPS endpoint → production application service → private Oracle database. Host on a managed campus server, not a personal development workstation. Campus IT owns DNS/certificates, firewall rules, database backups, service restart, capacity, and updates. All essential assets work without public internet access.

Keep development, staging, and production separate. Apply versioned migrations with a deployment record. Store secrets outside source and restrict database/service accounts. Disable debug mode in production. Decide whether to consolidate security state into Oracle; if SQLite remains, document its single-host limitation and durable storage. Restores invalidate active sessions.

Require server-side authorization for every page, action, export, and record identifier. Retain CSRF protection, secure session handling, password hashing, login throttling, identity-verified resets, and account deactivation. Privileged authentication strengthening is a deployment requirement to resolve with campus IT. No shared administrator accounts. Registration should use admin provisioning/import or verified requests, not automatically activated accounts.

Operational logs use correlation IDs without exposing grades or credentials unnecessarily. Monitor application readiness, database connectivity, failed jobs, storage capacity, and backup freshness. Internal health details must not be publicly exposed. In-app notifications cannot make grade publication fail after an academic transaction succeeds; enqueue them transactionally for retry where needed.

Proposed recovery targets, subject to IT acceptance: at most one hour of committed-data loss and restoration within four hours. Nightly backups alone cannot meet the one-hour target; require appropriate database recovery logging/backup frequency. Keep encrypted backups on separate storage and rehearse restoration. Name both primary and backup support owners, including a grade-deadline escalation path.

## 10. Migration and rollout

1. Inventory actual tables, row counts, IDs, duplicates, incomplete data, grade states, and current security configuration.
2. Back up and prove restoration on an isolated database before production migration.
3. Reconcile the eight unclassified legacy subjects and source curriculum ambiguities with department staff; never guess their program or silently rewrite codes.
4. Build migration mappings from text programs/sections to normalized records. Missing historical section evidence stays unknown and is flagged for review.
5. Preserve existing published values and provenance as legacy snapshots. Do not fabricate administrator approvals or recompute them with new rounding rules.
6. Run migrations in staging; compare students, teachers, classes, enrollments, raw scores, units, published results, and access scopes.
7. Pilot a small set of classes using synthetic/test records first, then a controlled departmental pilot with one authoritative writer for each record.
8. Schedule cutover, freeze old-system writes, take final backup, migrate, reconcile, run acceptance checks, and open the new system.
9. Retain the old system read-only for the approved transition period. Before new writes, rollback may restore the pre-cutover state. After new writes, preserve/reconcile those writes; do not blindly restore an older database.
10. Train administrators, teachers, and students; provide short task guides and a support channel.

## 11. Delivery phases and acceptance gates

| Phase | Deliverable | Gate |
|---|---|---|
| 0. Policy and discovery | Signed workflow, grading examples, data inventory, campus hosting profile | Academic and IT owners resolve launch-critical decisions |
| 1. Design foundation | Navigation, shared components, five-screen prototype | Users complete representative tasks without guidance |
| 2. Academic setup | Programs, curricula, terms, students, teachers, sections | Historical membership and archival behavior verified |
| 3. Classes and enrollment | Teacher assignment, bulk preview, exceptions, warnings | No duplicate or partial enrollment under concurrent requests |
| 4. Grade lifecycle | Entry, calculation, immutable submission, review, publication, correction | Approved calculation fixtures and role/state tests pass |
| 5. Reports and resilience | Role reports, exports, outage handling, audit, operations | Report reconciliation and recovery rehearsal pass |
| 6. Migration and pilot | Reconciled staging data, training, pilot results | Department acceptance and no unresolved critical defects |
| 7. Launch and support | Controlled cutover, monitoring, support ownership | Health, access, data reconciliation, and rollback readiness confirmed |

Estimate effort only after phase 0 establishes data condition, team capacity, and user load. Each phase should produce demonstrable software and updated tests, not only documents.

## 12. Production acceptance checklist

- Administrator cannot publish changed or unsubmitted data; teacher cannot publish via UI or direct request.
- Students cannot retrieve another student's results, drafts, exports, or identifiers through alternate endpoints.
- Submitted revisions remain unchanged when drafts are edited or a correction is requested.
- Prerequisite warnings appear without preventing enrollment, including when evidence is unknown.
- Main-section transfers preserve class enrollment unless explicitly changed.
- Repeated requests, concurrent admins, duplicate submissions, and stale browser tabs do not corrupt state.
- Approved grade boundary, rounding, zero, missing, INC, weighting, and correction examples pass.
- Full history survives user deactivation, subject archival, teacher replacement, and term closure.
- Keyboard, mobile, zoom, error recovery, accessible labels, and export reconciliation are verified.
- Database outages and interrupted writes produce no partial success or accidental duplicate writes.
- Migration reconciliation, backup restore, service restart, and incident escalation are demonstrated.
- Proposed performance target: common pages within two seconds at the 95th percentile on campus LAN under agreed peak load. Establish user counts and data volumes before testing; this is not a measured guarantee.

## 13. Remaining decisions

Before calculation implementation: approved CCSICT grading examples, weights, decimal conversion, average inclusion rules, and special-outcome handling.
Before review implementation: named academic approving authority, whether the same account can teach and administer, required correction authorization evidence, and approved review/closure deadlines.
Before launch: enrollment/student/class counts and peak concurrency; server and Oracle support arrangements; backup retention and recovery commitments; record retention policy; campus device/browser support; and whether campus IT permits students direct LAN access.

These decisions do not prevent design and academic setup work. They do prevent claiming the grading engine or deployment is institutionally ready.
