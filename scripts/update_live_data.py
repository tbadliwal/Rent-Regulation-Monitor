#!/usr/bin/env python3
"""Refresh 15-day rent-regulation discovery data for the static GitHub Pages monitor.

Design rule: this is DISCOVERY, not a legal baseline. It never edits baseline.json or
verified_events.json. If a state request fails, the previous successful state feed is kept.
"""
from __future__ import annotations
import json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data" / "baseline.json"
LIVE = ROOT / "data" / "live.json"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
WINDOW = "15d"
MAX_RECORDS = 12
THROTTLE_SECONDS = 5.2  # GDELT asks clients to avoid rapid-fire requests.

TOPIC_QUERY = '("rent control" OR "rent stabilization" OR "rent cap" OR "good cause eviction" OR "fair rent commission" OR "rental registry" OR "rent registry" OR "rent increase limit" OR "rent control ordinance")'
POLICY_WORDS = (
    "rent control", "rent stabilization", "rent cap", "good cause", "fair rent",
    "rental registry", "rent registry", "rent increase", "rent board", "rent guideline",
    "tenant protection", "landlord-tenant", "landlord tenant", "preemption", "decontrol",
    "rent ordinance", "rent-control", "rent-stabilization"
)
JUNK = ("mortgage", "hotel room", "airbnb price", "car rental", "vacation rental", "concert", "crypto")


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except Exception:
        return fallback


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Davis-Rent-Regulation-Monitor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def parse_seen(s: str):
    if not s:
        return ""
    # Typical GDELT: 20260918T183000Z
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    return s


def source_tier(domain: str):
    d=(domain or "").lower()
    if d.endswith(".gov") or d.endswith(".us") or ".gov." in d or any(x in d for x in ["legislature.", "legis.", "nysenate.gov", "revisor.mn.gov"]):
        return "A"
    if any(x in d for x in ["reuters.com", "apnews.com", "nytimes.com", "bloomberg.com", "npr.org", "wamc.org", "gothamist.com", "politico.com"]):
        return "B"
    return "C"


def classify(title: str):
    t=title.lower()
    if any(x in t for x in ["preempt", "preemption", "ban rent control", "prohibit rent control"]): typ="Preemption"
    elif any(x in t for x in ["good cause", "just cause"]): typ="Good Cause / Just Cause"
    elif any(x in t for x in ["registry", "registration", "audit", "enforcement", "complaint"]): typ="Registry / Enforcement"
    elif any(x in t for x in ["decontrol", "deregulat", "vacancy"]): typ="Vacancy / Decontrol"
    elif any(x in t for x in ["rent stabilization", "rent control", "rent cap", "rent increase"]): typ="Rent Amount Control"
    else: typ="Tenant / Rental Policy"

    if any(x in t for x in ["signed into law", "takes effect", "effective", "adopts", "adopted", "passes", "passed", "approved", "enacted"]): status="Enacted / Effective"
    elif any(x in t for x in ["proposal", "proposes", "proposed", "draft", "consider", "hearing", "ballot", "vote", "bill", "ordinance"]): status="Proposed / Process"
    elif any(x in t for x in ["lawsuit", "court", "judge", "appeal"]): status="Litigation"
    elif any(x in t for x in ["audit", "enforce", "registry", "registration", "commission"]): status="Enforcement / Administration"
    else: status="Discovery"
    return typ,status


def relevant(title: str):
    t=(title or "").lower()
    if not t or any(j in t for j in JUNK): return False
    return any(w in t for w in POLICY_WORDS)


def locality_from_title(title: str, localities):
    low=(title or "").lower()
    for loc in sorted(localities, key=len, reverse=True):
        if loc.lower() in low:
            return loc
    return ""


def normalize_article(a: dict, state_abbr: str, state_name: str, localities):
    title=(a.get("title") or "").strip()
    if not relevant(title): return None
    typ,status=classify(title)
    return {
        "state": state_abbr,
        "state_name": state_name,
        "locality": locality_from_title(title, localities),
        "published": parse_seen(a.get("seendate") or ""),
        "title": title,
        "url": a.get("url") or "",
        "domain": a.get("domain") or "",
        "source_country": a.get("sourcecountry") or "",
        "type": typ,
        "status": status,
        "source_tier": source_tier(a.get("domain") or ""),
        "verification": "Automated discovery — verify before relying on it"
    }


def sort_key(x):
    tier={"A":3,"B":2,"C":1}.get(x.get("source_tier"),0)
    return (x.get("published", ""), tier)


def main():
    base=load_json(BASELINE,{"states":{}})
    old=load_json(LIVE,{"state_feeds":{},"articles":[]})
    old_feeds=old.get("state_feeds") or {}
    state_feeds={}
    errors=[]
    all_articles=[]
    states=base.get("states") or {}

    # DC is searched too, even though it is not a state on a conventional 50-state map.
    for idx,(abbr,rec) in enumerate(states.items()):
        name=rec.get("name",abbr)
        localities=[x.get("name","") for x in rec.get("localities",[]) if x.get("name")]
        # Add city names to the query only for curated localities in high-information markets.
        q=f'{TOPIC_QUERY} "{name}" sourcecountry:US'
        params={"query":q,"mode":"artlist","format":"json","timespan":WINDOW,"maxrecords":MAX_RECORDS,"sort":"datedesc"}
        url=API+"?"+urllib.parse.urlencode(params)
        try:
            payload=fetch_json(url)
            feed=[]; seen=set()
            for raw in payload.get("articles",[]) or []:
                item=normalize_article(raw,abbr,name,localities)
                if not item or not item["url"] or item["url"] in seen: continue
                seen.add(item["url"]); feed.append(item)
            feed=sorted(feed,key=sort_key,reverse=True)[:10]
            state_feeds[abbr]=feed
            all_articles.extend(feed)
        except Exception as e:
            errors.append({"state":abbr,"error":str(e)[:240]})
            preserved=old_feeds.get(abbr,[]) if isinstance(old_feeds,dict) else []
            state_feeds[abbr]=preserved
            all_articles.extend(preserved)
        if idx < len(states)-1:
            time.sleep(THROTTLE_SECONDS)

    # Deduplicate national feed by canonical URL/title, favoring higher source tier and newer date.
    dedup={}
    for x in sorted(all_articles,key=sort_key,reverse=True):
        key=(x.get("url") or "").split("?")[0] or re.sub(r"\W+"," ",x.get("title","").lower()).strip()
        if key and key not in dedup: dedup[key]=x
    national=list(dedup.values())[:120]
    out={
      "generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
      "status":"ok" if len(errors)<8 else "partial",
      "window_days":15,
      "message":"Automated discovery feed. Items are candidates, not verified legal conclusions.",
      "articles":national,
      "state_feeds":state_feeds,
      "errors":errors,
      "method":"GDELT DOC 2.0 state-by-state query; relevance filter; last successful state feed preserved on upstream failure."
    }
    LIVE.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    print(f"Wrote {len(national)} national candidates across {len(states)} jurisdictions; errors={len(errors)}")

if __name__=="__main__": main()
