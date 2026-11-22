"""
Dual-Fuel Engine Analysis -- live Streamlit dashboard on top of the dbt
marts built in dbt_df_engine/. Deployed on Streamlit Community Cloud.

ARCHITECTURE
- One raw dataset (fact table joined to both dimensions) is fetched ONCE
  per 10-minute cache window.
- A sidebar holds every BUSINESS ASSUMPTION (fuel price, operating hours,
  rated power, NOx limit, carbon price) and every DATA FILTER (which
  combustion modes / load points count). Both are global: every module
  below reads from the same two sources, so moving one slider updates
  the whole dashboard consistently -- there is exactly one place to
  change "what if we only ran RCCI" or "what if fuel costs $1.40/kg",
  not nine different copies of the same number.
- Every module recomputes its own aggregates from the filtered raw data
  in pandas (mirroring the SQL in sql/dashboard_queries.sql), rather than
  reading a static, unfilterable mart table -- this is what makes the
  mode/load filters actually affect every chart, including the duty-cycle
  weighting itself ("what would our duty cycle cost if we eliminated
  Diffusion mode entirely?").

REMINDER FROM THE PROJECT'S README: the underlying dataset is synthetic.
Only NOx-vs-injection-pressure and efficiency-vs-load behave like real
engine physics in this data. Treat every number here as a demonstration
of the method, not as real engine facts -- this banner is repeated in the
app itself so viewers see the same caveat.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from databricks import sql

st.set_page_config(
    page_title="Dual-Fuel Engine Analysis",
    page_icon="🛠️",
    layout="wide",
)

# ============================================================================
# MODULE: Connection & data access
# Purpose: one cached Databricks connection, one helper to build fully
# qualified table names, one cached query runner. Nothing in any tab below
# talks to Databricks directly -- everything goes through run_query().
# ============================================================================


@st.cache_resource
def get_connection():
    return sql.connect(
        server_hostname=st.secrets["databricks"]["host"],
        http_path=st.secrets["databricks"]["http_path"],
        access_token=st.secrets["databricks"]["token"],
    )


_DB_SECRETS = st.secrets.get("databricks", {})
CATALOG = _DB_SECRETS.get("catalog", "df_project")
MART_SCHEMA = _DB_SECRETS.get("schema", "mart")
RAW_SCHEMA = _DB_SECRETS.get("raw_schema", "raw")


def mart(table_name: str) -> str:
    """Fully-qualified name of a dbt-built mart/dim/fact table."""
    return f"{CATALOG}.{MART_SCHEMA}.{table_name}"


def raw(table_name: str) -> str:
    """Fully-qualified name of a raw/seed table (e.g. the duty_cycles seed)."""
    return f"{CATALOG}.{RAW_SCHEMA}.{table_name}"


@st.cache_data(ttl=600, show_spinner="Querying Databricks...")
def run_query(query: str) -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute(query)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)


@st.cache_data(ttl=600, show_spinner="Loading engine readings...")
def get_raw_readings() -> pd.DataFrame:
    """One row per simulated reading, with mode/category text labels joined
    in. This is the single source every module filters and re-aggregates
    from -- it is fetched once, not once per tab."""
    return run_query(
        f"""
        select
            f.*,
            m.combustion_mode,
            m.combustion_mode_description,
            c.target_category
        from {mart('fct_engine_readings')} f
        join {mart('dim_combustion_mode')} m using (combustion_mode_id)
        join {mart('dim_target_category')} c using (target_category_id)
        """
    )


@st.cache_data(ttl=600, show_spinner="Loading duty-cycle definitions...")
def get_duty_cycle_seed() -> pd.DataFrame:
    """The hand-maintained duty_cycles seed: how much time each named duty
    cycle spends at each load point."""
    return run_query(f"select * from {raw('duty_cycles')}")


def engine_map_from(readings: pd.DataFrame) -> pd.DataFrame:
    """Recomputes the 'engine map' (avg performance per load point) from
    whatever subset of readings is passed in -- this is the pandas
    equivalent of mart_engine_map_by_load.sql, but it responds to the
    sidebar's combustion-mode and load filters instead of being frozen to
    dbt's last full-data build."""
    if readings.empty:
        return readings
    return (
        readings.groupby("engine_load_percent")
        .agg(
            number_of_readings=("reading_id", "count"),
            avg_bsfc_g_per_kwh=("bsfc_g_per_kwh", "mean"),
            avg_thermal_efficiency_pct=("thermal_efficiency_pct", "mean"),
            avg_nox_emissions=("nox_emissions_g_per_kwh", "mean"),
            avg_soot_emissions=("soot_emissions_g_per_kwh", "mean"),
            avg_co_emissions=("co_emissions_g_per_kwh", "mean"),
            avg_target_score=("target_score", "mean"),
        )
        .reset_index()
        .sort_values("engine_load_percent")
    )


