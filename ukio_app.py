
import io
import re
from datetime import date, datetime

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


st.set_page_config(
    page_title="Ūkio skaičiuoklė",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.0rem;
        padding-bottom: 1.0rem;
    }
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
    .app-title h1 {
        margin: 0;
        font-size: 28px;
    }
    .app-title p {
        margin: 6px 0 0 0;
        opacity: 0.95;
        font-size: 14px;
    }
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
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 12px;
        font-weight: 600;
        border: none;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 8px 14px;
        background: #f4f7f3;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

COLORS = ["#5a7d9a", "#7da87b", "#c4956a", "#b07aa1", "#9c9c9c", "#d4a574"]
RUSIS_MAP = {
    "herbicidas": ["mustang", "axial", "derby", "corum", "dash", "pantera", "butisan", "herold", "lentipur", "sekator", "biathlon", "husar", "stomp", "starane", "focus", "elite", "elit", "vantex", "belkar", "tombo", "fundamentum"],
    "fungicidas": ["prosaro", "osiris", "adexar", "fandango", "skyway", "input", "navura", "caramba", "tilt", "amistar", "acanto", "falcon", "opus", "signum"],
    "insekticidas": ["karate", "decis", "fastac", "fury", "biscaya", "proteus", "mavrik", "pirimor", "vantex"],
    "reguliatorius": ["moddus", "ccc", "terpal", "medax", "cerone", "prodax", "manipulator"],
    "trasos": ["npk", "amonio", "kas", "karbamidas", "urea", "salietra", "superfosfat", "kalio", "dap", "map", "kcl", "k40", "kalcio", "magnis", "sulfur", "siera", "mikro"],
    "seklos": ["sekla", "sėkla", "seed"],
}
PROD_KEYWORDS = [
    "preke", "prekė", "paslauga", "preke, paslauga", "prekė, paslauga", "pavadinimas", "aprasymas",
    "aprašymas", "prekes/paslaugu pavadinimas", "prekių/paslaugų pavadinimas", "prekes paslaugos pavadinimas",
    "prekės paslaugos pavadinimas", "aprasas", "aprašas"
]
SKIP_ROWS = [
    "suma be", "pvm", "viso", "moketi", "mokėti", "is viso", "iš viso", "nuolaida", "isankstinio",
    "išankstinio", "viso su", "apmokejimo", "apmokėjimo", "viso moketi", "viso mokėti", "suma zodziais",
    "suma žodžiais", "apmoketi iki", "apmokėti iki", "pirkėjas", "pirkejas", "pardavejas", "pardavėjas",
    "grazinta tara", "grąžinta tara", "dokumenta israse", "dokumentą išrašė", "prekes/paslaugas gavau",
    "prekės/paslaugos gavau", "viso be pvm", "pvm suma", "viso su pvm", "pvm tarifas", "pvm %",
    "pakrovimo", "sutartis", "užsakymo nr", "uzsakymo nr", "transporto", "tara", "bankas",
    "adresas", "tel.", "el.pašto adresas", "el. pašto adresas", "šis dokumentas"
]
UNIT_OPTIONS = ["kg", "l", "vnt", "t"]
LT_MONTHS = {
    "sausio": 1, "vasario": 2, "kovo": 3, "balandžio": 4, "gegužės": 5, "birželio": 6,
    "liepos": 7, "rugpjūčio": 8, "rugsėjo": 9, "spalio": 10, "lapkričio": 11, "gruodžio": 12,
}


def gauti_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


def txt_norm(s):
    return str(s or "").strip().lower().replace("\n", " ").replace("\xa0", " ")


