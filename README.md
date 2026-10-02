# Rent Regulation Monitor v4

In-place upgrade for `tbadliwal/Rent-Regulation-Monitor`.

## Core design

v4 separates signals that should not be mixed:

1. **Legal Structure** — curated current legal posture. This drives the base map and changes only after legal review.
2. **30-Day Momentum** — U.S.-only live discovery classified as Restrictive / Easing / Mixed / Neutral / Quiet. This never automatically rewrites the legal baseline.
3. **Property Coverage** — which properties/tenancies are actually subject to the rule, including building-age/new-construction tests, key exemptions and vacancy mechanics.
4. **Verified Chronology** — high-signal events tied to primary or reliable sources.

## Major v4 changes

- Map-first home page; duplicate national feed and static KPI strip removed.
- Dedicated **National Activity** tab with working state/topic/direction/source-tier/time-window/sort filters.
- Discovery disclaimer appears once at the top of the live feed, not on every article.
- Live window expanded from 15 to **30 days**.
- National discovery is **U.S.-only** and uses a small number of topical national queries rather than 51 state-by-state calls.
- Two discovery providers: GDELT DOC 2.0 + U.S.-localized Google News RSS.
- Still-in-window items from the prior successful snapshot are carried forward when a fresh provider pull is thin, preventing the feed from collapsing because of one weak API response.
- State dossier redesigned into four clean tabs in this order: **Live Activity → Property Coverage → Localities → Legal Framework**.
- State Live Activity shows current 30-day candidates first and verified chronology second.
- Dynamic locality watch combines curated priority markets with localities detected in live/verified activity and promotes the most active markets.
- Property scope is surfaced on both live and verified event cards.
- Priority applicability deep dives include California, Oregon, Washington, Minnesota/Saint Paul, New York, New Jersey, Connecticut, Maine, Maryland and D.C.

## Important underwriting corrections / validations

- **California:** statewide TPA new-construction exemption is a rolling 15-year certificate-of-occupancy test.
- **Oregon:** the statewide percentage-cap exemption is also **less than 15 years** from first certificate of occupancy — not 13 years.
- **Washington:** the statewide annual-cap exemption applies where first certificate of occupancy was issued **12 or less years** before the increase notice.
- **Saint Paul:** newly constructed rental properties first certificated after Dec. 31, 2004 are exempt from the rent-increase limitation.
- **New Jersey:** qualifying newly constructed multiple dwellings may be exempt from local rent control for the initial mortgage amortization period or 30 years, whichever is less; without initial mortgage financing, 30 years.
- **NYC RGB Order 58:** for covered rent-stabilized leases commencing Oct. 1, 2026 through Sept. 30, 2027, the adopted adjustments are 0% for one-year leases and 1.75% for two-year leases.

## Files to replace in the existing repository

Upload these while preserving folders:

- `index.html`
- `README.md`
- `scripts/update_live_data.py`
- `data/applicability.json`
- `data/live.json`
- `data/verified_updates.json`

Do **not** delete:

- `data/baseline.json`
- `data/verified_events.json`
- `.github/workflows/refresh-and-deploy.yml`

Your existing GitHub Actions workflow is compatible with the new updater because it already runs `scripts/update_live_data.py` and deploys the repository. Uploading `index.html` / `scripts/**` should trigger it automatically. If it does not, use **Actions → Refresh rent-regulation data and deploy monitor → Run workflow**.

## Post-deploy QA

After the Action turns green:

1. Hard refresh the live site (`Cmd + Shift + R`).
2. Confirm **National Activity** is visible in the top navigation and has more than the old three-item feed after the refresh.
3. Confirm the feed is newest-first and U.S.-only; test state, topic, direction, source tier and 7/15/30-day filters.
4. Toggle the map between **Legal Structure** and **30-Day Momentum**.
5. Click CA, OR, WA, MN, NY and NJ; confirm the state tabs open in this order: Live Activity, Property Coverage, Localities, Legal Framework.
6. Confirm California shows a 15-year statewide age test, Oregon 15 years, Washington 12 years, and Saint Paul the Dec. 31, 2004 new-construction test.
7. Open `data/live.json` in GitHub after the workflow. A successful v4 refresh should show `window_days: 30`, `health`, `direction_counts`, `state_feeds` and `locality_feeds`.

Automated discovery is a screening layer, not a legal conclusion. Asset-level underwriting should still verify the controlling statute/ordinance and property facts.
