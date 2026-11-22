# Learn dbt + Databricks by building this project

> **Status: already built, end to end.** Everything below (raw tables,
> dbt run, dashboard) has been done for you in this session, so you have
> a complete working example to learn from. This guide now doubles as a
> **reference** — read it to understand *why* each step exists, and use
> the steps to rebuild, tweak, or extend things yourself. Nothing stops
> you from deleting it all and redoing it by hand to cement what you
> learned; the guide works either way.

What exists right now, live in your Databricks workspace:
- Raw tables: `workspace.raw.dual_fuel_engine_dataset` and
  `..._categorical` (uploaded from your two CSVs)
- dbt-built tables: `workspace.staging.stg_engine_readings` (view) and
  six tables in `workspace.marts` (two dimensions, one fact, three
  dashboard-ready summaries) — see Step 6 for how dbt built these
- A published Lakeview dashboard named **"Dual-Fuel Engine Analysis"**
  (find it under **Dashboards** in the Databricks left sidebar), with
  a bar chart, line chart, pie chart, scatter plot, a 10-row table, and
  4 KPI counters, all built from 6 SQL datasets defined on its **Data**
  tab

You have two CSV files of simulated dual-fuel engine data. This guide
walks through how that data ended up in Databricks, got cleaned and
organized by dbt, and fed a dashboard — so you understand *why* every
step exists, not just *how* to click through it.

Read this top to bottom once. Then use it as a reference whenever you
want to change something or rebuild a piece yourself.

---

## 0. The big picture

```
 Your laptop                 Databricks (free edition)
 ┌─────────────┐             ┌───────────────────────────────────────────┐
 │ 2 CSV files │──(upload)──▶│ CATALOG: workspace                         │
 └─────────────┘             │   schema: raw                              │
                              │     - dual_fuel_engine_dataset             │
                              │     - dual_fuel_engine_dataset_categorical │
                              │                    │                       │
                              │            dbt reads raw,                 │
                              │            writes clean + modeled data    │
                              │                    ▼                       │
                              │   schema: staging  (views)                 │
                              │     - stg_engine_readings                  │
                              │   schema: marts    (tables)                │
                              │     - dim_combustion_mode                  │
                              │     - dim_target_category                  │
                              │     - fct_engine_readings                  │
                              │     - mart_performance_by_mode             │
                              │     - mart_emissions_by_load_bucket        │
                              │     - mart_target_category_summary         │
                              └───────────────────┬─────────────────────┘
                                                   │
                                        SQL queries read the marts
                                                   ▼
                                        Databricks Lakeview Dashboard
```

> **Update:** this workspace's Free Edition doesn't allow creating extra
> catalogs (`CREATE CATALOG` fails), so everything lives in the **one**
> catalog you already have (usually named `workspace` — confirm with
> `SHOW CATALOGS;`). We get the same "raw zone vs. analytics zone"
> separation using **schemas** instead of catalogs: `raw`, `staging`,
> and `marts`, all inside that one catalog.

A **catalog** is the top-level container in Databricks (think: a whole
database server). A **schema** is a folder inside a catalog. A **table**
lives inside a schema. So the full address of any table is always
`catalog.schema.table` — here that's always `workspace.<schema>.<table>`.

---

## 1. Concepts, explained plainly

**Databricks** — a cloud platform for running SQL and Spark on big data.
For this project, think of it as "a place that stores tables and lets you
run SQL against them," plus a UI for uploading files and building charts.

**SQL warehouse** — the compute engine that actually runs your SQL
queries. It has to be "on" (running) for queries to work. Free Edition
gives you a small serverless one already — you just need to make sure
it's started.

**Catalog / schema / table** — see the picture above. `catalog.schema.table`
is just like `folder/subfolder/file` but for data.

**dbt (data build tool)** — a tool that lets you write SQL `SELECT`
statements, and it handles turning each one into a real table or view,
in the right order, automatically. You never write `CREATE TABLE` by
hand — you just write what the table *should contain*, and dbt figures
out the rest.

**Source** — a raw table that already exists (we made it by uploading a
CSV). You declare it in a `.yml` file so dbt knows about it.

**Model** — any `.sql` file inside `models/`. Each one is one `SELECT`
statement, and dbt turns it into one table or view. Models can reference
other models.

