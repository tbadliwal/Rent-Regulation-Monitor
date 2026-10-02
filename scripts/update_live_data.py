#!/usr/bin/env python3
"""Refresh a U.S.-only 30-day rent-regulation discovery layer.

v4 design:
- Query nationally by topic (few requests) instead of 51 state-by-state calls.
- Keep automated discovery separate from legal baseline / verified archive.
- Require a U.S. jurisdiction signal (state/locality/federal-national) before retaining an item.
- Classify policy direction and property-scope hints for monitoring only.
"""
from __future__ import annotations

import json
import re
import time
import html as html_lib
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data" / "baseline.json"
LIVE = ROOT / "data" / "live.json"
API = "https://api.gdeltproject.org/api/v2/doc/doc"
WINDOW = "30d"
MAX_RECORDS = 250
THROTTLE_SECONDS = 5.0

QUERY_GROUPS = [
    '("rent control" OR "rent stabilization" OR "rent cap" OR "rent increase limit" OR "rent review") sourcecountry:US',
    '("good cause eviction" OR "just cause eviction" OR "tenant protection ordinance" OR "anti-harassment ordinance") sourcecountry:US',
    '("rental registry" OR "rent registry" OR "rent control audit" OR "rent board" OR "rent guidelines board") sourcecountry:US',
    '("rent control repeal" OR "rent stabilization repeal" OR "vacancy decontrol" OR "rent decontrol" OR "rent deregulation" OR "algorithmic rent" OR "rent-setting software") sourcecountry:US',
]


# Google News RSS is used as a second discovery path so a temporary GDELT
# throttle does not starve the feed. Jurisdiction filtering still happens
# after retrieval, so U.S. locale alone is never treated as proof that an
# article concerns U.S. policy.
RSS_QUERY_GROUPS = [
    '("rent control" OR "rent stabilization" OR "rent cap" OR "rent increase limit" OR "rent review") when:30d',
    '("good cause eviction" OR "just cause eviction" OR "tenant protection ordinance") when:30d',
    '("rental registry" OR "rent registry" OR "rent control audit" OR "rent board") when:30d',
    '("rent control repeal" OR "vacancy decontrol" OR "rent deregulation" OR "algorithmic rent" OR "rent-setting software") when:30d',
]

POLICY_WORDS = (
    "rent control", "rent stabilization", "rent cap", "rent increase limit", "rent increase",
    "good cause", "just cause", "rental registry", "rent registry", "rent board",
    "rent guideline", "tenant protection", "anti-harassment", "preemption", "preempt",
    "decontrol", "deregulat", "rent review", "algorithmic rent", "rent-setting software",
)
JUNK = (
    "spain", "madrid", "barcelona", "canada", "toronto", "vancouver", "uk ", "united kingdom",
    "australia", "ireland", "mortgage", "hotel room rate", "car rental", "vacation rental",
    "concert", "crypto", "commercial rent"  # residential monitor
)

# Helpful domain clues when a headline names only a city (e.g., "Portland") or is otherwise ambiguous.
DOMAIN_HINTS = {
    "pressherald.com": "ME", "mainepublic.org": "ME", "bangordailynews.com": "ME",
    "providencejournal.com": "RI", "rhodeislandcurrent.com": "RI",
    "bostonglobe.com": "MA", "masslive.com": "MA", "gloucestertimes.com": "MA",
    "nj.com": "NJ", "hudsoncountyview.com": "NJ", "jerseydigs.com": "NJ",
    "gothamist.com": "NY", "cityandstateny.com": "NY", "timesunion.com": "NY",
    "oregonlive.com": "OR", "opb.org": "OR", "portlandmercury.com": "OR",
    "seattletimes.com": "WA", "theolympian.com": "WA", "crosscut.com": "WA",
    "latimes.com": "CA", "sfchronicle.com": "CA", "sfgate.com": "CA", "calmatters.org": "CA", "laist.com": "CA", "kqed.org": "CA", "berkeleyside.org": "CA", "eastbaytimes.com": "CA", "sfstandard.com": "CA", "pasadenanow.com": "CA", "independent.com": "CA", "noozhawk.com": "CA",
    "startribune.com": "MN", "mprnews.org": "MN", "minnpost.com": "MN",
    "denverpost.com": "CO", "coloradosun.com": "CO", "chicagotribune.com": "IL",
    "inquirer.com": "PA", "baltimoresun.com": "MD", "marylandmatters.org": "MD",
    "washingtonpost.com": "DC", "wtop.com": "DC",
}

