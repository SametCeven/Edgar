# ARCHITECTURE


`-------------------------------------------------------------------------------------------------------------------------`


## FOLDER STRUCTURE
- data
  - edgar_cache
    - companyfacts (1 json per company, get_company_facts results)
    - submissions (1 json per company, get_submissions results)
    - tickers (1 json, get_company_tickers results)
    - preprocess (company_1000.csv preprocess output / load input; company_remaining.csv unmatched companies)
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

### PIPELINE ORDER (DONE SO FAR)
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
   2. int — read raw facts/filings + dims directly; filter on the dims' is_included flags, canonicalize, and denormalize company attrs so marts read int alone.
      1. int_financial — one value per (cik, normalized_concept, period). Filter (concept/period/form is_included + unit whitelist + non-empty fp), then (a) concept coalescing (most-prevalent raw tag per filing) and (b) restatement (latest filed wins via raw `filed`; was_restated flags differing values). This is where XBRL tag inconsistency is resolved.
      2. int_filing — one row per filing (included forms within the time window); is_annual/is_quarterly/is_amendment joined from dim_form; was_restated = an amendment exists for the same (cik, report_date); filing_lag.
   3. marts — reshape int into one table per ML task (revenue panel, filing features, capital-allocation, company-health).
3. train (mart → ml; one module per task via train.py)
   1. reads marts only; standard preprocessing (impute, scale, one-hot sector)
   2. writes predictions / cluster assignments to data/warehouse/ml
   3. each task run() returns its headline metrics; train_metrics aggregates them into ml_metrics.csv (task, metric, value) so Power BI metric cards are data-driven (ROC-AUC + silhouette/davies_bouldin/inertia otherwise live only in the log)
   4. Task 1 revenue regression · Task 2 restatement classification · Task 3 capital-allocation clustering · Task 4 company-health clustering

### DATA FLOW

layer read contract:
- dim reads raw only
- int reads raw + dim
- mart reads int only
- ml reads mart only
- powerbi reads mart/ml only

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
   2. chunked scan of raw to validate dim/int cardinalities and surface dirt (concept/unit/form/fp breakdowns, garbage end dates, null starts) before transform is built on it
3. TRANSFORMATION
   1. raw => dim => int => mart
4. ML
   1. mart => ml
5. POWERBI
   1. read from local mart + ml


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
   2. mart_restatement ratios (leverage, debt_to_equity, current_ratio, roa, net_margin) are inf→NaN'd then winsorized to [1%, 99%] — near-zero equity/revenue/current-liabilities denominators otherwise emit inf (breaks the classifier) and extreme finite values StandardScaler can't tame
   3. the classifier uses a minimal feature set (filing_lag_days, total_assets, net_income, leverage); adding the margin/ratio columns moved AUC <0.01, so they stay mart-only (PBI) and out of the model. Same for mart_revenue margins on Task 1
6. revenue panel — uses discrete quarterly revenue (duration_type == quarter) only
   1. growth (QoQ, YoY, next-Q target) is computed only between genuinely adjacent periods — gated on day-distance to the comparison row (≈1 quarter for QoQ/target, ≈1 year for YoY); jumps across a missing quarter or overlapping period become NaN instead of a spurious 100x growth
   2. target is winsorized to [1%, 99%] so a few micro-denominator quarters don't dominate OLS squared loss
   3. KNOWN GAP: Q4 isn't tagged discretely (only inside the annual 10-K). Deriving it as FY − (Q1+Q2+Q3) was tested but pushed test R² negative — the derived rows add seasonal Q4/Q1 swings a linear model can't fit (plus restatement-vintage noise from the subtraction), so the panel stays interim-only (Q1–Q3). Revisit only with a seasonality-aware model
7. clustering marts (Tasks 3/4) — one row per company, latest FY / period (snapshot, not panel); capital-allocation features scaled by operating cash flow, then winsorized to [1%, 99%] (near-zero CFO otherwise blows ratios up to 60x+ and collapses KMeans into one blob + outlier singletons)


`-------------------------------------------------------------------------------------------------------------------------`


## REMAINING TODO
1. understand the code
2. code and doc review and cleanup
3. powerbi