def duty_cycle_performance_from(engine_map: pd.DataFrame, duty_cycles: pd.DataFrame) -> pd.DataFrame:
    """Pandas equivalent of mart_duty_cycle_performance.sql: joins the duty
    cycle seed to a (possibly filtered) engine map and weights it."""
    merged = duty_cycles.merge(
        engine_map, left_on="load_percent", right_on="engine_load_percent", how="inner"
    )
    if merged.empty:
        return merged
    out = []
    for (cycle_name, industry, application, basis), g in merged.groupby(
        ["cycle_name", "industry", "application", "basis"]
    ):
        total_weight = g["weight"].sum()
        out.append(
            {
                "cycle_name": cycle_name,
                "industry": industry,
                "application": application,
                "basis": basis,
                "load_points_used": len(g),
                "total_weight": round(total_weight, 3),
                "weighted_bsfc_g_per_kwh": (g["weight"] * g["avg_bsfc_g_per_kwh"]).sum() / total_weight,
                "weighted_thermal_efficiency_pct": (g["weight"] * g["avg_thermal_efficiency_pct"]).sum()
                / total_weight,
                "weighted_nox_emissions": (g["weight"] * g["avg_nox_emissions"]).sum() / total_weight,
                "weighted_soot_emissions": (g["weight"] * g["avg_soot_emissions"]).sum() / total_weight,
                "weighted_co_emissions": (g["weight"] * g["avg_co_emissions"]).sum() / total_weight,
            }
        )
    result = pd.DataFrame(out)
    result["extra_bsfc_vs_best_cycle"] = result["weighted_bsfc_g_per_kwh"] - result["weighted_bsfc_g_per_kwh"].min()
    return result.sort_values("weighted_bsfc_g_per_kwh").reset_index(drop=True)


def add_cost_and_compliance(
    df: pd.DataFrame,
    bsfc_col: str,
    nox_col: str,
    fuel_price: float,
    hours: float,
    rated_power: float,
    nox_limit: float,
    co2_factor: float,
    carbon_price: float,
) -> pd.DataFrame:
    """Shared $ / CO2 / compliance math, used by every cost-facing module so
    the formula only lives in one place."""
    out = df.copy()
    out["annual_fuel_kg"] = (out[bsfc_col] * rated_power * hours) / 1000.0
    out["annual_fuel_cost_usd"] = out["annual_fuel_kg"] * fuel_price
    out["annual_co2_tons"] = (out["annual_fuel_kg"] * co2_factor) / 1000.0
    out["annual_co2_cost_usd"] = out["annual_co2_tons"] * carbon_price
    out["annual_total_cost_usd"] = out["annual_fuel_cost_usd"] + out["annual_co2_cost_usd"]
    out["extra_annual_cost_vs_best_usd"] = out["annual_total_cost_usd"] - out["annual_total_cost_usd"].min()
    out["nox_compliance_status"] = out[nox_col].apply(lambda v: "✅ PASS" if v <= nox_limit else "❌ FAIL")
    out["nox_pct_vs_limit"] = round((out[nox_col] - nox_limit) / nox_limit * 100, 1)
    return out


def about(title: str, body: str) -> None:
    """Renders a consistent '📘 About this module' explainer block."""
    with st.expander(f"📘 About this module: {title}", expanded=False):
        st.markdown(body)


# ============================================================================
# Page header & connection check
# ============================================================================

st.title("🛠️ Dual-Fuel Engine Analysis")
st.caption(
    "Same engine, different duty cycle. Live dashboard on top of a dbt + "
    "Databricks pipeline."
)
with st.expander("⚠️ Read before trusting any number here", expanded=False):
    st.markdown(
        """
The underlying dataset is **synthetic** (simulated, not measured on a real
engine). Only two relationships in it behave like real engine physics:
**NOx rises with fuel injection pressure**, and **efficiency improves with
load**. Everything else (soot, CO, stability, peak pressure, combustion
duration, and the effects of combustion mode / EGR / boost / timing /
intake temperature) is statistically close to noise in this particular
dataset. Treat this app as a demonstration of the **method** -- filtering
and weighting an engine map, and turning that into cost/compliance numbers
-- not as real engine facts. Point it at real measured data to get real
answers.
        """
    )

