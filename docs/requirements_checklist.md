# Requirement checklist (source: the project PDF, 14 pages)

Legend: **Verified** = executed and checked in the build environment (synthetic data, SQLite).
**Implemented, not executed** = code written and statically checked but it could not run there
(needs SQLAlchemy / Streamlit / Plotly / MySQL, which were not installable offline).
**Needs real data** = depends on the real dataset, which was not available.

| # | PDF requirement | Where | Status |
|---|---|---|---|
| 1 | Step 1: business problem, objectives, questions | notebook 01, README | Verified (code cells run); wording is documentation |
| 2 | Step 2: 9 tables, columns/types, PK/FK, relationships | notebook 01, `src/config.py`, `sql/schema.sql` | Verified (PK/FK enforced in SQLite) |
| 2 | Data dictionary | `docs/data_dictionary.md` | Done; **confirm against your real CSVs** (assumed standard 9-table layout) |
| 2 | ER diagram | `docs/er_diagram.md` (Mermaid) | Done; the PDF's linked official diagram could not be opened, so compare |
| 3 | Load all CSVs with Pandas; shape, columns, dtypes | `src/data_loader.py` | Verified (synthetic CSVs) |
| 4 | Missing, duplicates, types, invalid, outliers, PK uniqueness | `src/quality.py`, notebook 02 | Verified (injected problems detected by tests) |
| 5 | Missing, duplicates, types, dates, categories, invalid records, renames | `src/cleaning.py`, notebook 03 | Verified (tests assert fixes; log written) |
| 6 | Create DB, create tables from ER, load, PK/FK, verify | `sql/schema.sql`, `src/db.py`, `src/load_to_sql.py` | Schema + FK + counts **verified in SQLite via sqlite3**; SQLAlchemy loader **implemented, not executed**; MySQL **not executed** |
| 7 | Features: order value, delivery days/delay, customer order count/spending, AOV, seller revenue/orders, repeat indicator | `src/features.py` | Verified |
| 8 | EDA: uni/bi/multivariate, trend, correlation, distribution | notebook 06 | Code cells executed on synthetic data (no outputs saved; run on real data) |
| 9a | T-test, delivery status vs review score | `src/stats_tests.py` | Verified (p-value equals a direct SciPy call) |
| 9b | ANOVA, category vs order value | same | Verified runs; assumptions + Kruskal-Wallis + Tukey |
| 9c | Chi-square, payment method vs order status | same | Verified runs; expected-count check + Cramér's V |
| 9 | Hypothesis → test → assumptions → p-value → decision → insight | same + dashboard "Statistical Tests" | Verified (each result dict carries all six parts) |
| 10 | SQL: SELECT/WHERE/ORDER BY, GROUP BY/HAVING, joins, subqueries, CTEs, window functions, aggregations | `streamlit/queries.py` (`ANALYSIS_QUERIES`, `QUERIES`) | Verified (all 32 queries run on SQLite; results cross-checked with Pandas) |
| 10 | Interactive Streamlit dashboard connected to the DB | `streamlit/` | All 9 pages **executed with Streamlit/Plotly stubbed** (data flow, columns, filters); real rendering **not executed** |
| 10.1 | Overview: revenue, orders, customers, sellers, AOV, avg review | `app.py::page_overview` | Data flow verified; UI not rendered |
| 10.2 | Sales: monthly trend, revenue by category, top products, sales by location | `page_sales` | same |
| 10.3 | Customers: distribution, spending, repeat vs new, top customers | `page_customers` | same |
| 10.4 | Sellers & products: top sellers, seller revenue, category performance, seller ratings | `page_sellers_products` | same |
| 10.5 | Delivery: avg time, on-time vs delayed, by location, delay vs review | `page_delivery` | same |
| 10.6 | Experience: review distribution, reviews by category, rating vs delivery | `page_experience` | same |
| 11 | Insights: Observation → Interpretation → Business impact | `src/insights.py`, dashboard page, `reports/business_insights.md` | Verified generation (numbers computed from data); **real findings need real data** |
| – | Recommended directory structure | whole repo | Matches (`data/raw|cleaned`, `notebooks/01…07`, `streamlit/app|database|queries|utils`) |
| – | Deliverable: Source code | `src/`, notebooks, scripts | Done |
| – | Deliverable: SQL integration | `src/db.py`, `src/load_to_sql.py`, `streamlit/` | Done; SQLAlchemy path not executed here |
| – | Deliverable: Streamlit application | `streamlit/` | Done; real rendering not executed here |
| – | Deliverable: README (objective, approach, methodology, **key findings**) | `README.md` | Done except key findings: **needs real data** (deliberately not invented) |
| – | Deliverable: Business insights & recommendations | generated | Mechanism verified; **needs real data** |
| – | Deliverable: Final presentation | `scripts/build_presentation.py` → `reports/Cart2Insights_Final_Presentation.pptx` | Verified: built from report files, rendered and visually inspected on synthetic data |
| – | Guideline: no hardcoded credentials | `.env.example`, `src/db.py` | Verified by inspection (no credentials in code) |
| – | Guideline: Git with meaningful commits | local repository | Done (local commits; push to your GitHub is yours to do) |
| – | Guideline: no large datasets/credentials on GitHub | `.gitignore` | Verified (`git check-ignore` on data, `.env`, `*.db`) |
| – | Guideline: reproducible, documented | README, `scripts/check_environment.py` | Done |
| – | Tech tag: MySQL | `DB_BACKEND=mysql` | Implemented, **not executed** (no MySQL server available) |
