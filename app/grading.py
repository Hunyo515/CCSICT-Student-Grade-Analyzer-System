"""Grade computation helpers shared by the faculty (and later student) portals."""


def letter_grade(percent):
    """Map a weighted percentage to a letter grade, matching the design's bands."""
    if percent is None:
        return "—"
    if percent >= 90:
        return "Grade A"
    if percent >= 85:
        return "Grade B+"
    if percent >= 80:
        return "Grade B"
    if percent >= 75:
        return "Grade C+"
    if percent >= 70:
        return "Grade C"
    if percent >= 60:
        return "Grade D"
    return "Grade F"


def letter_grade_class(letter):
    """CSS modifier bucket for a letter grade badge."""
    if letter in ("Grade A",):
        return "gold"
    if letter in ("Grade B+", "Grade B", "Grade C+"):
        return "green"
    if letter in ("Grade C", "Grade D"):
        return "brown"
    return "red"


def gpa_scale(percent):
    """
    Convert a weighted percentage to a 4.0-scale GPA point, using the same
    letter-grade bands as letter_grade() so the two stay consistent.
    """
    if percent is None:
        return None
    if percent >= 90:
        return 4.0
    if percent >= 85:
        return 3.5
    if percent >= 80:
        return 3.0
    if percent >= 75:
        return 2.5
    if percent >= 70:
        return 2.0
    if percent >= 60:
        return 1.0
    return 0.0


def component_type(name):
    """Heuristic badge category for a grade component name."""
    n = (name or "").lower()
    if "quiz" in n:
        return "Quiz"
    if "exam" in n or "midterm" in n or "final" in n:
        return "Exam"
    if "project" in n:
        return "Project"
    return "Assignment"


def compute_weighted_total(scores_by_component, components, category_weights=None):
    """
    scores_by_component: dict {component_id: (score, max_score)}
    components: list of {component_id, weight_percent[, category_id]}
    category_weights: optional {category_id: weight_percent}, one entry per
    grade category defined for the assignment (any number, any names —
    faculty define these freely in the Grade Weighting page).

    A component with no category_id (or one not present in category_weights)
    is in "flat" mode: its weight_percent is used directly against the final
    grade — this is the original, simplest single-tier behaviour and stays
    the default for any assignment that hasn't set up categories.

    A component WITH a category_id scales its weight_percent by that
    category's own weight_percent (e.g. a component worth 20% within a
    "Laboratory" category that itself is 40% of the final grade contributes
    20% * 40% = 8% to the final grade). Each category's components are
    expected to sum to 100% *within* that category — that's enforced/
    surfaced in the UI, not here.

    Ungraded components count as 0 toward the weighted total (matches how
    the dashboard treats "Pending Grade Entries" — a score isn't assumed
    until the teacher enters one).
    """
    category_weights = category_weights or {}
    total = 0.0
    for c in components:
        score, max_score = scores_by_component.get(c["component_id"], (None, None))
        if score is not None and max_score:
            weight = float(c["weight_percent"])
            cat_id = c.get("category_id")
            if cat_id and cat_id in category_weights:
                weight = weight * float(category_weights[cat_id]) / 100.0
            total += (float(score) / float(max_score)) * weight
    return round(total, 2)
