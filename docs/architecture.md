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
  - russel_1000 (russel_1000.xlsx, manual input, used by preprocess to trim to 1000 companies)
- docs (md files, pptx files)
- logs (.log files written by AppLogger)
- scripts (one-off scripts)
  - diag_temp.py
- src
  - edgar
    - config (Config class)
      - config.py
    - shared (EdgarClient, AppLogger classes)
      - edgar_client.py
      - logger.py
    - orchestration (Orchestration Layer)
      - pipeline.py
    - ingestion (Raw Data Layer)
      - preprocess.py
      - fetch.py
      - load.py
    - transformation
      - dim_*.py
      - fact_*.py
      - int_*.py
      - mart_*.py
      - transform.py
    - ml (ML Layer)
      - train.py
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

### DATA FLOW
1. raw (edgar api + local xlsx input file)
2. dim/fact
3. int
4. mart
5. ml
6. powerbi (mart + ml)


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
   1. python diag_temp
3. TRANSFORMATION
   1. raw => dim/fact => int => mart
4. ML
   1. mart => ml
5. POWERBI
   1. read from local mart + ml