try:
    get_connection()
except Exception as exc:  # noqa: BLE001 -- surfaced to the viewer on purpose
    st.error(
        "Could not connect to Databricks. If you're the app owner, check "
        "that `host`, `http_path`, and `token` are set correctly under "
        "**Settings → Secrets** in Streamlit Community Cloud, and that "
        "your SQL warehouse is running (serverless warehouses auto-start "
        "on the first query, which can take ~30-60s)."
    )
    st.exception(exc)
    st.stop()

raw_readings_all = get_raw_readings()
duty_cycle_seed = get_duty_cycle_seed()
all_modes = sorted(raw_readings_all["combustion_mode"].unique().tolist())
all_loads = sorted(raw_readings_all["engine_load_percent"].unique().tolist())

# ============================================================================
# MODULE: Sidebar -- the single, shared control panel
# Purpose: every number and filter a business user might want to change
# lives here ONCE. No module below defines its own, separate copy of
# "fuel price" or "which modes count" -- they all read these same
# variables, so the whole dashboard stays internally consistent.
# ============================================================================

with st.sidebar:
    st.header("⚙️ Business Assumptions")
    st.caption("Applies to every cost, ROI, and compliance figure in this app.")
    fuel_price = st.number_input("Fuel price ($/kg)", min_value=0.0, value=1.10, step=0.05)
    hours = st.number_input("Operating hours / year", min_value=0, value=4000, step=100)
    rated_power = st.number_input("Rated power (kW)", min_value=1, value=1000, step=50)
    nox_limit = st.number_input("NOx regulatory/contractual limit (g/kWh)", min_value=0.0, value=14.4, step=0.1)
    carbon_price = st.number_input("Carbon price ($/ton CO2)", min_value=0.0, value=85.0, step=5.0)
    co2_factor = st.number_input(
        "CO2 emission factor (kg CO2 / kg fuel)", min_value=0.0, value=3.15, step=0.05,
        help="Default ~3.15 is a typical diesel figure. Edit if your fuel blend differs.",
    )

    st.divider()
    st.header("🔍 Data Filters")
    st.caption("Narrows every chart and recomputes the duty-cycle weighting live.")
    selected_modes = st.multiselect("Combustion modes to include", all_modes, default=all_modes)
    selected_loads = st.multiselect("Engine load points to include (%)", all_loads, default=all_loads)

    st.divider()
    st.caption(f"Dataset: {len(raw_readings_all):,} total readings (unfiltered).")

if not selected_modes or not selected_loads:
    st.warning("Select at least one combustion mode and one load point in the sidebar to see results.")
    st.stop()

filtered = raw_readings_all[
    raw_readings_all["combustion_mode"].isin(selected_modes)
    & raw_readings_all["engine_load_percent"].isin(selected_loads)
]
if filtered.empty:
    st.warning("No readings match the current filters. Widen your selection in the sidebar.")
    st.stop()

live_engine_map = engine_map_from(filtered)
live_duty_cycle_perf = duty_cycle_performance_from(live_engine_map, duty_cycle_seed)

st.caption(
    f"Showing **{len(filtered):,} / {len(raw_readings_all):,}** readings "
    f"({', '.join(selected_modes)}; loads {', '.join(str(x) for x in selected_loads)}%)."
)

tabs = st.tabs(
    [
        "📊 Executive Summary",
        "🔥 Combustion Modes",
        "⚙️ Engine Load",
        "🏆 Performance Categories",
        "🔬 Relationships",
        "📈 Top Performers",
        "💰 Duty Cycles & Cost",
        "🔁 Mode-Switching ROI",
        "🧪 Try Your Own Duty Cycle",
    ]
)

