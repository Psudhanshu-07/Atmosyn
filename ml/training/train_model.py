"""Train the bust classifier + error regressor with calibration and metrics.

Follows the ML requirements (PRD §12, Testing §1-2):

    chronological split -> baseline -> XGBoost models -> probability
    calibration -> evaluation (ROC-AUC, Brier, precision/recall/F1, MAE/RMSE)
    -> model registry entry with checksum.

Outputs: ml/models/<version>.joblib bundle containing both models, the
calibrator, feature list, metrics and version string.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT / "ml"))

from ml.training.dataset_builder import (  # noqa: E402
    build_training_dataset,
    chronological_split,
)
from app.core.constants import FEATURE_COLUMNS  # noqa: E402

MODEL_DIR = _ROOT / "ml" / "models"
MODEL_VERSION = "xgb_v1.3"


def _metrics(y_true, y_prob, y_pred) -> dict:
    from sklearn.metrics import (
        brier_score_loss,
        precision_recall_fscore_support,
        roc_auc_score,
    )

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    try:
        auc = roc_auc_score(y_true, y_prob)
    except ValueError:
        auc = 0.5
    return {
        "roc_auc": round(float(auc), 4),
        "brier": round(float(brier_score_loss(y_true, y_prob)), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
    }


def _reg_metrics(y_true, y_pred) -> dict:
    err = y_pred - y_true
    return {
        "mae": round(float(np.mean(np.abs(err))), 4),
        "rmse": round(float(np.sqrt(np.mean(err**2))), 4),
    }


def train(target_variable: str = "rainfall") -> dict:
    from sklearn.calibration import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import mean_absolute_error
    from xgboost import XGBClassifier, XGBRegressor

    from app.core.constants import FEATURE_COLUMNS

    print(f"Building training dataset for variable={target_variable} ...")
    df = build_training_dataset(target_variable)
    print(f"dataset rows={len(df)}, bust_rate={df['bust'].mean():.3f}")

    train_df, val_df, test_df = chronological_split(df)
    print(
        f"split: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
    )

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df["bust"]
    X_val, y_val = val_df[FEATURE_COLUMNS], val_df["bust"]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df["bust"]
    e_train = train_df["absolute_error"]
    e_test = test_df["absolute_error"]

    # ---- Baseline: logistic regression on the same features (TV-17) ----
    lr = LogisticRegression(max_iter=1000)
    lr.fit(X_train, y_train)
    lr_prob = lr.predict_proba(X_test)[:, 1]
    lr_metrics = _metrics(y_test, lr_prob, (lr_prob >= 0.5).astype(int))
    print(f"baseline LR  test metrics: {lr_metrics}")

    # ---- XGBoost bust classifier ----
    pos = max(int(y_train.sum()), 1)
    neg = max(len(y_train) - pos, 1)
    clf = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        scale_pos_weight=neg / pos,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    val_prob = clf.predict_proba(X_val)[:, 1]

    # ---- Probability calibration (isotonic, PRD §12 step 7) ----
    calib = IsotonicRegression(out_of_bounds="clip")
    calib.fit(val_prob, y_val)
    test_prob_raw = clf.predict_proba(X_test)[:, 1]
    test_prob = calib.predict(test_prob_raw)
    bust_metrics = _metrics(y_test, test_prob, (test_prob >= 0.5).astype(int))
    raw_metrics = _metrics(y_test, test_prob_raw, (test_prob_raw >= 0.5).astype(int))
    print(f"xgboost raw  test metrics: {raw_metrics}")
    print(f"xgboost cal. test metrics: {bust_metrics}")

    # ---- XGBoost error regressor (FR-07) ----
    reg = XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        objective="reg:squarederror",
    )
    reg.fit(X_train, e_train)
    e_pred = reg.predict(X_test)
    reg_metrics = _reg_metrics(e_test, e_pred)
    print(f"error model  test metrics: {reg_metrics}")

    # ---- Persist bundle with checksum ----
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"{MODEL_VERSION}.joblib"
    bundle = {
        "model_version": MODEL_VERSION,
        "variable": target_variable,
        "bust_model": clf,
        "error_model": reg,
        "calibrator": calib,
        "baseline_lr": lr,
        "baseline_metrics": lr_metrics,
        "metrics": bust_metrics,
        "reg_metrics": reg_metrics,
        "features": FEATURE_COLUMNS,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "trained_from": str(train_df["valid_time"].min())[:10],
        "trained_to": str(train_df["valid_time"].max())[:10],
    }
    joblib.dump(bundle, path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    print(f"saved {path} checksum={checksum}")

    return {
        "path": str(path),
        "checksum": checksum,
        "metrics": bust_metrics,
        "reg_metrics": reg_metrics,
        "baseline": lr_metrics,
        "features": FEATURE_COLUMNS,
        "trained_from": date.fromisoformat(bundle["trained_from"]),
        "trained_to": date.fromisoformat(bundle["trained_to"]),
        "rows": len(df),
    }


def register_model(info: dict) -> None:
    """Insert/refresh the model registry row inside the backend DB."""
    sys.path.insert(0, str(_ROOT / "backend"))
    from app.core.database import Base, SessionLocal, engine
    from app.core.models import ModelVersion

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = (
            db.query(ModelVersion)
            .filter(ModelVersion.model_version == MODEL_VERSION)
            .first()
        )
        data = dict(
            algorithm="XGBoost + isotonic calibration",
            status="ACTIVE",
            trained_from=info["trained_from"],
            trained_to=info["trained_to"],
            features=json.dumps(info.get("features", []))[:1900],
            roc_auc=info["metrics"]["roc_auc"],
            brier_score=info["metrics"]["brier"],
            precision_=info["metrics"]["precision"],
            recall_=info["metrics"]["recall"],
            f1=info["metrics"]["f1"],
            mae=info["reg_metrics"]["mae"],
            rmse=info["reg_metrics"]["rmse"],
            checksum=info["checksum"],
            model_path=info["path"],
        )
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
        else:
            db.add(ModelVersion(model_version=MODEL_VERSION, **data))
        db.commit()
        print("model registry updated")
    finally:
        db.close()


if __name__ == "__main__":
    info = train("rainfall")
    register_model(info)
    print(json.dumps(info["metrics"], indent=2))
