import numpy as np
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score

NUM = ["filing_lag_days", "total_assets", "net_income", "leverage"]
CAT = ["sector", "form"]
TARGET = "was_restated"


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Task 2: restatement classification (logistic, class_weight=balanced)")
    df = read_csv(logger, config.mart_dir / "mart_restatement.csv")
    X, y, groups = df[NUM + CAT], df[TARGET].astype(int), df["cik"]
    # group by cik so the same company can't appear in both train and test (leakage)
    tr_idx, te_idx = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42).split(X, y, groups)
    )
    Xtr, Xte = X.iloc[tr_idx], X.iloc[te_idx]
    ytr, yte = y.iloc[tr_idx], y.iloc[te_idx]

    pre = ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="median")),
                        ("sc", StandardScaler()),
                    ]
                ),
                NUM,
            ),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
        ]
    )
    model = Pipeline(
        [
            ("pre", pre),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000)),
        ]
    )
    model.fit(Xtr, ytr)
    p, proba = model.predict(Xte), model.predict_proba(Xte)[:, 1]
    # AUC is the headline (threshold-free). P@k = R-precision over the k actual positives.
    # P/R/F1 at the default 0.5 cutoff are secondary — they read low purely because of the
    # ~1.6% prevalence + balanced weighting, not because the model can't rank.
    auc = roc_auc_score(yte, proba)
    k = int(yte.sum())
    topk = np.argsort(proba)[::-1][:k]
    prec_at_k = float(yte.values[topk].mean()) if k else float("nan")
    prec, rec, f1 = precision_score(yte, p), recall_score(yte, p), f1_score(yte, p)
    logger.info(
        f"  AUC={auc:.3f} P@{k}={prec_at_k:.3f} "
        f"| @0.5 P={prec:.3f} R={rec:.3f} F1={f1:.3f}"
    )
    out = df.loc[
        Xte.index,
        ["accession_number", "cik", "ticker", "name", "sector", "form", "report_date"],
    ].copy()
    out["actual"] = yte.values
    out["proba"] = proba
    write_csv(logger, config.ml_dir / "pred_restatement.csv", out)
    logger.info("=" * 60)
    return [
        {"task": "restatement", "metric": "roc_auc", "value": auc},
        {"task": "restatement", "metric": "precision_at_k", "value": prec_at_k},
        {"task": "restatement", "metric": "test_positives_k", "value": k},
        {"task": "restatement", "metric": "precision", "value": prec},
        {"task": "restatement", "metric": "recall", "value": rec},
        {"task": "restatement", "metric": "f1", "value": f1},
    ]
