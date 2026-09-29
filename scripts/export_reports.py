"""Export human-readable + machine-readable reports from the ACTIVE model
(master prompts Prompt 5: reports/model_metrics.json, patterns.json,
shap_summary.png) and Prompt 10: test-period reliability validation table.

Reads the trained joblib bundle (ml/models/<version>.joblib), evaluates on
the chronological TEST slice of the DB training data, and writes:

    reports/model_metrics.json   MAE/RMSE/Precision/Recall/F1/ROC-AUC/PR-AUC/
                                 Brier + training window + model version
    reports/patterns.json        plain-English historical bust patterns
    reports/shap_summary.png     global SHAP summary plot
    reports/confidence_validation.json  mean abs error + bust rate per
                                 confidence label per lead day (TEST only)

Everything is derived from real stored data; nothing is fabricated.

Usage:
    python scripts/export_reports.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from app.core.constants import FEATURE_COLUMNS  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.models import ModelVersion  # noqa: E402
from ml.training.dataset_builder import build_training_dataset, chronological_split  # noqa: E402

REPORTS_DIR = _ROOT / "reports"


def _active_bundle():
    import joblib

    db = SessionLocal()
    try:
        mv = (
            db.query(ModelVersion)
            .filter(ModelVersion.status == "ACTIVE")
            .order_by(ModelVersion.created_at.desc())
            .first()
        )
        if mv is None:
            return None, None
        return mv, joblib.load(mv.model_path)
    finally:
        db.close()


def _classify(confidence_score: float) -> str:
    """Doc labels: High >= 70, Medium 40-69, Low < 40 (score is 0-1)."""
    s = confidence_score * 100.0
    if s >= 70:
        return "HIGH"
    if s >= 40:
        return "MEDIUM"
    return "LOW"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    mv, bundle = _active_bundle()
    if bundle is None:
        print("No ACTIVE model registered — run backend/seed_database.py or "
              "ml/training/train_model.py first.")
        return 2

    variable = bundle.get("variable", "rainfall")
    df = build_training_dataset(variable)
    train_df, val_df, test_df = chronological_split(df)

    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["bust"].astype(int)

    clf = bundle["bust_model"]
    reg = bundle["error_model"]
    calib = bundle.get("calibrator")

    raw_prob = clf.predict_proba(X_test)[:, 1]
    prob = calib.predict(raw_prob) if calib is not None else raw_prob
    pred = (np.asarray(prob) >= 0.5).astype(int)
    err_pred = reg.predict(X_test)
    err_true = test_df["absolute_error"].to_numpy()

    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        mean_absolute_error,
        precision_recall_fscore_support,
        roc_auc_score,
    )

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, pred, average="binary", zero_division=0
    )
    try:
        roc_auc = float(roc_auc_score(y_test, prob))
    except ValueError:
        roc_auc = 0.5

    metrics = {
        "model_version": bundle.get("model_version", mv.model_version if mv else "unknown"),
        "variable": variable,
        "trained_from": bundle.get("trained_from"),
        "trained_to": bundle.get("trained_to"),
        "test_rows": int(len(test_df)),
        "test_bust_rate": round(float(y_test.mean()), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(float(average_precision_score(y_test, prob)), 4),
        "brier": round(float(brier_score_loss(y_test, prob)), 4),
        "expected_error_mae": round(float(mean_absolute_error(err_true, err_pred)), 4),
        "expected_error_rmse": round(
            float(np.sqrt(np.mean((err_true - err_pred) ** 2))), 4
        ),
        "feature_columns": FEATURE_COLUMNS,
    }
    if metrics["roc_auc"] > 0.97:
        metrics["leakage_warning"] = (
            "ROC-AUC > 0.97 — per the doc this may indicate leakage; review "
            "shifted rolling features and the time-based split."
        )
    (REPORTS_DIR / "model_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(f"reports/model_metrics.json: ROC-AUC={metrics['roc_auc']}, "
          f"PR-AUC={metrics['pr_auc']}, Brier={metrics['brier']}")

    # ---- Confidence validation table (Prompt 10, judges' proof) ----
    conf = np.clip(1.0 - np.asarray(prob), 0.0, 1.0)
    labels = np.array([_classify(float(c)) for c in conf])
    rows = []
    for lead in sorted(test_df["lead_day"].unique()):
        for label in ("HIGH", "MEDIUM", "LOW"):
            mask = (labels == label) & (test_df["lead_day"].to_numpy() == lead)
            if mask.sum() == 0:
                continue
            rows.append(
                {
                    "lead_day": int(lead),
                    "confidence_label": label,
                    "rows": int(mask.sum()),
                    "mean_abs_error": round(float(err_true[mask].mean()), 3),
                    "bust_rate": round(float(y_test.to_numpy()[mask].mean()), 4),
                }
            )
    (REPORTS_DIR / "confidence_validation.json").write_text(
        json.dumps(
            {
                "note": "TEST period only. Proof: LOW confidence rows should show "
                        "larger mean_abs_error and higher bust_rate than HIGH.",
                "variable": variable,
                "table": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"reports/confidence_validation.json: {len(rows)} label/lead rows")

    # ---- Historical pattern learning (Prompt 5) ----
    patterns: list[str] = []
    try:
        import shap

        explainer = shap.TreeExplainer(clf)
        sample = test_df[FEATURE_COLUMNS].sample(
            n=min(3000, len(test_df)), random_state=42
        )
        sv = explainer.shap_values(sample)
        vals = sv[1] if isinstance(sv, list) else getattr(sv, "values", sv)
        if getattr(vals, "ndim", 2) == 3:
            vals = vals[:, :, 1]
        mean_abs = np.abs(np.asarray(vals)).mean(axis=0)
        top = np.argsort(mean_abs)[::-1][:5]

        feat_labels = {
            "lead_day": "Longer lead days",
            "historical_mae": "Regions with high historical error",
            "historical_bust_rate": "Regions with frequent historical busts",
            "forecast_run_change": "Forecasts that changed a lot between runs",
            "ensemble_spread": "Large ensemble disagreement",
            "month": "Seasonal effects",
            "season_monsoon": "Monsoon-season variability",
        }
        for i in top:
            fname = FEATURE_COLUMNS[i]
            patterns.append(
                f"{feat_labels.get(fname, fname)}: mean SHAP impact "
                f"{mean_abs[i]:.3f} on bust probability (feature value in "
                f"[{sample[fname].min():.2f}, {sample[fname].max():.2f}])."
            )

        summary_path = REPORTS_DIR / "shap_summary.png"
        shap.summary_plot(
            vals, sample, feature_names=FEATURE_COLUMNS, show=False
        )
        import matplotlib

        matplotlib.pyplot.tight_layout()
        matplotlib.pyplot.savefig(summary_path, dpi=120)
        matplotlib.pyplot.close()
        print(f"reports/shap_summary.png written ({len(patterns)} patterns)")
    except Exception as exc:  # SHAP/matplotlib optional for the reports
        patterns.append(f"SHAP summary unavailable in this environment: {exc!r}")
        print(f"SHAP summary skipped: {exc!r}")

    (REPORTS_DIR / "patterns.json").write_text(
        json.dumps(
            {
                "model_version": metrics["model_version"],
                "variable": variable,
                "patterns": patterns,
                "disclaimer": "Patterns describe estimated risk of forecast "
                              "error; they are not meteorological causes.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
