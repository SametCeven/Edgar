import pandas as pd
from collections import defaultdict
from edgar.config import Config
from edgar.shared import AppLogger, read_csv_incrementally, write_csv

# fmt: off
CONFIG_MODEL = {
    "output_csv": "dim_concept.csv",
    "raw_source": "raw_company_facts.csv",
    "taxonomy": "us-gaap",
    "output_cols": [
        "concept_id",
        "taxonomy",
        "concept",
        "normalized_concept",
        "statement",
        "is_included",
        "n_rows",
        "n_companies",
    ],
    # (concept, normalized_concept, statement)
    "concept_mapping": [
        # --- Income statement (flows) ---
        ("Revenues", "revenue", "IS"),
        ("RevenueFromContractWithCustomerExcludingAssessedTax", "revenue", "IS"),
        ("RevenueFromContractWithCustomerIncludingAssessedTax", "revenue", "IS"),
        ("SalesRevenueNet", "revenue", "IS"),
        ("SalesRevenueGoodsNet", "revenue", "IS"),
        ("CostOfRevenue", "cogs", "IS"),
        ("CostOfGoodsSold", "cogs", "IS"),
        ("CostOfGoodsAndServicesSold", "cogs", "IS"),
        ("GrossProfit", "gross_profit", "IS"),
        ("OperatingExpenses", "operating_expenses", "IS"),
        ("SellingGeneralAndAdministrativeExpense", "sga_expense", "IS"),
        ("ResearchAndDevelopmentExpense", "rd_expense", "IS"),
        ("OperatingIncomeLoss", "operating_income", "IS"),
        ("NonoperatingIncomeExpense", "nonoperating_income", "IS"),
        ("InterestExpense", "interest_expense", "IS"),
        ("InterestExpenseDebt", "interest_expense", "IS"),
        ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "pretax_income", "IS"),
        ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments", "pretax_income", "IS"),
        ("IncomeTaxExpenseBenefit", "income_tax", "IS"),
        ("NetIncomeLoss", "net_income", "IS"),
        ("ProfitLoss", "net_income", "IS"),
        ("EarningsPerShareBasic", "eps_basic", "IS"),
        ("EarningsPerShareDiluted", "eps_diluted", "IS"),
        ("WeightedAverageNumberOfSharesOutstandingBasic", "shares_basic", "IS"),
        ("WeightedAverageNumberOfDilutedSharesOutstanding", "shares_diluted", "IS"),
        # --- Balance sheet (instant) ---
        ("Assets", "total_assets", "BS"),
        ("AssetsCurrent", "current_assets", "BS"),
        ("Liabilities", "total_liabilities", "BS"),
        ("LiabilitiesCurrent", "current_liabilities", "BS"),
        ("StockholdersEquity", "total_equity", "BS"),
        ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "total_equity", "BS"),
        ("RetainedEarningsAccumulatedDeficit", "retained_earnings", "BS"),
        ("CashAndCashEquivalentsAtCarryingValue", "cash_and_equivalents", "BS"),
        ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "cash_and_equivalents", "BS"),
        ("PropertyPlantAndEquipmentNet", "ppe_net", "BS"),
        ("Goodwill", "goodwill", "BS"),
        ("IntangibleAssetsNetExcludingGoodwill", "intangibles_net", "BS"),
        ("InventoryNet", "inventory", "BS"),
        ("AccountsReceivableNetCurrent", "accounts_receivable", "BS"),
        ("AccountsPayableCurrent", "accounts_payable", "BS"),
        ("LongTermDebtNoncurrent", "long_term_debt", "BS"),
        ("LongTermDebt", "long_term_debt", "BS"),
        ("LongTermDebtCurrent", "current_debt", "BS"),
        ("DebtCurrent", "current_debt", "BS"),
        ("ShortTermBorrowings", "current_debt", "BS"),
        # --- Cash flow (flows) ---
        ("NetCashProvidedByUsedInOperatingActivities", "cf_operating", "CF"),
        ("NetCashProvidedByUsedInInvestingActivities", "cf_investing", "CF"),
        ("NetCashProvidedByUsedInFinancingActivities", "cf_financing", "CF"),
        ("PaymentsToAcquirePropertyPlantAndEquipment", "capex", "CF"),
        ("PaymentsToAcquireBusinessesNetOfCashAcquired", "acquisitions", "CF"),
        ("PaymentsForRepurchaseOfCommonStock", "buybacks", "CF"),
        ("PaymentsOfDividendsCommonStock", "dividends_paid", "CF"),
        ("PaymentsOfDividends", "dividends_paid", "CF"),
        ("ProceedsFromIssuanceOfLongTermDebt", "debt_issued", "CF"),
        ("RepaymentsOfLongTermDebt", "debt_repaid", "CF"),
        ("ShareBasedCompensation", "share_based_comp", "CF"),
        ("DepreciationDepletionAndAmortization", "depreciation_amortization", "CF"),
        ("DepreciationAndAmortization", "depreciation_amortization", "CF"),
        ("Depreciation", "depreciation_amortization", "CF"),
        ("AmortizationOfIntangibleAssets", "depreciation_amortization", "CF"),
    ],
}
# fmt: on


