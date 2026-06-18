
import io
import re
from datetime import date, datetime
from typing import Dict, List, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from supabase import create_client
    SUPABASE_OK = True
except ImportError:
    SUPABASE_OK = False

try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False

# =====================================================
# UI / STILIUS
# =====================================================
st.set_page_config(
    page_title="Ūkio skaičiuoklė",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f7faf7 0%, #eef5ee 100%);
        border-right: 1px solid #dfe8df;
    }
    .app-title {
        background: linear-gradient(90deg, #4f7f39, #6ba84f);
        color: white;
        padding: 16px 20px;
        border-radius: 16px;
        margin-bottom: 16px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    }
    .app-title h1 {margin: 0; font-size: 28px;}
    .app-title p {margin: 6px 0 0 0; opacity: 0.95; font-size: 14px;}
    .metric-card {
        background: white;
        padding: 14px 16px;
        border-radius: 16px;
        border: 1px solid #e6ece6;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid #e8ecef;
    }
    .stButton > button, .stDownloadButton > button {
        border-radius: 12px; font-weight: 600; border: none;
    }
    .stTabs [data-baseweb="tab-list"] {gap: 10px;}
    .stTabs [data-baseweb="tab"] {border-radius: 10px; padding: 8px 14px; background: #f4f7f3;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-title">
        <h1>🌾 Ūkio skaičiuoklė</h1>
        <p>Laukai • Išlaidos • Sandėlis • Pajamos • Pelningumas • Hibridinis PDF parseris</p>
    </div>
    """,
    unsafe_allow_html=True,
)

COLORS = ["#5a7d9a", "#7da87b", "#c4956a", "#b07aa1", "#9c9c9c", "#d4a574"]
UNIT_OPTIONS = ["kg", "l", "vnt", "t"]
LT_MONTHS = {
    "sausio": 1, "vasario": 2, "kovo": 3, "balandžio": 4, "gegužės": 5, "birželio": 6,
    "liepos": 7, "rugpjūčio": 8, "rugsėjo": 9, "spalio": 10, "lapkričio": 11, "gruodžio": 12,
}

PARSER_OPTIONS = {
    "Automatinis": "auto",
    "Universalus": "universal",
    "Agrokoncernas – trąšos": "agrokoncernas_trasos",
    "Agrokoncernas – chemija": "agrokoncernas_chemija",
    "Agrochema": "agrochema",
    "Linas Agro": "linas_agro",
    "Scandagra": "scandagra",
}

RUSIS_MAP = {
    "herbicidas": ["mustang", "axial", "derby", "corum", "dash", "pantera", "butisan", "herold", "lentipur", "sekator", "biathlon", "husar", "stomp", "starane", "focus", "elite", "elit", "belkar", "tombo", "nexa", "kestrel", "agrotop", "rodeo"],
    "fungicidas": ["prosaro", "osiris", "adexar", "fandango", "skyway", "input", "navura", "caramba", "tilt", "amistar", "acanto", "falcon", "opus", "signum"],
    "insekticidas": ["karate", "decis", "fastac", "fury", "biscaya", "proteus", "mavrik", "pirimor", "vantex"],
    "reguliatorius": ["moddus", "ccc", "terpal", "medax", "cerone", "prodax", "manipulator"],
    "trasos": ["npk", "amonio", "kas", "karbamidas", "urea", "salietra", "sulfatas", "superfosfat", "kalio", "dap", "map", "kcl", "k40", "kalcio", "magnis", "sulfur", "siera", "mikro", "makro"],
    "seklos": ["sekla", "sėkla", "seed"],
}

SKIP_TEXTS = [
    "suma be pvm", "viso", "viso su pvm", "iš viso", "pvm 21", "pvm (21%) suma", "pvm suma",
    "suma žodžiais", "apmokėti iki", "apmoketi iki", "užsakymo nr", "uzsakymo nr", "tiekėjas",
    "tiekejas", "pardavėjas", "pardavejas", "pirkėjas", "pirkejas", "dokumentą išrašė",
    "dokumenta israse", "el.pašto adresas", "el. pašto adresas", "bankas", "adresas", "pagal",
    "sutartį", "sutarti", "pakrovimo", "pristatymo sąlygos", "pristatymo salygos"
]

ALLOWED_UNITS_BY_MODE = {
    "agrokoncernas_trasos": {"kg", "t"},
    "agrokoncernas_chemija": {"l", "vnt", "kg"},
    "agrochema": {"kg", "t", "l", "vnt"},
    "linas_agro": {"kg", "t", "l", "vnt"},
    "scandagra": {"kg", "t", "l", "vnt"},
    "universal": {"kg", "t", "l", "vnt"},
}

# =====================================================
# BENDROS FUNKCIJOS
# =====================================================
def gauti_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


def txt_norm(s):
    return str(s or "").strip().lower().replace("\xa0", " ").replace("\n", " ").replace("\u00ad", "")


def sutvarkyti_tarpus(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def parse_lt_number(v):
    if v is None:
        return 0.0
    s = str(v).strip().replace("\xa0", " ").replace("\u00ad", "")
    if not s:
        return 0.0
    s = s.replace("EUR", "").replace("eur", "").replace("€", "")
    s = re.sub(r"[^0-9,\.\- ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return 0.0
    s = s.replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def formatuoti_data(dt):
    if isinstance(dt, (date, datetime)):
        return dt.strftime("%Y-%m-%d")
    return str(dt or "")

def normalizuoti_vieneta(v):
    vv = txt_norm(v)
    mapping = {
        "kg": "kg",
        "t": "t",
        "tona": "t",
        "tonos": "t",
        "tona.": "t",
        "tonos.": "t",
        "l": "l",
        "lt": "l",
        "ltr": "l",
        "l.": "l",
        "vnt": "vnt",
        "vnt.": "vnt",
        "v.": "vnt",
    }
    return mapping.get(vv, vv if vv else "vnt")


def rodyti_kpi(antraste, reiksme, emoji="📌"):
    st.markdown(
        f"""
        <div class="metric-card">
            <div style="font-size:13px;color:#6b7280;">{emoji} {antraste}</div>
            <div style="font-size:26px;font-weight:700;margin-top:4px;">{reiksme}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def nustatyti_rusi(pavadinimas, numatytasis=None):
    p = txt_norm(pavadinimas)
    for rusis, zodziai in RUSIS_MAP.items():
        if any(z in p for z in zodziai):
            return rusis
    return numatytasis or "kita"


def yra_suvestines_eilute(line):
    t = txt_norm(line)
    return any(k in t for k in SKIP_TEXTS)


def yra_prekes_kodas(token: str) -> bool:
    t = str(token or "").strip().strip(",.;:)")
    if len(t) < 4:
        return False
    # Tipiniai tiekėjų kodai: FI02-0282, KFE_NPK112_MAR, FI02-0031 ir pan.
    if re.fullmatch(r"[A-Z0-9_-]{4,}", t) and re.search(r"[A-Z]", t) and re.search(r"\d", t):
        return True
    return False


def isvalyti_produkto_pavadinima(pavadinimas):
    s = sutvarkyti_tarpus(pavadinimas)
    s = re.sub(r"^\d+[.)]?\s*", "", s)
    s = re.sub(r"\(([A-Z]{3,}[A-Z0-9]{4,})\)\s*$", "", s).strip()
    parts = s.split()
    while parts and yra_prekes_kodas(parts[0]):
        parts = parts[1:]
    s = " ".join(parts)
    return s.strip(" -")


def deduplikoti_produktus(produktai: List[dict]) -> List[dict]:
    out = []
    seen = set()
    for p in produktai:
        key = (
            str(p.get("Produktas", "")).strip().lower(),
            str(p.get("Vienetas", "")).strip().lower(),
            round(float(p.get("Kiekis", 0) or 0), 4),
            round(float(p.get("Kaina", 0) or 0), 4),
            round(float(p.get("Verte", 0) or 0), 2),
        )
        if key in seen:
            continue
        seen.add(key)
        if p.get("Produktas"):
            out.append(p)
    return out


def papildyti_kaina_ir_verte(kiekis, kaina, verte):
    kiekis = float(kiekis or 0)
    kaina = float(kaina or 0)
    verte = float(verte or 0)
    if kiekis > 0 and verte > 0 and kaina <= 0:
        kaina = verte / kiekis
    if kiekis > 0 and kaina > 0 and verte <= 0:
        verte = kiekis * kaina
    return round(kaina, 4), round(verte, 2)


def koreguoti_eilute_pagal_logika(produktas, vienetas, kiekis, kaina, verte, mode_key):
    vienetas = normalizuoti_vieneta(vienetas)
    allowed = ALLOWED_UNITS_BY_MODE.get(mode_key, ALLOWED_UNITS_BY_MODE["universal"])
    if vienetas not in allowed and vienetas not in {"kg", "t", "l", "vnt"}:
        vienetas = "vnt"

    kaina, verte = papildyti_kaina_ir_verte(kiekis, kaina, verte)

    if mode_key == "agrokoncernas_trasos" and kiekis > 0 and verte > 0:
        teorine = verte / kiekis
        if kaina <= 0 or abs(kaina - teorine) > max(2, teorine * 0.5):
            kaina = round(teorine, 4)

    rusis_default = "trasos" if mode_key == "agrokoncernas_trasos" else None
    return {
        "Produktas": isvalyti_produkto_pavadinima(produktas),
        "Rusis": nustatyti_rusi(produktas, rusis_default),
        "Kiekis": round(float(kiekis or 0), 4),
        "Vienetas": vienetas,
        "Kaina": round(float(kaina or 0), 4),
        "Verte": round(float(verte or 0), 2),
    }


def gauti_visa_pdf_teksta(failas):
    with pdfplumber.open(failas) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def gauti_data_is_pdf(failas):
    txt = gauti_visa_pdf_teksta(failas)
    for m in re.findall(r"\b\d{4}[-./]\d{2}[-./]\d{2}\b", txt):
        y, mm, dd = re.split(r"[-./]", m)
        return f"{y}-{mm}-{dd}"
    for m in re.findall(r"\b\d{2}[-./]\d{2}[-./]\d{4}\b", txt):
        dd, mm, y = re.split(r"[-./]", m)
        return f"{y}-{mm}-{dd}"
    m = re.search(r"(\d{4})\s*m\.\s*([a-ząčęėįšųūž]+)\s*(\d{1,2})\s*d\.", txt, re.IGNORECASE)
    if m:
        year = int(m.group(1))
        month = LT_MONTHS.get(m.group(2).lower())
        day = int(m.group(3))
        if month:
            return date(year, month, day).strftime("%Y-%m-%d")
    return date.today().strftime("%Y-%m-%d")


def gauti_saskaitos_nr(failas):
    txt = gauti_visa_pdf_teksta(failas).replace("\n", " ")
    patterns = [
        r"serija\s*[:\-]?\s*([A-Z0-9\-_/]+)\s*nr\.?\s*[:\-]?\s*([A-Z0-9\-_/]+)",
        r"nr\.?\s*[:\-]?\s*([A-Z]{2,}[A-Z0-9\-_/]*)",
        r"serija\s*[:\-]?\s*([A-Z]{2,}[A-Z0-9\-_/]*)",
        r"(?:pvm\s+saskaita(?:[-\s]?faktura)?|pvm\s+sąskaita(?:[-\s]?faktūra)?)\s*(?:serija\s*)?([A-Z0-9\-_/]+)?\s*nr\.?\s*[:\-]?\s*([A-Z0-9\-_/]+)",
    ]
    for pat in patterns:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            vals = [x for x in m.groups() if x]
            if len(vals) >= 2:
                return " ".join(vals).strip()
            if len(vals) == 1:
                return vals[0].strip()
    return ""


def aptikti_tiekeja_is_text(txt):
    t = txt_norm(txt)
    if "agrokoncern" in t:
        return "agrokoncernas"
    if "agrochema" in t:
        return "agrochema"
    if "linas agro" in t:
        return "linas_agro"
    if "scandagra" in t:
        return "scandagra"
    return "nezinomas"

# =====================================================
# DB UŽKLAUSOS
# =====================================================
def gauti_laukus(sb):
    r = sb.table("laukai").select("*").order("pavadinimas").execute()
    return pd.DataFrame(r.data) if getattr(r, "data", None) else pd.DataFrame()


def gauti_islaidas(sb, filtrai=None):
    q = sb.table("islaidos").select("*, laukai(pavadinimas, kultura, plotas_ha)")
    if filtrai:
        if filtrai.get("lauko_id"):
            q = q.eq("lauko_id", filtrai["lauko_id"])
        if filtrai.get("nuo"):
            q = q.gte("data", filtrai["nuo"])
        if filtrai.get("iki"):
            q = q.lte("data", filtrai["iki"])
    r = q.order("data").execute()
    if not getattr(r, "data", None):
        return pd.DataFrame()
    df = pd.DataFrame(r.data)
    if "laukai" in df.columns:
        li = df["laukai"].apply(lambda x: pd.Series(x) if isinstance(x, dict) else pd.Series({"pavadinimas": "", "kultura": "", "plotas_ha": 0}))
        li = li.rename(columns={"pavadinimas": "lauko_pavadinimas", "plotas_ha": "plotas_ha_laukas"})
        df = pd.concat([df.drop(columns=["laukai"]), li], axis=1)
    return df


def gauti_sandeli(sb):
    r = sb.table("sandelis").select("*").order("produktas").execute()
    return pd.DataFrame(r.data) if getattr(r, "data", None) else pd.DataFrame()


def gauti_pajamas(sb, lauko_id=None, nuo=None, iki=None):
    q = sb.table("pajamos").select("*, laukai(pavadinimas, kultura)")
    if lauko_id:
        q = q.eq("lauko_id", lauko_id)
    if nuo:
        q = q.gte("data", nuo)
    if iki:
        q = q.lte("data", iki)
    r = q.order("data").execute()
    if not getattr(r, "data", None):
        return pd.DataFrame()
    df = pd.DataFrame(r.data)
    if "laukai" in df.columns:
        li = df["laukai"].apply(lambda x: pd.Series(x) if isinstance(x, dict) else pd.Series({"pavadinimas": "", "kultura": ""}))
        li = li.rename(columns={"pavadinimas": "lauko_pavadinimas"})
        df = pd.concat([df.drop(columns=["laukai"]), li], axis=1)
    return df

# =====================================================
# PDF PARSERIO SLUOKSNIS A: BENDRAS
# =====================================================
def header_map_from_row(row_vals: List[str]) -> Dict[str, int]:
    mapping = {}
    for idx, val in enumerate(row_vals):
        v = txt_norm(val)
        if any(k in v for k in ["pavadinimas", "prekė", "preke", "paslauga", "aprašymas", "aprasymas"]):
            mapping.setdefault("produktas", idx)
        elif "mato" in v or v == "vnt" or "mato vnt" in v:
            mapping.setdefault("vienetas", idx)
        elif "kiekis" in v:
            mapping.setdefault("kiekis", idx)
        elif "kaina" in v and "su pvm" not in v:
            mapping.setdefault("kaina", idx)
        elif "suma" in v and "su pvm" not in v and "pvm suma" not in v:
            mapping.setdefault("suma", idx)
    return mapping


def parse_table_extract_generic(failas, mode_key="universal") -> List[dict]:
    produktai = []
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "intersection_tolerance": 8,
        "snap_tolerance": 5,
        "join_tolerance": 5,
    }
    with pdfplumber.open(failas) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(table_settings=table_settings) or []
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header_idx = None
                mapping = {}
                for i, row in enumerate(table[:8]):
                    row_vals = [sutvarkyti_tarpus(c) for c in row if c is not None]
                    row_text = " ".join(txt_norm(c) for c in row_vals)
                    if any(x in row_text for x in ["kiekis", "kaina", "suma"]):
                        candidate = header_map_from_row(row)
                        if "produktas" in candidate and "kiekis" in candidate:
                            mapping = candidate
                            header_idx = i
                            break
                if header_idx is None:
                    continue

                for row in table[header_idx + 1:]:
                    if not row:
                        continue
                    row_text = " ".join(sutvarkyti_tarpus(c) for c in row if c is not None)
                    if not row_text or yra_suvestines_eilute(row_text):
                        continue
                    produs = row[mapping.get("produktas")] if mapping.get("produktas") is not None and mapping.get("produktas") < len(row) else ""
                    unit = row[mapping.get("vienetas")] if mapping.get("vienetas") is not None and mapping.get("vienetas") < len(row) else "vnt"
                    qty = parse_lt_number(row[mapping.get("kiekis")] if mapping.get("kiekis") is not None and mapping.get("kiekis") < len(row) else 0)
                    price = parse_lt_number(row[mapping.get("kaina")] if mapping.get("kaina") is not None and mapping.get("kaina") < len(row) else 0)
                    total = parse_lt_number(row[mapping.get("suma")] if mapping.get("suma") is not None and mapping.get("suma") < len(row) else 0)
                    item = koreguoti_eilute_pagal_logika(produs, unit, qty, price, total, mode_key)
                    if item["Produktas"] and item["Kiekis"] > 0:
                        produktai.append(item)
    return deduplikoti_produktus(produktai)


def parse_universal_lines(txt: str, mode_key="universal") -> List[dict]:
    produktai = []
    lines = [sutvarkyti_tarpus(l) for l in txt.splitlines() if sutvarkyti_tarpus(l)]
    # Bendras patternas: pavadinimas + vienetas + kiekis + kaina + suma
    pattern = re.compile(
        r"^(?:\d+[.)]?\s+)?(.+?)\s+(kg|t|l|vnt)\s+([0-9][0-9 .]*,[0-9]{0,3}|[0-9]+)\s+([0-9][0-9 .]*,[0-9]{2,4})\s+([0-9][0-9 .]*,[0-9]{2})(?:\s+.*)?$",
        flags=re.IGNORECASE,
    )
    for line in lines:
        if yra_suvestines_eilute(line):
            continue
        m = pattern.match(line)
        if not m:
            continue
        pavadinimas, vienetas, kiekis_s, kaina_s, suma_s = m.groups()
        item = koreguoti_eilute_pagal_logika(
            pavadinimas, vienetas, parse_lt_number(kiekis_s), parse_lt_number(kaina_s), parse_lt_number(suma_s), mode_key
        )
        if item["Produktas"] and item["Kiekis"] > 0:
            produktai.append(item)
    return deduplikoti_produktus(produktai)

# =====================================================
# PDF PARSERIO SLUOKSNIS B: TIEKĖJO ATPAŽINIMAS
# =====================================================
def parinkti_parseri(failas, pasirinktas_mode_key: str) -> Tuple[str, str, str]:
    txt = gauti_visa_pdf_teksta(failas)
    aptiktas_tiekejas = aptikti_tiekeja_is_text(txt)
    if pasirinktas_mode_key != "auto":
        return pasirinktas_mode_key, aptiktas_tiekejas, txt

    if aptiktas_tiekejas == "agrokoncernas":
        low = txt_norm(txt)
        if any(k in low for k in ["nexa", "kestrel", "corum", "dash", "navura", "pantera", "terpal", "ec", "cs", "sl", "wg"]):
            return "agrokoncernas_chemija", aptiktas_tiekejas, txt
        return "agrokoncernas_trasos", aptiktas_tiekejas, txt

    if aptiktas_tiekejas in {"agrochema", "linas_agro", "scandagra"}:
        return aptiktas_tiekejas, aptiktas_tiekejas, txt

    return "universal", aptiktas_tiekejas, txt

# =====================================================
# PDF PARSERIO SLUOKSNIS C: SPECIALŪS PARSERIAI
# =====================================================
def parse_agrokoncernas_lines(txt: str, mode_key: str) -> List[dict]:
    produktai = []
    lines = [sutvarkyti_tarpus(l) for l in txt.splitlines() if sutvarkyti_tarpus(l)]
    start = 0
    for i, line in enumerate(lines):
        low = txt_norm(line)
        if "prekė, paslauga" in low or "preke, paslauga" in low:
            start = i + 1
            break
    candidate_lines = []
    for line in lines[start:]:
        low = txt_norm(line)
        if "suma be pvm" in low or low.startswith("viso"):
            break
        if re.match(r"^\d+\s+", line):
            candidate_lines.append(line)

    row_pattern = re.compile(
        r"^(\d+)\s+(.+?)\s+(kg|t|l|vnt)\s+([0-9][0-9 .]*,[0-9]{0,3}|[0-9]+)\s+([0-9][0-9 .]*,[0-9]{2,4})\s+([0-9][0-9 .]*,[0-9]{2})$",
        flags=re.IGNORECASE,
    )
    for line in candidate_lines:
        m = row_pattern.match(line)
        if not m:
            continue
        _, pavadinimas, vienetas, kiekis_s, kaina_s, suma_s = m.groups()
        item = koreguoti_eilute_pagal_logika(pavadinimas, vienetas, parse_lt_number(kiekis_s), parse_lt_number(kaina_s), parse_lt_number(suma_s), mode_key)
        if item["Produktas"] and item["Kiekis"] > 0:
            produktai.append(item)
    return deduplikoti_produktus(produktai)


def parse_agrochema_lines(txt: str, mode_key: str = "agrochema") -> List[dict]:
    produktai = []
    lines = [sutvarkyti_tarpus(l) for l in txt.splitlines() if sutvarkyti_tarpus(l)]
    start_idx = 0
    for i, line in enumerate(lines):
        low = txt_norm(line)
        if "pavadinimas" in low and "kiekis" in low and "kaina" in low and "suma" in low:
            start_idx = i + 1
            break

    row_pattern = re.compile(
        r"^(?P<kodas>[A-Z0-9\-]+)\s+"
        r"(?P<pavadinimas>.+?)\s+"
        r"(?P<vienetas>kg|t|l|vnt)\s+"
        r"(?P<kiekis>[0-9][0-9 ]*,[0-9]{0,3}|[0-9]+)\s+"
        r"(?P<kaina>[0-9][0-9 ]*,[0-9]{2,4})\s+"
        r"(?P<suma>[0-9][0-9 ]*,[0-9]{2})\s+"
        r"(?P<pvm>[0-9]{1,2}%)$",
        flags=re.IGNORECASE,
    )

    current_item = None
    for line in lines[start_idx:]:
        low = txt_norm(line)
        if "viso be pvm" in low or "viso su pvm" in low or "suma žodžiais" in low:
            break
        if low.startswith("kiekis :") or "dokumento nr." in low:
            continue
        m = row_pattern.match(line)
        if m:
            if current_item:
                produktai.append(current_item)
            current_item = koreguoti_eilute_pagal_logika(
                m.group("pavadinimas"), m.group("vienetas"), parse_lt_number(m.group("kiekis")),
                parse_lt_number(m.group("kaina")), parse_lt_number(m.group("suma")), mode_key
            )
            continue
        if current_item and not yra_suvestines_eilute(line):
            if not any(x in low for x in ["dokumento nr", "kiekis :", "užsakymo", "uzsakymo"]):
                current_item["Produktas"] = sutvarkyti_tarpus(f'{current_item["Produktas"]} {line}')

    if current_item:
        produktai.append(current_item)

    out = []
    for p in produktai:
        p["Produktas"] = isvalyti_produkto_pavadinima(p["Produktas"])
        if p["Produktas"] and p["Kiekis"] > 0:
            out.append(p)
    return deduplikoti_produktus(out)



def parse_linas_agro_lines(txt: str, mode_key: str = "linas_agro") -> List[dict]:
    produktai = []
    lines = [sutvarkyti_tarpus(l) for l in txt.splitlines() if sutvarkyti_tarpus(l)]

    start_idx = 0
    for i, line in enumerate(lines):
        low = txt_norm(line)
        if "prekės/paslaugos pavadinimas" in low or ("prekės" in low and "kaina" in low and "suma" in low):
            start_idx = i + 1
            break

    current_item = None

    # Pvz.:
    # 1. KFE_NPK112_MAR NPK 10-26-26, Marocco 600 kg 0,600 Tonos 645,00 387,0021,00% 81,27 468,27
    row_pattern = re.compile(
        r"^(?P<eil>\d+)[.]?\s+"
        r"(?P<kodas>[A-Z0-9_\-]+)\s+"
        r"(?P<pavadinimas>.+?)\s+"
        r"(?P<kiekis>[0-9][0-9 ]*,[0-9]{0,3}|[0-9]+)\s+"
        r"(?P<vienetas>Tonos|Tona|kg|t|l|vnt)\s+"
        r"(?P<kaina>[0-9][0-9 ]*,[0-9]{2,4})\s+"
        r"(?P<suma>[0-9][0-9 ]*,[0-9]{2})\s+"
        r"(?P<pvmproc>[0-9]{1,2},[0-9]{2}%|[0-9]{1,2}%?)\s+"
        r"(?P<pvmsuma>[0-9][0-9 ]*,[0-9]{2})\s+"
        r"(?P<suma_su_pvm>[0-9][0-9 .]*,[0-9]{2})$",
        flags=re.IGNORECASE,
    )

    for line in lines[start_idx:]:
        low = txt_norm(line)

        if "iš viso be pvm" in low or "is viso be pvm" in low or "apmokėti iki" in low or "apmoketi iki" in low:
            break

        # Pašalinam priklijuotą papildomą tekstą
        line_clean = line.replace("_", " ").replace("!", " ")

        # Sutvarkom atvejį, kai suma ir PVM proc. sulipę, pvz. 387,0021,00%
        line_clean = re.sub(r"(\d,\d{2})(\d{1,2},\d{2}%)", r"\1 \2", line_clean)

        # Nukerpam logistinę informaciją, jei prilipus
        line_clean = re.split(r"\bKiekis\s*:", line_clean, maxsplit=1)[0].strip()
        line_clean = re.split(r"\bVažtaraščio\s+Nr\b", line_clean, maxsplit=1)[0].strip()
        line_clean = sutvarkyti_tarpus(line_clean)

        if not line_clean:
            continue

        if low.startswith("kiekis :") or low.startswith("pakuočių skaičius") or low.startswith("pakuociu skaicius"):
            continue

        m = row_pattern.match(line_clean)
        if m:
            if current_item:
                produktai.append(current_item)

            # Prekės kodo nereikia - imam tik pavadinimą
            pavadinimas = m.group("pavadinimas")
            kiekis = parse_lt_number(m.group("kiekis"))
            vienetas = normalizuoti_vieneta(m.group("vienetas"))
            kaina = parse_lt_number(m.group("kaina"))
            suma = parse_lt_number(m.group("suma"))

            current_item = koreguoti_eilute_pagal_logika(
                produktas=pavadinimas,
                vienetas=vienetas,
                kiekis=kiekis,
                kaina=kaina,
                verte=suma,
                mode_key=mode_key,
            )
            continue

        # Jei yra produkto tęsinys - prijungiam
        if current_item and not yra_suvestines_eilute(line_clean):
            if not any(x in txt_norm(line_clean) for x in [
                "važtaraščio nr", "vaztarascio nr",
                "pakuočių skaičius", "pakuociu skaicius"
            ]):
                current_item["Produktas"] = sutvarkyti_tarpus(
                    f'{current_item["Produktas"]} {line_clean}'
                )

    if current_item:
        produktai.append(current_item)

    out = []
    for p in produktai:
        p["Produktas"] = isvalyti_produkto_pavadinima(p["Produktas"])
        if p["Produktas"] and p["Kiekis"] > 0:
            out.append(p)

    return deduplikoti_produktus(out)




def parse_scandagra_lines(txt: str, mode_key: str = "scandagra") -> List[dict]:
    # Kol kas naudojam bendrą fallback; funkcija palikta plėtrai
    return parse_universal_lines(txt, mode_key)


def parse_vendor_specific(failas, mode_key: str) -> List[dict]:
    txt = gauti_visa_pdf_teksta(failas)
    if mode_key == "agrokoncernas_trasos":
        return parse_agrokoncernas_lines(txt, mode_key)
    if mode_key == "agrokoncernas_chemija":
        return parse_agrokoncernas_lines(txt, mode_key)
    if mode_key == "agrochema":
        rez = parse_agrochema_lines(txt, mode_key)
        if rez:
            return rez
    if mode_key == "linas_agro":
        rez = parse_linas_agro_lines(txt, mode_key)
        if rez:
            return rez
    if mode_key == "scandagra":
        rez = parse_scandagra_lines(txt, mode_key)
        if rez:
            return rez

    failas.seek(0)
    rez = parse_table_extract_generic(failas, mode_key)
    if rez:
        return rez
    return parse_universal_lines(txt, mode_key)


def nuskaityti_pdf(failas, pasirinktas_mode_key: str):
    final_mode, aptiktas_tiekejas, txt = parinkti_parseri(failas, pasirinktas_mode_key)
    failas.seek(0)
    produktai = parse_vendor_specific(failas, final_mode)
    if not produktai:
        failas.seek(0)
        produktai = parse_vendor_specific(failas, "universal")
    return deduplikoti_produktus(produktai), final_mode, aptiktas_tiekejas, txt

# =====================================================
# APP PUSLAPIAI
# =====================================================
if not SUPABASE_OK:
    st.error("Neįdiegta supabase biblioteka.")
    st.stop()

sb = gauti_supabase()
if sb is None:
    st.title("Konfigūracija")
    st.markdown(
        """
### Reikia sukonfigūruoti Supabase
1. Sukurkite projektą [supabase.com](https://supabase.com)
2. Paleiskite savo SQL lentelių skriptą Supabase SQL Editor'e
3. Streamlit `Settings -> Secrets` įrašykite:

```toml
SUPABASE_URL = "https://jusu-projektas.supabase.co"
SUPABASE_KEY = "jusu-anon-key"
```
4. Perkraukite aplikaciją
        """
    )
    st.stop()

with st.sidebar:
    st.markdown("## 🚜 Navigacija")
    st.markdown("---")
    puslapis = st.radio(
        "Pasirinkite",
        ["📊 Suvestinė", "🌱 Laukai", "💸 Išlaidos", "🧾 Naujas darbas", "📦 Sandėlis", "💰 Pajamos", "📈 Pelningumas", "✏️ Redaguoti", "📤 Eksportas"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown("### 🔎 Filtrai")
    laukai_df = gauti_laukus(sb)
    lauku_opt = {"Visi": None}
    if not laukai_df.empty:
        for _, r in laukai_df.iterrows():
            lauku_opt[f'{r["pavadinimas"]} ({r["kultura"]})'] = r["id"]
    pasirinktas_laukas = st.selectbox("Laukas", list(lauku_opt.keys()))
    c1, c2 = st.columns(2)
    with c1:
        d_nuo = st.date_input("Nuo", value=date(2024, 1, 1), format="YYYY-MM-DD")
    with c2:
        d_iki = st.date_input("Iki", value=date(2026, 12, 31), format="YYYY-MM-DD")

filtrai = {}
if lauku_opt.get(pasirinktas_laukas):
    filtrai["lauko_id"] = lauku_opt[pasirinktas_laukas]
if d_nuo:
    filtrai["nuo"] = formatuoti_data(d_nuo)
if d_iki:
    filtrai["iki"] = formatuoti_data(d_iki)

if puslapis == "📊 Suvestinė":
    st.title("Suvestinė")
    df = gauti_islaidas(sb, filtrai)
    if df.empty:
        st.info("Nėra išlaidų duomenų.")
    else:
        bendra_suma = df["suma"].sum()
        bendras_plotas = laukai_df["plotas_ha"].sum() if not laukai_df.empty else 0
        kaina_ha = bendra_suma / bendras_plotas if bendras_plotas > 0 else 0
        c1, c2, c3, c4 = st.columns(4)
        with c1: rodyti_kpi("Bendra suma", f"{round(bendra_suma, 2)} EUR", "💸")
        with c2: rodyti_kpi("Kaina / ha", f"{round(kaina_ha, 2)} EUR", "🌾")
        with c3: rodyti_kpi("Įrašų", str(len(df)), "🧾")
        with c4: rodyti_kpi("Laukų", str(len(laukai_df) if not laukai_df.empty else 0), "🌱")
        st.markdown("---")
        cl, cr = st.columns(2)
        with cl:
            md = df.groupby("menuo")["suma"].sum().reset_index()
            f1 = px.bar(md, x="menuo", y="suma", title="Išlaidos pagal mėnesį", labels={"menuo": "Mėnuo", "suma": "Suma EUR"}, color_discrete_sequence=[COLORS[0]])
            f1.update_layout(plot_bgcolor="white", paper_bgcolor="white", xaxis_tickangle=-35, title_font_size=14)
            st.plotly_chart(f1, use_container_width=True)
        with cr:
            if "lauko_pavadinimas" in df.columns:
                ld = df.groupby("lauko_pavadinimas")["suma"].sum().reset_index()
                f2 = px.bar(ld, x="lauko_pavadinimas", y="suma", title="Išlaidos pagal lauką", labels={"lauko_pavadinimas": "Laukas", "suma": "Suma EUR"}, color_discrete_sequence=[COLORS[1]])
                f2.update_layout(plot_bgcolor="white", paper_bgcolor="white", xaxis_tickangle=-35, title_font_size=14)
                st.plotly_chart(f2, use_container_width=True)
        cl2, cr2 = st.columns(2)
        with cl2:
            rd = df.groupby("rusis")["suma"].sum().reset_index()
            f3 = px.pie(rd, values="suma", names="rusis", title="Išlaidos pagal rūšį", color_discrete_sequence=COLORS)
            st.plotly_chart(f3, use_container_width=True)
        with cr2:
            dd = df.groupby("darbas")["suma"].sum().reset_index().sort_values("suma", ascending=False)
            f4 = px.bar(dd, x="darbas", y="suma", title="Išlaidos pagal darbą", labels={"darbas": "Darbas", "suma": "Suma EUR"}, color_discrete_sequence=[COLORS[2]])
            f4.update_layout(plot_bgcolor="white", paper_bgcolor="white", xaxis_tickangle=-35, title_font_size=14)
            st.plotly_chart(f4, use_container_width=True)

elif puslapis == "🌱 Laukai":
    st.title("Laukai")
    t1, t2 = st.tabs(["Peržiūra", "Pridėti lauką"])
    with t1:
        if laukai_df.empty:
            st.info("Nėra laukų.")
        else:
            el = laukai_df[["id", "pavadinimas", "plotas_ha", "kultura", "pastaba"]].copy()
            el.insert(0, "X", False)
            red = st.data_editor(el, use_container_width=True, hide_index=True, column_config={
                "X": st.column_config.CheckboxColumn("X", default=False, width="small"),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "pavadinimas": st.column_config.TextColumn("Pavadinimas"),
                "plotas_ha": st.column_config.NumberColumn("Plotas ha", format="%.2f"),
                "kultura": st.column_config.TextColumn("Kultūra"),
                "pastaba": st.column_config.TextColumn("Pastaba"),
            }, disabled=["id"])
            st.caption(f'Laukų: {len(red)} | Plotas: {round(red["plotas_ha"].sum(), 2)} ha')
            cs, cd = st.columns(2)
            with cs:
                if st.button("Išsaugoti laukų pakeitimus", use_container_width=True):
                    n = 0
                    for i, row in red.iterrows():
                        old = el.iloc[i]
                        changed = any(str(row[c]) != str(old[c]) for c in ["pavadinimas", "plotas_ha", "kultura", "pastaba"])
                        if changed:
                            sb.table("laukai").update({"pavadinimas": row["pavadinimas"], "plotas_ha": float(row["plotas_ha"]), "kultura": row["kultura"], "pastaba": row.get("pastaba", "") or ""}).eq("id", int(row["id"])).execute()
                            n += 1
                    if n:
                        st.success(f"Atnaujinta: {n}")
                        st.rerun()
                    else:
                        st.info("Pakeitimų nerasta.")
            with cd:
                tr = red[red["X"] == True]
                if st.button(f"Ištrinti pažymėtus ({len(tr)})", use_container_width=True, disabled=len(tr) == 0, key="dl"):
                    for _, r in tr.iterrows():
                        sb.table("islaidos").delete().eq("lauko_id", int(r["id"])).execute()
                        sb.table("pajamos").delete().eq("lauko_id", int(r["id"])).execute()
                        sb.table("laukai").delete().eq("id", int(r["id"])).execute()
                    st.success(f"Ištrinta: {len(tr)}")
                    st.rerun()
    with t2:
        with st.form("nl", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                lp = st.text_input("Pavadinimas", placeholder="pvz. 1 laukas")
                lh = st.number_input("Plotas (ha)", min_value=0.0, value=0.0, step=0.1)
            with c2:
                lk = st.text_input("Kultūra", placeholder="pvz. Kviečiai žieminiai")
                lpast = st.text_input("Pastaba", placeholder="(neprivaloma)")
            if st.form_submit_button("Pridėti", use_container_width=True):
                if not lp or not lk:
                    st.error("Įveskite pavadinimą ir kultūrą.")
                else:
                    sb.table("laukai").insert({"pavadinimas": lp, "plotas_ha": lh, "kultura": lk, "pastaba": lpast or ""}).execute()
                    st.success(f"Laukas pridėtas: {lp}")
                    st.rerun()

elif puslapis == "💸 Išlaidos":
    st.title("Išlaidos")
    df = gauti_islaidas(sb, filtrai)
    if df.empty:
        st.info("Nėra įrašų.")
    else:
        cols = ["data", "lauko_pavadinimas", "darbas", "produktas", "rusis", "norma", "vienetas", "kaina_uz_vnt_eur", "sunaudotas_kiekis", "suma", "pastaba"]
        ex = [c for c in cols if c in df.columns]
        rd = df[ex].copy()
        rd.columns = [c.replace("_", " ").title() for c in ex]
        st.dataframe(rd, use_container_width=True, hide_index=True, height=520)
        st.caption(f'Irašų: {len(df)} | Suma: {round(df["suma"].sum(), 2)} EUR')

elif puslapis == "🧾 Naujas darbas":
    st.title("Naujas darbas")
    if laukai_df.empty:
        st.warning("Pirma sukurkite laukus.")
    else:
        sdf = gauti_sandeli(sb)
        if sdf.empty:
            st.warning("Sandėlis tuščias. Pirmiausia pridėkite produktų.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                idata = st.date_input("Data", value=date.today(), format="YYYY-MM-DD", key="nd_data")
                ilaukas = st.selectbox("Laukas", laukai_df["id"].tolist(), format_func=lambda x: f'{laukai_df[laukai_df["id"] == x].iloc[0]["pavadinimas"]} - {laukai_df[laukai_df["id"] == x].iloc[0]["kultura"]} ({laukai_df[laukai_df["id"] == x].iloc[0]["plotas_ha"]} ha)', key="nd_laukas")
                idarbas = st.text_input("Darbas", placeholder="pvz. Tręšimas, purškimas", key="nd_darbas")
            with c2:
                prod_ids = st.multiselect("Produktai", sdf["id"].tolist(), format_func=lambda x: f'{sdf[sdf["id"] == x].iloc[0]["produktas"]} ({sdf[sdf["id"] == x].iloc[0]["kiekis"]} {sdf[sdf["id"] == x].iloc[0]["vienetas"]})', key="nd_produktai")
            with c3:
                ipast = st.text_input("Pastaba", placeholder="(neprivaloma)", key="nd_pastaba")
            li = laukai_df[laukai_df["id"] == ilaukas].iloc[0]
            plotas = li["plotas_ha"]
            normos = {}
            bendra_suma = 0.0
            if prod_ids:
                st.markdown("---")
                for pid in prod_ids:
                    pr = sdf[sdf["id"] == pid].iloc[0]
                    pc1, pc2, pc3 = st.columns([3, 2, 3])
                    with pc1:
                        st.markdown(f'**{pr["produktas"]}**')
                        st.caption(f'{pr["rusis"]} | {pr["kaina_uz_vnt_eur"]} EUR/{pr["vienetas"]} | Likutis: {pr["kiekis"]} {pr["vienetas"]}')
                    with pc2:
                        norma = st.number_input(f'Norma ({pr["vienetas"]}/ha)', min_value=0.0, value=0.0, step=0.01, format="%.3f", key=f"norma_{pid}")
                        normos[pid] = norma
                    with pc3:
                        sun = plotas * norma
                        suma = sun * pr["kaina_uz_vnt_eur"]
                        if norma > 0:
                            st.markdown(f'{plotas} ha × {norma} = **{round(sun, 2)} {pr["vienetas"]}** | **{round(suma, 2)} EUR**')
                            if sun > pr["kiekis"]:
                                st.error(f'Nepakanka! Reikia {round(sun, 2)}, yra {pr["kiekis"]}')
                        bendra_suma += suma
                if bendra_suma > 0:
                    st.markdown(f'### Viso: {round(bendra_suma, 2)} EUR')
                if st.button("Registruoti darbą", type="primary", use_container_width=True, key="nd_submit"):
                    if not idarbas:
                        st.error("Įveskite darbo pavadinimą.")
                    elif not any(n > 0 for n in normos.values()):
                        st.error("Įveskite bent vieną normą.")
                    else:
                        reg_count = reg_suma = 0
                        for pid in prod_ids:
                            norma = normos.get(pid, 0)
                            if norma <= 0:
                                continue
                            pr = sdf[sdf["id"] == pid].iloc[0]
                            sun = plotas * norma
                            suma = sun * pr["kaina_uz_vnt_eur"]
                            sb.table("islaidos").insert({"data": formatuoti_data(idata), "menuo": idata.strftime("%Y-%m"), "lauko_id": int(ilaukas), "darbas": idarbas, "produktas": pr["produktas"], "rusis": pr["rusis"], "norma": float(norma), "vienetas": pr["vienetas"], "kaina_uz_vnt_eur": float(pr["kaina_uz_vnt_eur"]), "sunaudotas_kiekis": round(sun, 4), "suma": round(suma, 2), "pastaba": ipast or ""}).execute()
                            nk = max(0, float(pr["kiekis"]) - float(sun))
                            nv = nk * float(pr["kaina_uz_vnt_eur"])
                            sb.table("sandelis").update({"kiekis": round(nk, 4), "bendra_verte": round(nv, 2)}).eq("id", int(pid)).execute()
                            reg_count += 1
                            reg_suma += suma
                        st.success(f"Registruota: {reg_count} produktų | {round(reg_suma, 2)} EUR")
                        st.rerun()

elif puslapis == "📦 Sandėlis":
    st.title("Sandėlis")
    t1, t2, t3 = st.tabs(["Atsargos", "Pridėti rankiniu būdu", "Importas iš PDF"])
    with t1:
        sdf = gauti_sandeli(sb)
        if sdf.empty:
            st.info("Sandėlis tuščias.")
        else:
            es = sdf[["id", "produktas", "rusis", "kiekis", "vienetas", "kaina_uz_vnt_eur", "bendra_verte", "data_prideta", "pastaba"]].copy()
            es.insert(0, "X", False)
            rs = st.data_editor(es, use_container_width=True, hide_index=True, column_config={
                "X": st.column_config.CheckboxColumn("X", default=False, width="small"),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "produktas": st.column_config.TextColumn("Produktas"),
                "rusis": st.column_config.SelectboxColumn("Rūšis", options=["trasos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "seklos", "kita"]),
                "kiekis": st.column_config.NumberColumn("Kiekis", format="%.3f"),
                "vienetas": st.column_config.SelectboxColumn("Vnt", options=UNIT_OPTIONS),
                "kaina_uz_vnt_eur": st.column_config.NumberColumn("Kaina EUR", format="%.2f"),
                "bendra_verte": st.column_config.NumberColumn("Vertė EUR", format="%.2f", disabled=True),
                "data_prideta": st.column_config.TextColumn("Pirkimo data"),
                "pastaba": st.column_config.TextColumn("Pastaba"),
            }, disabled=["id", "bendra_verte"])
            st.caption(f'Produktų: {len(rs)} | Vertė: {round(rs["bendra_verte"].sum(), 2)} EUR')
            cs, cd = st.columns(2)
            with cs:
                if st.button("Išsaugoti sandėlio pakeitimus", use_container_width=True):
                    n = 0
                    for i, row in rs.iterrows():
                        old = es.iloc[i]
                        changed = any(str(row[c]) != str(old[c]) for c in ["produktas", "rusis", "kiekis", "vienetas", "kaina_uz_vnt_eur", "pastaba"])
                        if changed:
                            nv = float(row["kiekis"]) * float(row["kaina_uz_vnt_eur"])
                            sb.table("sandelis").update({"produktas": row["produktas"], "rusis": row["rusis"], "kiekis": float(row["kiekis"]), "vienetas": row["vienetas"], "kaina_uz_vnt_eur": float(row["kaina_uz_vnt_eur"]), "bendra_verte": round(nv, 2), "pastaba": row.get("pastaba", "") or ""}).eq("id", int(row["id"])).execute()
                            n += 1
                    if n:
                        st.success(f"Atnaujinta: {n}")
                        st.rerun()
                    else:
                        st.info("Pakeitimų nerasta.")
            with cd:
                tr = rs[rs["X"] == True]
                if st.button(f"Ištrinti pažymėtus ({len(tr)})", use_container_width=True, disabled=len(tr) == 0, key="ds"):
                    for _, r in tr.iterrows():
                        sb.table("sandelis").delete().eq("id", int(r["id"])).execute()
                    st.success(f"Ištrinta: {len(tr)}")
                    st.rerun()
    with t2:
        with st.form("sp", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                sp = st.text_input("Produktas", placeholder="pvz. Amonio salietra")
                sr = st.selectbox("Rūšis", ["trasos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "seklos", "kita"])
                sk = st.number_input("Kiekis", min_value=0.0, value=0.0, step=0.1)
            with c2:
                sv = st.selectbox("Vienetas", UNIT_OPTIONS)
                skn = st.number_input("Kaina už vnt (EUR)", min_value=0.0, value=0.0, step=0.01)
                spast = st.text_input("Pastaba", placeholder="(neprivaloma)")
            if st.form_submit_button("Pridėti", use_container_width=True):
                if not sp:
                    st.error("Įveskite produkto pavadinimą.")
                else:
                    bv = sk * skn
                    sb.table("sandelis").insert({"produktas": sp, "rusis": sr, "kiekis": sk, "vienetas": sv, "kaina_uz_vnt_eur": skn, "bendra_verte": round(bv, 2), "data_prideta": date.today().strftime("%Y-%m-%d"), "pastaba": spast or ""}).execute()
                    st.success(f"Produktas pridėtas: {sp}")
                    st.rerun()
    with t3:
        st.markdown("### Importas iš PDF sąskaitos")
        st.caption("Bendras parseris bando gaudyti headerius, vienetus ir skaičius. Tiekėjo parseris naudojamas tik kai reikia tikslumo.")
        if not PDF_OK:
            st.error("Reikia įdiegti pdfplumber biblioteką.")
        else:
            pasirinktas_rezimas = st.selectbox("Importo režimas", list(PARSER_OPTIONS.keys()))
            pdf_file = st.file_uploader("Pasirinkite PDF", type=["pdf"])
            if pdf_file is not None:
                failo_pav = pdf_file.name
                jau_ikelta = False
                ikelta_data = ""
                try:
                    esama = sb.table("saskaitos").select("*").eq("failo_pavadinimas", failo_pav).execute()
                    if getattr(esama, "data", None):
                        jau_ikelta = True
                        ikelta_data = esama.data[0].get("data_ikelta", "")
                except Exception:
                    pass
                testi = True
                if jau_ikelta:
                    st.warning(f"Tokia sąskaita ({failo_pav}) jau buvo įkelta {ikelta_data}. Produktų kiekiai bus pridėti prie esamų.")
                    testi = st.checkbox("Suprantu, noriu tęsti")
                if testi:
                    with st.spinner("Nuskaitoma..."):
                        mode_key = PARSER_OPTIONS[pasirinktas_rezimas]
                        pdf_file.seek(0)
                        produktai, galutinis_parseris, aptiktas_tiekejas, parsed_text = nuskaityti_pdf(pdf_file, mode_key)
                        pdf_file.seek(0)
                        pdf_data_str = gauti_data_is_pdf(pdf_file)
                        pdf_file.seek(0)
                        sask_nr = gauti_saskaitos_nr(pdf_file)
                    if not produktai:
                        st.warning("Nepavyko rasti produktų. Jei reikės – pridėsim dar vieną tiekėją arba pagerinsim bendrą sluoksnį.")
                        with st.expander("Rodyti ištrauktą PDF tekstą diagnostikai"):
                            st.text(parsed_text[:10000])
                    else:
                        info_txt = f"Rasta produktų: {len(produktai)} | Data: {pdf_data_str} | Tiekėjas: {aptiktas_tiekejas} | Parseris: {galutinis_parseris}"
                        if sask_nr:
                            info_txt += f" | Nr: {sask_nr}"
                        st.success(info_txt)
                        try:
                            default_date = datetime.strptime(pdf_data_str, "%Y-%m-%d").date()
                        except Exception:
                            default_date = date.today()
                        pirkimo_data = st.date_input("Pirkimo data", value=default_date, format="YYYY-MM-DD")
                        edf = pd.DataFrame(produktai)
                        st.markdown("#### Patikrinkite duomenis (nereikalingas eilutes galite ištrinti):")
                        red_pdf = st.data_editor(edf, use_container_width=True, hide_index=True, num_rows="dynamic", column_config={
                            "Produktas": st.column_config.TextColumn("Produktas"),
                            "Rusis": st.column_config.SelectboxColumn("Rūšis", options=["trasos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "seklos", "kita"]),
                            "Kiekis": st.column_config.NumberColumn("Kiekis", format="%.3f"),
                            "Vienetas": st.column_config.SelectboxColumn("Vienetas", options=UNIT_OPTIONS),
                            "Kaina": st.column_config.NumberColumn("Kaina EUR/vnt", format="%.2f"),
                            "Verte": st.column_config.NumberColumn("Vertė EUR", format="%.2f"),
                        })
                        valid = red_pdf[red_pdf["Produktas"].notna() & (red_pdf["Produktas"].astype(str).str.strip() != "") & (red_pdf["Produktas"].astype(str).str.lower() != "none")]
                        st.caption(f'Bus pridėta: {len(valid)} | Vertė: {round(valid["Verte"].sum(), 2)} EUR')
                        if st.button("Pridėti į sandėlį", type="primary", use_container_width=True):
                            prideta = atnaujinta = 0
                            data_str = pirkimo_data.strftime("%Y-%m-%d")
                            for _, row in valid.iterrows():
                                pav = str(row["Produktas"]).strip()
                                if not pav:
                                    continue
                                esamas = sb.table("sandelis").select("*").eq("produktas", pav).execute()
                                if getattr(esamas, "data", None):
                                    e = esamas.data[0]
                                    nk = float(e["kiekis"]) + float(row["Kiekis"])
                                    nv = nk * float(e["kaina_uz_vnt_eur"])
                                    sb.table("sandelis").update({"kiekis": round(nk, 4), "bendra_verte": round(nv, 2)}).eq("id", e["id"]).execute()
                                    atnaujinta += 1
                                else:
                                    sb.table("sandelis").insert({"produktas": pav, "rusis": row["Rusis"], "kiekis": float(row["Kiekis"]), "vienetas": row["Vienetas"], "kaina_uz_vnt_eur": float(row["Kaina"]), "bendra_verte": round(float(row["Verte"]), 2), "data_prideta": data_str, "pastaba": f"Iš: {failo_pav}"}).execute()
                                    prideta += 1
                            try:
                                sb.table("saskaitos").insert({"failo_pavadinimas": failo_pav, "saskaitos_numeris": sask_nr or "", "data_ikelta": datetime.now().strftime("%Y-%m-%d %H:%M"), "produktu_skaicius": int(len(valid)), "parserio_rezimas": galutinis_parseris, "tiekejas": aptiktas_tiekejas}).execute()
                            except Exception:
                                try:
                                    sb.table("saskaitos").insert({"failo_pavadinimas": failo_pav, "saskaitos_numeris": sask_nr or "", "data_ikelta": datetime.now().strftime("%Y-%m-%d %H:%M"), "produktu_skaicius": int(len(valid))}).execute()
                                except Exception:
                                    pass
                            st.success(f"Naujų: {prideta}, atnaujinta: {atnaujinta}")
                            st.rerun()

elif puslapis == "💰 Pajamos":
    st.title("Pajamos")
    t1, t2 = st.tabs(["Registruoti", "Peržiūra"])
    with t1:
        if laukai_df.empty:
            st.warning("Pirma sukurkite laukus.")
        else:
            with st.form("pf", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    pdata = st.date_input("Pardavimo data", value=date.today())
                    plaukas = st.selectbox("Laukas", laukai_df["id"].tolist(), format_func=lambda x: f'{laukai_df[laukai_df["id"] == x].iloc[0]["pavadinimas"]} ({laukai_df[laukai_df["id"] == x].iloc[0]["plotas_ha"]} ha)')
                with c2:
                    pder = st.number_input("Derlius (t/ha)", min_value=0.0, value=0.0, step=0.1)
                    pkaina = st.number_input("Pardavimo kaina (EUR/t)", min_value=0.0, value=0.0, step=1.0)
                    ppast = st.text_input("Pastaba", placeholder="(neprivaloma)")
                if st.form_submit_button("Registruoti", use_container_width=True):
                    lr = laukai_df[laukai_df["id"] == plaukas].iloc[0]
                    bd = float(lr["plotas_ha"]) * float(pder)
                    ps = bd * float(pkaina)
                    sb.table("pajamos").insert({"data": formatuoti_data(pdata), "lauko_id": int(plaukas), "derlius_t_ha": float(pder), "bendras_derlius_t": round(bd, 2), "pardavimo_kaina_eur_t": float(pkaina), "pajamu_suma": round(ps, 2), "pastaba": ppast or ""}).execute()
                    st.success(f"Pajamos: {round(ps, 2)} EUR")
                    st.rerun()
    with t2:
        pajdf = gauti_pajamas(sb, filtrai.get("lauko_id"), filtrai.get("nuo"), filtrai.get("iki"))
        if pajdf.empty:
            st.info("Pajamų nėra.")
        else:
            cols = ["data", "lauko_pavadinimas", "kultura", "derlius_t_ha", "bendras_derlius_t", "pardavimo_kaina_eur_t", "pajamu_suma", "pastaba"]
            ex = [c for c in cols if c in pajdf.columns]
            st.dataframe(pajdf[ex], use_container_width=True, hide_index=True)
            st.caption(f'Visos pajamos: {round(pajdf["pajamu_suma"].sum(), 2)} EUR')

elif puslapis == "📈 Pelningumas":
    st.title("Pelningumas")
    idf = gauti_islaidas(sb, filtrai)
    pajdf = gauti_pajamas(sb, filtrai.get("lauko_id"), filtrai.get("nuo"), filtrai.get("iki"))
    vi = idf["suma"].sum() if not idf.empty else 0
    vp = pajdf["pajamu_suma"].sum() if not pajdf.empty else 0
    pel = vp - vi
    mar = (pel / vp * 100) if vp > 0 else 0
    c1, c2, c3, c4 = st.columns(4)
    with c1: rodyti_kpi("Išlaidos", f"{round(vi, 2)} EUR", "💸")
    with c2: rodyti_kpi("Pajamos", f"{round(vp, 2)} EUR", "💰")
    with c3: rodyti_kpi("Pelnas", f"{round(pel, 2)} EUR", "📈")
    with c4: rodyti_kpi("Marža", f"{round(mar, 1)} %", "📊")
    st.markdown("---")
    if not idf.empty or not pajdf.empty:
        fig = go.Figure()
        if not idf.empty:
            im = idf.groupby("menuo")["suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=im["menuo"], y=im["suma"], name="Išlaidos", marker_color="#c0392b"))
        if not pajdf.empty:
            pajdf_m = pajdf.copy()
            pajdf_m["menuo"] = pd.to_datetime(pajdf_m["data"], errors="coerce").dt.strftime("%Y-%m")
            pm = pajdf_m.groupby("menuo")["pajamu_suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=pm["menuo"], y=pm["pajamu_suma"], name="Pajamos", marker_color="#27ae60"))
        fig.update_layout(title="Išlaidos ir pajamos", barmode="group", plot_bgcolor="white", paper_bgcolor="white", title_font_size=14)
        st.plotly_chart(fig, use_container_width=True)
        if not idf.empty and "lauko_pavadinimas" in idf.columns:
            il = idf.groupby("lauko_pavadinimas")["suma"].sum().reset_index()
            il.columns = ["Laukas", "Išlaidos"]
            if not pajdf.empty and "lauko_pavadinimas" in pajdf.columns:
                plk = pajdf.groupby("lauko_pavadinimas")["pajamu_suma"].sum().reset_index()
                plk.columns = ["Laukas", "Pajamos"]
                peld = il.merge(plk, on="Laukas", how="outer").fillna(0)
            else:
                peld = il.copy(); peld["Pajamos"] = 0
            peld["Pelnas"] = peld["Pajamos"] - peld["Išlaidos"]
            st.dataframe(peld, use_container_width=True, hide_index=True)
    else:
        st.info("Pridėkite duomenų.")

elif puslapis == "✏️ Redaguoti":
    st.title("Redaguoti išlaidas")
    df = gauti_islaidas(sb)
    if df.empty:
        st.info("Nėra įrašų.")
    else:
        ecols = ["id", "data", "lauko_pavadinimas", "darbas", "produktas", "rusis", "norma", "vienetas", "kaina_uz_vnt_eur", "pastaba"]
        ex = [c for c in ecols if c in df.columns]
        edf = df[ex].copy(); edf.insert(0, "X", False)
        red = st.data_editor(edf, use_container_width=True, hide_index=True, height=520, column_config={
            "X": st.column_config.CheckboxColumn("X", default=False, width="small"),
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "data": st.column_config.TextColumn("Data"),
            "lauko_pavadinimas": st.column_config.TextColumn("Laukas", disabled=True),
            "darbas": st.column_config.TextColumn("Darbas"),
            "produktas": st.column_config.TextColumn("Produktas"),
            "rusis": st.column_config.SelectboxColumn("Rūšis", options=["trasos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "seklos", "kita"]),
            "norma": st.column_config.NumberColumn("Norma", format="%.3f"),
            "vienetas": st.column_config.SelectboxColumn("Vnt", options=UNIT_OPTIONS),
            "kaina_uz_vnt_eur": st.column_config.NumberColumn("Kaina EUR", format="%.2f"),
            "pastaba": st.column_config.TextColumn("Pastaba"),
        }, disabled=["id", "lauko_pavadinimas"])
        cs, cd = st.columns(2)
        with cs:
            if st.button("Išsaugoti pakeitimus", use_container_width=True):
                n = 0
                for i, row in red.iterrows():
                    old = edf.iloc[i]
                    changed = any(str(row[c]) != str(old[c]) for c in ["data", "darbas", "produktas", "rusis", "norma", "vienetas", "kaina_uz_vnt_eur", "pastaba"])
                    if changed:
                        rid = int(row["id"])
                        orig = df[df["id"] == rid].iloc[0]
                        lid = orig["lauko_id"]
                        lr = laukai_df[laukai_df["id"] == lid]
                        plotas = lr.iloc[0]["plotas_ha"] if not lr.empty else 0
                        norma = float(row["norma"])
                        kaina = float(row["kaina_uz_vnt_eur"])
                        sun = plotas * norma
                        suma = sun * kaina
                        ds = str(row["data"])
                        menuo = ds[:7] if len(ds) >= 7 else ""
                        sb.table("islaidos").update({"data": ds, "menuo": menuo, "darbas": row["darbas"], "produktas": row["produktas"], "rusis": row["rusis"], "norma": norma, "vienetas": row["vienetas"], "kaina_uz_vnt_eur": kaina, "sunaudotas_kiekis": round(sun, 4), "suma": round(suma, 2), "pastaba": row.get("pastaba", "") or ""}).eq("id", rid).execute()
                        n += 1
                if n:
                    st.success(f"Atnaujinta: {n}")
                    st.rerun()
                else:
                    st.info("Pakeitimų nerasta.")
        with cd:
            tr = red[red["X"] == True]
            if st.button(f"Ištrinti pažymėtus ({len(tr)})", use_container_width=True, disabled=len(tr) == 0, key="di"):
                for _, r in tr.iterrows():
                    sb.table("islaidos").delete().eq("id", int(r["id"])).execute()
                st.success(f"Ištrinta: {len(tr)}")
                st.rerun()

elif puslapis == "📤 Eksportas":
    st.title("Eksportas")
    df = gauti_islaidas(sb)
    if df.empty:
        st.info("Nėra duomenų.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            buf = io.StringIO(); df.to_csv(buf, index=False, sep=";")
            st.download_button("Parsisiųsti CSV", data=buf.getvalue(), file_name=f'ukio_islaidos_{datetime.now().strftime("%Y%m%d")}.csv', mime="text/csv", use_container_width=True)
        with c2:
            buf2 = io.BytesIO()
            with pd.ExcelWriter(buf2, engine="openpyxl") as w:
                df.to_excel(w, sheet_name="Islaidos", index=False)
                suv = pd.DataFrame({"Rodiklis": ["Bendra suma", "Įrašų", "Laukų"], "Reiksme": [str(round(df["suma"].sum(), 2)), str(len(df)), str(len(laukai_df)) if not laukai_df.empty else "0"]})
                suv.to_excel(w, sheet_name="Suvestine", index=False)
                sdf = gauti_sandeli(sb)
                if not sdf.empty:
                    sdf.to_excel(w, sheet_name="Sandelis", index=False)
            st.download_button("Parsisiųsti Excel", data=buf2.getvalue(), file_name=f'ukio_ataskaita_{datetime.now().strftime("%Y%m%d")}.xlsx', mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
