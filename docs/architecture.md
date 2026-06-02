# ARCHITECTURE


`-------------------------------------------------------------------------------------------------------------------------`


## FOLDER STRUCTURE
- data
  - edgar_cache
    - companyfacts (1 json per company, get_company_facts results)
    - submissions (1 json per company, get_submissions results)
    - tickers (1 json, get_company_tickers results)
    - preprocess (company_1000.csv preprocess output / fetch + dim_company input; company_remaining.csv unmatched companies)
    - fetch_failed.csv (fetch failures)
  - warehouse (one CSV per table, full overwrite per run)
    - raw (load output: raw_companies, raw_filings, raw_company_facts)
    - dim (dim_company, dim_concept, dim_form, dim_period)
    - int (int_financial, int_filing)
    - mart (mart_revenue, mart_restatement, mart_capital_allocation, mart_company_health)
    - ml (train output: predictions + cluster assignments + ml_metrics.csv)
  - russel_1000 (russel_1000.xlsx, manual input, used by preprocess to trim to 1000 companies)
- docs (md files, pptx files)
- logs (.log files written by AppLogger)
- scripts (one-off scripts)
  - diag_temp.py
- src
  - edgar
    - config (Config class)
      - config.py
    - shared (EdgarClient, AppLogger, csv helpers)
      - edgar_client.py
      - logger.py
      - csv.py (read_csv, read_csv_incrementally, write_csv, write_csv_incrementally)
    - orchestration (Orchestration Layer)
      - pipeline.py
    - ingestion (Raw Data Layer)
      - preprocess.py
      - fetch.py
      - load.py
    - transformation
      - dim_company.py, dim_concept.py, dim_form.py, dim_period.py
      - int_financial.py, int_filing.py
      - mart_revenue.py, mart_restatement.py, mart_capital_allocation.py, mart_company_health.py
      - transform.py (orchestrates the above in FK order)
    - ml (ML Layer)
      - train_revenue.py, train_restatement.py, train_capital_allocation.py, train_company_health.py
      - train_metrics.py (aggregates the 4 tasks' returned metrics → ml_metrics.csv)
      - train.py (orchestrates the 4 task modules)
- pyproject.toml
- requirements.txt
- .env
- .env.example
- .gitignore
- .venv
- run.py (cli entry point)


`-------------------------------------------------------------------------------------------------------------------------`


## PIPELINE

### CLI
1. python run.py pipeline --preprocess --fetch --load --transform --train
   1. canonical order is forced
   2. pipeline => runs the whole pipeline in order
   3. pipeline --fetch => only runs fetch
   4. pipeline --fetch --load => runs fetch + load
   5. pipeline --fetch --transform => runs fetch + transform
   6. pipeline --transform --fetch => runs fetch + transform
2. python run.py diag-temp

### PIPELINE ORDER
1. ingestion
   1. preprocess
      1. read local 1000 company xlsx for ticker
      2. normalize tickers for join (BRKB → BRK-B)
      3. join to edgar api company ticker json for cik
      4. write company_1000.csv with ticker+cik+sector
      5. writes company_remaining.csv => unmatched companies
   2. fetch
      1. fetch from edgar api, write to local json
      2. edgar_client parameter use_cache=False is set, so it uses api
      3. writes fetch_failed.csv
   3. load (verbatim flatten of cached JSON → CSV; CONFIG_MODEL dict at top of load.py is the schema source of truth)
      1. _load_companies — submissions/CIK*.json top-level → raw_companies.csv (987 rows)
      2. _load_submissions — submissions/CIK*.json filings.recent (parallel arrays) → raw_filings.csv (~970k rows)
      3. _load_company_facts — companyfacts/CIK*.json walked → raw_company_facts.csv (~21.8M rows, chunked per-CIK via write_csv_incrementally to avoid a 10-15GB in-memory DataFrame)
      4. column names preserved verbatim from EDGAR JSON (camelCase)
      5. universe filter is implicit (fetch only cached the ~1k CIKs); no time/form/unit/concept filter at raw
2. transform (raw → dim → int → mart; runs in FK order via transform.py). Each module is _extract/_transform/_load with a CONFIG_MODEL dict at the top.
   1. dims — catalog every distinct value in raw and flag the analytical subset with is_included.
      1. dim_company — raw_companies joined to IWB (company_1000.csv) for sector; one row per cik
      2. dim_concept — distinct (taxonomy, concept) in raw facts; concept_mapping flags included tags and assigns normalized_concept + statement (IS/BS/CF)
      3. dim_form — distinct forms in raw_filings; form_mapping flags 10-K/10-Q/10-K-A/10-Q-A and annual/quarterly/amendment
      4. dim_period — distinct (start, end) windows; duration_type (instant/quarter/semi/ytd9/annual); is_included = end in [2015 .. today+1y]
   2. int — read raw facts/filings + dims directly; filter on the dims' is_included flags (int_financial: concept/period/form; int_filing: form only — its time filter is filing_date year ≥ 2015 applied directly, no dim_period join), canonicalize, and denormalize company attrs so marts read int alone.
      1. int_financial — one value per (cik, normalized_concept, period). Filter (concept/period/form is_included + unit whitelist + non-empty fp), then (a) concept coalescing (most-prevalent raw tag per filing) and (b) restatement (latest filed wins via raw `filed`; was_restated flags differing values, n_versions counts the contributing filings — both int-only, not carried to marts). This is where XBRL tag inconsistency is resolved.
      2. int_filing — one row per filing (included forms, filing_date year ≥ 2015 — applied directly, no dim_period join, no upper bound); is_annual/is_quarterly/is_amendment joined from dim_form; was_restated = an amendment exists for the same (cik, report_date); filing_lag.
   3. marts — reshape int into one table per ML task (revenue panel, filing features, capital-allocation, company-health).
3. train (mart → ml; one module per task via train.py)
   1. reads marts only; standard preprocessing (impute, scale, one-hot sector)
   2. writes predictions / cluster assignments to data/warehouse/ml
   3. each task run() returns its headline metrics; train_metrics aggregates them into ml_metrics.csv (task, metric, value) so Power BI metric cards are data-driven (ROC-AUC + silhouette/davies_bouldin/inertia otherwise live only in the log)
   4. Task 1 revenue regression · Task 2 restatement classification · Task 3 capital-allocation clustering · Task 4 company-health clustering

### DATA FLOW

layer read contract:
- dim reads raw (dim_company also joins company_1000 from edgar_cache/preprocess)
- int reads raw + dim
- mart reads int only
- ml reads mart only
- powerbi reads mart/ml only — exception: the Financial Data page also reads int_financial + int_filing directly

module reads-from:

preprocess               <- russel_1000.xlsx, edgar api
fetch                    <- company_1000, edgar api
load                     <- edgar_cache (submissions, companyfacts)

dim_company              <- raw_companies, company_1000
dim_concept              <- raw_company_facts
dim_form                 <- raw_filings
dim_period               <- raw_company_facts

int_financial            <- raw_company_facts, dim_concept, dim_period, dim_form, dim_company
int_filing               <- raw_filings, dim_form, dim_company

mart_revenue             <- int_financial
mart_restatement         <- int_filing, int_financial
mart_capital_allocation  <- int_financial
mart_company_health      <- int_financial

train_revenue            <- mart_revenue
train_restatement        <- mart_restatement
train_capital_allocation <- mart_capital_allocation
train_company_health     <- mart_company_health
train_metrics            <- the four train run() returns (in-memory, not a layer read) → ml_metrics.csv

no deviations: every module reads only its allowed upstream layers (company attrs are denormalized into int so marts need no dim read).


`-------------------------------------------------------------------------------------------------------------------------`


## INFRASTRUCTURE

### CONFIG
1. Centralized Config class, initialized at run.py passed to pipeline.py to consumers
2. folder paths, file paths, logging config, edgar api endpoints, edgar api configs, .env reads for apis

### LOGGER
1. Centralized AppLogger class, initialized at run.py passed to pipeline.py to consumers
2. one log file per run (`run_<timestamp>.log` under logs/); retention prunes to the newest `log_max_files` (60), so old runs self-clean

### EDGAR CLIENT
1. EdgarClient class, initialized at pipeline.py passed to consumers
2. public methods
   1. get_company_tickers
      1. used by preprocess
      2. ticker + cik + title data
      3. endpoint: `https://www.sec.gov/files/company_tickers.json`
   2. get_submissions
      1. used by fetch
      2. filing history + company metadata
      3. endpoint: `https://data.sec.gov/submissions/CIK{padded_cik}.json`
   3. get_company_facts
      1. used by fetch
      2. xbrl facts: tagged financial data points (e.g. us-gaap:Revenues = 394B for FY2023) — concept, value, period, unit, filing ref
      3. endpoint: `https://data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json`
3. public methods use use_cache parameter, if true uses local json and not api.
4. User-Agent is required by the api, defined in .env
5. To avoid blocked, api rate limit is set at config.
6. Retry mechanic with exponential backoff is implemented, constants set at config.


`-------------------------------------------------------------------------------------------------------------------------`


## PROJECT STEPS
1. RAW DATA
   1. preprocess
   2. fetch
   3. load
2. EDA
   1. python run.py diag-temp
   2. diag-temp is a scratch diagnostic subcommand, now a no-op stub; its chunked scan of raw (dim/int cardinalities, concept/unit/form/fp breakdowns, garbage end dates, null starts) informed the dim/int filter design
3. TRANSFORMATION
   1. raw => dim => int => mart
4. ML
   1. mart => ml
5. POWERBI
   1. read from local mart + ml (+ int_financial, int_filing for the Financial Data page)


`-------------------------------------------------------------------------------------------------------------------------`


## BUSINESS LOGIC
1. company universe — S&P 500 + Russell 1000 (~1k) via iShares IWB membership
   1. survivorship bias: current membership only, so exited companies (M&A, bankruptcy) are missing; affects Task 1 (revenue) more than Task 2 (restatements)
2. row filters at dim/int (raw stays verbatim)
   1. time window — end in [2015 .. today+1y]; upper bound drops garbage end dates (up to 2199)
   2. forms — 10-K, 10-Q, 10-K/A, 10-Q/A only
   3. units — USD, USD/shares, shares, pure
   4. fp — drop empty/None
   5. taxonomy — us-gaap only; dei/srt/etc. concepts dropped
3. concept normalization — many raw XBRL tags → one normalized_concept (e.g. Revenues / RevenueFromContractWithCustomerExcludingAssessedTax → revenue); resolves tag inconsistency, the highest-leverage data quality issue
4. period classification — duration_type by day-count: instant (no start), quarter ≤100d, semi ≤195, ytd9 ≤285, annual ≤380, else other
5. restatement handling — int_financial keeps the latest-filed value per (cik, normalized_concept, period); was_restated flags a value that changed across filings
   1. Task 2 target = amendment-existence: a 10-K/A or 10-Q/A filed for the same cik+report_date. Alternative: value-change via int_financial.was_restated
   2. mart_restatement joins each original filing to a financial snapshot from int_financial at (cik, report_date): instant balance-sheet items plus flows matched to the filing cadence — annual for 10-K, quarter for 10-Q (so 10-Q rows carry net_income/revenue instead of NaN; FY-end ties prefer annual). Ratios (leverage, debt_to_equity, current_ratio, roa, net_margin) are inf→NaN'd then winsorized to [1%, 99%] — near-zero equity/revenue/current-liabilities denominators otherwise emit inf (breaks the classifier) and extreme finite values StandardScaler can't tame
   3. the classifier uses a minimal feature set (filing_lag_days, total_assets, net_income, leverage); adding the margin/ratio columns moved AUC <0.01, so they stay mart-only (PBI) and out of the model. Same for mart_revenue margins on Task 1
6. revenue panel — uses discrete quarterly revenue (duration_type == quarter) only
   1. growth (QoQ, YoY, next-Q target) is computed only between genuinely adjacent periods — gated on day-distance to the comparison row (≈1 quarter for QoQ/target, ≈1 year for YoY); jumps across a missing quarter or overlapping period become NaN instead of a spurious 100x growth
   2. target is winsorized to [1%, 99%] so a few micro-denominator quarters don't dominate OLS squared loss
   3. KNOWN GAP: Q4 isn't tagged discretely (only inside the annual 10-K). Deriving it as FY − (Q1+Q2+Q3) was tested but pushed test R² negative — the derived rows add seasonal Q4/Q1 swings a linear model can't fit (plus restatement-vintage noise from the subtraction), so the panel stays interim-only (Q1–Q3). Revisit only with a seasonality-aware model
   4. margin columns (gross/operating/net) are PBI context, not model features; gross_profit falls back to revenue − cogs when GrossProfit isn't separately tagged
7. clustering marts (Tasks 3/4) — one row per company, latest FY / period (snapshot, not panel). Both winsorize their clustering features to [1%, 99%]: capital-allocation ratios are scaled by |operating cash flow| (abs, so a negative CFO doesn't sign-flip the ratios; zero CFO → NaN, near-zero blows them to 60x+); company-health uses six distress ratios (debt_to_assets, debt_to_equity, current_ratio, roa, interest_coverage, cfo_to_debt), which blow up on near-zero equity/current-liabilities/interest-expense/debt. Unwinsorized, KMeans collapses into one blob + outlier singletons (a false-high silhouette); absolute-$ and PBI-context columns stay unclipped.
   1. cluster count (K) — silhouette and Davies-Bouldin both peak at K=2, but that is degenerate: K=2 isolates one outlier speck from one blob (sizes 960/9 capital-allocation, 968/2 company-health), the same false-high silhouette winsorization targets. K is therefore not chosen by maximizing the metric; K=4 is the most balanced tested partition (817/122/23/7 and 622/324/22/2) and is the interpretability choice, picked from a K 2–10 and DBSCAN eps × min_samples sweep.
   2. DBSCAN — after winsorizing + scaling, the features are one dense cloud with scattered outliers (worst case for density clustering). At eps=1.5/min_samples=5, and across the full grid, DBSCAN returns a single ~900-point cluster plus 37–75 noise points (capital-allocation collapses to exactly one cluster). It produces no usable segmentation, so it functions as outlier detection — the noise points flag the unusual companies — not as a second clustering view alongside KMeans.


`-------------------------------------------------------------------------------------------------------------------------`


## ML FLOW

common: every task reads its mart only, builds the sklearn pipeline (impute → scale → encode) inside a ColumnTransformer/Pipeline so train-set statistics never leak into test, fits, scores, then writes predictions/cluster-assignments to data/warehouse/ml. run() returns headline metrics for train_metrics.

1. regression - revenue (train_revenue.py)
   1. read — mart_revenue.csv; drop rows with null target_next_q_growth
   2. split — time-based: train end_date < 2023-01-01, test end_date >= 2023-01-01 (no random split; mirrors forecasting forward in time)
   3. encode — NUM [revenue, revenue_qoq_growth, revenue_yoy_growth] → median impute → StandardScaler; CAT [sector] → OneHotEncoder(handle_unknown="ignore")
   4. train — LinearRegression fit on train
   5. test — predict on test; R², RMSE, MAE
   6. write — pred_revenue.csv (ids + actual target + prediction)
2. classification - restatement (train_restatement.py)
   1. read — mart_restatement.csv; X = NUM + CAT, y = was_restated (int), groups = cik
   2. split — GroupShuffleSplit(test_size=0.25, random_state=42) grouped by cik so one company can't sit in both train and test (leakage guard)
   3. encode — NUM [filing_lag_days, total_assets, net_income, leverage] → median impute → StandardScaler; CAT [sector, form] → OneHotEncoder(handle_unknown="ignore")
   4. train — LogisticRegression(class_weight="balanced", max_iter=1000); balanced weighting counters the ~1.6% positive rate
   5. test — predict labels + proba; ROC-AUC (headline, threshold-free) + P@k (R-precision over the k actual positives; k emitted as test_positives_k) + precision/recall/F1 at the 0.5 cutoff (read low purely from prevalence + balancing, not ranking ability)
   6. write — pred_restatement.csv (ids + actual + proba)
3. clustering - capital allocation (train_capital_allocation.py)
   1. read — mart_capital_allocation.csv
   2. features — all columns except ID_COLS (ids + raw-$ magnitudes are interpretation context, not features); no train/test split (unsupervised, whole dataset)
   3. encode — inf → NaN → median impute → StandardScaler
   4. fit — KMeans(n_clusters=4, n_init=10, random_state=42) + DBSCAN(eps=1.5, min_samples=5)
   5. score — silhouette, Davies-Bouldin, inertia on KMeans labels (DBSCAN labels unscored — at the tuned eps it collapses to one dense cluster + noise, so it serves as outlier detection; see Business Logic §7)
   6. write — cluster_capital_allocation.csv (full mart + kmeans_cluster + dbscan_cluster)
4. clustering - financial health (train_company_health.py)
   1. read — mart_company_health.csv
   2. features — all columns except ID_COLS (ids + absolute-$ magnitudes + net_margin/equity_ratio are context); feature set is the six distress ratios; no train/test split (unsupervised)
   3. encode — inf → NaN → median impute → StandardScaler
   4. fit — KMeans(n_clusters=4, n_init=10, random_state=42) + DBSCAN(eps=1.5, min_samples=5)
   5. score — silhouette, Davies-Bouldin, inertia on KMeans labels (DBSCAN labels unscored — at the tuned eps it collapses to one dense cluster + noise, so it serves as outlier detection; see Business Logic §7)
   6. write — cluster_company_health.csv (full mart + kmeans_cluster + dbscan_cluster)


`-------------------------------------------------------------------------------------------------------------------------`

## POWERBI

Card measure (one per metric, in `_measures`):
`<Metric> = CALCULATE(SUM(ml_metrics[value]), ml_metrics[task]="<task>", ml_metrics[metric]="<metric>")`

No relationships: each visual's slicers come from the same table as the visual. Cluster pages: set `kmeans_cluster` to Don't summarize (category), and rename 0–3 to the personas in the page text box.

### PAGE 1 — architecture
- text box (overview): "SEC EDGAR financial analysis — ~1,000 S&P 500 / Russell 1000 companies, ~10 years. 21.8M raw XBRL facts distilled to 1.5M canonical financial values feeding four ML models: revenue regression, restatement classification, and two clustering tasks. Universe = current iShares IWB membership, so exited companies (M&A, bankruptcy) are absent — survivorship bias."
- text box: DATA SOURCE — EDGAR endpoints + manual IWB xlsx
- text box: DATA FLOW — preprocess → fetch → load → dim → int → mart → ml
- cards (typed): companies 987 · filings 970,892 (raw) · facts 21,782,145 · canonical 1,501,984

### PAGE 2 — financial data
tables: int_financial, int_filing
- text box (explanation): "The canonical cleaned data every mart and model reads from. 21.8M raw XBRL facts are distilled to 1,501,984 values — one per (company, normalized_concept, period) — after resolving the two biggest data-quality issues: inconsistent XBRL tags (many raw tags → one normalized_concept) and restatements (latest-filed value wins; was_restated flags the changes). int_filing is one row per filing (34,171 after the form + 2015-onward filters)."
- cards (computed): canonical values = COUNTROWS(int_financial) (1,501,984) · companies = DISTINCTCOUNT(int_financial[cik]) · concepts = DISTINCTCOUNT(int_financial[normalized_concept]) · filings = COUNTROWS(int_filing) (34,171)
- table — int_financial · Columns: ticker, name, sector, statement, normalized_concept, fy, end_date, val, unit, was_restated, n_versions
- bar — int_financial · Axis: statement (IS/BS/CF) · Values: Count of val (fact coverage by statement)
- bar — int_financial · Axis: normalized_concept · Values: Count of val (most-populated line items)
- table — int_filing · Columns: ticker, name, sector, form, report_date, filing_date, filing_lag_days, is_amendment, was_restated
- column — int_filing · X axis: report_year · Values: Count of accession_number (filing volume over time)
- bar — int_filing · Axis: form · Values: Count of accession_number (10-K / 10-Q / amendment mix)
- slicers — int_financial: sector, statement, normalized_concept, duration_type, fy, ticker
- slicers — int_filing: sector, form, report_year, was_restated
- no relationships: int_financial visuals + slicers read int_financial, int_filing's read int_filing (same rule as the rest of the report)

### PAGE 3 — regression · revenue
tables: mart_revenue, pred_revenue, ml_metrics
- text box (explanation): "Can next-quarter revenue growth be predicted from a company's recent growth and sector? Linear regression on ~26k company-quarters, trained pre-2023 and tested on 2023+. Finding: quarter-to-quarter growth is near-unpredictable (low R²) — the model reverts to the mean, so revenue behaves close to a random walk. The descriptive trend (COVID dip and recovery) is the real story."
- line — mart_revenue · X axis: end_year, end_quarter · Values: Avg revenue_qoq_growth, Avg revenue_yoy_growth
- scatter — pred_revenue · X: target_next_q_growth (Don't summarize) · Y: prediction (Don't summarize) · Details: ticker, period_id
- bar — mart_revenue · Axis: sector · Values: Avg target_next_q_growth
- column (histogram) — mart_revenue · X axis: target_next_q_growth (bins) · Values: Count
- table — mart_revenue · Columns: ticker, name, sector, revenue, revenue_yoy_growth
- slicers — mart_revenue: sector, end_year, end_quarter, ticker
- cards — task=revenue: r2, rmse, mae

### PAGE 4 — classification · restatement
tables: mart_restatement, pred_restatement, ml_metrics
- text box (explanation): "Which filings are most likely to be restated? Logistic regression scores restatement risk across ~34k filings (only ~1.6% are restated). With balanced class weighting it ranks risk well (ROC-AUC ≈ 0.75): restated filings score higher probabilities, and 10-K annual reports are restated far more often than 10-Qs. Use it to prioritize which filings to review, not as a hard yes/no."
- column (histogram) — pred_restatement · X axis: proba (bins) · Values: Count · Legend: actual
- bar — mart_restatement · Axis: form · Values: Avg was_restated
- bar — mart_restatement · Axis: sector · Values: Avg was_restated
- matrix — pred_restatement · Rows: actual · Columns: predicted (new column = IF(proba>=0.5,1,0)) · Values: Count of accession_number
- table — pred_restatement (sort proba desc) · Columns: ticker, name, form, report_date, proba, actual
- slicers — pred_restatement: sector, form (filter the model visuals; the two rate bars stay unfiltered population context)
- cards — task=restatement: roc_auc, recall, precision, f1, precision_at_k (test_positives_k = k also in ml_metrics as P@k context; not carded)

### PAGE 5 — clustering · capital allocation
tables: cluster_capital_allocation, ml_metrics
- text box (explanation): "How do companies deploy their operating cash flow? K-means groups ~1,000 companies by capex, buybacks, dividends, acquisitions and debt activity (each scaled to operating cash flow). Most fall into one 'typical' allocation profile, with smaller distinct groups: buyback-led returners, debt-funded acquirers, and heavy debt-refinancers."
- matrix — Rows: kmeans_cluster · Values: Avg capex_to_cfo, buybacks_to_cfo, dividends_paid_to_cfo, acquisitions_to_cfo, debt_issued_to_cfo, debt_repaid_to_cfo, share_based_comp_to_cfo
- column — X axis: kmeans_cluster · Values: Count of cik
- scatter — X: buybacks_to_cfo (Don't summarize) · Y: acquisitions_to_cfo (Don't summarize) · Legend: kmeans_cluster · Details: ticker
- column — X axis: kmeans_cluster · Values: Avg total_payout, Avg fcf, Avg net_debt_change
- stacked column — X axis: kmeans_cluster · Legend: sector · Values: Count of cik
- slicers — sector, kmeans_cluster, exchange, dbscan_cluster (-1 = outliers)
- cards — task=capital_allocation: silhouette, davies_bouldin, inertia

### PAGE 6 — clustering · financial health
tables: cluster_company_health, ml_metrics
- text box (explanation): "How financially healthy are these companies? K-means groups ~1,000 companies on six distress ratios (leverage, liquidity, profitability, coverage). The result is a clear health gradient — low-leverage / high-coverage, levered / capital-intensive (utilities and real estate), and high-leverage / negative-equity — plus a small set of outliers."
- scatter — X: debt_to_assets (Don't summarize) · Y: current_ratio (Don't summarize) · Legend: kmeans_cluster · Details: ticker
- matrix — Rows: kmeans_cluster · Values: Avg debt_to_assets, debt_to_equity, current_ratio, roa, interest_coverage, cfo_to_debt
- stacked column — X axis: kmeans_cluster · Legend: sector · Values: Count of cik
- column — X axis: kmeans_cluster · Values: Avg total_assets, Avg total_liabilities, Avg net_income
- table — cluster_company_health · Columns: ticker, name, sector, debt_to_assets, debt_to_equity, current_ratio
- slicers — sector, kmeans_cluster, exchange, state_of_incorporation, dbscan_cluster (-1 = outliers)
- cards — task=company_health: silhouette, davies_bouldin, inertia


`-------------------------------------------------------------------------------------------------------------------------`

## REMAINING TODO
1. understand the code
2. code and doc review and cleanup
3. powerbi



