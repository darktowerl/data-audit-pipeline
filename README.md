# Data Audit & Cleansing Pipeline

> Production-grade data quality framework for e-commerce data. Audits **1.55M rows** across 9 related tables, catches **2,167 data quality issues** through Great Expectations and custom multi-table checks, and runs cleansing with explicit strategy per issue type.

![Python](https://img.shields.io/badge/python-3.13-blue.svg)
![Great Expectations](https://img.shields.io/badge/great__expectations-1.17-orange.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)

---

## Why this exists

Real-world e-commerce data is messy. Marketplace integrations break silently, ETL jobs drop records, and dimensions creep in with zeros, nulls, and duplicates. Before any analytics, ML model, or financial report can be trusted, somebody has to answer the boring question first: **what fraction of these rows are usable?**

This pipeline answers that question automatically on the Brazilian e-commerce dataset (Olist, 100k orders across 9 related tables), then takes the next step — cleansing — with an explicit strategy for every category of defect rather than a single `dropna()` swipe.

## Results

| Metric                            | Value         |
| --------------------------------- | ------------- |
| Tables audited                    | 9             |
| Total rows analyzed               | **1,550,851** |
| Great Expectations defined        | ~30 across 5 suites |
| Custom multi-table checks         | 10            |
| **Data quality issues found**     | **2,167**     |
| Issues resolved by cleansing      | 2,159         |
| Issues remaining (upstream bugs)  | 8             |
| Rows removed (duplicates + invalid) | 262,658     |
| Final Data Quality Score          | **99.999%**   |

The 8 remaining issues are intentional. They flag `order_status = 'delivered'` rows that lack a delivery date — an inconsistency the cleansing layer refuses to silently mask, because the right fix lives upstream in the source system.

## Architecture

```
                  data/raw/  (Olist CSVs)
                       |
                       v
              +-------------------+
              |    Profiling      |   notebook 01: schema + nulls + outliers
              +-------------------+
                       |
                       v
              +-------------------+
              |  Great Expecta-   |   notebook 02 + gx/
              |  tions (5 suites) |   ~30 expectations, HTML Data Docs
              +-------------------+
                       |
                       v
              +-------------------+
              |  Custom Checks    |   src/custom_checks.py
              |  (cross-table,    |   conditional, FK, date order,
              |   conditional)    |   referential completeness
              +-------------------+
                       |
                       v
              +-------------------+
              |  Cleansing        |   src/cleanser.py
              |  (typed strategy  |   coerce / fill / dedupe / filter
              |   per defect)     |
              +-------------------+
                       |
                       v
                data/processed/  (cleansed CSVs)
```

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/<your_username>/data-audit-pipeline.git
cd data-audit-pipeline
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt

# 2. Download Olist dataset from Kaggle into data/raw/
#    https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

# 3. Run end-to-end
python main.py

# 4. View interactive Great Expectations report
jupyter lab notebooks/02_build_expectations.ipynb
# (run the final cell — opens Data Docs in browser)
```

## Sample findings

A selection of issues the pipeline catches:

| Table           | Column                | Issue                              | Action               |
| --------------- | --------------------- | ---------------------------------- | -------------------- |
| `geolocation`   | (all)                 | 261,831 full-row duplicates (26%)  | `drop_duplicates`    |
| `order_reviews` | `review_id`           | 814 duplicate primary keys         | `keep_first`         |
| `order_items`   | `price`               | Non-positive prices                | Filter out           |
| `order_payments`| `payment_type`        | 3 rows with `'not_defined'`        | Filter out           |
| `order_payments`| `payment_value`       | 9 rows with `0.0` (fraud signal)   | Filter + log         |
| `products`      | `product_category_name` | 610 nulls                        | Fill `'unknown'`     |
| `products`      | `product_weight_g`    | Zero values                        | Filter out           |
| `orders`        | dates (multi-column)  | Carrier date < approved date       | Flag, escalate       |
| `orders`        | `order_status` ↔ dates| 8 'delivered' without date         | Flag, no autofix     |

## Tech stack

- **Python 3.13** — runtime
- **pandas 2.3** — data manipulation
- **Great Expectations 1.17** — declarative data validation, HTML Data Docs
- **pytest** — unit tests for cleansing and check modules
- **Jupyter** — exploratory notebooks (profiling, suite building)

## Project layout

```
data-audit-pipeline/
├── main.py                   # entry point: load → check → cleanse → save → report
├── src/
│   ├── cleanser.py           # type-coercion, dedup, null handling, filtering
│   └── custom_checks.py      # conditional / cross-table / date-order checks
├── notebooks/
│   ├── 01_data_profiling.ipynb
│   ├── 02_build_expectations.ipynb
│   └── 03_custom_checks_and_cleansing.ipynb
├── tests/
│   ├── test_cleanser.py
│   └── test_custom_checks.py
├── gx/                       # Great Expectations project (auto-generated)
├── data/
│   ├── raw/                  # Olist CSVs (gitignored)
│   └── processed/            # cleansed CSVs (gitignored)
├── requirements.txt
└── README.md
```

## Design notes

A few opinions baked into this codebase that are worth calling out, because they're what an interviewer might ask about.

**Validation and cleansing are separate stages.** Validation answers *what's wrong*; cleansing answers *what we do about it*. Combining them — the path of least resistance — produces a black box where it's impossible to argue with stakeholders about the data, because the evidence has already been erased. Keeping them apart means a defect report exists for every fix.

**Each cleansing strategy is explicit per defect class.** No global `dropna()`. Duplicates in `geolocation` get `drop_duplicates`. Null `product_category_name` gets filled with `'unknown'` because the row still carries useful pricing data. Zero prices get filtered out because they can't be salvaged. Choosing the strategy is the engineering work; documenting it is the deliverable.

**Some defects are intentionally not autofixed.** The 8 `delivered`-without-date orders aren't a data issue we can fix — they're a process bug somewhere between the warehouse system and the order management system. Silently filling those dates would lie about the underlying problem. Surfacing them in the report is the value.

**Cross-table checks live outside Great Expectations.** GE 1.x is great at column-level validation within a single dataset, but it doesn't natively express "every `order_items.product_id` must exist in `products`". Those checks are in `src/custom_checks.py` with a uniform `CheckResult` interface so both sets compose into a single report.

## Roadmap

- [ ] Slack/email notification for any check failure on scheduled runs
- [ ] Persist check history to track defect trend over time
- [ ] DBT-style lineage view: which downstream tables depend on which checks
- [ ] Add Streamlit dashboard wrapping the JSON results
- [ ] Wrap pipeline in Airflow / Prefect DAG for daily execution

## License

MIT — see [`LICENSE`](./LICENSE).

---

*Built as part of a Data Science portfolio. Based on real data quality patterns encountered in marketplace operations.*
