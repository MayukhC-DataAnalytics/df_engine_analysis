# Step by step: rebuild the project in `workspace.df_project`

Every step below is run by you, by hand, so you learn what each one does.
Do the steps in order. Do not skip Step 5; it shows you what dbt built.

Where things live after this guide:

    Catalog  workspace
      Schema df_project          <- the "folder". Everything lives here.
        dual_fuel_engine_dataset_categorical   (raw CSV you upload)
        stg_engine_readings                    (view, built by dbt)
        dim_*, fct_*, mart_*                   (tables, built by dbt)
        duty_cycles                            (seed, built by dbt)

---

## Step 1. Clean up the old build (Databricks SQL editor)

Dropping is permanent. Look first, then drop.

```sql
SHOW SCHEMAS IN workspace;
```
You should see `raw`, `staging`, `marts` (plus `default` and `information_schema`, which you must NOT touch).

```sql
DROP SCHEMA IF EXISTS workspace.staging CASCADE;
DROP SCHEMA IF EXISTS workspace.marts   CASCADE;
DROP SCHEMA IF EXISTS workspace.raw     CASCADE;
```
`CASCADE` means "drop the schema and every table and view inside it".
The old raw CSV tables go too, which is why Step 3 uploads them again.

Then delete the old dashboard: left sidebar, **Dashboards**, tick **Dual-Fuel Engine Analysis**, delete.
It points at the schemas you just dropped, so it would show errors anyway.

## Step 2. Create the new schema

```sql
CREATE SCHEMA IF NOT EXISTS workspace.df_project;
```
In Databricks a schema is the folder that holds tables. Refresh **Catalog**, then
`workspace`, and you will see `df_project`.

(If you also want a folder for dashboards and notebooks: **Workspace**, **Create**, **Folder**,
name it `df_project`. That is a different thing from the schema and dbt does not use it.)

## Step 3. Upload the raw CSV

1. **Catalog**, `workspace`, `df_project`, **Create**, **Table**.
2. Upload `D:\analysis\df_engine_analysis\dual_fuel_engine_dataset_categorical.csv`.
3. Table name must be exactly: `dual_fuel_engine_dataset_categorical`
4. Create it. (The other CSV is optional; upload it as `dual_fuel_engine_dataset` if you want.)

Check it:
```sql
SELECT COUNT(*) FROM workspace.df_project.dual_fuel_engine_dataset_categorical;
```
Expected: **1463**.

## Step 4. Point dbt at df_project

Open `C:\Users\MAYUKH\.dbt\profiles.yml` (this file holds your token, so it stays outside the project).
Only one line changes: `schema:` must be `df_project`.

```yaml
df_engine_analysis:
  target: dev
  outputs:
    dev:
      type: databricks
      host: <your host>
      http_path: <your warehouse path>
      token: <your token>
      catalog: workspace
      schema: df_project
      threads: 4
```

## Step 5. Run dbt, one command at a time

Open a terminal and go to the project:
```
cd D:\analysis\df_engine_analysis\dbt_df_engine
```

| Command | What it does | What to check |
|---|---|---|
| `dbt debug` | Tests the connection and the config. | All checks pass. |
| `dbt seed` | Loads `seeds/duty_cycles.csv` as a table. | `duty_cycles` appears in df_project, 12 rows. |
| `dbt run --select stg_engine_readings` | Builds only the staging view. | A view appears in df_project. |
| `dbt run` | Builds every model in dependency order. | Dims, fact and marts appear. |
| `dbt test` | Runs every test. | All pass. |
| `dbt build` | Seed, run and test together, in order. | The one you will use day to day. |

Then in Databricks:
```sql
SELECT * FROM workspace.df_project.mart_duty_cycle_performance;
```
Expected weighted BSFC: **E3 236.21, D2 240.55, light-load genset 245.40**.

## Step 6. What each piece of code does

**`dbt_project.yml`** is dbt's settings file. `staging` models become views, `marts` models become tables.
There is no `+schema` any more, so everything uses the `schema:` from profiles.yml (`df_project`).

**`macros/generate_schema_name.sql`** is the macro dbt calls to decide which schema a model goes to.
With no custom schema set it simply returns your profile schema.

**`_sources.yml`** declares the raw table dbt did not build. Models read it with
`{{ source('raw_engine_data', 'dual_fuel_engine_dataset_categorical') }}`.

**`stg_engine_readings.sql` (staging, view)** renames columns, adds `reading_id`, changes no meaning.
Everything downstream builds on this, never on the raw table.

**`dim_combustion_mode.sql` and `dim_target_category.sql`** are small lookup tables
(one row per mode or category, with an id and a description).

**`fct_engine_readings.sql`** is the fact table: every measurement, joined to the dims with `{{ ref(...) }}`.
`ref()` is how one model points at another, and it is how dbt works out the build order.

**`mart_engine_map_by_load.sql`** groups the fact table by exact load (10, 25, 50, 75, 100)
and averages BSFC, efficiency and emissions. This is the "engine map".

**`seeds/duty_cycles.csv`** is a small CSV that dbt loads as a table. Each row is one load point
of one duty cycle, with its weight.

**`mart_duty_cycle_performance.sql`** is the headline model. It joins the seed to the engine map and
computes `sum(weight x value) / sum(weight)` per cycle. That is how the same engine gets a
different fuel figure for a marine propeller cycle and a lightly loaded generator.

**`mart_emissions_by_load_bucket.sql`** is a thin view of the engine map, kept so the old dashboard dataset still works.

**Tests.** In the `.yml` files: `unique`, `not_null`, `accepted_values`, `relationships`.
In `tests/`: two SQL files that return the bad rows, so zero rows means pass
(energy shares add to 100, cycle weights add to 1).

## Step 7. Rebuild the dashboard

**Dashboards**, **Create dashboard**, **Data** tab, add a dataset per query in `sql/dashboard_queries.sql`
(they already point at `workspace.df_project`). Start with query 8, the duty-cycle bar chart.

## If something fails

- **Table or view not found: dual_fuel_engine_dataset_categorical.** The upload name or schema is wrong. It must be `workspace.df_project.dual_fuel_engine_dataset_categorical`.
- **Column not found in staging.** The UI upload may have changed a column name. Run `DESCRIBE workspace.df_project.dual_fuel_engine_dataset_categorical;` and compare with `stg_engine_readings.sql`.
- **A test errors on its arguments.** dbt-fusion is strict, so paste the full error and the file name.
- **Permission or schema errors.** Check `catalog: workspace` and `schema: df_project` in profiles.yml.

Never paste your token into chat.
