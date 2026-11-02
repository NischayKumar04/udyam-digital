"""Trains the lead score and saves it as plain numbers, so the app needs no ML libraries.

Uses only what's known when a lead arrives. Stage, drop reason and outcome fields would
leak the answer, so they're excluded.

The test figures are averaged across many random splits. Each test set holds only about
110 activations, so a single split can look much better or worse than the model really is.

Needs pandas and scikit-learn. Run from prototype/backend:  python -m scripts.train_propensity
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "propensity_model.json"
CATEGORIES = ["lead_source", "segment", "preferred_language", "annual_turnover_band", "has_gstin", "has_udyam", "current_internet", "current_provider", "contact_role"]
TEST_SPLITS = 200
# The back office shows the score as a percentage, so it has to mean what it says. At this
# strength, scores on unseen leads have a calibration slope of 1.0; at 0.5 they ran too high.
REGULARISATION = 0.1

# "None" is a real value here (no internet, or no provider), so only blanks count as missing.
leads = pd.read_csv(ROOT / "smb_leads.csv", keep_default_na=False, na_values=[""])
y = (leads.outcome == "Activated").astype(int)
numeric = pd.DataFrame({
    "city_tier": leads.city_tier,
    "log_employees": np.log1p(leads.employee_count),
    "num_sites": leads.num_sites,
    "log_spend": np.log1p(leads.monthly_telecom_spend_inr),
    "interest_count": leads.products_of_interest.fillna("").str.count(";") + 1,
})
X = pd.concat([numeric, pd.get_dummies(leads[CATEGORIES], prefix_sep="=", drop_first=False).astype(float)], axis=1)


def new_model() -> LogisticRegression:
    return LogisticRegression(max_iter=4000, C=REGULARISATION)


def evaluate_split(seed: int) -> dict[str, float]:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=seed, stratify=y)
    scores = new_model().fit(X_train, y_train).predict_proba(X_test)[:, 1]
    ranked = pd.DataFrame({"y": y_test.values, "p": scores}).sort_values("p", ascending=False)
    top = ranked.head(int(len(ranked) * 0.2))
    return {
        "auc": roc_auc_score(y_test, scores),
        "top_20pct_share_of_activations": top.y.sum() / ranked.y.sum(),
        "top_20pct_rate": top.y.mean(),
        "base_rate": ranked.y.mean(),
    }


results = pd.DataFrame([evaluate_split(seed) for seed in range(TEST_SPLITS)])
metrics = {"test_splits": TEST_SPLITS, **{name: round(float(results[name].mean()), 3) for name in results}}

final = new_model().fit(X, y)
model = {
    "intercept": float(final.intercept_[0]),
    "coefficients": {name: round(float(value), 5) for name, value in zip(X.columns, final.coef_[0])},
    "holdout_metrics": metrics,
}
OUTPUT.write_text(json.dumps(model, indent=1), encoding="utf-8")
print("Saved", OUTPUT, metrics)
print(f"Middle 90% of splits: AUC {results.auc.quantile(0.05):.3f} to {results.auc.quantile(0.95):.3f}, "
      f"top 20% share {results.top_20pct_share_of_activations.quantile(0.05):.1%} to {results.top_20pct_share_of_activations.quantile(0.95):.1%}")
