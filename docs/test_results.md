# Test results

Environment: Python 3.13, pandas 3.0, NumPy 2.5, SciPy 1.18, matplotlib/seaborn, python-pptx, pytest 9.
**Not installed (no network in the build environment):** SQLAlchemy, PyMySQL, Streamlit, Plotly, Jupyter.
Data: synthetic (`scripts/make_synthetic_data.py`), with deliberately injected defects. SQLite via the
standard-library `sqlite3` driver.

## Automated suite: `python -m pytest tests -q` → **21 passed**

| Area | Tests | What is asserted |
|---|---|---|
| Cleaning | 3 | PKs unique and no orphan FK rows after cleaning; injected defects (invalid scores, non-positive prices, duplicates, missing categories, zip padding, installments) are fixed |
| Quality analysis | 1 | Injected duplicates, invalid scores, bad prices and non-unique geolocation keys are detected |
| Features | 1 | Delay/status consistency, total = items + freight, repeat flag = order count > 1, unique orders |
| SQL | 11 | Schema loads with FK enforcement; row counts match; all 21 dashboard queries and 6 analysis queries execute and return rows; KPIs match Pandas; category revenue sums to total; filters change results correctly; LAG/cumulative window results match manual calculation; delay buckets cover all delivered orders; HAVING threshold respected |
| Statistics | 2 | All three tests return p-value, effect size, assumptions and insight; t-test p-value equals a direct `scipy.stats.ttest_ind` call (diff < 1e-12) |
| Insights | 1 | ≥ 8 insights, each with observation, interpretation, impact, recommendation |
| Reports + deck | 1 | `generate_reports` writes JSON/Markdown with a SYNTHETIC banner and KPIs equal to Pandas; the .pptx builds with ≥ 12 slides |

## Additional manual/scripted checks

| Check | Result |
|---|---|
| All 9 dashboard pages run end to end with Streamlit/Plotly stubbed, against SQLite | 9 / 9 executed without errors |
| Notebook code cells executed on synthetic data | 01, 02, 03, 06, 07 pass |
| Notebooks 04, 05 | Syntax-checked only (need SQLAlchemy) |
| `compileall` on all modules | OK |
| AST check for undefined names (21 files) | none |
| Bind-parameter / `%` hazards in 32 SQL statements (MySQL + SQLAlchemy) | none found |
| Final-presentation deck rendered to images and inspected | Layout correct, charts render, banner on every slide |
| Environment checker | Correctly reports Streamlit/Plotly/SQLAlchemy missing (the earlier `import streamlit` "success" was the project's `streamlit/` folder shadowing the package) |

## Reading the synthetic statistics

On synthetic data the three tests reject H0 (t = -16.89; ANOVA F = 37.05, η² = 0.18; χ² = 25.9, Cramér's V = 0.054).
This is **expected by construction**: the generator seeds a delay → lower rating effect, category-specific
price levels and a payment-dependent cancellation rate. It shows that the code detects effects that exist.
It says nothing about your real business.

## Not verified (honest list)

1. Real Streamlit rendering: layout, chart appearance, mobile responsiveness, widget behaviour.
2. SQLAlchemy code paths: `src/db.py`, `src/load_to_sql.py`, `streamlit/database.py`, `run_pipeline.py` as a whole, notebooks 04–05.
3. MySQL execution (SQL is written portably and checked statically only).
4. Behaviour and runtime on the real dataset (≈100k orders, ≈1M geolocation rows).
5. No screenshots of the live dashboard exist, because it could not be launched.

Please run on your machine: `pip install -r requirements.txt`, `python scripts/check_environment.py`,
`python run_pipeline.py`, `streamlit run streamlit/app.py`, and report any error text.
