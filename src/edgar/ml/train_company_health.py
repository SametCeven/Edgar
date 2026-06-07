import numpy as np
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import silhouette_score, davies_bouldin_score

# Clustering feature set: the six distress ratios. Everything else in the mart
# (absolute $ magnitudes, margins, ids) is PBI context, not a model input.
FEATURES = [
    "debt_to_assets",
    "debt_to_equity",
    "current_ratio",
    "roa",
    "interest_coverage",
    "cfo_to_debt",
]
K = 4


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Task 4: company health clustering (KMeans + DBSCAN)")
    df = read_csv(logger, config.mart_dir / "mart_company_health.csv")
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
    write_csv(logger, config.ml_dir / "cluster_company_health.csv", df)
    logger.info("=" * 60)
    return [
        {"task": "company_health", "metric": "silhouette", "value": sil},
        {"task": "company_health", "metric": "davies_bouldin", "value": db_score},
        {"task": "company_health", "metric": "inertia", "value": km.inertia_},
    ]
