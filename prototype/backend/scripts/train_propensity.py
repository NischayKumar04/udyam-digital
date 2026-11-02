"""Trains the lead score and saves it as plain numbers, so the app needs no ML libraries.

Uses only what's known when a lead arrives. Stage, drop reason and outcome fields would
leak the answer, so they're excluded.

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

leads = pd.read_csv(ROOT / "smb_leads.csv")
y = (leads.outcome == "Activated").astype(int)
numeric = pd.DataFrame({
    "city_tier": leads.city_tier,
    "log_employees": np.log1p(leads.employee_count),
    "num_sites": leads.num_sites,
    "log_spend": np.log1p(leads.monthly_telecom_spend_inr),
    "interest_count": leads.products_of_interest.fillna("").str.count(";") + 1,
})
X = pd.concat([numeric, pd.get_dummies(leads[CATEGORIES], prefix_sep="=", drop_first=False).astype(float)], axis=1)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=7, stratify=y)
holdout = LogisticRegression(max_iter=4000, C=0.5).fit(X_train, y_train)
scores = holdout.predict_proba(X_test)[:, 1]
ranked = pd.DataFrame({"y": y_test.values, "p": scores}).sort_values("p", ascending=False)
top = ranked.head(int(len(ranked) * 0.2))
metrics = {
    "auc": round(float(roc_auc_score(y_test, scores)), 3),
    "top_20pct_share_of_activations": round(float(top.y.sum() / ranked.y.sum()), 3),
    "top_20pct_rate": round(float(top.y.mean()), 3),
    "base_rate": round(float(ranked.y.mean()), 3),
}

final = LogisticRegression(max_iter=4000, C=0.5).fit(X, y)
model = {
    "intercept": float(final.intercept_[0]),
    "coefficients": {name: round(float(value), 5) for name, value in zip(X.columns, final.coef_[0])},
    "holdout_metrics": metrics,
}
OUTPUT.write_text(json.dumps(model, indent=1), encoding="utf-8")
print("Saved", OUTPUT, metrics)
