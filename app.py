import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date, datetime
import calendar
import json

st.set_page_config(page_title="Spending Diary", layout="wide")

# -----------------------------
# Config
# -----------------------------
CATEGORIES = [
    "groceries",
    "coffee",
    "transport",
    "pilates",
    "miscellaneous",
    "stocks",
    "savings",
    "rent", 
]

DATA_PATH = Path("spending_diary.csv")
BUDGETS_PATH = Path("monthly_budgets.json")

SPEND_COLS = ["date", "notes"] + [f"{c}_spend" for c in CATEGORIES]

# -----------------------------
# Helpers
# -----------------------------
def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"

def ensure_files():
    if not DATA_PATH.exists():
        pd.DataFrame(columns=SPEND_COLS).to_csv(DATA_PATH, index=False)
    if not BUDGETS_PATH.exists():
        BUDGETS_PATH.write_text(json.dumps({}, indent=2))

def load_spend_df() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    if len(df) == 0:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for c in CATEGORIES:
        col = f"{c}_spend"
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "notes" not in df.columns:
        df["notes"] = ""
    return df.sort_values("date")

def save_spend_row(row: dict):
    df = load_spend_df()
    # if same date exists, overwrite (diary-like)
    if len(df) > 0 and (df["date"] == row["date"]).any():
        df = df[df["date"] != row["date"]]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True).sort_values("date")
    df.to_csv(DATA_PATH, index=False)

def load_budgets() -> dict:
    return json.loads(BUDGETS_PATH.read_text())

def save_budgets(budgets: dict):
    BUDGETS_PATH.write_text(json.dumps(budgets, indent=2))

def get_month_bounds(d: date):
    last_day = calendar.monthrange(d.year, d.month)[1]
    start = date(d.year, d.month, 1)
    end = date(d.year, d.month, last_day)
    return start, end

def week_start(d: date) -> date:
    # Monday-based weeks
    return d - pd.Timedelta(days=d.weekday())

def week_end(d: date) -> date:
    return week_start(d) + pd.Timedelta(days=6)

def weeks_in_month(d: date) -> list[tuple[date, date]]:
    # All Monday-Sunday weeks that intersect the month
    m_start, m_end = get_month_bounds(d)
    ws = week_start(m_start)
    we = week_end(m_end)
    weeks = []
    cur = ws
    while cur <= we:
        weeks.append((cur, cur + pd.Timedelta(days=6)))
        cur = cur + pd.Timedelta(days=7)
    return weeks

def filter_df_by_range(df: pd.DataFrame, start_d: date, end_d: date) -> pd.DataFrame:
    if len(df) == 0:
        return df
    return df[(df["date"] >= start_d) & (df["date"] <= end_d)].copy()

def totals_by_category(df: pd.DataFrame) -> dict:
    out = {}
    for c in CATEGORIES:
        col = f"{c}_spend"
        out[c] = float(df[col].sum()) if (len(df) and col in df.columns) else 0.0
    return out

# -----------------------------
# Init
# -----------------------------
ensure_files()
df = load_spend_df()
budgets = load_budgets()

st.title("🧾 Spending Diary (Weekly Budgets)")

# Sidebar controls
today = date.today()
selected_date = st.sidebar.date_input("Select date", value=today)
mkey = month_key(selected_date)

st.sidebar.markdown("---")
st.sidebar.subheader("Month")
st.sidebar.write(f"Selected month: **{mkey}**")

# -----------------------------
# Budget setup (monthly)
# -----------------------------
st.subheader("1) Monthly setup")

month_budget = budgets.get(mkey, {"income": 0.0, "allocations": {c: 0.0 for c in CATEGORIES}})

colA, colB = st.columns([1, 2])

with colA:
    income = st.number_input("Monthly income ($)", min_value=0.0, step=50.0, value=float(month_budget.get("income", 0.0)))

with colB:
    st.caption("Set **monthly allocations** per category. Weekly budgets are auto-calculated from the number of calendar weeks in the month.")
    alloc_cols = st.columns(4)
    allocations = {}
    for i, c in enumerate(CATEGORIES):
        with alloc_cols[i % 4]:
            allocations[c] = st.number_input(
                f"{c.title()} ($/month)",
                min_value=0.0,
                step=10.0,
                value=float(month_budget.get("allocations", {}).get(c, 0.0)),
                key=f"alloc_{mkey}_{c}"
            )

total_alloc = sum(allocations.values())
leftover = income - total_alloc

c1, c2, c3 = st.columns(3)
c1.metric("Total allocated (month)", f"${total_alloc:,.2f}")
c2.metric("Income (month)", f"${income:,.2f}")
c3.metric("Unallocated", f"${leftover:,.2f}")

