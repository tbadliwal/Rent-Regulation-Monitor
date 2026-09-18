# Residential Rent Regulation Monitor — Phase 1

Self-contained static website for Davis Advisors residential rent-regulation research.

## What is in this build
- One `index.html` containing the CSS, JavaScript, initial state/locality dataset and interactive UI.
- Plotly is loaded from its public CDN for the geographic U.S. map.
- A built-in CSS tile map appears automatically if Plotly cannot load.
- Six priority-state baselines are populated: CA, OR, WA, MN, NY and NJ.
- All other states are explicitly marked **Pending audit**, not low risk.

## Fastest GitHub Pages deployment
1. Create a new public GitHub repository, e.g. `Rent-Regulation-Monitor`.
2. Upload `index.html`, `README.md`, and `.nojekyll` to the repository root.
3. Open **Settings → Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Select branch `main` and folder `/ (root)`, then Save.
6. GitHub will provide the permanent site URL after the Pages build completes.

## Later automation
Do not add an automated discovery/update workflow until the UI and research taxonomy are approved. The next build should separate curated verified data from live discovery candidates, following the pattern used in the Data Center Monitor.

## Security
GitHub Pages repositories/sites are generally public. Do not publish confidential Davis analysis or internal commentary unless approved for public exposure.