def num(v):
    if v is None:
        return 0.0
    s = str(v).strip().replace(" ", "")
    if not s:
        return 0.0
    s = s.replace("€", "").replace("eur", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(s)
    except Exception:
        return 0.0


def nustatyti_rusi(pav):
    p = txt_norm(pav)
    for rusis, kws in RUSIS_MAP.items():
        for kw in kws:
            if kw in p:
                return rusis
    return "kita"


def isvalyti_pav(pav):
    s = str(pav or "").replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\([A-Z0-9\-_/]+\)", "", s)
    s = re.sub(r"^\d+[.)]?\s*", "", s)
    return s.strip(" -")


def normalizuoti_vieneta(v):
    vv = txt_norm(v)
    mapping = {
        "kg": "kg",
        "kilogramai": "kg",
        "kilogramas": "kg",
        "l": "l",
        "lt": "l",
        "ltr": "l",
        "l.": "l",
        "vnt": "vnt",
        "v.": "vnt",
        "vnt.": "vnt",
        "t": "t",
    }
    return mapping.get(vv, vv if vv else "vnt")


def yra_suvestines_eilute(txt):
    t = txt_norm(txt)
    return any(k in t for k in SKIP_ROWS)


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


def deduplikoti_produktus(produktai):
    out = []
    seen = set()
    for p in produktai:
        key = (
            str(p.get("Produktas", "")).strip().lower(),
            str(p.get("Vienetas", "")).strip().lower(),
            round(float(p.get("Kiekis", 0)), 3),
            round(float(p.get("Kaina", 0)), 3),
        )
        if key in seen:
            continue
        seen.add(key)
        if p.get("Produktas") and str(p["Produktas"]).strip().lower() not in ["none", "nan", ""]:
            out.append(p)
    return out


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


def gauti_data_is_pdf(failas):
    text_all = []
    with pdfplumber.open(failas) as pdf:
        for page in pdf.pages:
            text_all.append(page.extract_text() or "")
    txt = "\n".join(text_all)

    for m in re.findall(r"\b\d{4}[-./]\d{2}[-./]\d{2}\b", txt):
        parts = re.split(r"[-./]", m)
        return f"{parts[0]}-{parts[1]}-{parts[2]}"

    for m in re.findall(r"\b\d{2}[-./]\d{2}[-./]\d{4}\b", txt):
        parts = re.split(r"[-./]", m)
        return f"{parts[2]}-{parts[1]}-{parts[0]}"

    m = re.search(r"(\d{4})\s*m\.\s*([a-ząčęėįšųūž]+)\s*(\d{1,2})\s*d\.", txt, re.IGNORECASE)
    if m:
        year = int(m.group(1))
        month = LT_MONTHS.get(m.group(2).lower())
        day = int(m.group(3))
        if month:
            return date(year, month, day).strftime("%Y-%m-%d")

    return date.today().strftime("%Y-%m-%d")


def gauti_saskaitos_nr(failas):
    patterns = [
        r"serija\s*[:\-]?\s*([A-Z0-9\-_/]+)\s*nr\.?\s*[:\-]?\s*([A-Z0-9\-_/]+)",
        r"nr\.?\s*[:\-]?\s*([A-Z]{2,}[A-Z0-9\-_/]*)",
        r"serija\s*[:\-]?\s*([A-Z]{2,}[A-Z0-9\-_/]*)",
        r"(?:pvm\s+saskaita(?:[-\s]?faktura)?|pvm\s+sąskaita(?:[-\s]?faktūra)?)\s*(?:serija\s*)?([A-Z0-9\-_/]+)?\s*nr\.?\s*[:\-]?\s*([A-Z0-9\-_/]+)",
    ]
    with pdfplumber.open(failas) as pdf:
        for page in pdf.pages:
            txt = (page.extract_text() or "").replace("\n", " ")
            for pat in patterns:
                m = re.search(pat, txt, re.IGNORECASE)
                if m:
                    groups = [g for g in m.groups() if g]
                    if len(groups) >= 2:
                        return " ".join(groups).strip()
                    if len(groups) == 1:
                        return groups[0].strip()
    return ""


def aptikti_tiekeja(failas):
    with pdfplumber.open(failas) as pdf:
        txt = " ".join((page.extract_text() or "") for page in pdf.pages[:2]).lower()
    if "agrochema" in txt:
        return "agrochema"
    if "agrokoncern" in txt:
        return "agrokoncernas"
    if "linas agro" in txt:
        return "linas_agro"
    if "scandagra" in txt:
        return "scandagra"
    return "nezinomas"


def nuskaityti_pdf_lentele(failas):
    produktai = []
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "intersection_tolerance": 8,
        "snap_tolerance": 6,
        "join_tolerance": 6,
    }

    with pdfplumber.open(failas) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(table_settings=table_settings) or []
            for table in tables:
                if not table or len(table) < 2:
                    continue

                hdr_idx = None
                for i, row in enumerate(table[:8]):
                    row_txt = " ".join(txt_norm(c) for c in row if c is not None)
                    if any(k in row_txt for k in PROD_KEYWORDS) and any(k in row_txt for k in ["kiekis", "kaina", "suma"]):
                        hdr_idx = i
                        break

                if hdr_idx is None:
                    continue

                hdr = [txt_norm(c) for c in table[hdr_idx]]
                pi = ki = vi = kai = si = None

                for j, c in enumerate(hdr):
                    if any(k in c for k in ["preke", "prekė", "paslauga", "pavadinimas", "aprasymas", "aprašymas", "prekes/paslaugu", "prekių/paslaugų", "aprasas", "aprašas"]):
                        pi = j
                    elif "mato" in c or c == "vnt" or "mato vnt" in c:
                        vi = j
                    elif "kiekis" in c:
                        ki = j
                    elif "kaina" in c and kai is None:
                        kai = j
                    elif "suma" in c and si is None:
                        si = j

                if pi is None or ki is None:
                    continue

                for row in table[hdr_idx + 1:]:
                    if not row:
                        continue
                    row_txt = " ".join(txt_norm(c) for c in row if c is not None).strip()
                    if not row_txt or yra_suvestines_eilute(row_txt):
                        continue
                    try:
                        pav = isvalyti_pav(row[pi]) if pi < len(row) else ""
                        kiekis = num(row[ki]) if ki is not None and ki < len(row) else 0
                        vnt = normalizuoti_vieneta(row[vi]) if vi is not None and vi < len(row) else "vnt"
                        kaina = num(row[kai]) if kai is not None and kai < len(row) else 0
                        suma = num(row[si]) if si is not None and si < len(row) else round(kiekis * kaina, 2)
                        if not pav or len(str(pav).strip()) < 2 or kiekis <= 0:
                            continue
                        produktai.append({
                            "Produktas": str(pav).strip(),
                            "Rusis": nustatyti_rusi(str(pav)),
                            "Kiekis": kiekis,
                            "Vienetas": vnt,
                            "Kaina": kaina,
                            "Verte": round(suma if suma > 0 else kiekis * kaina, 2),
                        })
                    except Exception:
                        continue
    return deduplikoti_produktus(produktai)


