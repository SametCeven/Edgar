import numpy as np
from edgar.config import Config
from edgar.shared import AppLogger, read_csv, write_csv
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

NUM = ["revenue", "revenue_qoq_growth", "revenue_yoy_growth"]
CAT = ["sector"]
TARGET = "target_next_q_growth"
SPLIT_DATE = "2023-01-01"


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Task 1: revenue regression (time split train<2023 / test>=2023)")
    df = read_csv(
        logger, config.mart_dir / "mart_revenue.csv", parse_dates=["end_date"]
    )
    df = df.dropna(subset=[TARGET])
    train = df[df["end_date"] < SPLIT_DATE]
    test = df[df["end_date"] >= SPLIT_DATE]

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
    model = Pipeline([("pre", pre), ("lr", LinearRegression())])
    model.fit(train[NUM + CAT], train[TARGET])
    pred = model.predict(test[NUM + CAT])

    r2 = r2_score(test[TARGET], pred)
    rmse = mean_squared_error(test[TARGET], pred) ** 0.5
    mae = mean_absolute_error(test[TARGET], pred)
    logger.info(f"  R2={r2:.3f} RMSE={rmse:.3f} MAE={mae:.3f}")
    out = test[
        ["cik", "ticker", "name", "sector", "period_id", "end_date", TARGET]
    ].copy()
    out["prediction"] = np.asarray(pred)
    write_csv(logger, config.ml_dir / "pred_revenue.csv", out)
    logger.info("=" * 60)
    return [
        {"task": "revenue", "metric": "r2", "value": r2},
        {"task": "revenue", "metric": "rmse", "value": rmse},
        {"task": "revenue", "metric": "mae", "value": mae},
    ]
