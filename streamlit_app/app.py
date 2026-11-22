"""
Dual-Fuel Engine Analysis -- live Streamlit dashboard on top of the dbt
marts built in dbt_df_engine/. Deployed on Streamlit Community Cloud.

WHAT THIS APP DOES
- Connects live to the Databricks SQL warehouse (credentials come from
  st.secrets, never hardcoded -- see .streamlit/secrets.toml.example).
- Reads the finished mart tables dbt already built (df_project.mart.*).
- Renders the same 11 charts described in sql/dashboard_queries.sql, plus
  two interactive calculators where viewers move sliders and see numbers
  recompute instantly (no re-querying Databricks on every slider move --
  the raw per-cycle/per-mode numbers are fetched once and cached, then the
  $ math happens in pandas), and a "bring your own duty cycle" tool.

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

# ----------------------------------------------------------------------------
# Connection -- cached so Streamlit reuses one connection across reruns
# instead of opening a new one every time a viewer moves a slider.
# ----------------------------------------------------------------------------


@st.cache_resource
def get_connection():
    return sql.connect(
        server_hostname=st.secrets["databricks"]["host"],
        http_path=st.secrets["databricks"]["http_path"],
        access_token=st.secrets["databricks"]["token"],
    )


CATALOG = st.secrets.get("databricks", {}).get("catalog", "df_project")
SCHEMA = st.secrets.get("databricks", {}).get("schema", "mart")


def t(table_name: str) -> str:
    """Fully-qualified table name: catalog.schema.table."""
    return f"{CATALOG}.{SCHEMA}.{table_name}"


@st.cache_data(ttl=600, show_spinner="Querying Databricks...")
def run_query(query: str) -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute(query)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    return pd.DataFrame(rows, columns=columns)


# ----------------------------------------------------------------------------
# Page header
# ----------------------------------------------------------------------------

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
dataset. Treat this app as a demonstration of the **method** -- weighting
an engine map by a duty cycle, and turning that into cost/compliance
numbers -- not as real engine facts. Point it at real measured data to get
real answers.
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

tabs = st.tabs(
    [
        "Overview",
        "Combustion Modes",
        "Engine Load",
        "Performance Categories",
        "Relationships",
        "Top Performers",
        "Duty Cycles & Cost",
        "Mode-Switching ROI",
        "Try Your Own Duty Cycle",
    ]
)

# ----------------------------------------------------------------------------
# Tab 1 -- Overview (KPI counters)
# ----------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Overall KPIs")
    kpis = run_query(
        f"""
        select
            count(*)                               as total_readings,
            round(avg(thermal_efficiency_pct), 2)  as avg_thermal_efficiency_pct,
            round(avg(nox_emissions_g_per_kwh), 3) as avg_nox_emissions,
            round(avg(target_score), 2)            as avg_target_score
        from {t('fct_engine_readings')}
        """
    ).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Readings", f"{int(kpis['total_readings']):,}")
    c2.metric("Avg Thermal Efficiency", f"{kpis['avg_thermal_efficiency_pct']}%")
    c3.metric("Avg NOx Emissions", f"{kpis['avg_nox_emissions']} g/kWh")
    c4.metric("Avg Target Score", f"{kpis['avg_target_score']}")

    st.subheader("Engine Map by Load")
    engine_map = run_query(
        f"select * from {t('mart_engine_map_by_load')} order by engine_load_percent"
    )
    fig = px.line(
        engine_map,
        x="engine_load_percent",
        y="avg_bsfc_g_per_kwh",
        markers=True,
        title="Average BSFC vs. Engine Load",
        labels={"engine_load_percent": "Engine Load (%)", "avg_bsfc_g_per_kwh": "BSFC (g/kWh)"},
    )
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------
# Tab 2 -- Combustion Modes
# ----------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Efficiency & Emissions by Combustion Mode")
    st.caption(
        "Caution: in this synthetic data the three modes are nearly identical "
        "(target scores ~10.07 / 10.02 / 9.98) -- do not read small gaps as "
        "real engine behaviour."
    )
    by_mode = run_query(f"select * from {t('mart_performance_by_mode')}")
    metric = st.radio(
        "Metric",
        ["avg_thermal_efficiency_pct", "avg_bsfc_g_per_kwh", "avg_nox_emissions", "avg_target_score"],
        horizontal=True,
    )
    fig = px.bar(by_mode, x="combustion_mode", y=metric, color="combustion_mode", title=metric)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(by_mode, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Tab 3 -- Engine Load
# ----------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Emissions & Efficiency vs. Engine Load")
    by_load = run_query(
        f"select * from {t('mart_emissions_by_load_bucket')} order by engine_load_percent"
    )
    fig = px.line(
        by_load,
        x="engine_load_bucket",
        y=["avg_nox_emissions", "avg_soot_emissions", "avg_co_emissions"],
        markers=True,
        title="Emissions by Load Bucket",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(by_load, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Tab 4 -- Performance Categories
# ----------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Readings by Performance Category")
    by_category = run_query(f"select * from {t('mart_target_category_summary')}")
    fig = px.pie(
        by_category,
        names="target_category",
        values="number_of_readings",
        title="Share of Readings by Performance Category",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(by_category, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Tab 5 -- Relationships (scatter plots)
# ----------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Air-Fuel Ratio vs. NOx")
    st.caption("Essentially no relationship in this synthetic data (correlation ~0.01).")
    eq_ratio = run_query(
        f"""
        select f.equivalence_ratio, f.nox_emissions_g_per_kwh, m.combustion_mode
        from {t('fct_engine_readings')} f
        join {t('dim_combustion_mode')} m using (combustion_mode_id)
        """
    )
    fig = px.scatter(
        eq_ratio,
        x="equivalence_ratio",
        y="nox_emissions_g_per_kwh",
        color="combustion_mode",
        title="Equivalence Ratio vs. NOx",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Fuel Injection Pressure vs. NOx")
    st.caption("The one strong relationship in this synthetic data (correlation ~0.99).")
    inj_pressure = run_query(
        f"""
        select f.fuel_injection_pressure_bar, f.nox_emissions_g_per_kwh, m.combustion_mode
        from {t('fct_engine_readings')} f
        join {t('dim_combustion_mode')} m using (combustion_mode_id)
        """
    )
    fig2 = px.scatter(
        inj_pressure,
        x="fuel_injection_pressure_bar",
        y="nox_emissions_g_per_kwh",
        color="combustion_mode",
        title="Fuel Injection Pressure vs. NOx",
        trendline="ols",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------------------------------
# Tab 6 -- Top Performers
# ----------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Top 10 Best-Performing Runs")
    n = st.slider("How many rows", 5, 50, 10)
    top_n = run_query(
        f"""
        select reading_id, engine_load_percent, injection_timing_deg, equivalence_ratio,
               boost_pressure_bar, thermal_efficiency_pct, nox_emissions_g_per_kwh, target_score
        from {t('fct_engine_readings')}
        order by target_score desc
        limit {n}
        """
    )
    st.dataframe(top_n, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------------
# Tab 7 -- Duty Cycles & Cost calculator (interactive, computed in pandas)
# ----------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Same Engine, Different Duty Cycle")
    duty_cycle_perf = run_query(f"select * from {t('mart_duty_cycle_performance')} order by weighted_bsfc_g_per_kwh")
    fig = px.bar(
        duty_cycle_perf,
        x="cycle_name",
        y="weighted_bsfc_g_per_kwh",
        color="industry",
        title="Weighted BSFC by Duty Cycle",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("💰 Fuel Cost & Emissions Compliance Calculator")
    st.caption(
        "Move the sliders to match a real engine/contract and the table "
        "below recalculates instantly -- no page reload, no new query."
    )
    col1, col2, col3, col4 = st.columns(4)
    fuel_price = col1.number_input("Fuel price ($/kg)", min_value=0.0, value=1.10, step=0.05)
    hours = col2.number_input("Operating hours/year", min_value=0, value=4000, step=100)
    rated_power = col3.number_input("Rated power (kW)", min_value=1, value=1000, step=50)
    nox_limit = col4.number_input("NOx limit (g/kWh)", min_value=0.0, value=14.4, step=0.1)

    econ = duty_cycle_perf.copy()
    econ["annual_fuel_kg"] = (econ["weighted_bsfc_g_per_kwh"] * rated_power * hours) / 1000.0
    econ["annual_fuel_cost_usd"] = econ["annual_fuel_kg"] * fuel_price
    econ["extra_annual_cost_vs_best_cycle_usd"] = (
        econ["annual_fuel_cost_usd"] - econ["annual_fuel_cost_usd"].min()
    )
    econ["nox_compliance_status"] = econ["weighted_nox_emissions"].apply(
        lambda v: "✅ PASS" if v <= nox_limit else "❌ FAIL"
    )
    econ["nox_pct_vs_limit"] = round((econ["weighted_nox_emissions"] - nox_limit) / nox_limit * 100, 1)

    display_cols = [
        "cycle_name", "industry", "application",
        "weighted_bsfc_g_per_kwh", "annual_fuel_kg", "annual_fuel_cost_usd",
        "extra_annual_cost_vs_best_cycle_usd", "weighted_nox_emissions",
        "nox_compliance_status", "nox_pct_vs_limit",
    ]
    st.dataframe(
        econ[display_cols].round(2).sort_values("annual_fuel_cost_usd"),
        use_container_width=True,
        hide_index=True,
    )
    fig_cost = px.bar(
        econ.sort_values("annual_fuel_cost_usd"),
        x="cycle_name",
        y="annual_fuel_cost_usd",
        color="nox_compliance_status",
        title="Annual Fuel Cost by Duty Cycle",
        color_discrete_map={"✅ PASS": "#2e7d32", "❌ FAIL": "#c62828"},
    )
    st.plotly_chart(fig_cost, use_container_width=True)

# ----------------------------------------------------------------------------
# Tab 8 -- Combustion-Mode Switching ROI
# ----------------------------------------------------------------------------
with tabs[7]:
    st.subheader("🔁 Combustion-Mode Switching ROI")
    st.caption(
        "If every engine were standardized on the single best-performing "
        "combustion mode instead of today's mix, what would it save per year?"
    )
    col1, col2, col3 = st.columns(3)
    fuel_price2 = col1.number_input("Fuel price ($/kg)", min_value=0.0, value=1.10, step=0.05, key="roi_price")
    hours2 = col2.number_input("Operating hours/year", min_value=0, value=4000, step=100, key="roi_hours")
    rated_power2 = col3.number_input("Rated power (kW)", min_value=1, value=1000, step=50, key="roi_power")

    by_mode_roi = run_query(f"select * from {t('mart_performance_by_mode')}").copy()
    by_mode_roi["annual_fuel_cost_usd"] = (
        by_mode_roi["avg_bsfc_g_per_kwh"] * rated_power2 * hours2 / 1000.0 * fuel_price2
    )
    by_mode_roi["potential_annual_savings_usd_if_switched"] = (
        by_mode_roi["annual_fuel_cost_usd"] - by_mode_roi["annual_fuel_cost_usd"].min()
    )
    st.dataframe(
        by_mode_roi[
            ["combustion_mode", "combustion_mode_description", "avg_bsfc_g_per_kwh",
             "avg_target_score", "annual_fuel_cost_usd", "potential_annual_savings_usd_if_switched"]
        ].round(2).sort_values("annual_fuel_cost_usd"),
        use_container_width=True,
        hide_index=True,
    )
    fig = px.bar(
        by_mode_roi.sort_values("annual_fuel_cost_usd"),
        x="combustion_mode",
        y="annual_fuel_cost_usd",
        title="Annual Fuel Cost by Combustion Mode",
    )
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------
# Tab 9 -- Try Your Own Duty Cycle (fully interactive, no dbt rebuild needed)
# ----------------------------------------------------------------------------
with tabs[8]:
    st.subheader("🧪 Try Your Own Duty Cycle")
    st.caption(
        "Define how much time YOUR engine spends at each load point, and "
        "see the weighted result instantly -- computed live against the "
        "engine map dbt already built, with no need to edit a seed file "
        "or re-run dbt."
    )
    engine_map = run_query(
        f"select * from {t('mart_engine_map_by_load')} order by engine_load_percent"
    )
    st.write("Set a relative weight for each load point (they'll be auto-normalized to sum to 1):")

    default_weights = {10: 0.10, 25: 0.20, 50: 0.30, 75: 0.25, 100: 0.15}
    cols = st.columns(len(engine_map))
    user_weights = {}
    for col, (_, row) in zip(cols, engine_map.iterrows()):
        load = int(row["engine_load_percent"])
        user_weights[load] = col.number_input(
            f"{load}% load", min_value=0.0, value=default_weights.get(load, 0.2), step=0.05, key=f"w_{load}"
        )

    total_weight = sum(user_weights.values())
    if total_weight == 0:
        st.warning("Set at least one non-zero weight.")
    else:
        normalized = {k: v / total_weight for k, v in user_weights.items()}
        custom = engine_map.copy()
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

        compare = run_query(f"select cycle_name, weighted_bsfc_g_per_kwh from {t('mart_duty_cycle_performance')}")
        compare = pd.concat(
            [compare, pd.DataFrame([{"cycle_name": "Your Custom Cycle", "weighted_bsfc_g_per_kwh": weighted_bsfc}])],
            ignore_index=True,
        )
        fig = px.bar(
            compare.sort_values("weighted_bsfc_g_per_kwh"),
            x="cycle_name",
            y="weighted_bsfc_g_per_kwh",
            color="cycle_name",
            title="Your Cycle vs. the Built-In Duty Cycles",
        )
        st.plotly_chart(fig, use_container_width=True)
