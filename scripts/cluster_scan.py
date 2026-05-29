"""One-off: sweep KMeans K and DBSCAN (eps, min_samples) for the two clustering
tasks. Reuses each train module's ID_COLS so the feature set matches training
exactly, and replicates the train preprocessing (inf->NaN, median impute,
StandardScaler). Read-only -- prints tables, writes nothing.

Run: .venv/Scripts/python scripts/cluster_scan.py
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import silhouette_score, davies_bouldin_score

from edgar.ml import train_capital_allocation as tca
from edgar.ml import train_company_health as tch

MART_DIR = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "mart"
K_RANGE = range(2, 11)
EPS_RANGE = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
MIN_SAMPLES_RANGE = [3, 5, 10]


def preprocess(df, id_cols):
    feats = [c for c in df.columns if c not in set(id_cols)]
    X = df[feats].replace([np.inf, -np.inf], np.nan)
    Xp = Pipeline(
        [("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]
    ).fit_transform(X)
    return Xp, feats


def kmeans_scan(Xp):
    print("  KMeans (n_init=10, random_state=42)")
    print(f"  {'K':>3}  {'silhouette':>10}  {'davies_bouldin':>14}  {'inertia':>10}")
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xp)
        sil = silhouette_score(Xp, km.labels_)
        db = davies_bouldin_score(Xp, km.labels_)
        flag = "  <- current" if k == 4 else ""
        print(f"  {k:>3}  {sil:>10.3f}  {db:>14.3f}  {km.inertia_:>10.0f}{flag}")


def dbscan_scan(Xp):
    print("  DBSCAN")
    print(f"  {'eps':>4}  {'min_samples':>11}  {'clusters':>8}  {'noise':>6}  {'silhouette':>10}")
    for eps in EPS_RANGE:
        for ms in MIN_SAMPLES_RANGE:
            labels = DBSCAN(eps=eps, min_samples=ms).fit(Xp).labels_
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            n_noise = int((labels == -1).sum())
            mask = labels != -1
            if n_clusters >= 2 and mask.sum() > n_clusters:
                sil = f"{silhouette_score(Xp[mask], labels[mask]):.3f}"
            else:
                sil = "n/a"
            flag = "  <- current" if (eps == 1.5 and ms == 5) else ""
            print(f"  {eps:>4.1f}  {ms:>11}  {n_clusters:>8}  {n_noise:>6}  {sil:>10}{flag}")


def scan(name, csv, id_cols):
    df = pd.read_csv(MART_DIR / csv)
    Xp, feats = preprocess(df, id_cols)
    print("=" * 72)
    print(f"{name}: {len(df)} rows, {len(feats)} features")
    print(f"features: {feats}")
    print("-" * 72)
    kmeans_scan(Xp)
    print("-" * 72)
    dbscan_scan(Xp)
    print("=" * 72)
    print()


if __name__ == "__main__":
    scan("capital_allocation", "mart_capital_allocation.csv", tca.ID_COLS)
    scan("company_health", "mart_company_health.csv", tch.ID_COLS)
