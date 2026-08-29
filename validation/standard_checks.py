"""
standard_checks.py -- Track U: the real, repeated validation pattern this
project has actually used, every time, across Track E (fire), Track F
(crop-share), Track D/I (flood), Track O (yield), and Track L (fusion
U-Net) -- extracted into one shared module instead of five independent
from-scratch implementations. This is the real, named gap Track U closes:
every model was validated rigorously, but ad hoc each time, which is
exactly how a silent bug (stale data, a dead field name) slips through
undetected until caught by luck rather than by process.

The five real checks, in the order every prior model applied them:

1. No identity/positional leak -- confirm banned columns (lat, lon,
   district/district_id, any row-identity field) are absent from the real
   feature list BEFORE training, not discovered after a suspiciously good
   score (Track E's with-geo F1=0.728 lat/lon leak is the reason this
   exists at all).
2. A real spatially- or temporally-blocked split -- whole groups (districts,
   dates, seasons) held out entirely, never a random row-level split that
   lets correlated rows leak between train and test.
3. Real class-balance / value-distribution check, printed before training --
   positive rate for classification, or real min/max/mean/std/exact-zero
   count for regression targets (this is the one check Track O's yield
   model applied as a one-off manual pass rather than repeatable code --
   see this track's retroactive audit finding).
4. Permutation-feature-importance self-check, computed and reported BEFORE
   any headline number, not after -- the real, general form of the check
   that caught Track E's lat/lon leak and Track L's positional-channel
   question.
5. An honest baseline comparison -- the existing rule-based detector, a
   naive/constant baseline, or a simple linear model, run on the exact same
   real held-out data, reported alongside the trained model's own number,
   never presented alone.

Every function here is a real, runnable check, not documentation-only --
call them from a training script the same way Track E/F/D/O/L each wrote
their own equivalent by hand. Any future model (Track S2's fine-tuning
included, if it's ever revived) is expected to import from here rather than
re-deriving the pattern again.
"""

from __future__ import annotations

import numpy as np

try:
    from sklearn.inspection import permutation_importance as _sk_permutation_importance
except ImportError:  # pragma: no cover -- sklearn is a real dependency of every
    # model script that would call this; only missing in an environment that
    # would fail on its own model-training imports anyway.
    _sk_permutation_importance = None


# ------------------------------------------------------------------ check 1
# banned columns, exactly the set every prior model's own comment excluded
# by hand -- see e.g. train_crop_share_model.py's "confirmed: no lat, no
# lon, no district-identity feature -- Track E's lesson applied from the
# start".
BANNED_IDENTITY_FEATURES = {"lat", "lon", "latitude", "longitude", "district", "district_id"}


def check_no_identity_leak(feature_names, allow=()):
    """Raise if any banned identity/positional column is in the real feature
    list. `allow` lets a model explicitly opt a name back in with a stated
    reason at the call site (e.g. Track L's fixed-grid lat/lon, which is a
    real per-pixel positional encoding identical across every sample, not a
    row-identity leak -- see permutation_check_track_l.py's own docstring
    for why that case is different from Track E's).

    Returns the list of features checked (for logging), so a caller can
    print "checked N real features, 0 banned" as part of its own console
    output, matching every prior model's own printed confirmation.
    """
    banned = BANNED_IDENTITY_FEATURES - set(allow)
    leaked = [f for f in feature_names if f in banned]
    if leaked:
        raise ValueError(
            f"identity/positional leak: {leaked} present in feature list. "
            f"If this is a deliberate, reasoned exception (e.g. a fixed "
            f"per-pixel grid encoding, not row identity), pass it in `allow=` "
            f"with a comment at the call site explaining why, matching "
            f"Track L's documented exception."
        )
    return list(feature_names)


# ------------------------------------------------------------------ check 2
def assert_no_group_overlap(splits: dict, group_values: dict):
    """`splits` maps a split name ("train"/"val"/"test") to an iterable of
    row indices or a boolean mask; `group_values` maps the same split names
    to the group id (district, date, season) each of those rows belongs to.
    Confirms no group value appears in more than one split -- the real,
    general form of "whole districts held out" (Track F, Track D/I) or
    "whole dates held out" (Track E, Track L).

    Raises with the actual overlapping group values on failure, since
    "there's a leak somewhere" without naming which district/date leaked
    is not an actionable error message.
    """
    group_sets = {name: set(np.atleast_1d(vals)) for name, vals in group_values.items()}
    names = list(group_sets.keys())
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlap = group_sets[a] & group_sets[b]
            if overlap:
                raise ValueError(f"real group overlap between '{a}' and '{b}' splits: {sorted(overlap)}")
    return {name: len(vals) for name, vals in group_sets.items()}