EASING_TERMS = (
    "repeal", "rollback", "roll back", "block", "blocks", "blocking", "blocked", "struck down", "strike down", "strikes down", "invalidat",
    "overturn", "fizzling", "withdrawn", "withdraw", "defeat", "rejected", "rejects",
    "exempt", "exemption", "decontrol", "deregulat", "preempt", "ban rent control",
    "pause", "suspend", "sunset", "raise the cap", "higher cap", "cap rises", "cap increases",
)
RESTRICTING_TERMS = (
    "adopt", "approved", "approve", "passes", "passed", "enact", "signed into law",
    "introduce", "introduced", "proposal", "propose", "ordinance", "ballot measure",
    "rent control", "rent stabilization", "rent cap", "freeze", "good cause", "just cause",
    "registry", "registration", "audit", "enforcement", "limit rent", "tenant protection",
    "anti-harassment", "rent review", "moratorium", "strengthen", "expand",
)

STATE_ALIASES = {
    "CA": ("calif.", "california"), "OR": ("ore.", "oregon"), "WA": ("wash. state", "washington state"),
    "NY": ("n.y.", "new york"), "NJ": ("n.j.", "new jersey"), "MA": ("mass.", "massachusetts"),
    "MN": ("minn.", "minnesota"), "CT": ("conn.", "connecticut"), "MD": ("md.", "maryland"),
    "PA": ("pa.", "pennsylvania"), "RI": ("r.i.", "rhode island"), "ME": ("maine",),
    "IL": ("ill.", "illinois"), "CO": ("colo.", "colorado"), "VA": ("va.", "virginia"),
}

STATE_NAMES = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado",
    "CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho",
    "IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana",
    "ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey",
    "NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma",
    "OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota",
    "TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia",
}


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except Exception:
        return fallback


