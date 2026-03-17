"""
Source-it/scrapers.py

Scheduled data ingestion workers — run via Celery beat or cron.
Each scraper hits a government API / portal and pushes to /api/ingest/.

Install requirements:
    pip install requests beautifulsoup4 lxml pandas celery redis

Example cron (crontab -e):
    */30 * * * * cd /srv/Source-it && python manage.py run_scrapers

Or Celery beat task schedule — see celery_schedule below.
"""

import requests
import logging
from datetime import datetime, timezone
from django.utils import timezone as dj_tz
from .models import StateUT, ResourceType, SupplyRecord

log = logging.getLogger(__name__)

INGEST_URL = "http://localhost:8000/api/ingest/"   # change to production URL
ADMIN_TOKEN = "Bearer <your-django-admin-jwt>"     # set via env var in production


def _post_ingest(records: list):
    try:
        r = requests.post(
            INGEST_URL,
            json=records,
            headers={"Authorization": ADMIN_TOKEN, "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Ingest failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# LPG  —  PPAC / data.gov.in
# API: https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
#      Dataset: LPG Domestic Consumption by State
# Requires free API key from data.gov.in
# ──────────────────────────────────────────────────────────────
def scrape_lpg(api_key: str):
    """
    Fetches state-wise LPG subscriber and monthly supply data from data.gov.in.
    Converts to a supply index (actual / target * 100).
    """
    url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    params = {
        "api-key": api_key,
        "format":  "json",
        "limit":   50,
        "fields":  "state,month,total_connections_supplied,target",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        rows = r.json().get("records", [])
    except Exception as e:
        log.error(f"LPG API error: {e}")
        return

    resource_id = ResourceType.objects.get(slug="lgp").id
    records = []
    for row in rows:
        state = StateUT.objects.filter(name__icontains=row.get("state", "")).first()
        if not state:
            continue
        supplied = float(row.get("total_connections_supplied", 0) or 0)
        target   = float(row.get("target", 1) or 1)
        value    = min(round(supplied / target * 100, 1), 100)
        records.append({
            "state_id":     state.id,
            "resource_slug": "lgp",
            "value":         value,
            "source":        "data.gov.in / PPAC LPG dataset",
            "recorded_at":   dj_tz.now().isoformat(),
        })
    if records:
        result = _post_ingest(records)
        log.info(f"LPG ingested: {result}")


# ──────────────────────────────────────────────────────────────
# WATER  —  CWC India-WRIS weekly reservoir bulletin
# URL: https://indiawris.gov.in/wris/#/ReservoirMonitoring
# Machine-readable JSON feed published every Thursday
# ──────────────────────────────────────────────────────────────
def scrape_water_cwc():
    """
    CWC publishes reservoir storage as % of total live capacity.
    We group by state (metadata file maps reservoir → state).
    """
    BULLETIN_URL = "https://cwc.gov.in/sites/default/files/reservoir_bulletin_latest.json"
    try:
        r = requests.get(BULLETIN_URL, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error(f"CWC water error: {e}")
        # Fallback: parse the HTML bulletin page
        return

    records = []
    for entry in data.get("reservoirs", []):
        state = StateUT.objects.filter(name__icontains=entry.get("state", "")).first()
        if not state:
            continue
        pct = float(entry.get("storage_pct", 0) or 0)
        records.append({
            "state_id":      state.id,
            "resource_slug": "water",
            "value":          pct,
            "source":        "CWC Reservoir Bulletin / indiawris.gov.in",
            "recorded_at":   dj_tz.now().isoformat(),
        })
    if records:
        _post_ingest(records)
        log.info(f"Water ingested: {len(records)} states")


# ──────────────────────────────────────────────────────────────
# FOOD GRAINS  —  FCI stock position
# URL: https://fci.gov.in/stocks.php
# Published weekly as HTML table; parse with BeautifulSoup
# ──────────────────────────────────────────────────────────────
def scrape_fci_food_grains():
    """
    Scrapes FCI weekly stock position table.
    Computes index as (actual stock MT) / (strategic buffer norm MT) * 100.
    """
    from bs4 import BeautifulSoup

    FCI_URL   = "https://fci.gov.in/stocks.php"
    # Minimum buffer norms (lakh MT) as per GoI: rice+wheat combined per quarter
    NORMS = {
        "Q1": 214.1,   # 1 Apr
        "Q2": 197.6,   # 1 Jul
        "Q3": 141.2,   # 1 Oct
        "Q4": 128.4,   # 1 Jan
    }
    try:
        r = requests.get(FCI_URL, timeout=25, headers={"User-Agent": "RashtraKavach/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        # FCI renders a table with columns: State | Rice | Wheat | Coarse | Total
        table = soup.find("table", {"class": "table"})
        if not table:
            log.warning("FCI table not found — site structure may have changed")
            return
        rows = table.find_all("tr")[1:]
    except Exception as e:
        log.error(f"FCI scrape error: {e}")
        return

    month = datetime.now().month
    quarter = "Q" + str((month - 1) // 3 + 1)
    norm = NORMS.get(quarter, 170.0) / 36   # rough per-state average norm

    records = []
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 5:
            continue
        state_name, _, _, _, total_str = cells[:5]
        state = StateUT.objects.filter(name__icontains=state_name).first()
        if not state:
            continue
        try:
            total = float(total_str.replace(",", ""))
        except ValueError:
            continue
        value = min(round(total / norm * 100, 1), 100)
        records.append({
            "state_id":      state.id,
            "resource_slug": "food_grains",
            "value":          value,
            "source":        "FCI weekly stock position / fci.gov.in",
            "recorded_at":   dj_tz.now().isoformat(),
        })
    if records:
        _post_ingest(records)
        log.info(f"Food grains ingested: {len(records)} states")


# ──────────────────────────────────────────────────────────────
# FUEL  —  PPAC daily price & availability dashboard
# URL: https://ppac.gov.in/pridemenu (requires scrape or MoU API)
# ──────────────────────────────────────────────────────────────
def scrape_fuel_ppac():
    """
    PPAC PRIDE dashboard — daily pump availability data by OMC and state.
    This endpoint requires a registered API key via MoPNG.
    Uses the data.gov.in petroleum dataset as an alternative.
    """
    API_URL = "https://api.data.gov.in/resource/fuel-retail-outlets-state-wise"
    # Implement similarly to scrape_lpg()
    log.info("Fuel scraper: implement with PPAC PRIDE API key")


# ──────────────────────────────────────────────────────────────
# MEDICINES  —  CDSCO / PharmaTrac
# ──────────────────────────────────────────────────────────────
def scrape_medicines_cdsco():
    """
    CDSCO publishes essential medicines availability at state drug controllers.
    PharmaTrac (NIC) provides structured CSV monthly.
    URL: https://cdsco.gov.in/opencms/opencms/en/Drugs/Essential-Medicines/
    """
    log.info("Medicine scraper: fetch CDSCO essential medicines availability CSV")


# ──────────────────────────────────────────────────────────────
# CELERY BEAT SCHEDULE
# Add to your Celery config:
# ──────────────────────────────────────────────────────────────
"""
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'scrape-lpg-daily': {
        'task':     'Source-it.tasks.task_scrape_lpg',
        'schedule': crontab(hour=6, minute=0),     # 6 AM daily
    },
    'scrape-water-weekly': {
        'task':     'Source-it.tasks.task_scrape_water',
        'schedule': crontab(hour=7, minute=0, day_of_week='thursday'),  # CWC bulletin day
    },
    'scrape-food-weekly': {
        'task':     'Source-it.tasks.task_scrape_food',
        'schedule': crontab(hour=8, minute=0, day_of_week='monday'),
    },
    'scrape-fuel-daily': {
        'task':     'Source-it.tasks.task_scrape_fuel',
        'schedule': crontab(hour=6, minute=30),
    },
}
"""


# ──────────────────────────────────────────────────────────────
# DATA SOURCE REFERENCE MAP
# ──────────────────────────────────────────────────────────────
DATA_SOURCES = {
    "lgp": [
        {
            "name": "PPAC — Petroleum Planning & Analysis Cell",
            "type": "GOV",
            "url":  "ppac.gov.in",
            "method": "Monthly PDF + data.gov.in REST API",
            "key_required": True,
            "register_at": "data.gov.in/user/register",
            "fields": "state, month, cylinders_supplied, connections",
        },
        {
            "name": "MoPNG Open Data — OMC LPG Distribution",
            "type": "GOV",
            "url":  "data.gov.in",
            "method": "REST JSON API",
            "key_required": True,
            "dataset_id": "9ef84268-d588-465a-a308-a864a43d0070",
        },
        {
            "name": "IOCL / BPCL / HPCL Distributor Portals",
            "type": "API",
            "url":  "mylpg.in · iocl.com · bpcl.in",
            "method": "Requires MOU for programmatic access",
            "key_required": True,
        },
    ],
    "water": [
        {
            "name": "CWC India-WRIS",
            "type": "LIVE",
            "url":  "indiawris.gov.in",
            "method": "REST JSON + daily gauge data",
            "key_required": False,
        },
        {
            "name": "CWC Weekly Reservoir Bulletin",
            "type": "LIVE",
            "url":  "cwc.gov.in/reservoir-monitoring",
            "method": "JSON bulletin (updated every Thursday)",
            "key_required": False,
        },
        {
            "name": "eJalShakti — Jal Jeevan Mission",
            "type": "GOV",
            "url":  "ejalshakti.gov.in",
            "method": "State/district coverage reports (quarterly)",
            "key_required": False,
        },
    ],
    "food_grains": [
        {
            "name": "FCI Stock Position Portal",
            "type": "LIVE",
            "url":  "fci.gov.in/stocks.php",
            "method": "HTML table scrape (weekly)",
            "key_required": False,
        },
        {
            "name": "ANNAVITRAN / DFPD",
            "type": "GOV",
            "url":  "dfpd.gov.in · annavitran.nic.in",
            "method": "NFSA allocation vs. offtake data",
            "key_required": False,
        },
        {
            "name": "Agmarknet API",
            "type": "API",
            "url":  "agmarknet.gov.in",
            "method": "Mandi arrival & price data (proxy indicator)",
            "key_required": True,
        },
    ],
    "fuel": [
        {
            "name": "PPAC PRIDE Dashboard",
            "type": "LIVE",
            "url":  "ppac.gov.in/pridemenu",
            "method": "Daily OMC pump availability",
            "key_required": True,
        },
    ],
    "medicine": [
        {
            "name": "CDSCO / PharmaTrac",
            "type": "GOV",
            "url":  "cdsco.gov.in",
            "method": "Monthly essential drug availability CSV",
            "key_required": False,
        },
    ],
    "general": [
        {
            "name": "data.gov.in Master Portal",
            "type": "API",
            "url":  "data.gov.in",
            "method": "REST API — 500K+ datasets across all ministries",
            "key_required": True,
            "register_at": "data.gov.in/user/register",
        },
        {
            "name": "NDMA Disaster Alert Feed",
            "type": "LIVE",
            "url":  "ndma.gov.in",
            "method": "Event API for floods, cyclones, road closures",
            "key_required": False,
        },
        {
            "name": "IMD Weather API",
            "type": "API",
            "url":  "mausam.imd.gov.in",
            "method": "5-day extreme weather forecast per district",
            "key_required": True,
        },
    ],
}