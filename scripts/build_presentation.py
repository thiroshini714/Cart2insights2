"""Build the final project presentation (.pptx) from the pipeline's report files.

Usage (after `python run_pipeline.py`):
    python scripts/build_presentation.py            # -> reports/Cart2Insights_Final_Presentation.pptx

Every number on the data slides comes from reports/*.json|csv produced by the pipeline. If the
database was loaded with synthetic test data, every slide carries a visible SYNTHETIC DATA banner.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

GREEN = RGBColor(0x1B, 0x7F, 0x5C)
DARK = RGBColor(0x1F, 0x2A, 0x26)
GREY = RGBColor(0x5F, 0x6B, 0x66)
RED = RGBColor(0xC0, 0x39, 0x2B)
W, H = Inches(13.333), Inches(7.5)


def _text(slide, left, top, width, height, text, size=18, bold=False, color=DARK, wrap=True):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size, run.font.bold, run.font.color.rgb = Pt(size), bold, color
    return tf


def _bullets(slide, items: list[str], left=Inches(0.7), top=Inches(1.7), width=Inches(11.9),
             height=Inches(5.0), size=18):
    tf = slide.shapes.add_textbox(left, top, width, height).text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = f"•  {item}"
        r.font.size, r.font.color.rgb = Pt(size), DARK
        p.space_after = Pt(8)
    return tf


class Deck:
    def __init__(self, synthetic: bool):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.synthetic = synthetic
        self.n = 0

    def slide(self, title: str):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])  # blank
        self.n += 1
        bar = s.shapes.add_shape(1, 0, 0, W, Inches(0.18))
        bar.fill.solid(); bar.fill.fore_color.rgb = GREEN; bar.line.fill.background()
        _text(s, Inches(0.7), Inches(0.4), Inches(11.9), Inches(1.0), title, size=30, bold=True,
              color=GREEN)
        if self.synthetic:
            _text(s, Inches(0.7), Inches(7.0), Inches(11.9), Inches(0.4),
                  "SYNTHETIC TEST DATA: figures are illustrative and are not real business results",
                  size=12, bold=True, color=RED)
        _text(s, Inches(12.3), Inches(7.0), Inches(0.8), Inches(0.4), str(self.n), size=11, color=GREY)
        return s

    def bar_chart(self, slide, categories, values, left, top, width, height, title, horizontal=False):
        cd = CategoryChartData()
        cd.categories = categories
        cd.add_series(title, values)
        kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
        chart = slide.shapes.add_chart(kind, left, top, width, height, cd).chart
        chart.has_legend = False
        chart.has_title = True
        chart.chart_title.text_frame.text = title
        chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        chart.plots[0].series[0].format.fill.solid()
        chart.plots[0].series[0].format.fill.fore_color.rgb = GREEN
        if horizontal:
            chart.category_axis.reverse_order = True
        return chart

    def line_chart(self, slide, categories, values, left, top, width, height, title):
        cd = CategoryChartData()
        cd.categories = categories
        cd.add_series(title, values)
        chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, left, top, width, height, cd).chart
        chart.has_legend = False
        chart.has_title = True
        chart.chart_title.text_frame.text = title
        chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        ser = chart.plots[0].series[0]
        ser.format.line.color.rgb = GREEN
        return chart


def _load_json(name: str, reports_dir: Path = REPORTS) -> dict:
    path = Path(reports_dir) / name
    if not path.exists():
        raise SystemExit(f"{path} not found. Run `python run_pipeline.py` first.")
    return json.loads(path.read_text())


def _p(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"


def build(out_path: Path, reports_dir: Path = REPORTS) -> Path:
    reports_dir = Path(reports_dir)
    summary = _load_json("summary_data.json", reports_dir)
    stats = _load_json("statistical_results.json", reports_dir)
    quality = _load_json("data_quality_report.json", reports_dir)
    log_path = reports_dir / "cleaning_log.csv"
    cleaning = pd.read_csv(log_path) if log_path.exists() \
        else pd.DataFrame(columns=["table", "step", "rows_affected"])
    deck = Deck(synthetic=summary["data_source"] == "synthetic")
    k = summary["kpis"]
    cur = "R$"

    # 1 title
    s = deck.slide("Cart2Insights: Decoding E-Commerce Performance")
    _text(s, Inches(0.7), Inches(2.2), Inches(11.9), Inches(1.0),
          "End-to-end analytics: Python · Pandas · SQL · SQLAlchemy · SciPy · Streamlit", size=22, color=DARK)
    _text(s, Inches(0.7), Inches(3.3), Inches(11.9), Inches(1.0),
          f"Data period {summary['period']['start']} to {summary['period']['end']}", size=18, color=GREY)

    # 2 problem
    s = deck.slide("Problem and objectives")
    _bullets(s, [
        "Order, product, seller, payment, delivery and review data sit in 9 related tables, so overall performance is hard to see.",
        "Objective: uncover business insights on sales, customers, products, sellers, payments, delivery and satisfaction.",
        "Questions: What drives revenue? Who are our customers and do they return? Which sellers and categories perform? Where does delivery fail, and does it hurt ratings?",
    ])

    # 3 workflow
    s = deck.slide("Approach: from raw CSV to insight")
    _bullets(s, [
        "Load 9 CSVs with Pandas, then profile quality: missing values, duplicates, types, invalid values, outliers, key uniqueness.",
        "Clean and preprocess; every change is written to a cleaning log.",
        "Store in SQL (MySQL / SQLite via SQLAlchemy) with primary and foreign keys; verify after loading.",
        "Engineer features (order value, delivery delay, customer and seller metrics); explore with EDA.",
        "Test hypotheses (t-test, ANOVA, chi-square); analyse with SQL; explore in a Streamlit dashboard; derive insights.",
    ], size=17)

    # 4 data quality + cleaning
    s = deck.slide("Data quality and cleaning")
    rows = [(t, r["rows"], sum(r["missing_values"].values()), r["duplicate_rows"],
             sum(r["invalid_values"].values())) for t, r in quality.items()]
    tbl = s.shapes.add_table(len(rows) + 1, 5, Inches(0.7), Inches(1.6), Inches(11.9),
                             Inches(0.38 * (len(rows) + 1))).table
    for j, head in enumerate(["Table", "Rows", "Missing cells", "Duplicate rows", "Invalid records"]):
        tbl.cell(0, j).text = head
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row):
            tbl.cell(i, j).text = f"{v:,}" if isinstance(v, int) else str(v)
    for r_ in tbl.rows:
        for c in r_.cells:
            for para in c.text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(12)
    _text(s, Inches(0.7), Inches(5.9), Inches(11.9), Inches(0.9),
          f"{len(cleaning)} cleaning actions logged (reports/cleaning_log.csv): duplicates removed, dates parsed, "
          "categories standardised, invalid records fixed or dropped, orphan rows removed.", size=14, color=GREY)

    # 5 KPIs
    s = deck.slide("Business overview")
    tiles = [("Revenue", f"{cur} {k['total_revenue']:,.0f}"), ("Orders", f"{int(k['total_orders']):,}"),
             ("Customers", f"{int(k['total_customers']):,}"), ("Sellers", f"{summary['total_sellers']:,}"),
             ("Avg order value", f"{cur} {k['avg_order_value']:,.2f}"),
             ("Avg review", "n/a" if k["avg_review_score"] is None else f"{k['avg_review_score']:.2f} / 5")]
    for i, (label, value) in enumerate(tiles):
        left = Inches(0.7 + (i % 3) * 4.1)
        top = Inches(1.8 + (i // 3) * 2.2)
        _text(s, left, top, Inches(3.8), Inches(0.5), label, size=16, color=GREY)
        _text(s, left, top + Inches(0.5), Inches(3.8), Inches(1.0), value, size=34, bold=True, color=GREEN)
    _text(s, Inches(0.7), Inches(6.3), Inches(11.9), Inches(0.5),
          "Revenue = item price + freight, excluding canceled and unavailable orders.", size=13, color=GREY)

    # 6 revenue trend + categories
    s = deck.slide("Sales: trend and categories")
    mr, tc = summary["monthly_revenue"], summary["top_categories"]
    deck.line_chart(s, [m["order_month"] for m in mr], [round(m["revenue"], 2) for m in mr],
                    Inches(0.5), Inches(1.5), Inches(6.4), Inches(5.3), "Monthly revenue")
    deck.bar_chart(s, [c["category"] for c in tc], [round(c["revenue"], 2) for c in tc],
                   Inches(7.0), Inches(1.5), Inches(5.9), Inches(5.3), "Top categories by revenue",
                   horizontal=True)

    # 7 delivery + reviews
    s = deck.slide("Delivery and customer experience")
    ov = summary["ontime_vs_delayed"]
    d = summary["delivery"]
    _bullets(s, [f"Average delivery time: {d['avg_delivery_days']:.1f} days",
                 f"Delayed orders: {d['pct_delayed']:.1f}% of {int(d['delivered_orders']):,} delivered"],
             top=Inches(1.5), height=Inches(1.2), size=17)
    if ov:
        deck.bar_chart(s, [o["delivery_status"] for o in ov],
                       [round(o["avg_review_score"], 2) for o in ov],
                       Inches(0.5), Inches(2.8), Inches(5.8), Inches(4.0),
                       "Average review score by delivery status")
    rd = summary["review_distribution"]
    if rd:
        deck.bar_chart(s, [str(int(r["review_score"])) for r in rd],
                       [int(r["review_count"]) for r in rd], Inches(6.8), Inches(2.8), Inches(6.0),
                       Inches(4.0), "Review score distribution")

    # 8-10 statistical tests
    t = stats["t_test_delivery_vs_review"]
    a = stats["anova_category_vs_order_value"]
    c = stats["chi_square_payment_vs_status"]
    for title, res in (("T-test: delivery delay and satisfaction", t),
                       ("ANOVA: product category and order value", a),
                       ("Chi-square: payment method and order status", c)):
        s = deck.slide(title)
        if "p_value" not in res:
            _bullets(s, [res["question"], f"Not run: {res.get('status', 'insufficient data')}"])
            continue
        _bullets(s, [f"Question: {res['question']}",
                     f"H0: {res['H0']}",
                     f"H1: {res['H1']}",
                     f"Test: {res['test']}, α = {res['alpha']}",
                     f"Statistic = {res['statistic']:.3f}, p-value = {_p(res['p_value'])} → {res['decision']}",
                     f"Insight: {res['business_insight']}"], size=16)

    # 11+ insights (3 per slide)
    ins = summary["insights"]
    for i in range(0, len(ins), 3):
        s = deck.slide(f"Business insights and recommendations ({i // 3 + 1})")
        tf = s.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(11.9), Inches(5.3)).text_frame
        tf.word_wrap = True
        first = True
        for item in ins[i:i + 3]:
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            r = p.add_run(); r.text = item["area"]; r.font.bold = True; r.font.size = Pt(16)
            r.font.color.rgb = GREEN
            for label, key in (("Observation", "observation"), ("Impact", "business_impact"),
                               ("Recommendation", "recommendation")):
                q = tf.add_paragraph()
                rr = q.add_run(); rr.text = f"{label}: {item[key]}"; rr.font.size = Pt(12)
                rr.font.color.rgb = DARK
            tf.add_paragraph()

    # closing
    s = deck.slide("Deliverables and how to run")
    _bullets(s, [
        "Source code: src/ modules, 7 notebooks, run_pipeline.py",
        "SQL integration: sql/schema.sql, SQLAlchemy loading, streamlit/queries.py",
        "Streamlit dashboard: 9 pages with sidebar filters (streamlit run streamlit/app.py)",
        "Documentation: README, data dictionary, ER diagram, requirement checklist, test results",
        "Reproduce: pip install -r requirements.txt → python run_pipeline.py → streamlit run streamlit/app.py",
    ], size=17)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    deck.prs.save(out_path)
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default=str(REPORTS / "Cart2Insights_Final_Presentation.pptx"))
    path = build(Path(ap.parse_args().out))
    print(f"Wrote {path}")