def fetch_json(url: str):
    """Fetch JSON with a short bounded retry budget.

    The monitor must never spend minutes waiting on one upstream provider.
    """
    last = None
    for attempt in range(2):
        if attempt:
            time.sleep(2)
        req = urllib.request.Request(url, headers={"User-Agent": "Davis-Rent-Regulation-Monitor/2.1"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                break
    raise RuntimeError(str(last) if last else "unknown fetch error")


def fetch_text(url: str):
    """Fetch text with a short bounded retry budget."""
    last = None
    for attempt in range(2):
        if attempt:
            time.sleep(2)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Davis-Rent-Regulation-Monitor/2.1"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                break
    raise RuntimeError(str(last) if last else "unknown fetch error")


def parse_google_news_rss(xml_text: str):
    out = []
    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = html_lib.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        src = item.find("source")
        source_url = (src.attrib.get("url", "") if src is not None else "").strip()
        domain = urllib.parse.urlparse(source_url).netloc.lower().removeprefix("www.")
        if src is not None and src.text:
            suffix = " - " + src.text.strip()
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        seen = ""
        if pub:
            try:
                seen = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except Exception:
                seen = pub
        out.append({
            "title": title,
            "url": link,
            "domain": domain,
            "sourcecountry": "United States",
            "seendate": seen,
        })
    return out


def parse_seen(s: str):
    if not s:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return s
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    return s


def source_tier(domain: str):
    d=(domain or "").lower()
    if d.endswith(".gov") or d.endswith(".us") or ".gov." in d or any(x in d for x in ["legislature.","legis.","revisor.mn.gov"]):
        return "A"
    if any(x in d for x in ["reuters.com","apnews.com","nytimes.com","bloomberg.com","npr.org","politico.com","propublica.org","governing.com"]):
        return "B"
    return "C"


def classify_type_status(title: str):
    t=title.lower()
    if "algorithmic" in t or "rent-setting software" in t: typ="Algorithmic Pricing"
    elif any(x in t for x in ["preempt", "preemption", "ban rent control"]): typ="Preemption"
    elif any(x in t for x in ["good cause", "just cause"]): typ="Good Cause / Just Cause"
    elif any(x in t for x in ["registry", "registration", "audit", "enforcement", "complaint"]): typ="Registry / Enforcement"
    elif any(x in t for x in ["decontrol", "deregulat", "vacancy"]): typ="Vacancy / Decontrol"
    elif any(x in t for x in ["rent review", "mediation"]): typ="Rent Review / Mediation"
    elif any(x in t for x in ["rent stabilization", "rent control", "rent cap", "rent increase", "rent guideline"]): typ="Rent Amount Control"
    else: typ="Tenant / Rental Policy"

    if any(x in t for x in ["signed into law", "takes effect", "effective", "adopts", "adopted", "passes", "passed", "approved", "enacted"]): status="Enacted / Effective"
    elif any(x in t for x in ["proposal", "proposes", "proposed", "draft", "consider", "hearing", "ballot", "vote", "bill", "ordinance", "introduce"]): status="Proposed / Process"
    elif any(x in t for x in ["lawsuit", "court", "judge", "appeal", "injunction"]): status="Litigation"
    elif any(x in t for x in ["audit", "enforce", "registry", "registration", "commission"]): status="Enforcement / Administration"
    else: status="Discovery"
    return typ,status


def policy_direction(title: str):
    t=title.lower()

    # Context-sensitive preemption language. Preempting/banning local rent
    # control generally eases direct rent-amount constraint; repealing that
    # preemption moves in the opposite direction.
    if re.search(r"\b(repeal|repeals|repealing|end|ends|ending|lift|lifts|lifting)\b.{0,45}\b(preempt\w*|ban on (?:local )?rent control)\b", t):
        return "Restrictive", 1
    if re.search(r"\b(preempt\w*|ban|bars?|prohibit\w*)\b.{0,45}\b(local )?(rent control|rent stabilization|rent caps?)\b", t):
        return "Easing", -1

    easing=sum(1 for x in EASING_TERMS if x in t)
    restricting=sum(1 for x in RESTRICTING_TERMS if x in t)

    # Headlines often phrase an easing mechanically (for example,
    # "Oregon publishes higher 2027 rent cap"). Catch those formulations
    # before generic terms such as "rent cap" add a restrictive point.
    if re.search(r"\b(higher|raise[sd]?|raising|increase[sd]?|increasing)\b.{0,35}\b(cap|ceiling|maximum|limit)\b", t):
        easing += 2
    if re.search(r"\b(cap|ceiling|maximum|limit)\b.{0,25}\b(rises?|raised|increases?|increased)\b", t):
        easing += 2
    if re.search(r"\b(lower|reduce[sd]?|reducing|cut|cuts|tighten[sed]*|decrease[sd]?)\b.{0,35}\b(cap|ceiling|maximum|limit)\b", t):
        restricting += 2

    # Strong easing verbs/mechanics should win over the mere presence of
    # "rent control" or "rent cap" in the same headline.
    strong_easing = any(x in t for x in [
        "repeal", "block", "blocks", "blocking", "blocked", "struck down", "strike down", "strikes down", "fizzling", "defeat", "rejected",
        "decontrol", "deregulat", "higher cap", "raise the cap", "cap rises",
        "cap increases",
    ]) or easing >= restricting + 1
    if easing and strong_easing:
        return "Easing", -1
    if restricting:
        return "Restrictive", 1
    return "Neutral", 0


def property_scope_hint(title: str, typ: str):
    t=title.lower()
    if any(x in t for x in ["mobilehome", "mobile home", "manufactured home", "trailer park"]): return "Mobile / manufactured housing"
    if any(x in t for x in ["single-family", "single family", "condo", "condominium", "co-op", "coop"]): return "Single-family / condo / co-op mentioned"
    if any(x in t for x in ["apartment", "multifamily", "multi-family", "rental building", "landlord"]): return "Rental housing / multifamily mentioned"
    if "registry" in t or "registration" in t: return "Registered rental units; ordinance-specific coverage"
    if typ == "Algorithmic Pricing": return "Landlords / properties using covered pricing software"
    return "Property scope must be verified in source"


def relevant(title: str):
    t=(title or "").lower()
    if not t or any(j in t for j in JUNK): return False
    return any(w in t for w in POLICY_WORDS)


def build_location_indexes(base):
    locality_to_states={}
    for abbr,rec in (base.get("states") or {}).items():
        for loc in rec.get("localities",[]) or []:
            name=(loc.get("name") or "").strip()
            if not name: continue
            locality_to_states.setdefault(name.lower(), set()).add(abbr)
    return locality_to_states


def detect_jurisdiction(title: str, domain: str, base, locality_to_states):
    t=" "+re.sub(r"\s+"," ",(title or "").lower())+" "
    # Strongest: a curated locality name.
    locality_hits=[]
    for loc, states in locality_to_states.items():
        if len(loc) >= 4 and re.search(r"\b"+re.escape(loc)+r"\b", t):
            locality_hits.append((len(loc),loc,states))
    locality_hits.sort(reverse=True)

    # Explicit state name / common journalistic abbreviation.
    state_hit=""
    for abbr,name in STATE_NAMES.items():
        if abbr not in (base.get("states") or {}): continue
        aliases=(name.lower(),)+STATE_ALIASES.get(abbr,())
        if any(re.search(r"(?<![a-z])"+re.escape(alias)+r"(?![a-z])", t) for alias in aliases):
            # "Washington" alone is ambiguous; prefer state-qualified wording or local/domain context.
            if abbr=="WA" and not ("washington state" in t or "wash. state" in t or "seattle" in t or "tacoma" in t or DOMAIN_HINTS.get((domain or "").lower())=="WA"):
                continue
            state_hit=abbr; break

    if state_hit:
        loc=""
        for _,name,states in locality_hits:
            if state_hit in states:
                loc=next((x.get("name","") for x in base["states"][state_hit].get("localities",[]) if x.get("name","").lower()==name),"")
                break
        return state_hit, loc

    # Common headline shorthand such as "Providence, RI" or "(CA)".
    # Requiring punctuation around the two-letter code avoids matching ordinary words.
    raw = title or ""
    for abbr in (base.get("states") or {}):
        if re.search(r"(?:,|\(|\[|—|-|/)\s*"+re.escape(abbr)+r"(?:\b|\)|\])", raw):
            loc=""
            for _,name,states in locality_hits:
                if abbr in states:
                    loc=next((x.get("name","") for x in base["states"][abbr].get("localities",[]) if x.get("name","").lower()==name),"")
                    break
            return abbr,loc

    # Unique locality can identify state.
    for _,name,states in locality_hits:
        if len(states)==1:
            abbr=next(iter(states))
            loc=next((x.get("name","") for x in base["states"][abbr].get("localities",[]) if x.get("name","").lower()==name),"")
            return abbr,loc

    hint=DOMAIN_HINTS.get((domain or "").lower())
    if hint and hint in (base.get("states") or {}):
        loc=""
        for _,name,states in locality_hits:
            if hint in states:
                loc=next((x.get("name","") for x in base["states"][hint].get("localities",[]) if x.get("name","").lower()==name),"")
                break
        return hint,loc

    # National U.S. item only when the headline itself signals federal/national scope.
    if any(x in t for x in [" united states "," u.s. "," us housing "," federal "," nationwide "," national rent "]):
        return "US",""
    return "",""



def guess_locality(title: str, existing: str):
    if existing:
        return existing
    raw=(title or "").strip()
    patterns=[
        r"\bCity of ([A-Z][A-Za-z .'-]{2,36}?)(?:\s+(?:Council|passes|approves|considers|adopts|rent|rental)|$)",
        r"^([A-Z][A-Za-z .'-]{2,32}?)\s+(?:City Council|Council|rent control|rent stabilization|rental registry|landlords|tenants|voters)\b",
    ]
    banned={"new york state","united states","state","city","county","rent","rental","housing"}
    for pat in patterns:
        m=re.search(pat,raw)
        if not m: continue
        name=re.sub(r"\s+"," ",m.group(1)).strip(" ,-—")
        if name and name.lower() not in banned and 2 <= len(name.split()) <= 4:
            return name
    return ""

def normalize_article(a: dict, base, locality_to_states):
    title=(a.get("title") or "").strip()
    domain=(a.get("domain") or "").strip().lower()
    source_country=(a.get("sourcecountry") or "").strip()
    if not relevant(title): return None
    if source_country and source_country.lower() not in ("united states","us","usa","united states of america"): return None
    state,locality=detect_jurisdiction(title,domain,base,locality_to_states)
    if not state: return None
    locality=guess_locality(title,locality)
    typ,status=classify_type_status(title)
    direction,score=policy_direction(title)
    state_name="United States" if state=="US" else (base.get("states",{}).get(state,{}).get("name") or STATE_NAMES.get(state,state))
    return {
        "state": state,
        "state_name": state_name,
        "locality": locality,
        "published": parse_seen(a.get("seendate") or ""),
        "title": title,
        "url": a.get("url") or "",
        "domain": domain,
        "source_country": source_country or "United States",
        "type": typ,
        "status": status,
        "direction": direction,
        "direction_score": score,
        "property_scope": property_scope_hint(title,typ),
        "source_tier": source_tier(domain)
    }


def sort_key(x):
    tier={"A":3,"B":2,"C":1}.get(x.get("source_tier"),0)
    return (x.get("published", ""), tier)


def main():
    base=load_json(BASELINE,{"states":{}})
    old=load_json(LIVE,{"articles":[],"state_feeds":{},"locality_feeds":{}})
    locality_to_states=build_location_indexes(base)
    all_articles=[]
    errors=[]
    successes=0
    provider_success={"gdelt":0,"google_news_rss":0}

    # Run the small set of national discovery queries concurrently. This keeps
    # a slow/throttled provider from blocking the whole GitHub Pages deployment.
    tasks=[]
    for idx,q in enumerate(QUERY_GROUPS):
        params={"query":q,"mode":"artlist","format":"json","timespan":WINDOW,"maxrecords":MAX_RECORDS,"sort":"datedesc"}
        tasks.append(("GDELT", idx+1, API+"?"+urllib.parse.urlencode(params)))
    for idx,q in enumerate(RSS_QUERY_GROUPS):
        params={"q":q,"hl":"en-US","gl":"US","ceid":"US:en"}
        tasks.append(("Google News RSS", idx+1, "https://news.google.com/rss/search?"+urllib.parse.urlencode(params)))

    def run_task(task):
        provider, query_no, url = task
        if provider == "GDELT":
            payload = fetch_json(url)
            raws = payload.get("articles",[]) or []
        else:
            raws = parse_google_news_rss(fetch_text(url))
        return provider, query_no, raws

    print(f"Starting {len(tasks)} national discovery queries with 4 workers...", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map={pool.submit(run_task,t): t for t in tasks}
        for fut in as_completed(future_map):
            provider, query_no, _ = future_map[fut]
            try:
                provider, query_no, raws = fut.result()
                successes += 1
                key = "gdelt" if provider == "GDELT" else "google_news_rss"
                provider_success[key] += 1
                print(f"OK: {provider} query {query_no} returned {len(raws)} raw items", flush=True)
                for raw in raws:
                    item=normalize_article(raw,base,locality_to_states)
                    if item and item.get("url"):
                        item["discovery_provider"]=provider
                        all_articles.append(item)
            except Exception as exc:
                errors.append({"provider":provider,"query":query_no,"error":str(exc)[:260]})
                print(f"WARN: {provider} query {query_no} failed: {str(exc)[:140]}", flush=True)

    # If every upstream query failed, preserve the previous successful snapshot rather than wiping it.
    if successes==0:
        out=dict(old) if isinstance(old,dict) else {}
        out["attempted_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        out["status"]="partial"
        out["message"]="All discovery queries failed; previous U.S. snapshot preserved. generated_at remains the timestamp of the last usable snapshot."
        out["errors"]=errors
        LIVE.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
        print("All queries failed; preserved prior snapshot")
        return

    # Deduplicate nationally, favoring newer/higher-tier instances.
    # Title-first de-dupe prevents the same syndicated story from appearing twice under tracking URLs.
    dedup={}
    for x in sorted(all_articles,key=sort_key,reverse=True):
        title_key=re.sub(r"\W+"," ",x.get("title","").lower()).strip()
        canonical=(x.get("url") or "").split("?")[0].rstrip("/")
        key=(x.get("state","")+"|"+title_key) if title_key else canonical
        if key and key not in dedup:
            dedup[key]=x
    # Keep a true rolling 30-day snapshot. Fresh discovery providers can be
    # bursty, so merge still-in-window items from the previous successful
    # snapshot instead of letting one thin pull collapse the feed. Fresh
    # articles win on duplicate keys.
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - 31 * 86400
    def recent_enough(item):
        raw = item.get("published") or ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.timestamp() >= cutoff
        except Exception:
            return False

    for x in (old.get("articles", []) if isinstance(old, dict) else []):
        if not recent_enough(x):
            continue
        title_key=re.sub(r"\W+"," ",x.get("title","").lower()).strip()
        canonical=(x.get("url") or "").split("?")[0].rstrip("/")
        key=(x.get("state","")+"|"+title_key) if title_key else canonical
        if key and key not in dedup:
            carried=dict(x)
            carried["carried_forward"]=True
            dedup[key]=carried

    national=sorted(dedup.values(),key=sort_key,reverse=True)[:180]

    state_feeds={abbr:[] for abbr in (base.get("states") or {})}
    locality_feeds={}
    for x in national:
        st=x.get("state")
        if st in state_feeds:
            state_feeds[st].append(x)
        if st and st!="US" and x.get("locality"):
            locality_feeds.setdefault(st+"|"+x["locality"],[]).append(x)
    for st in state_feeds:
        state_feeds[st]=state_feeds[st][:30]

    direction_counts={"Restrictive":0,"Easing":0,"Neutral":0}
    for x in national:
        direction_counts[x.get("direction","Neutral")]=direction_counts.get(x.get("direction","Neutral"),0)+1

    out={
      "generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
      "status":"ok" if not errors else "partial",
      "window_days":30,
      "message":"U.S.-only automated discovery. Items are monitoring candidates, not verified legal conclusions.",
      "articles":national,
      "state_feeds":state_feeds,
      "locality_feeds":locality_feeds,
      "direction_counts":direction_counts,
      "health":{"queries":len(QUERY_GROUPS)+len(RSS_QUERY_GROUPS),"successful_queries":successes,"provider_success":provider_success,"errors":len(errors),"retained_articles":len(national)},
      "errors":errors,
      "method":"Parallel GDELT DOC 2.0 plus U.S.-localized Google News RSS topical discovery; U.S.-jurisdiction filter; state/locality assignment after retrieval; 30-day window; prior snapshot preserved only if all upstream queries fail."
    }
    LIVE.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    print(f"Wrote {len(national)} U.S. candidates from {successes}/{len(QUERY_GROUPS)+len(RSS_QUERY_GROUPS)} successful queries; providers={provider_success}; errors={len(errors)}")

if __name__=="__main__":
    main()