def parse_produkto_eilute(line):
    line_clean = re.sub(r"\s+", " ", str(line or "")).strip()
    if not line_clean or yra_suvestines_eilute(line_clean):
        return None

    m = re.search(r"^(?:\d+[.)]?\s+)?(?:[A-Z0-9\-_/]+\s+)?(.+?)\s+(kg|l|vnt|t)\s+([\d\s.,]+)\s+([\d\s.,]+)\s+([\d\s.,]+)(?:\s+[\d\s.,%]+)?$", line_clean, re.IGNORECASE)
    if m:
        pav = isvalyti_pav(m.group(1))
        vienetas = normalizuoti_vieneta(m.group(2))
        kiekis = num(m.group(3))
        kaina = num(m.group(4))
        suma = num(m.group(5))
        if pav and kiekis > 0:
            return {
                "Produktas": pav,
                "Rusis": nustatyti_rusi(pav),
                "Kiekis": kiekis,
                "Vienetas": vienetas,
                "Kaina": kaina,
                "Verte": round(suma if suma > 0 else kiekis * kaina, 2),
            }

    m2 = re.search(r"^(?:\d+[.)]?\s+)?(?:[A-Z0-9\-_/]+\s+)?(.+?)\s+([\d\s.,]+)\s+([\d\s.,]+)\s+([\d\s.,]+)$", line_clean, re.IGNORECASE)
    if m2:
        pav = isvalyti_pav(m2.group(1))
        kiekis = num(m2.group(2))
        kaina = num(m2.group(3))
        suma = num(m2.group(4))
        if pav and kiekis > 0 and kaina >= 0:
            return {
                "Produktas": pav,
                "Rusis": nustatyti_rusi(pav),
                "Kiekis": kiekis,
                "Vienetas": "vnt",
                "Kaina": kaina,
                "Verte": round(suma if suma > 0 else kiekis * kaina, 2),
            }
    return None