# ============================================================================
# MODULE 1: Executive Summary
# Purpose: the one screen a decision-maker (not an engineer) needs --
# "what does this engine cost us today, are we compliant, and what's the
# single biggest lever to pull?" Everything here is derived from the
# sidebar's shared assumptions/filters; nothing is computed independently.
# ============================================================================
with tabs[0]:
    about(
        "Executive Summary",
        """
**Purpose**: answer three business questions at a glance -- *What does
running this engine cost us per year? Do we meet our emissions limit? What's
the single best lever available to cut cost?*

**Inputs**: the duty cycle you say best represents real operation, plus the
sidebar's fuel price / hours / rated power / NOx limit / carbon price.

**How to use it**: pick your actual operating profile below, read the three
KPI tiles, then check the recommendation line -- it tells you whether
switching duty cycle or switching combustion mode saves more.
        """,
    )

    if live_duty_cycle_perf.empty:
        st.warning("No duty cycle has all its required load points in the current filter -- widen the load filter.")
    else:
        baseline_cycle = st.selectbox(
            "Which duty cycle best represents your actual operation today?",
            live_duty_cycle_perf["cycle_name"].tolist(),
        )
        cycle_econ = add_cost_and_compliance(
            live_duty_cycle_perf, "weighted_bsfc_g_per_kwh", "weighted_nox_emissions",
            fuel_price, hours, rated_power, nox_limit, co2_factor, carbon_price,
        )
        baseline = cycle_econ[cycle_econ["cycle_name"] == baseline_cycle].iloc[0]
        best_cycle = cycle_econ.sort_values("annual_total_cost_usd").iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Annual Fuel Cost", f"${baseline['annual_fuel_cost_usd']:,.0f}")
        c2.metric("Annual CO2 Cost", f"${baseline['annual_co2_cost_usd']:,.0f}")
        c3.metric("NOx Compliance", baseline["nox_compliance_status"])
        c4.metric(
            "Savings If Switched to Best Cycle",
            f"${baseline['annual_total_cost_usd'] - best_cycle['annual_total_cost_usd']:,.0f}",
        )

        mode_perf = filtered.groupby("combustion_mode").agg(avg_bsfc_g_per_kwh=("bsfc_g_per_kwh", "mean")).reset_index()
        mode_econ = add_cost_and_compliance(
            mode_perf.assign(avg_nox_emissions=filtered.groupby("combustion_mode")["nox_emissions_g_per_kwh"].mean().values),
            "avg_bsfc_g_per_kwh", "avg_nox_emissions",
            fuel_price, hours, rated_power, nox_limit, co2_factor, carbon_price,
        )
        best_mode = mode_econ.sort_values("annual_total_cost_usd").iloc[0]
        worst_mode = mode_econ.sort_values("annual_total_cost_usd").iloc[-1]
        mode_savings = worst_mode["annual_total_cost_usd"] - best_mode["annual_total_cost_usd"]
        cycle_savings = baseline["annual_total_cost_usd"] - best_cycle["annual_total_cost_usd"]

        st.markdown("#### 💡 Recommendation")
        if baseline["nox_compliance_status"] == "❌ FAIL":
            st.error(
                f"**Compliance risk**: `{baseline_cycle}` exceeds your NOx limit by "
                f"{abs(baseline['nox_pct_vs_limit'])}%. Address this before cost optimization."
            )
        if cycle_savings <= 1 and mode_savings <= 1:
            st.success("Current setup is already at (or near) the best available combination in this data.")
        elif cycle_savings >= mode_savings:
            st.info(
                f"**Duty cycle is the bigger lever.** Switching from `{baseline_cycle}` to "
                f"`{best_cycle['cycle_name']}` saves an estimated **${cycle_savings:,.0f}/year** -- "
                f"more than standardizing combustion mode (**${mode_savings:,.0f}/year** potential)."
            )
        else:
            st.info(
                f"**Combustion mode is the bigger lever.** Standardizing on `{best_mode['combustion_mode']}` "
                f"saves an estimated **${mode_savings:,.0f}/year** -- more than switching duty cycle "
                f"(**${cycle_savings:,.0f}/year** potential)."
            )

        st.markdown("#### All duty cycles, side by side")
        fig = px.bar(
            cycle_econ.sort_values("annual_total_cost_usd"),
            x="cycle_name", y="annual_total_cost_usd", color="nox_compliance_status",
            title="Annual Total Cost (Fuel + CO2) by Duty Cycle",
            color_discrete_map={"✅ PASS": "#2e7d32", "❌ FAIL": "#c62828"},
        )
        st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# MODULE 2: Combustion Modes
