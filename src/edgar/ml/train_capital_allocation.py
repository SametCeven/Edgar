import numpy as np
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import silhouette_score, davies_bouldin_score

# Clustering feature set: cash deployment scaled by operating cash flow. The raw $
# magnitudes they derive from (capex, buybacks, ...) stay as PBI context, not inputs.
FEATURES = [
    "capex_to_cfo",
    "buybacks_to_cfo",
    "dividends_paid_to_cfo",
    "acquisitions_to_cfo",
    "debt_issued_to_cfo",
    "debt_repaid_to_cfo",
    "share_based_comp_to_cfo",
]
K = 4


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Task 3: capital allocation clustering (KMeans + DBSCAN)")
    df = read_csv(logger, config.mart_dir / "mart_capital_allocation.csv")
    X = df[FEATURES].replace([np.inf, -np.inf], np.nan)
    Xp = Pipeline(
        [("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]
    ).fit_transform(X)

    km = KMeans(n_clusters=K, n_init=10, random_state=42).fit(Xp)
    db = DBSCAN(eps=1.5, min_samples=5).fit(Xp)
    sil = silhouette_score(Xp, km.labels_)
    db_score = davies_bouldin_score(Xp, km.labels_)
    logger.info(
        f"  KMeans silhouette={sil:.3f} DB={db_score:.3f} inertia={km.inertia_:.0f}"
    )
    df["kmeans_cluster"], df["dbscan_cluster"] = km.labels_, db.labels_
    write_csv(logger, config.ml_dir / "cluster_capital_allocation.csv", df)
    logger.info("=" * 60)
    return [
        {"task": "capital_allocation", "metric": "silhouette", "value": sil},
        {"task": "capital_allocation", "metric": "davies_bouldin", "value": db_score},
        {"task": "capital_allocation", "metric": "inertia", "value": km.inertia_},
    ]