def nuskaityti_pdf_tekstu(failas):
    produktai = []
    with pdfplumber.open(failas) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            lines = [l.strip() for l in txt.split("\n") if l.strip()]
            start_idx = None
            for i, line in enumerate(lines):
                ln = txt_norm(line)
                if any(k in ln for k in PROD_KEYWORDS) and any(k in ln for k in ["kiekis", "kaina", "suma"]):
                    start_idx = i + 1
                    break
            if start_idx is None:
                continue

            buferis = []
            for line in lines[start_idx:]:
                lin = txt_norm(line)
                if yra_suvestines_eilute(lin):
                    continue
                parsed_now = parse_produkto_eilute(line)
                if parsed_now:
                    buferis.append(line)
                    continue
                if buferis and len(lin.split()) <= 7:
                    buferis[-1] = buferis[-1] + " " + line
                else:
                    buferis.append(line)

            for line in buferis:
                p = parse_produkto_eilute(line)
                if p:
                    produktai.append(p)
    return deduplikoti_produktus(produktai)


def nuskaityti_pdf(failas):
    produktai = nuskaityti_pdf_lentele(failas)
    if produktai:
        return produktai
    failas.seek(0)
    produktai = nuskaityti_pdf_tekstu(failas)
    if produktai:
        return produktai
    return []


st.markdown(
    """
    <div class="app-title">
        <h1>🌾 Ūkio skaičiuoklė</h1>
        <p>Laukai • Išlaidos • Sandėlis • Pajamos • Pelningumas</p>
    </div>
    """,
    unsafe_allow_html=True,
)

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
2. SQL Editor paleiskite `setup_atnaujintas.sql`
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
        [
            "📊 Suvestinė",
            "🌱 Laukai",
            "💸 Išlaidos",
            "🧾 Naujas darbas",
            "📦 Sandėlis",
            "💰 Pajamos",
            "📈 Pelningumas",
            "✏️ Redaguoti",
            "📤 Eksportas",
        ],
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
    filtrai["nuo"] = d_nuo.strftime("%Y-%m-%d")
if d_iki:
    filtrai["iki"] = d_iki.strftime("%Y-%m-%d")