# ============================================================================
with tabs[1]:
    about(
        "Combustion Modes",
        """
**Purpose**: compare the three combustion strategies (Diffusion, Homogeneous,
RCCI) on efficiency, fuel use, emissions, and overall score.

**Business read**: if one mode is clearly better, standardizing engines on
it is the lowest-effort lever available (no hardware change, just operating
strategy). Check the **Mode-Switching ROI** tab for the dollar value.
        """,
    )
    by_mode = (
        filtered.groupby(["combustion_mode", "combustion_mode_description"])
        .agg(
            number_of_readings=("reading_id", "count"),
            avg_thermal_efficiency_pct=("thermal_efficiency_pct", "mean"),
            avg_bsfc_g_per_kwh=("bsfc_g_per_kwh", "mean"),
            avg_nox_emissions=("nox_emissions_g_per_kwh", "mean"),
            avg_soot_emissions=("soot_emissions_g_per_kwh", "mean"),
            avg_co_emissions=("co_emissions_g_per_kwh", "mean"),
            avg_target_score=("target_score", "mean"),
        )
        .reset_index()
        .round(3)
    )
    metric = st.radio(
        "Metric", ["avg_thermal_efficiency_pct", "avg_bsfc_g_per_kwh", "avg_nox_emissions", "avg_target_score"],
        horizontal=True,
    )
    fig = px.bar(by_mode, x="combustion_mode", y=metric, color="combustion_mode", title=metric)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(by_mode, use_container_width=True, hide_index=True)

# ============================================================================
# MODULE 3: Engine Load
# ============================================================================
with tabs[2]:
    about(
        "Engine Load",
        """
**Purpose**: shows how fuel use, efficiency, and emissions change as load
rises from 10% to 100% -- the base "engine map" that every duty-cycle
calculation is built on.

**Business read**: engines are almost always less efficient at low load.
If your real operation spends a lot of time lightly loaded, expect worse
BSFC than the engine's rated spec sheet implies -- this is exactly why
duty-cycle weighting (not a single spec number) is the right way to budget
fuel cost.
        """,
    )
    fig = px.line(
        live_engine_map, x="engine_load_percent", y="avg_bsfc_g_per_kwh", markers=True,
        title="Average BSFC vs. Engine Load",
        labels={"engine_load_percent": "Engine Load (%)", "avg_bsfc_g_per_kwh": "BSFC (g/kWh)"},
    )
    st.plotly_chart(fig, use_container_width=True)
    fig2 = px.line(
        live_engine_map, x="engine_load_percent",
        y=["avg_nox_emissions", "avg_soot_emissions", "avg_co_emissions"],
        markers=True, title="Emissions vs. Engine Load",
    )
    st.plotly_chart(fig2, use_container_width=True)
    st.dataframe(live_engine_map.round(3), use_container_width=True, hide_index=True)

# ============================================================================
# MODULE 4: Performance Categories
# ============================================================================
with tabs[3]:
    about(
        "Performance Categories",
        """
**Purpose**: shows what share of readings fall into each performance bucket
(Low/Moderate/High/Excellent) under the current filters.

**Business read**: a quick health check -- if tightening a filter (say,
restricting to one combustion mode) shrinks the "Excellent" share, that
mode is operationally riskier than it looks from averages alone.
        """,
    )
    by_category = (
        filtered.groupby("target_category")
        .agg(
            number_of_readings=("reading_id", "count"),
            avg_thermal_efficiency_pct=("thermal_efficiency_pct", "mean"),
            avg_combustion_stability_index=("combustion_stability_index", "mean"),
        )
        .reset_index()
        .round(3)
    )
    fig = px.pie(by_category, names="target_category", values="number_of_readings", title="Share of Readings by Performance Category")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(by_category, use_container_width=True, hide_index=True)

