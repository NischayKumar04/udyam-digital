"""Trains the lead scores and saves them as plain numbers, so the app needs no ML libraries.

Uses only what's known when a lead arrives. Stage, drop reason and outcome fields would
leak the answer, so they're excluded.

There are two models. The main one scores last quarter's leads. The chat model scores owners
who ask for a call in the app, using only the facts the chat collects, because it never asks
for lead source, turnover, current provider and the like.

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
CHAT_CATEGORIES = ["segment", "preferred_language", "has_gstin"]
CHAT_NUMBERS = ["city_tier", "log_employees", "num_sites", "interest_count"]
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


def features(numbers: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    return pd.concat([numbers, pd.get_dummies(leads[categories], prefix_sep="=", drop_first=False).astype(float)], axis=1)


def new_model() -> LogisticRegression:
    return LogisticRegression(max_iter=4000, C=REGULARISATION)


def evaluate_split(X: pd.DataFrame, seed: int) -> dict[str, float]:
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


def train(name: str, X: pd.DataFrame) -> dict:
    results = pd.DataFrame([evaluate_split(X, seed) for seed in range(TEST_SPLITS)])
    metrics = {"test_splits": TEST_SPLITS, **{column: round(float(results[column].mean()), 3) for column in results}}
    print(name, metrics)
    print(f"  Middle 90% of splits: AUC {results.auc.quantile(0.05):.3f} to {results.auc.quantile(0.95):.3f}, "
          f"top 20% share {results.top_20pct_share_of_activations.quantile(0.05):.1%} to {results.top_20pct_share_of_activations.quantile(0.95):.1%}")
    final = new_model().fit(X, y)
    return {
        "intercept": float(final.intercept_[0]),
        "coefficients": {column: round(float(value), 5) for column, value in zip(X.columns, final.coef_[0])},
        "holdout_metrics": metrics,
    }


model = train("Main model", features(numeric, CATEGORIES))
model["chat_model"] = train("Chat model", features(numeric[CHAT_NUMBERS], CHAT_CATEGORIES))
OUTPUT.write_text(json.dumps(model, indent=1), encoding="utf-8")
print("Saved", OUTPUT)