def _extract(config: Config, logger: AppLogger) -> pd.DataFrame:
    logger.info("Started extract")
    path = config.raw_dir / CONFIG_MODEL["raw_source"]
    row_counts: defaultdict = defaultdict(int)
    cik_sets: defaultdict = defaultdict(set)
    for chunk in read_csv_incrementally(
        logger,
        path,
        usecols=["cik", "taxonomy", "concept"],
        dtype={"cik": "string", "taxonomy": "string", "concept": "string"},
    ):
        agg = chunk.groupby(["taxonomy", "concept"])["cik"].agg(["size", "unique"])
        for key, r in agg.iterrows():
            row_counts[key] += int(r["size"])
            cik_sets[key].update(r["unique"])
    df = pd.DataFrame(
        [(t, c, row_counts[(t, c)], len(cik_sets[(t, c)])) for (t, c) in row_counts],
        columns=["taxonomy", "concept", "n_rows", "n_companies"],
    )
    logger.info(f"dim_concept: {len(df):,} distinct (taxonomy, concept) in raw facts")
    logger.info("Completed extract")
    return df


def _transform(
    config: Config, logger: AppLogger, extracted: pd.DataFrame
) -> pd.DataFrame:
    logger.info("Started transform")
    wl = pd.DataFrame(
        CONFIG_MODEL["concept_mapping"],
        columns=["concept", "normalized_concept", "statement"],
    )
    wl["taxonomy"] = CONFIG_MODEL["taxonomy"]

    dupes = int(wl.duplicated(subset=["taxonomy", "concept"]).sum())
    if dupes:
        logger.warning(f"dim_concept: {dupes} duplicate (taxonomy, concept) in mapping")

    df = extracted.merge(wl, on=["taxonomy", "concept"], how="left")
    df["is_included"] = df["normalized_concept"].notna()

    found = set(
        zip(df.loc[df["is_included"], "taxonomy"], df.loc[df["is_included"], "concept"])
    )
    wl_keys = set(zip(wl["taxonomy"], wl["concept"]))
    missing = wl_keys - found
    if missing:
        logger.warning(
            f"dim_concept: {len(missing)} mapped concepts absent from facts: "
            f"{sorted(c for _, c in missing)}"
        )

    # deterministic surrogate key: included first (statement/normalized/concept),
    # then the rest by prevalence
    df = df.sort_values(
        ["is_included", "statement", "normalized_concept", "n_rows", "concept"],
        ascending=[False, True, True, False, True],
    ).reset_index(drop=True)
    df.insert(0, "concept_id", range(1, len(df) + 1))
    df = df[CONFIG_MODEL["output_cols"]]

    n_inc = int(df["is_included"].sum())
    n_norm = int(df.loc[df["is_included"], "normalized_concept"].nunique())
    logger.info(
        f"dim_concept: {len(df):,} catalogued; {n_inc} included → {n_norm} normalized"
    )
    logger.info("Completed transform")
    return df


def _load(config: Config, logger: AppLogger, df_transformed: pd.DataFrame) -> None:
    logger.info("Started load")
    write_csv(logger, config.dim_dir / CONFIG_MODEL["output_csv"], df_transformed)
    logger.info("Completed load")


def run(config: Config, logger: AppLogger):
    logger.info("=" * 60)
    logger.info("Started dim_concept")
    extracted = _extract(config, logger)
    df_transformed = _transform(config, logger, extracted)
    _load(config, logger, df_transformed)
    logger.info("Completed dim_concept")
    logger.info("=" * 60)