**`ref()`** — the function you use inside a model to point at *another
model* (never write another model's raw table name by hand). This is how
dbt knows which models depend on which, so it can run them in the right
order.

**Materialization** — *how* a model gets built:
- `view` — a saved query. Fast to create, always fresh, but re-runs the
  underlying query every time someone reads it.
- `table` — a real, physical copy of the result. Slower to build, but
  fast to read — good for anything a dashboard will hit repeatedly.

**Staging → Marts** — the standard dbt layering:
- **staging**: one model per raw source, doing only light cleanup
  (renaming, type-casting). Boring by design.
- **marts**: the "finished" layer — dimension tables, fact tables, and
  summary tables, built for a specific question or dashboard.

**Test** — an assertion dbt checks for you, like "this column should
never be null" or "this column should only ever contain these values."
Run with `dbt test`.

**Lakeview Dashboard** — Databricks' built-in dashboard tool. You write
a SQL query, turn its result into a chart ("visualization"), and pin
several charts onto one dashboard page.

---

## 2. Step 1 — Confirm your Databricks workspace and warehouse

1. Log into your Databricks Free Edition workspace in a browser.
2. In the left sidebar, go to **SQL Warehouses**. You should see one
   already created for you (often named "Serverless Starter Warehouse").
   Click it, and if it's not already running, start it.
3. While you're on that warehouse's page, click the **Connection details**
   tab and note down:
   - **Server hostname** (looks like `xxxx.cloud.databricks.com`)
   - **HTTP path** (looks like `/sql/1.0/warehouses/xxxxxxxxxxxxxxxx`)

   You'll need both of these in Step 5.

---

## 3. Step 2 — Create the schemas

First, find the name of your one catalog:

```sql
SHOW CATALOGS;
```

It's commonly named `workspace`. The rest of this guide assumes that —
if yours is different, swap it in everywhere you see `workspace.` below
(including in `profiles_example.yml` and `sql/dashboard_queries.sql`).

Now open the **SQL Editor** in Databricks (left sidebar) and run these
one at a time. This is you doing, by hand, the "folder structure" from
the picture above — three schemas inside your one catalog:

```sql
CREATE SCHEMA IF NOT EXISTS workspace.raw;
CREATE SCHEMA IF NOT EXISTS workspace.staging;
CREATE SCHEMA IF NOT EXISTS workspace.marts;
```

---

## 4. Step 3 — Upload the raw CSVs

1. In Databricks, go to **Catalog** (left sidebar) → find your catalog
   (`workspace`) → `raw`.
2. Click **Create** → **Table** → **Upload file** (the exact wording
   may say "Add data" → "Upload files to volume/table" depending on
   your workspace version).
3. Upload `D:\analysis\df_engine_analysis\dual_fuel_engine_dataset.csv`.
   - Set the **catalog** to `workspace`, **schema** to `raw`.
   - Set the **table name** to exactly: `dual_fuel_engine_dataset`
   - Let Databricks auto-detect column types from the header row.
4. Repeat for `dual_fuel_engine_dataset_categorical.csv`, table name
   exactly: `dual_fuel_engine_dataset_categorical`

Quick sanity check back in the SQL Editor:

```sql
SELECT * FROM workspace.raw.dual_fuel_engine_dataset_categorical LIMIT 5;
```

You should see your data. This table is now the "inbox" — dbt will read
from it but never change it.

---

## 5. Step 4 — Install dbt on your machine

Open a terminal and run:

```powershell
pip install dbt-databricks
```

This installs dbt-core plus the Databricks-specific adapter (the plugin
that knows how to talk to Databricks specifically). Confirm it worked:

```powershell
dbt --version
```

---

## 6. Step 5 — Set up your connection (profiles.yml)

dbt keeps your secret token in a file *outside* the project, so it never
accidentally gets shared or backed up with the project.

1. Create the folder `C:\Users\MAYUKH\.dbt\` if it doesn't already exist.
2. Copy `D:\analysis\df_engine_analysis\dbt_df_engine\profiles_example.yml`
   into that folder and rename it to `profiles.yml`.
3. In Databricks: click your profile icon (top-right) → **Settings** →
   **Developer** → **Access tokens** → **Generate new token**. Copy it
   immediately (Databricks shows it only once).
4. Fill in the 3 placeholders in `profiles.yml`:
   - `host` → the server hostname from Step 1
   - `http_path` → the HTTP path from Step 1
   - `token` → the access token you just generated

---

## 7. Step 6 — Run dbt

From a terminal, move into the project folder and run each command,
reading what it prints:

```powershell
cd D:\analysis\df_engine_analysis\dbt_df_engine

dbt debug     REM checks your connection actually works
dbt run       REM builds every model (views + tables), in dependency order
dbt test      REM runs all the data-quality checks from the .yml files
```

If `dbt debug` fails, it's almost always one of: warehouse not running,
wrong host/http_path, or an expired/incorrect token. Fix and re-run.

Once `dbt run` succeeds, go back to the Databricks SQL Editor and look:

```sql
SHOW TABLES IN workspace.staging;
SHOW TABLES IN workspace.marts;

SELECT * FROM workspace.marts.mart_performance_by_mode;
```

Optional but worth doing once, to *see* the dependency graph we talked
about:

```powershell
dbt docs generate
dbt docs serve
```

This opens a browser page with a diagram of every model and how they
connect (source → staging → dims/fact → marts).

---

## 8. Step 7 — Build the dashboard

This is already done — open **Dashboards** in the left sidebar and click
**Dual-Fuel Engine Analysis** to see it. Here's how it's built, and how
to rebuild or extend it yourself:

A Lakeview dashboard has two tabs: **Data** and a canvas page (here,
named **Overview**).

1. **Data tab**: holds "datasets" — each one is a named SQL query. This
   dashboard has 6, one per chart: `Performance by Combustion Mode`,
   `Emissions by Load Bucket`, `Performance Category Summary`,
   `Overall KPIs`, `Equivalence Ratio vs NOx`, `Top 10 Best Performing`.
   Each is just `select * from workspace.marts.<table>` (or a small join)
   — all the hard work already happened in dbt, so these stay simple.
   You can see and edit them anytime by clicking **Data**.
2. **Canvas page**: click the chart-icon tool in the floating toolbar,
   then click-and-drag on the grid to draw a new tile. In the panel on
   the right: pick a **Visualization** type (Bar, Line, Pie, Scatter,
   Table, Counter, ...), then pick which **dataset** feeds it, then map
   fields to **X axis / Y axis / Color / Value** etc. Drag a tile's edge
   to resize it; drag its border to move it.
3. The 4 KPI numbers (Total Readings, Avg Thermal Efficiency %, Avg NOx
   Emissions, Avg Target Score) are all **Counter** visualizations
   pointed at the same `Overall KPIs` dataset, each showing a different
   column.
4. Click **Publish** (top right) whenever you want your changes visible
   to others / in the clean "published" view — editing the draft never
   changes what a published viewer sees until you publish again.

You now have a working dashboard built entirely on top of tables dbt
created — if the raw data changes and you re-run `dbt run`, the
dashboard updates automatically next time it refreshes, with zero manual
rework.

> `sql/dashboard_queries.sql` in this project still has the same 6
> queries as plain SQL, with comments on what chart type/fields to use —
> handy if you ever want to paste one into the ad hoc **SQL Editor**
> instead of using the dashboard's Data tab.

---

## 9. Two real bugs we hit (worth knowing about)

Your machine runs **dbt-fusion** (`dbt --version` shows
`dbt-fusion 2.0.0-preview.*`), a newer, stricter dbt engine. Two things
it caught that plain dbt-core might not:

1. **Jinja renders inside SQL comments too.** A `-- {{ ref('x') }}`
   comment explaining what `ref()` does isn't safe — dbt's templating
   engine processes the whole file, comments included, so literal
   `{{ }}` text there can crash the parse. Lesson: never write `{{ }}`
   in a comment unless you mean it as real Jinja.
2. **Newer test syntax.** dbt-fusion wants test arguments nested under
   an `arguments:` key — e.g. `accepted_values: {arguments: {values: [...]}}`
   instead of the older flat `accepted_values: {values: [...]}`. If you
   add a new test and get a `DbtYamlValidationError` about deprecated
   arguments, this is why — check `models/staging/_staging.yml` and
   `models/marts/_marts.yml` for the current pattern to copy.

## 10. What you actually learned

- Databricks' object hierarchy: catalog → schema → table.
- The ELT pattern: load raw data first, transform it *inside* the
  warehouse afterward (as opposed to transforming it before loading).
- dbt's core building blocks: sources, models, `ref()`, materializations,
  tests, docs.
- The staging → dimension/fact → marts layering, and why each layer
  exists.
- Turning SQL into charts and a dashboard in Databricks Lakeview.

## 11. Ideas to keep going

- Add a new column to `stg_engine_readings` (e.g. a `diesel_to_gasoline_ratio`
  computed column) and watch it flow downstream after `dbt run`.
- Add a new test, e.g. that `engine_load_percent` is always between 0
  and 100 (`dbt_utils.accepted_range` — this needs installing the
  `dbt_utils` package, a good next lesson in dbt package management).
- Try changing `mart_performance_by_mode` from a `table` to an
  `incremental` materialization and read why incremental models exist.
- Schedule `dbt run` to happen automatically on a schedule using
  Databricks Workflows, so your dashboard stays fresh without you
  typing `dbt run` by hand.