if puslapis == "📊 Suvestinė":
    st.title("Suvestinė")
    df = gauti_islaidas(sb, filtrai)
    if df.empty:
        st.info("Nėra išlaidų duomenų.")
    else:
        bs = df["suma"].sum()
        bp = laukai_df["plotas_ha"].sum() if not laukai_df.empty else 0
        kh = bs / bp if bp > 0 else 0
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            rodyti_kpi("Bendra suma", f"{round(bs, 2)} EUR", "💸")
        with c2:
            rodyti_kpi("Kaina / ha", f"{round(kh, 2)} EUR", "🌾")
        with c3:
            rodyti_kpi("Įrašų", str(len(df)), "🧾")
        with c4:
            rodyti_kpi("Laukų", str(len(laukai_df) if not laukai_df.empty else 0), "🌱")

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
            f3.update_layout(paper_bgcolor="white", title_font_size=14)
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
                        reg_count = 0
                        reg_suma = 0.0
                        for pid in prod_ids:
                            norma = normos.get(pid, 0)
                            if norma <= 0:
                                continue
                            pr = sdf[sdf["id"] == pid].iloc[0]
                            sun = plotas * norma
                            suma = sun * pr["kaina_uz_vnt_eur"]
                            sb.table("islaidos").insert({"data": idata.strftime("%Y-%m-%d"), "menuo": idata.strftime("%Y-%m"), "lauko_id": int(ilaukas), "darbas": idarbas, "produktas": pr["produktas"], "rusis": pr["rusis"], "norma": float(norma), "vienetas": pr["vienetas"], "kaina_uz_vnt_eur": float(pr["kaina_uz_vnt_eur"]), "sunaudotas_kiekis": round(sun, 4), "suma": round(suma, 2), "pastaba": ipast or ""}).execute()
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
        st.caption("Įkelkite PDF sąskaitą – sistema bandys automatiškai atpažinti produktus, kiekį, vienetą, kainą ir sumą.")
        if not PDF_OK:
            st.error("Reikia įdiegti pdfplumber biblioteką.")
        else:
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
                        pdf_file.seek(0)
                        produktai = nuskaityti_pdf(pdf_file)
                        pdf_file.seek(0)
                        pdf_data_str = gauti_data_is_pdf(pdf_file)
                        pdf_file.seek(0)
                        sask_nr = gauti_saskaitos_nr(pdf_file)
                        pdf_file.seek(0)
                        tiekejas = aptikti_tiekeja(pdf_file)
                    if not produktai:
                        st.warning("Nepavyko rasti produktų lentelės. Jei nori, galėsiu dar papildyti parserį pagal konkretų PDF šabloną.")
                    else:
                        info_txt = f"Rasta produktų: {len(produktai)} | Data: {pdf_data_str} | Tiekėjas: {tiekejas}"
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
                            prideta = 0
                            atnaujinta = 0
                            data_str = pirkimo_data.strftime("%Y-%m-%d")
                            for _, row in valid.iterrows():
                                pav = str(row["Produktas"]).strip()
                                if not pav or pav.lower() in ["none", "nan", ""]:
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
                    sb.table("pajamos").insert({"data": pdata.strftime("%Y-%m-%d"), "lauko_id": int(plaukas), "derlius_t_ha": float(pder), "bendras_derlius_t": round(bd, 2), "pardavimo_kaina_eur_t": float(pkaina), "pajamu_suma": round(ps, 2), "pastaba": ppast or ""}).execute()
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
    with c1:
        rodyti_kpi("Išlaidos", f"{round(vi, 2)} EUR", "💸")
    with c2:
        rodyti_kpi("Pajamos", f"{round(vp, 2)} EUR", "💰")
    with c3:
        rodyti_kpi("Pelnas", f"{round(pel, 2)} EUR", "📈")
    with c4:
        rodyti_kpi("Marža", f"{round(mar, 1)} %", "📊")
    st.markdown("---")
    if not idf.empty or not pajdf.empty:
        fig = go.Figure()
        if not idf.empty:
            im = idf.groupby("menuo")["suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=im["menuo"], y=im["suma"], name="Išlaidos", marker_color="#c0392b"))
        if not pajdf.empty:
            pajdf = pajdf.copy()
            pajdf["menuo"] = pd.to_datetime(pajdf["data"], errors="coerce").dt.strftime("%Y-%m")
            pm = pajdf.groupby("menuo")["pajamu_suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=pm["menuo"], y=pm["pajamu_suma"], name="Pajamos", marker_color="#27ae60"))
        fig.update_layout(title="Išlaidos ir pajamos", barmode="group", plot_bgcolor="white", paper_bgcolor="white", title_font_size=14)
        st.plotly_chart(fig, use_container_width=True)
        if not idf.empty and "lauko_pavadinimas" in idf.columns:
            st.markdown("#### Pagal lauką")
            il = idf.groupby("lauko_pavadinimas")["suma"].sum().reset_index()
            il.columns = ["Laukas", "Išlaidos"]
            if not pajdf.empty and "lauko_pavadinimas" in pajdf.columns:
                plk = pajdf.groupby("lauko_pavadinimas")["pajamu_suma"].sum().reset_index()
                plk.columns = ["Laukas", "Pajamos"]
                peld = il.merge(plk, on="Laukas", how="outer").fillna(0)
            else:
                peld = il.copy()
                peld["Pajamos"] = 0
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
        edf = df[ex].copy()
        edf.insert(0, "X", False)
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
            buf = io.StringIO()
            df.to_csv(buf, index=False, sep=";")
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
