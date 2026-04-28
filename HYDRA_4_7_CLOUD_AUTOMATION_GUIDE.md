# HYDRA V4.7 — Cloud Automation Guide

You no longer need your laptop to run the backtest. GitHub will run it for you, free, in the cloud.

---

## How it works (2 minutes to read)

```
┌────────────────┐     git push     ┌────────────────┐
│ Your laptop    │ ───────────────► │  GitHub repo   │
│ (one-time)     │                  │  (the code)    │
└────────────────┘                  └────────┬───────┘
                                              │
                                              │ Actions auto-runs
                                              ▼
                                     ┌────────────────┐
                                     │ GitHub cloud   │
                                     │ Linux runner   │
                                     │  - 2-year      │
                                     │    backtest    │
                                     │  - War Room    │
                                     │  - Report      │
                                     └────────┬───────┘
                                              │
                                              │ commits results
                                              ▼
                                     ┌────────────────┐
                                     │ Your repo now  │
                                     │ has the report │
                                     └────────────────┘
```

You upload the project once. After that, every time you click "Run workflow" on the GitHub Actions page (or every time code is pushed that touches gating logic), GitHub spins up a free Linux machine, runs the full 99,298-cycle backtest, runs the War Room investigation, writes the final report with real numbers, and commits it back to the repo.

You never touch the laptop again for backtests.

---

## What's in the project for this

| File | Purpose |
|---|---|
| `.github/workflows/v47_pipeline.yml` | GitHub Actions workflow (the cloud recipe) |
| `.gitattributes` | Cross-platform line-ending and LFS rules |
| `.gitignore` | Don't push secrets, large per-cycle ledgers, or __pycache__ |
| `C:\Users\Mansur\Desktop\HYDRA_GitHub_Setup.bat` | One-click upload helper |
| `replay/run_v47_backtest.py` | The resumable backtest (already built) |
| `replay/war_room/` | The investigation toolkit (already built) |

---

## Step-by-step (one-time setup, ~10 minutes)

### Step 1 — Install Git for Windows

Go to https://git-scm.com/download/win and click the download. Run it. Click Next, Next, Install. That's it. (If you already have Git, skip.)

### Step 2 — Create an empty private repo on GitHub

1. Go to https://github.com/new
2. Owner: your username.
3. Repository name: `hydra-v4`
4. Visibility: **Private**.
5. **Important:** do NOT tick "Add a README", do NOT add .gitignore, do NOT add a license. Leave it empty.
6. Click "Create repository".

### Step 3 — Create a Personal Access Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)".
3. Note: `HYDRA upload`.
4. Expiration: 90 days is fine.
5. Scopes: tick the **`repo`** checkbox (this gives the token push access).
6. Click "Generate token".
7. **Copy the token now.** You will not see it again. It looks like `ghp_xxxxxxxx...`.

### Step 4 — Run the upload helper

Double-click `HYDRA_GitHub_Setup.bat` on your desktop.

It asks three things:
- Your GitHub username.
- The repo name (default `hydra-v4`).
- The token (paste; nothing visible while you paste — that's normal).

It then commits and pushes everything to your repo. About 30 seconds.

### Step 5 — Trigger the cloud run

1. Open `https://github.com/<yourusername>/hydra-v4/actions` in your browser.
2. On the left, click "HYDRA V4.7 — Backtest + War Room".
3. On the right, click "Run workflow", then the green "Run workflow" button.
4. The run starts. It takes ~30–60 minutes. You can close the browser; GitHub keeps running.

### Step 6 — Read the result

When the run finishes (you can watch live or come back later):

1. Repo home page now has the updated `HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md` with **real numbers** in place of the placeholders.
2. Inside `replay_runs/v47_warroom/` there are five sibling files:
   - `diagnostics.md`
   - `bottleneck_attribution.md`
   - `shadow_pnl.md`
   - `hypotheses.md`
   - `red_team.md`

You can paste the content of any of these into a chat with me and I will read the numbers and decide whether HYDRA 4.7 is closed or needs another rescue iteration.

---

## What costs money

Nothing for this scale. GitHub gives you:

- **Free private repos**: unlimited.
- **Free Actions minutes**: 2,000 / month for private repos. The HYDRA pipeline uses ~30–60 minutes per run.
- **Free LFS**: 1 GB storage / 1 GB bandwidth / month — the cached bars are well under this.

If you somehow hit the cap (you won't unless you re-run dozens of times) GitHub just pauses Actions until next month. No surprise bill.

---

## What is safe / not safe

- **Repo visibility:** Private. Only you can see the code and the cached bars.
- **Token:** the helper embeds the token only briefly to push, then strips it from the local config. The repo on GitHub never sees the token.
- **Secrets:** the workflow does not use any. No OANDA API key, no Anthropic key, no live order capability. The workflow is read-only against cached data.
- **Live trading:** disabled. LIVE_ORDER_GUARD is intact across all 6 layers. The cloud pipeline is replay-only.
- **What can leak:** if you accidentally tick "Public" instead of "Private" on the repo, the cached bars (just OHLC mid-prices) become public. That's not catastrophic but you should re-create the repo as private.

---

## دليل سريع بالعربي

١. ثبّت Git for Windows من https://git-scm.com/download/win — تثبيت عادي بدون أي تعديل.

٢. اعمل repo فاضي على GitHub باسم `hydra-v4`، اخترها **Private**، ولا تضيف README.

٣. اعمل Personal Access Token من https://github.com/settings/tokens، اختر `repo` فقط، انسخ الـ token.

٤. انقر مرّتين على `HYDRA_GitHub_Setup.bat` على سطح المكتب. اكتب اسم المستخدم، اسم الـ repo، الـ token. خلاص — رفع تلقائي.

٥. روح على `https://github.com/<اسمك>/hydra-v4/actions` → "HYDRA V4.7 — Backtest + War Room" → "Run workflow".

٦. ٣٠–٦٠ دقيقة وترجع تلقي التقرير النهائي بأرقام حقيقية في `HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md`. الصق محتواه في المحادثة وأنا أحلّل وأقرر مرحلة V4.8 أم لا.

كل شي مجاني، خاص، آمن، بلا live trading. ما تحتاج تشغّل أي شي محلياً أبداً بعد الإعداد الأول.

---

## Re-running later

After the first push, you can re-trigger the cloud run any time without touching your laptop:

1. Open `https://github.com/<yourusername>/hydra-v4/actions`.
2. Click "Run workflow".

If you change a gating rule (say in V4.8), commit the change with `git push` from the laptop or directly through the GitHub web editor (pencil icon on any file). The workflow auto-runs on every push that touches `gatemind/`, `chartmind/`, `marketmind/`, `newsmind/`, `orchestrator/`, `contracts/`, or `replay/`.

---

## Why this is the right architecture

You are not a sysadmin. You should not be running 30-minute backtests on your laptop. The job belongs in the cloud, where:

- Disk is unlimited (the `/tmp` issue that wedged my sandbox doesn't exist on GitHub runners).
- Compute is free for this scale.
- Results are version-controlled by default.
- You can step away and come back to the answer.

Setup happens once. After that, every iteration of HYDRA — V4.8, V4.9, V5 — re-uses the same pipeline with no extra plumbing.
