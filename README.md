# Davis Advisors — U.S. Rent Regulation Monitor

Static GitHub Pages dashboard with three deliberately separate layers:

1. **50-state statutory baseline** — statewide cap, local preemption/authority and priority localities.
2. **Verified archive** — curated high-signal developments linked to primary/official sources.
3. **Automated 15-day discovery** — GDELT-powered candidate feed refreshed every six hours. Discovery items never overwrite the legal baseline.

## Files

- `index.html` — dashboard UI.
- `data/baseline.json` — 50-state + DC baseline.
- `data/verified_events.json` — curated chronological developments.
- `data/live.json` — generated discovery snapshot.
- `scripts/update_live_data.py` — state-by-state 15-day discovery updater.
- `.github/workflows/refresh-and-deploy.yml` — refresh + GitHub Pages deployment every six hours.

## Deploy / upgrade existing repository

Upload the **contents** of this package into the root of the existing `Rent-Regulation-Monitor` repository, replacing `index.html` and `README.md` and adding the `data`, `scripts`, and `.github/workflows` folders.

Then in **Settings → Pages**, set **Source = GitHub Actions**.

Go to **Actions → Refresh rent-regulation data and deploy monitor → Run workflow**. The first run takes several minutes because the updater deliberately throttles GDELT requests. When the workflow finishes, the site will deploy and `data/live.json` will contain the current 15-day discovery layer.

## Research discipline

- Green = low current **direct rent-amount constraint**, not “no regulation.”
- Automated discovery is not legal verification.
- Priority/locality baselines should be re-checked against current statutes and ordinances before an investment decision.
- The 50-state posture layer is seeded from a September 16, 2026 statutory survey that links to controlling official state statutes; priority markets include direct official/primary source links.

## Security

GitHub Pages is public. Do not place Davis-confidential investment commentary, portfolio holdings, non-public analysis, credentials or secrets in this repository.