# ============================================================================
# MODULE 5: Relationships
# ============================================================================
with tabs[4]:
    about(
        "Relationships",
        """
**Purpose**: explores whether two engineering variables actually move
together, using the current filtered data.

**Business read**: in this synthetic dataset only Fuel Injection Pressure
vs. NOx shows a real relationship (correlation ~0.99) -- a genuine
engineering lever. Air-fuel ratio vs. NOx shows essentially none; treat any
apparent pattern there as noise until confirmed on real measured data.
        """,
    )
    st.subheader("Air-Fuel Ratio vs. NOx")
    fig = px.scatter(filtered, x="equivalence_ratio", y="nox_emissions_g_per_kwh", color="combustion_mode", title="Equivalence Ratio vs. NOx")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Fuel Injection Pressure vs. NOx")
    fig2 = px.scatter(
        filtered, x="fuel_injection_pressure_bar", y="nox_emissions_g_per_kwh", color="combustion_mode",
        title="Fuel Injection Pressure vs. NOx", trendline="ols",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ============================================================================
# MODULE 6: Top Performers
# ============================================================================
with tabs[5]:
    about(
        "Top Performers",
        """
**Purpose**: surfaces the best individual operating points under the
current filters -- "what does a great run actually look like?"

**Business read**: use this as a reference/calibration target when tuning
a real engine -- the injection timing, pressure, and ratio values of the
top rows are the settings worth reproducing.
        """,
    )
    n = st.slider("How many rows", 5, 50, 10)
    top_n = filtered.nlargest(n, "target_score")[
        ["reading_id", "engine_load_percent", "combustion_mode", "injection_timing_deg", "equivalence_ratio",
         "boost_pressure_bar", "thermal_efficiency_pct", "nox_emissions_g_per_kwh", "target_score"]
    ]
    st.dataframe(top_n, use_container_width=True, hide_index=True)

# ============================================================================
# MODULE 7: Duty Cycles & Cost
# ============================================================================
with tabs[6]:
    about(
        "Duty Cycles & Cost",
        """
**Purpose**: converts the weighted engine-map result for each duty cycle
into annual $ (fuel + CO2) and a PASS/FAIL compliance flag, using the
sidebar's shared assumptions.

**Business read**: this is the number a buyer or finance team actually
wants -- not g/kWh, but dollars per year and "do we meet the limit."
Change the sidebar's fuel price / hours / carbon price and every row
recalculates instantly.
        """,
    )
    if live_duty_cycle_perf.empty:
        st.warning("No duty cycle has all its required load points in the current filter -- widen the load filter.")
    else:
        fig = px.bar(
            live_duty_cycle_perf, x="cycle_name", y="weighted_bsfc_g_per_kwh", color="industry",
            title="Weighted BSFC by Duty Cycle",
        )
        st.plotly_chart(fig, use_container_width=True)

        econ = add_cost_and_compliance(
            live_duty_cycle_perf, "weighted_bsfc_g_per_kwh", "weighted_nox_emissions",
            fuel_price, hours, rated_power, nox_limit, co2_factor, carbon_price,
        )
        display_cols = [
            "cycle_name", "industry", "application", "weighted_bsfc_g_per_kwh",
            "annual_fuel_kg", "annual_fuel_cost_usd", "annual_co2_tons", "annual_co2_cost_usd",
            "annual_total_cost_usd", "extra_annual_cost_vs_best_usd",
            "weighted_nox_emissions", "nox_compliance_status", "nox_pct_vs_limit",
        ]
        st.dataframe(econ[display_cols].round(2).sort_values("annual_total_cost_usd"), use_container_width=True, hide_index=True)
        fig_cost = px.bar(
            econ.sort_values("annual_total_cost_usd"), x="cycle_name", y="annual_total_cost_usd",
            color="nox_compliance_status", title="Annual Total Cost (Fuel + CO2) by Duty Cycle",
            color_discrete_map={"✅ PASS": "#2e7d32", "❌ FAIL": "#c62828"},
        )
        st.plotly_chart(fig_cost, use_container_width=True)

# ============================================================================
# MODULE 8: Mode-Switching ROI
# ============================================================================
with tabs[7]:
    about(
        "Mode-Switching ROI",
        """
**Purpose**: answers "if every engine were standardized on the single
best-performing combustion mode, what would we save per year?"

**Business read**: pairs with the Executive Summary's recommendation --
this is the detail behind that headline number, broken out per mode.
        """,
    )
    mode_perf = (
        filtered.groupby(["combustion_mode", "combustion_mode_description"])
        .agg(avg_bsfc_g_per_kwh=("bsfc_g_per_kwh", "mean"), avg_nox_emissions=("nox_emissions_g_per_kwh", "mean"),
             avg_target_score=("target_score", "mean"))
        .reset_index()
    )
    mode_econ = add_cost_and_compliance(
        mode_perf, "avg_bsfc_g_per_kwh", "avg_nox_emissions",
        fuel_price, hours, rated_power, nox_limit, co2_factor, carbon_price,
    )
    display_cols = [
        "combustion_mode", "combustion_mode_description", "avg_bsfc_g_per_kwh", "avg_target_score",
        "annual_fuel_cost_usd", "annual_co2_cost_usd", "annual_total_cost_usd", "extra_annual_cost_vs_best_usd",
    ]
    st.dataframe(mode_econ[display_cols].round(2).sort_values("annual_total_cost_usd"), use_container_width=True, hide_index=True)
    fig = px.bar(
        mode_econ.sort_values("annual_total_cost_usd"), x="combustion_mode", y="annual_total_cost_usd",
        title="Annual Total Cost (Fuel + CO2) by Combustion Mode",
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# MODULE 9: Try Your Own Duty Cycle
# ============================================================================
with tabs[8]:
    about(
        "Try Your Own Duty Cycle",
        """
**Purpose**: lets you define a custom load-time profile (not one of the
3 built-in cycles) and see its weighted cost/emissions result instantly,
computed against the currently filtered engine map -- no dbt rebuild or
seed-file edit needed for a one-off "what if" question.

**Business read**: use this to model a specific customer's actual duty
cycle before committing to the standard ISO test cycles.
        """,
    )
    st.write("Set a relative weight for each load point (auto-normalized to sum to 1):")
    default_weights = {10: 0.10, 25: 0.20, 50: 0.30, 75: 0.25, 100: 0.15}
    cols = st.columns(len(live_engine_map))
    user_weights = {}
    for col, (_, row) in zip(cols, live_engine_map.iterrows()):
        load = int(row["engine_load_percent"])
        user_weights[load] = col.number_input(
            f"{load}% load", min_value=0.0, value=default_weights.get(load, 0.2), step=0.05, key=f"w_{load}"
        )

    total_weight = sum(user_weights.values())
    if total_weight == 0:
        st.warning("Set at least one non-zero weight.")
    else:
        normalized = {k: v / total_weight for k, v in user_weights.items()}
        custom = live_engine_map.copy()
        custom["weight"] = custom["engine_load_percent"].astype(int).map(normalized)
        weighted_bsfc = (custom["weight"] * custom["avg_bsfc_g_per_kwh"]).sum()
        weighted_eff = (custom["weight"] * custom["avg_thermal_efficiency_pct"]).sum()
        weighted_nox = (custom["weight"] * custom["avg_nox_emissions"]).sum()
        weighted_soot = (custom["weight"] * custom["avg_soot_emissions"]).sum()
        weighted_co = (custom["weight"] * custom["avg_co_emissions"]).sum()

        st.markdown("#### Your custom duty cycle's weighted result")
        c1, c2, c3 = st.columns(3)
        c1.metric("Weighted BSFC", f"{weighted_bsfc:.2f} g/kWh")
        c2.metric("Weighted Thermal Efficiency", f"{weighted_eff:.2f}%")
        c3.metric("Weighted NOx", f"{weighted_nox:.3f} g/kWh")
        c4, c5 = st.columns(2)
        c4.metric("Weighted Soot", f"{weighted_soot:.3f} g/kWh")
        c5.metric("Weighted CO", f"{weighted_co:.3f} g/kWh")

        custom_cost = add_cost_and_compliance(
            pd.DataFrame([{"weighted_bsfc_g_per_kwh": weighted_bsfc, "weighted_nox_emissions": weighted_nox}]),
            "weighted_bsfc_g_per_kwh", "weighted_nox_emissions",
            fuel_price, hours, rated_power, nox_limit, co2_factor, carbon_price,
        ).iloc[0]
        c6, c7, c8 = st.columns(3)
        c6.metric("Annual Fuel Cost", f"${custom_cost['annual_fuel_cost_usd']:,.0f}")
        c7.metric("Annual CO2 Cost", f"${custom_cost['annual_co2_cost_usd']:,.0f}")
        c8.metric("NOx Compliance", custom_cost["nox_compliance_status"])

        compare = live_duty_cycle_perf[["cycle_name", "weighted_bsfc_g_per_kwh"]].copy() if not live_duty_cycle_perf.empty else pd.DataFrame(columns=["cycle_name", "weighted_bsfc_g_per_kwh"])
        compare = pd.concat(
            [compare, pd.DataFrame([{"cycle_name": "Your Custom Cycle", "weighted_bsfc_g_per_kwh": weighted_bsfc}])],
            ignore_index=True,
        )
        fig = px.bar(
            compare.sort_values("weighted_bsfc_g_per_kwh"), x="cycle_name", y="weighted_bsfc_g_per_kwh",
            color="cycle_name", title="Your Cycle vs. the Built-In Duty Cycles",
        )
        st.plotly_chart(fig, use_container_width=True)