if st.button("💾 Save monthly setup"):
    budgets[mkey] = {"income": float(income), "allocations": {k: float(v) for k, v in allocations.items()}}
    save_budgets(budgets)
    st.success("Saved monthly setup!")

# -----------------------------
# Weekly budget calculation
# -----------------------------
weeks = weeks_in_month(selected_date)
num_weeks = len(weeks)

weekly_budget = {c: (allocations[c] / num_weeks if num_weeks else 0.0) for c in CATEGORIES}

st.subheader("2) Daily diary log")

# -----------------------------
# Daily log form
# -----------------------------
existing_row = None
if len(df) > 0 and (df["date"] == selected_date).any():
    existing_row = df[df["date"] == selected_date].iloc[0].to_dict()

with st.form("daily_log", clear_on_submit=False):
    st.write(f"Logging for: **{selected_date}**")
    notes = st.text_input("Notes (optional)", value=str(existing_row.get("notes", "")) if existing_row else "")

    spend_inputs = {}
    spend_cols = st.columns(4)
    for i, c in enumerate(CATEGORIES):
        default_val = float(existing_row.get(f"{c}_spend", 0.0)) if existing_row else 0.0
        with spend_cols[i % 4]:
            spend_inputs[c] = st.number_input(
                f"{c.title()} spend ($)",
                min_value=0.0,
                step=1.0,
                value=default_val,
                key=f"spend_{selected_date}_{c}"
            )

    submitted = st.form_submit_button("✅ Save day")
    if submitted:
        row = {"date": selected_date, "notes": notes}
        for c in CATEGORIES:
            row[f"{c}_spend"] = float(spend_inputs[c])
        save_spend_row(row)
        st.success("Saved!")
        df = load_spend_df()  # refresh

# -----------------------------
# 3) Dashboard summaries
# -----------------------------
st.subheader("3) Weekly + Monthly overview")

# current week range
ws = week_start(selected_date)
we = week_end(selected_date)

# month range
ms, me = get_month_bounds(selected_date)

week_df = filter_df_by_range(df, ws, we)
month_df = filter_df_by_range(df, ms, me)

week_totals = totals_by_category(week_df)
month_totals = totals_by_category(month_df)

# Build summary table
summary_rows = []
for c in CATEGORIES:
    wb = weekly_budget[c]
    ws_spent = week_totals[c]
    ms_budget = allocations[c]
    ms_spent = month_totals[c]
    summary_rows.append({
        "Category": c.title(),
        "Weekly budget": wb,
        "Spent this week": ws_spent,
        "Weekly remaining": wb - ws_spent,
        "Monthly budget": ms_budget,
        "Spent this month": ms_spent,
        "Monthly remaining": ms_budget - ms_spent,
    })

summary = pd.DataFrame(summary_rows)

left, right = st.columns([1.2, 1])

with left:
    st.write(f"**Week:** {ws} → {we}  |  **Month:** {ms} → {me}  |  Weeks in month: **{num_weeks}**")
    st.dataframe(
        summary.style.format({
            "Weekly budget": "${:,.2f}",
            "Spent this week": "${:,.2f}",
            "Weekly remaining": "${:,.2f}",
            "Monthly budget": "${:,.2f}",
            "Spent this month": "${:,.2f}",
            "Monthly remaining": "${:,.2f}",
        }),
        use_container_width=True
    )

with right:
    # quick totals
    total_week_spend = sum(week_totals.values())
    total_week_budget = sum(weekly_budget.values())
    total_month_spend = sum(month_totals.values())

    st.metric("Total spent this week", f"${total_week_spend:,.2f}")
    st.metric("Total weekly budget (all cats)", f"${total_week_budget:,.2f}")
    st.metric("Total spent this month", f"${total_month_spend:,.2f}")

    # simple charts
    if len(week_df) > 0:
        chart_week = pd.DataFrame({
            "Category": [c.title() for c in CATEGORIES],
            "Spent": [week_totals[c] for c in CATEGORIES],
            "Budget": [weekly_budget[c] for c in CATEGORIES],
        }).set_index("Category")
        st.bar_chart(chart_week[["Spent", "Budget"]])

st.subheader("4) Diary entries")
if len(month_df) == 0:
    st.info("No entries logged for this month yet.")
else:
    show = month_df.copy()
    # show only non-zero spends + notes
    show["total_spend"] = show[[f"{c}_spend" for c in CATEGORIES]].sum(axis=1)
    show = show.sort_values("date", ascending=False)
    st.dataframe(show[["date", "notes", "total_spend"] + [f"{c}_spend" for c in CATEGORIES]], use_container_width=True)

st.caption("Data stored locally in spending_diary.csv + monthly_budgets.json")
