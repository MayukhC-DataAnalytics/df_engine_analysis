# Deploying this dashboard to Streamlit Community Cloud

This app reads live from the Databricks tables `dbt build` already
created (`df_project.mart.*`). It does not copy or cache your data anywhere
outside Streamlit's own query cache (10-minute TTL).

## 1. Get this folder into a GitHub repo
Streamlit Community Cloud deploys from a public (or Streamlit-connected
private) GitHub repo. If `D:\analysis` isn't already pushed to GitHub:

```powershell
cd D:\analysis
git add df_engine_analysis
git commit -m "Add Streamlit dashboard"
git push
```

(If you don't want the whole `D:\analysis` repo public, create a fresh
repo containing just the `df_engine_analysis` folder instead.)

## 2. Create the app on Streamlit Community Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub.
2. Click **New app**.
3. Pick your repo and branch.
4. Set **Main file path** to `df_engine_analysis/streamlit_app/app.py`
   (adjust if your repo root is different).
5. Click **Deploy**. It will fail on first boot -- that's expected, you
   haven't added secrets yet (next step).

## 3. Add your Databricks credentials as Secrets
This is the step that keeps your token out of git entirely.

1. On your app's page, click **Settings** (⋮ menu) → **Secrets**.
2. Paste the contents of `.streamlit/secrets.toml.example` in this folder,
   with your real values filled in:

   ```toml
   [databricks]
   host = "xxxx.cloud.databricks.com"
   http_path = "/sql/1.0/warehouses/xxxxxxxxxxxxxxxx"
   token = "dapiXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
   catalog = "df_project"
   schema = "mart"
   ```

3. Save. The app reboots automatically and should now connect.

## 3b. (Optional) Add a free Groq API key for the AI "explain this" buttons
Every chart has a **🤖 Explain this in plain English** button, powered by
an open-source model (Meta's **Llama 3.3 70B**) hosted free by Groq -- no
credit card required, unlike a metered API. Without this key the rest of
the dashboard works fine -- clicking the button just shows a reminder to
add it.

1. Go to [console.groq.com](https://console.groq.com) → sign in (GitHub or
   Google login works) → **API Keys** → **Create API Key**. Copy it (starts
   with `gsk_`).
2. Add a second block to the same Streamlit Secrets box from step 3:
   ```toml
   [groq]
   api_key = "gsk_..."
   ```
3. Save -- the app reboots again.

**Usage control, by design**: explanations only run when a viewer clicks
the button (never automatically on page load), cap responses at 250
tokens, and are cached for an hour per (chart, data, assumptions)
combination -- so the same click twice in a row doesn't call the API
twice. If a lot of viewers click explain buttons at once, Groq's free tier
has a request-per-minute limit; the app catches that and shows "please
wait a minute and try again" instead of a raw error.

## 4. Keep the SQL warehouse reachable
- If you're on a **serverless** SQL warehouse, it auto-starts on the first
  query (viewers will see a ~30-60s delay on a cold start) and auto-stops
  after a period of inactivity -- no action needed, just expect that delay.
- If it's a **classic** warehouse that someone has to manually start, your
  dashboard will error for viewers whenever it's stopped. Either switch to
  serverless, or set the warehouse's auto-stop to a longer idle time.
- Use a Databricks personal access token scoped as narrowly as your admin
  allows (read-only on the `df_project` catalog). Rotate it periodically
  from Databricks (profile icon → Settings → Developer → Access tokens)
  and update the Streamlit secret -- the app needs no code change.

## 5. Try it locally first (optional, recommended)
```powershell
cd D:\analysis\df_engine_analysis\streamlit_app
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
REM edit .streamlit\secrets.toml with real values
streamlit run app.py
```
`.streamlit/secrets.toml` is already covered by `.gitignore`, so a local
copy never accidentally gets committed.

## What viewers can actually do
- **AI explanations on every chart**: click **🤖 Explain this in plain
  English** under any chart for a short, non-technical summary of what it
  shows, grounded in that chart's actual current numbers (not a canned
  description) -- requires the optional free Groq key from step 3b.
- **One shared control panel (sidebar)**: fuel price, operating hours,
  rated power, NOx limit, and carbon price apply to every cost/compliance
  figure in the app -- change one number once, not nine times across tabs.
- **Live data filters (sidebar)**: pick which combustion modes and which
  load points count. Every module -- including the duty-cycle weighting
  itself -- recomputes from the filtered data, so you can ask "what would
  our fuel cost be if we eliminated Diffusion mode entirely?" and get a
  real answer, not just a filtered chart.
- **Executive Summary tab**: the one screen for a non-engineer -- current
  annual cost, CO2 cost, compliance status, and a plain-language
  recommendation on whether switching duty cycle or combustion mode saves
  more.
- **Every tab has a "📘 About this module" expander** explaining its
  purpose, inputs, and how to read it for a business decision -- not just
  engineering context.
- Define a custom duty cycle (any load-point weighting) on the
  **Try Your Own Duty Cycle** tab and see it compared live against the
  three built-in ISO/illustrative cycles -- no dbt rebuild required for a
  one-off "what if" question.
- All of this recomputes in Python from data fetched once per 10-minute
  cache window, so moving a slider or filter is instant -- not a new
  Databricks query every time.

## Reusing this for a different company's engine data
1. Point your `profiles.yml` at the new data and run `dbt build` as usual
   (see `../STEP_BY_STEP.md`) -- this app makes no assumptions about which
   specific dataset is behind the mart tables, only that they have the
   same columns.
2. Nothing in `app.py` needs to change. Viewers now see the new engine's
   numbers the next time the 10-minute query cache expires (or restart the
   app to force an immediate refresh).