# ------------------------------------------------------------------ check 3
def class_balance_report(y, positive_label=1):
    """Classification version -- real positive rate, printed the same way
    every classifier script here already does by hand
    (`f"{df[LABEL].sum()} positive ({df[LABEL].mean()*100:.2f}%)"`).
    Returns the dict so a caller can also persist it into that model's own
    results JSON, matching the existing pattern."""
    y = np.asarray(y)
    n = len(y)
    n_pos = int(np.sum(y == positive_label))
    report = {"n": int(n), "n_positive": n_pos, "positive_rate": n_pos / n if n else float("nan")}
    print(f"real class balance: {n} rows, {n_pos} positive ({report['positive_rate']*100:.2f}%)")
    return report


def regression_distribution_report(y, exact_zero_atol=1e-9):
    """Regression version -- the check Track O's yield model applied by hand
    once (7 real print-precision-floor zero cells, 1 genuine outlier) but
    never wrote as repeatable code. Reports real min/max/mean/std, the
    count of exact (or near-exact) zeros, and simple IQR-based outlier
    count -- flagged for a human to look at, not auto-excluded, since a
    real outlier (e.g. Nasirabad rice) may be a genuine data point, not an
    error."""
    y = np.asarray(y, dtype=float)
    y = y[~np.isnan(y)]
    if len(y) == 0:
        return {"n": 0}
    q1, q3 = np.percentile(y, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    n_outliers = int(np.sum((y < lo) | (y > hi)))
    n_zero = int(np.sum(np.abs(y) <= exact_zero_atol))
    report = {
        "n": int(len(y)), "min": float(y.min()), "max": float(y.max()),
        "mean": float(y.mean()), "std": float(y.std()),
        "n_near_zero": n_zero, "n_iqr_outliers": n_outliers,
    }
    print(
        f"real value distribution: n={report['n']} min={report['min']:.4f} "
        f"max={report['max']:.4f} mean={report['mean']:.4f} std={report['std']:.4f} "
        f"near-zero={n_zero} IQR-outliers={n_outliers}"
    )
    return report


# ------------------------------------------------------------------ check 4
def permutation_importance_report(model, X_test, y_test, feature_names, scoring, flagged_features=(), n_repeats=5, random_state=0):
    """Thin, shared wrapper around sklearn's permutation_importance -- same
    call every tabular model here already makes by hand. `flagged_features`
    names any positional/identity feature a caller deliberately kept (via
    check_no_identity_leak's `allow=`); if one of those ends up dominating
    real importance, this prints a loud warning instead of letting it slide
    into a headline number the way Track E's first with-geo run almost did.

    Returns {feature_name: mean_importance}, sorted descending, so a caller
    can persist it into that model's own results JSON."""
    if _sk_permutation_importance is None:
        raise ImportError("scikit-learn is required for permutation_importance_report")
    imp = _sk_permutation_importance(
        model, X_test, y_test, n_repeats=n_repeats, random_state=random_state, scoring=scoring
    )
    ranked = sorted(zip(feature_names, imp.importances_mean), key=lambda kv: -kv[1])
    print("real permutation feature importance:")
    for name, val in ranked:
        flag = "  <-- FLAGGED (positional/identity)" if name in flagged_features else ""
        print(f"  {name:<40} {val:+.4f}{flag}")
    if flagged_features:
        flagged_vals = [v for n, v in ranked if n in flagged_features]
        other_vals = [v for n, v in ranked if n not in flagged_features]
        if flagged_vals and other_vals and max(flagged_vals) > 2 * max(other_vals, default=0) and max(flagged_vals) > 0.05:
            print(
                "  WARNING: a flagged positional/identity feature dominates real "
                "importance -- this is the exact Track E lat/lon-leak pattern. "
                "Do not report a headline number from this run without investigating."
            )
    return dict(ranked)


# ------------------------------------------------------------------ check 5
def baseline_comparison_report(model_metric: float, baseline_metric: float, metric_name: str, baseline_label: str = "baseline", higher_is_better: bool = True):
    """Prints and returns a real before/after comparison -- the one line
    every prior model's own script prints by hand
    ("trained model beats/loses to <baseline_label>"). Exists so a headline
    number is never reported without this line appearing next to it in the
    same run's console output."""
    beat = (model_metric > baseline_metric) if higher_is_better else (model_metric < baseline_metric)
    verdict = "beats" if beat else "does NOT beat"
    print(f"real baseline comparison ({metric_name}): model={model_metric:.4f} {verdict} {baseline_label}={baseline_metric:.4f}")
    return {"model": model_metric, "baseline_label": baseline_label, "baseline": baseline_metric, "model_beats_baseline": beat}
