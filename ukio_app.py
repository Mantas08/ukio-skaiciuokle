import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import io
import os
import re

# =====================================================
# SUPABASE PRISIJUNGIMAS
# =====================================================

try:
    from supabase import create_client
    SUPABASE_GALIMAS = True
except ImportError:
    SUPABASE_GALIMAS = False

try:
    import pdfplumber
    PDF_GALIMAS = True
except ImportError:
    PDF_GALIMAS = False


def gauti_supabase():
    """Gauti Supabase klientą iš Streamlit secrets."""
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


# =====================================================
# STREAMLIT KONFIGŪRACIJA
# =====================================================

st.set_page_config(
    page_title="🌾 Ūkio skaičiuoklė",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Šviesus/pilkas dizainas
st.markdown("""
<style>
    .stApp {
        background-color: #f7f8fa;
    }
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e3e8;
    }
    section[data-testid="stSidebar"] .stRadio label {
        color: #333333;
    }
    h1, h2, h3 {
        color: #1a1a2e;
    }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e3e8;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    div[data-testid="stMetric"] label {
        color: #666666;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #1a1a2e;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }
    .stTabs [data-baseweb="tab"] {
        color: #555555;
    }
    .stTabs [aria-selected="true"] {
        color: #2e7d32;
        border-bottom-color: #2e7d32;
    }
    .stDataFrame {
        border-radius: 8px;
    }
    [data-testid="stForm"] {
        background-color: #ffffff;
        border: 1px solid #e0e3e8;
        border-radius: 12px;
        padding: 20px;
    }
    .stRadio > div {
        gap: 2px;
    }
</style>
""", unsafe_allow_html=True)


# =====================================================
# PAGALBINĖS FUNKCIJOS
# =====================================================

RUSIS_ZODYNAS = {
    "herbicidas": ["mustang", "axial", "derby", "corum", "dash", "pantera",
                   "butisan", "herold", "lentipur", "sekator", "biathlon",
                   "husar", "maraton", "stomp", "tomigan", "starane"],
    "fungicidas": ["prosaro", "osiris", "adexar", "fandango", "skyway",
                   "input", "navura", "caramba", "tilt", "amistar",
                   "acanto", "rex", "falcon", "opus"],
    "insekticidas": ["karate", "decis", "fastac", "fury", "biscaya",
                     "proteus", "mavrik", "pirimor"],
    "reguliatorius": ["moddus", "ccc", "terpal", "medax", "cerone",
                      "manipulator", "prodax"],
    "trąšos": ["npk", "amonio", "kas", "karbamidas", "urea", "saletra",
               "superfosfat", "kalio", "dap", "map"],
    "sėklos": ["sėkla", "sekla", "seed"]
}


def nustatyti_rusi(produkto_pavadinimas):
    """Automatiškai nustatyti produkto rūšį pagal pavadinimą."""
    pav_lower = produkto_pavadinimas.lower()
    for rusis, raktazodziai in RUSIS_ZODYNAS.items():
        for rz in raktazodziai:
            if rz in pav_lower:
                return rusis
    return "kita"


def isvalyti_produkto_pavadinima(pavadinimas):
    """Pašalinti kodus skliaustėliuose iš produkto pavadinimo."""
    # Pašalinti (KODAS123) tipo tekstą
    isvalytas = re.sub(r'\s*\([A-Z0-9]+\)', '', str(pavadinimas))
    # Pašalinti papildomus skliaustus su kodais
    isvalytas = re.sub(r'\s*\([^)]*[A-Z]{2,}[^)]*\)', '', isvalytas)
    return isvalytas.strip()


# =====================================================
# DUOMENŲ BAZĖS FUNKCIJOS
# =====================================================

def gauti_laukus(sb):
    res = sb.table("laukai").select("*").order("pavadinimas").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


def gauti_islaidas(sb, filtrai=None):
    query = sb.table("islaidos").select("*, laukai(pavadinimas, kultura, plotas_ha)")
    if filtrai:
        if filtrai.get("lauko_id"):
            query = query.eq("lauko_id", filtrai["lauko_id"])
        if filtrai.get("data_nuo"):
            query = query.gte("data", filtrai["data_nuo"])
        if filtrai.get("data_iki"):
            query = query.lte("data", filtrai["data_iki"])
    res = query.order("data").execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    if "laukai" in df.columns:
        laukai_info = df["laukai"].apply(pd.Series)
        laukai_info.columns = ["lauko_pavadinimas", "kultura", "plotas_ha_laukas"]
        df = pd.concat([df.drop(columns=["laukai"]), laukai_info], axis=1)
    return df


def gauti_sandeli(sb):
    res = sb.table("sandelis").select("*").order("produktas").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


def gauti_pajamas(sb):
    res = sb.table("pajamos").select("*, laukai(pavadinimas, kultura)").order("data").execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    if "laukai" in df.columns:
        laukai_info = df["laukai"].apply(pd.Series)
        laukai_info.columns = ["lauko_pavadinimas", "kultura"]
        df = pd.concat([df.drop(columns=["laukai"]), laukai_info], axis=1)
    return df


# =====================================================
# PDF SĄSKAITOS SKAITYMAS
# =====================================================

def nuskaityti_pdf_saskaita(failas):
    """Nuskaityti sąskaitos PDF ir ištraukti produktų lentelę."""
    produktai = []

    with pdfplumber.open(failas) as pdf:
        for puslapis in pdf.pages:
            lenteles = puslapis.extract_tables()
            for lentele in lenteles:
                if not lentele or len(lentele) < 2:
                    continue

                # Rasti antraštės eilutę
                antraste_idx = None
                for i, eilute in enumerate(lentele):
                    eilute_str = " ".join(str(cell or "").lower() for cell in eilute)
                    if any(kw in eilute_str for kw in ["prekė", "preke", "paslauga", "pavadinimas", "eil"]):
                        antraste_idx = i
                        break

                if antraste_idx is None:
                    # Bandyti pirmą eilutę kaip antraštę
                    antraste_idx = 0

                antraste = [str(cell or "").strip().lower() for cell in lentele[antraste_idx]]

                # Nustatyti stulpelių indeksus
                preke_idx = None
                vnt_idx = None
                kiekis_idx = None
                kaina_idx = None
                suma_idx = None

                for j, col in enumerate(antraste):
                    if any(kw in col for kw in ["prekė", "preke", "paslauga", "pavadinimas"]):
                        preke_idx = j
                    elif any(kw in col for kw in ["mato", "vnt", "matav"]):
                        vnt_idx = j
                    elif "kiekis" in col or "kiek" in col:
                        kiekis_idx = j
                    elif "kaina" in col and suma_idx is None:
                        kaina_idx = j
                    elif "suma" in col:
                        suma_idx = j

                if preke_idx is None:
                    continue

                # Nuskaityti duomenis
                for eilute in lentele[antraste_idx + 1:]:
                    if not eilute or len(eilute) <= preke_idx:
                        continue

                    preke = str(eilute[preke_idx] or "").strip()
                    if not preke or preke.lower() in ["", "suma", "viso", "iš viso", "pvm"]:
                        continue

                    # Patikrinti ar tai ne sumos eilutė
                    if any(kw in preke.lower() for kw in ["suma be pvm", "pvm", "viso", "iš viso", "mokėti"]):
                        continue

                    isvalytas_pav = isvalyti_produkto_pavadinima(preke)

                    def parsinti_skaiciu(val):
                        if val is None:
                            return 0.0
                        val_str = str(val).strip().replace(" ", "").replace(",", ".")
                        try:
                            return float(val_str)
                        except ValueError:
                            return 0.0

                    vnt = str(eilute[vnt_idx] or "").strip() if vnt_idx and vnt_idx < len(eilute) else "vnt"
                    kiekis = parsinti_skaiciu(eilute[kiekis_idx]) if kiekis_idx and kiekis_idx < len(eilute) else 0
                    kaina = parsinti_skaiciu(eilute[kaina_idx]) if kaina_idx and kaina_idx < len(eilute) else 0
                    suma = parsinti_skaiciu(eilute[suma_idx]) if suma_idx and suma_idx < len(eilute) else kiekis * kaina

                    rusis = nustatyti_rusi(isvalytas_pav)

                    produktai.append({
                        "produktas": isvalytas_pav,
                        "rusis": rusis,
                        "kiekis": kiekis,
                        "vienetas": vnt,
                        "kaina_uz_vnt_eur": kaina,
                        "bendra_verte": round(suma, 2)
                    })

    return produktai


# =====================================================
# INICIALIZACIJA
# =====================================================

if not SUPABASE_GALIMAS:
    st.error("❌ Neįdiegta `supabase` biblioteka. Pridėkite ją į requirements.txt")
    st.stop()

sb = gauti_supabase()

if sb is None:
    st.title("⚙️ Supabase konfigūracija")
    st.markdown("""
    ### Norint naudoti programą, reikia sukonfigūruoti Supabase duomenų bazę.

    **1. Sukurkite nemokamą Supabase projektą:**
    - Eikite į [supabase.com](https://supabase.com) → Start your project
    - Sukurkite naują projektą

    **2. Sukurkite lenteles:**
    - Supabase dashboarde eikite į **SQL Editor**
    - Paleiskite `setup.sql` turinį (rasite GitHub repo)

    **3. Pridėkite secrets į Streamlit Cloud:**
    - Streamlit Cloud → app nustatymai → **Secrets**
    - Įrašykite:

    ```toml
    SUPABASE_URL = "https://jūsų-projektas.supabase.co"
    SUPABASE_KEY = "jūsų-anon-key"
    ```

    **4. Perkraukite app** ir viskas veiks! 🎉

    > 💡 URL ir Key rasite: Supabase → Settings → API
    """)
    st.stop()


# =====================================================
# ŠONINĖ JUOSTA
# =====================================================

with st.sidebar:
    st.markdown("### 🌾 Ūkio skaičiuoklė")
    st.markdown("---")

    puslapis = st.radio(
        "Navigacija",
        [
            "📊 Suvestinė",
            "🗺️ Laukai",
            "📋 Išlaidos",
            "➕ Naujas darbas",
            "📦 Sandėlis",
            "💰 Pajamos",
            "📈 Pelningumas",
            "✏️ Redaguoti / Trinti",
            "📤 Eksportas",
        ],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Filtrai
    st.markdown("##### 🔍 Filtrai")

    laukai_df = gauti_laukus(sb)

    if not laukai_df.empty:
        lauku_options = {"Visi": None}
        for _, row in laukai_df.iterrows():
            lauku_options[f"{row['pavadinimas']} ({row['kultura']})"] = row["id"]
        pasirinktas_laukas = st.selectbox("Laukas", list(lauku_options.keys()))
    else:
        pasirinktas_laukas = "Visi"
        lauku_options = {"Visi": None}

    col1, col2 = st.columns(2)
    with col1:
        data_nuo = st.date_input("Nuo", value=date(2024, 1, 1), format="YYYY-MM-DD")
    with col2:
        data_iki = st.date_input("Iki", value=date(2026, 12, 31), format="YYYY-MM-DD")

    st.markdown("---")
    st.markdown(
        f"<div style='text-align:center;color:#999;font-size:12px;'>"
        f"Ūkio skaičiuoklė v3.1<br>© {datetime.now().year}</div>",
        unsafe_allow_html=True
    )

# Filtrai
filtrai = {}
if lauku_options.get(pasirinktas_laukas):
    filtrai["lauko_id"] = lauku_options[pasirinktas_laukas]
if data_nuo:
    filtrai["data_nuo"] = data_nuo.strftime("%Y-%m-%d")
if data_iki:
    filtrai["data_iki"] = data_iki.strftime("%Y-%m-%d")


# =====================================================
# 📊 SUVESTINĖ
# =====================================================

if puslapis == "📊 Suvestinė":
    st.title("📊 Suvestinė")

    df = gauti_islaidas(sb, filtrai)

    if df.empty:
        st.info("Nėra išlaidų duomenų. Pradėkite nuo laukų sukūrimo → tada pridėkite darbų.")
    else:
        bendra_suma = df["suma"].sum()
        bendras_plotas = laukai_df["plotas_ha"].sum() if not laukai_df.empty else 0
        kaina_ha = bendra_suma / bendras_plotas if bendras_plotas > 0 else 0
        irasu_sk = len(df)
        lauku_sk = laukai_df.shape[0] if not laukai_df.empty else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Bendra suma", f"{bendra_suma:,.2f} €")
        with col2:
            st.metric("🌾 Kaina/ha", f"{kaina_ha:,.2f} €/ha")
        with col3:
            st.metric("📝 Įrašų", irasu_sk)
        with col4:
            st.metric("🗺️ Laukų", lauku_sk)

        st.markdown("---")

        col_l, col_r = st.columns(2)

        with col_l:
            men_df = df.groupby("menuo")["suma"].sum().reset_index()
            fig1 = px.bar(men_df, x="menuo", y="suma",
                          title="Išlaidos pagal mėnesį",
                          labels={"menuo": "Mėnuo", "suma": "Suma, €"},
                          color_discrete_sequence=["#5b9bd5"])
            fig1.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                               xaxis_tickangle=-35)
            st.plotly_chart(fig1, use_container_width=True)

        with col_r:
            if "lauko_pavadinimas" in df.columns:
                lauk_df = df.groupby("lauko_pavadinimas")["suma"].sum().reset_index()
                fig2 = px.bar(lauk_df, x="lauko_pavadinimas", y="suma",
                              title="Išlaidos pagal lauką",
                              labels={"lauko_pavadinimas": "Laukas", "suma": "Suma, €"},
                              color_discrete_sequence=["#70ad47"])
                fig2.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                                   xaxis_tickangle=-35)
                st.plotly_chart(fig2, use_container_width=True)

        col_l2, col_r2 = st.columns(2)

        with col_l2:
            rusys_df = df.groupby("rusis")["suma"].sum().reset_index()
            fig3 = px.pie(rusys_df, values="suma", names="rusis",
                          title="Išlaidos pagal produkto rūšį",
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig3.update_layout(paper_bgcolor="white")
            st.plotly_chart(fig3, use_container_width=True)

        with col_r2:
            darbai_df = df.groupby("darbas")["suma"].sum().reset_index().sort_values("suma", ascending=False)
            fig4 = px.bar(darbai_df, x="darbas", y="suma",
                          title="Išlaidos pagal darbą",
                          labels={"darbas": "Darbas", "suma": "Suma, €"},
                          color_discrete_sequence=["#ed7d31"])
            fig4.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                               xaxis_tickangle=-35)
            st.plotly_chart(fig4, use_container_width=True)


# =====================================================
# 🗺️ LAUKAI
# =====================================================

elif puslapis == "🗺️ Laukai":
    st.title("🗺️ Mano laukai")

    tab_view, tab_add = st.tabs(["📋 Peržiūra", "➕ Pridėti lauką"])

    with tab_view:
        if laukai_df.empty:
            st.info("Dar nėra laukų. Pridėkite pirmąjį!")
        else:
            rodymo_df = laukai_df[["id", "pavadinimas", "plotas_ha", "kultura", "pastaba"]].copy()
            rodymo_df.columns = ["ID", "Pavadinimas", "Plotas (ha)", "Kultūra", "Pastaba"]
            st.dataframe(rodymo_df, use_container_width=True, hide_index=True)

            bendras_plotas = laukai_df["plotas_ha"].sum()
            st.info(f"**Viso laukų:** {len(laukai_df)} | **Bendras plotas:** {bendras_plotas:.2f} ha")

            st.markdown("---")
            st.markdown("##### 🗑️ Ištrinti lauką")
            lauko_trinimui = st.selectbox(
                "Pasirinkite lauką trynimui",
                laukai_df["id"].tolist(),
                format_func=lambda x: f"{laukai_df[laukai_df['id']==x].iloc[0]['pavadinimas']} ({laukai_df[laukai_df['id']==x].iloc[0]['plotas_ha']} ha)"
            )
            if st.button("🗑️ Ištrinti pasirinktą lauką", type="secondary"):
                sb.table("laukai").delete().eq("id", lauko_trinimui).execute()
                st.success("✅ Laukas ištrintas!")
                st.rerun()

    with tab_add:
        with st.form("naujas_laukas", clear_on_submit=True):
            st.markdown("##### Naujo lauko duomenys")
            col1, col2 = st.columns(2)
            with col1:
                l_pav = st.text_input("📌 Pavadinimas", placeholder="pvz. 1 laukas, Pamiškės")
                l_plotas = st.number_input("📐 Plotas (ha)", min_value=0.0, value=0.0, step=0.1)
            with col2:
                l_kultura = st.text_input("🌾 Kultūra", placeholder="pvz. Kviečiai žieminiai")
                l_pastaba = st.text_input("📝 Pastaba", placeholder="(neprivaloma)")

            pateikti = st.form_submit_button("✅ Pridėti lauką", use_container_width=True)

            if pateikti:
                if not l_pav or not l_kultura:
                    st.error("❌ Įveskite pavadinimą ir kultūrą!")
                else:
                    sb.table("laukai").insert({
                        "pavadinimas": l_pav,
                        "plotas_ha": l_plotas,
                        "kultura": l_kultura,
                        "pastaba": l_pastaba or ""
                    }).execute()
                    st.success(f"✅ Laukas '{l_pav}' pridėtas!")
                    st.rerun()


# =====================================================
# 📋 IŠLAIDOS (peržiūra)
# =====================================================

elif puslapis == "📋 Išlaidos":
    st.title("📋 Visos išlaidos")

    df = gauti_islaidas(sb, filtrai)

    if df.empty:
        st.info("Nėra įrašų.")
    else:
        rodymo_cols = ["data", "lauko_pavadinimas", "darbas", "produktas",
                       "rusis", "norma", "vienetas", "kaina_uz_vnt_eur",
                       "sunaudotas_kiekis", "suma", "pastaba"]
        existing = [c for c in rodymo_cols if c in df.columns]
        rodymo_df = df[existing].copy()
        rodymo_df.columns = [c.replace("_", " ").title() for c in existing]
        st.dataframe(rodymo_df, use_container_width=True, hide_index=True, height=500)
        st.info(f"**Įrašų:** {len(df)} | **Bendra suma:** {df['suma'].sum():,.2f} €")


# =====================================================
# ➕ NAUJAS DARBAS
# =====================================================

elif puslapis == "➕ Naujas darbas":
    st.title("➕ Naujas darbas")

    if laukai_df.empty:
        st.warning("⚠️ Pirma sukurkite bent vieną lauką (🗺️ Laukai)!")
    else:
        sand_df = gauti_sandeli(sb)

        if sand_df.empty:
            st.warning("⚠️ Sandėlis tuščias! Pridėkite produktų į sandėlį prieš registruojant darbus.")
            st.info("Eikite į 📦 Sandėlis → pridėkite produktų rankiniu būdu arba importuokite iš PDF sąskaitos.")
        else:
            with st.form("naujas_darbas", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)

                with col1:
                    i_data = st.date_input("📅 Data", value=date.today(), format="YYYY-MM-DD")
                    i_laukas = st.selectbox(
                        "🗺️ Laukas",
                        laukai_df["id"].tolist(),
                        format_func=lambda x: f"{laukai_df[laukai_df['id']==x].iloc[0]['pavadinimas']} – {laukai_df[laukai_df['id']==x].iloc[0]['kultura']} ({laukai_df[laukai_df['id']==x].iloc[0]['plotas_ha']} ha)"
                    )
                    i_darbas = st.text_input("🔧 Darbas", placeholder="pvz. Tręšimas, Purškimas, Sėja")

                with col2:
                    # Produktas iš sandėlio
                    produktu_options = sand_df["id"].tolist()
                    i_produktas_id = st.selectbox(
                        "🧪 Produktas (iš sandėlio)",
                        produktu_options,
                        format_func=lambda x: f"{sand_df[sand_df['id']==x].iloc[0]['produktas']} – {sand_df[sand_df['id']==x].iloc[0]['kiekis']:.1f} {sand_df[sand_df['id']==x].iloc[0]['vienetas']} sandėlyje"
                    )

                    # Auto-fill iš sandėlio
                    pasirinktas_prod = sand_df[sand_df["id"] == i_produktas_id].iloc[0]
                    st.caption(f"**Rūšis:** {pasirinktas_prod['rusis']} | **Vienetas:** {pasirinktas_prod['vienetas']} | **Kaina:** {pasirinktas_prod['kaina_uz_vnt_eur']:.2f} €/{pasirinktas_prod['vienetas']}")
                    st.caption(f"📦 **Sandėlyje likutis:** {pasirinktas_prod['kiekis']:.1f} {pasirinktas_prod['vienetas']}")

                    i_norma = st.number_input("⚖️ Norma (vnt/ha)", min_value=0.0, value=0.0, step=0.01, format="%.3f")

                with col3:
                    i_pastaba = st.text_input("📝 Pastaba", placeholder="(neprivaloma)")

                    # Skaičiavimas
                    laukas_info = laukai_df[laukai_df["id"] == i_laukas].iloc[0]
                    plotas = laukas_info["plotas_ha"]
                    sunaudota = plotas * i_norma
                    suma = sunaudota * pasirinktas_prod["kaina_uz_vnt_eur"]

                    if i_norma > 0:
                        st.markdown(f"""
                        **Skaičiavimas:**
                        - Plotas: {plotas} ha
                        - Norma: {i_norma} {pasirinktas_prod['vienetas']}/ha
                        - Sunaudota: **{sunaudota:.2f} {pasirinktas_prod['vienetas']}**
                        - Suma: **{suma:.2f} €**
                        """)

                        if sunaudota > pasirinktas_prod["kiekis"]:
                            st.error(f"⚠️ Nepakanka sandėlyje! Reikia {sunaudota:.1f}, yra {pasirinktas_prod['kiekis']:.1f} {pasirinktas_prod['vienetas']}")

                pateikti = st.form_submit_button("✅ Registruoti darbą", use_container_width=True)

                if pateikti:
                    if not i_darbas:
                        st.error("❌ Įveskite darbo pavadinimą!")
                    elif i_norma <= 0:
                        st.error("❌ Įveskite normą!")
                    else:
                        menuo = i_data.strftime("%Y-%m")

                        # Įrašyti išlaidą
                        sb.table("islaidos").insert({
                            "data": i_data.strftime("%Y-%m-%d"),
                            "menuo": menuo,
                            "lauko_id": int(i_laukas),
                            "darbas": i_darbas,
                            "produktas": pasirinktas_prod["produktas"],
                            "rusis": pasirinktas_prod["rusis"],
                            "norma": i_norma,
                            "vienetas": pasirinktas_prod["vienetas"],
                            "kaina_uz_vnt_eur": pasirinktas_prod["kaina_uz_vnt_eur"],
                            "sunaudotas_kiekis": round(sunaudota, 4),
                            "suma": round(suma, 2),
                            "pastaba": i_pastaba or ""
                        }).execute()

                        # Atnaujinti sandėlį (sumažinti kiekį)
                        naujas_kiekis = max(0, pasirinktas_prod["kiekis"] - sunaudota)
                        nauja_verte = naujas_kiekis * pasirinktas_prod["kaina_uz_vnt_eur"]
                        sb.table("sandelis").update({
                            "kiekis": round(naujas_kiekis, 4),
                            "bendra_verte": round(nauja_verte, 2)
                        }).eq("id", int(i_produktas_id)).execute()

                        st.success(f"✅ Darbas registruotas: {i_darbas} – {pasirinktas_prod['produktas']} – {suma:.2f} €")
                        st.info(f"📦 Sandėlyje liko: {naujas_kiekis:.1f} {pasirinktas_prod['vienetas']}")
                        st.balloons()


# =====================================================
# 📦 SANDĖLIS
# =====================================================

elif puslapis == "📦 Sandėlis":
    st.title("📦 Sandėlis")

    tab_view, tab_add, tab_pdf = st.tabs(["📋 Atsargos", "➕ Pridėti rankiniu", "📄 Importas iš PDF"])

    with tab_view:
        sand_df = gauti_sandeli(sb)
        if sand_df.empty:
            st.info("Sandėlis tuščias. Pridėkite produktų!")
        else:
            rodymo_df = sand_df[["id", "produktas", "rusis", "kiekis", "vienetas",
                                  "kaina_uz_vnt_eur", "bendra_verte", "data_prideta", "pastaba"]].copy()
            rodymo_df.columns = ["ID", "Produktas", "Rūšis", "Kiekis", "Vnt.",
                                  "Kaina €/vnt", "Vertė €", "Data pridėta", "Pastaba"]
            st.dataframe(rodymo_df, use_container_width=True, hide_index=True)

            bendra_verte = sand_df["bendra_verte"].sum()
            st.info(f"**Viso produktų:** {len(sand_df)} | **Bendra vertė:** {bendra_verte:,.2f} €")

            st.markdown("---")
            trinti_id = st.selectbox(
                "Pasirinkite produktą trynimui",
                sand_df["id"].tolist(),
                format_func=lambda x: f"{sand_df[sand_df['id']==x].iloc[0]['produktas']} – {sand_df[sand_df['id']==x].iloc[0]['kiekis']} {sand_df[sand_df['id']==x].iloc[0]['vienetas']}"
            )
            if st.button("🗑️ Ištrinti produktą"):
                sb.table("sandelis").delete().eq("id", trinti_id).execute()
                st.success("✅ Produktas ištrintas!")
                st.rerun()

    with tab_add:
        with st.form("naujas_produktas", clear_on_submit=True):
            st.markdown("##### Naujas produktas sandėlyje")
            col1, col2 = st.columns(2)
            with col1:
                s_produktas = st.text_input("🧪 Produktas", placeholder="pvz. Amonio salietra")
                s_rusis = st.selectbox("🏷️ Rūšis", ["trąšos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "sėklos", "kita"])
                s_kiekis = st.number_input("📦 Kiekis", min_value=0.0, value=0.0, step=0.1)
            with col2:
                s_vienetas = st.selectbox("📏 Vienetas", ["kg", "l", "vnt", "t"])
                s_kaina = st.number_input("💶 Kaina už vnt (€)", min_value=0.0, value=0.0, step=0.01)
                s_pastaba = st.text_input("📝 Pastaba", placeholder="(neprivaloma)")

            pateikti = st.form_submit_button("✅ Pridėti į sandėlį", use_container_width=True)

            if pateikti:
                if not s_produktas:
                    st.error("❌ Įveskite produkto pavadinimą!")
                else:
                    bendra_verte = s_kiekis * s_kaina
                    sb.table("sandelis").insert({
                        "produktas": s_produktas,
                        "rusis": s_rusis,
                        "kiekis": s_kiekis,
                        "vienetas": s_vienetas,
                        "kaina_uz_vnt_eur": s_kaina,
                        "bendra_verte": round(bendra_verte, 2),
                        "data_prideta": date.today().strftime("%Y-%m-%d"),
                        "pastaba": s_pastaba or ""
                    }).execute()
                    st.success(f"✅ Produktas '{s_produktas}' pridėtas! Vertė: {bendra_verte:.2f} €")
                    st.rerun()

    with tab_pdf:
        st.markdown("##### 📄 Importuoti produktus iš PDF sąskaitos")
        st.markdown("Įkelkite sąskaitą PDF formatu – programa automatiškai atpažins produktus, kiekius ir kainas.")

        if not PDF_GALIMAS:
            st.error("❌ Reikia `pdfplumber` bibliotekos. Pridėkite ją į requirements.txt")
        else:
            ikeltas_pdf = st.file_uploader("📎 Pasirinkite PDF sąskaitą", type=["pdf"])

            if ikeltas_pdf is not None:
                with st.spinner("🔍 Nuskaitoma sąskaita..."):
                    produktai = nuskaityti_pdf_saskaita(ikeltas_pdf)

                if not produktai:
                    st.warning("⚠️ Nepavyko rasti produktų lentelės PDF faile. Patikrinkite ar sąskaita turi lentelę su prekėmis.")
                else:
                    st.success(f"✅ Rasta **{len(produktai)}** produktų!")

                    # Konvertuoti į DataFrame redagavimui
                    edit_df = pd.DataFrame(produktai)
                    edit_df.columns = ["Produktas", "Rūšis", "Kiekis", "Vienetas", "Kaina €/vnt", "Vertė €"]

                    st.markdown("##### ✏️ Patikrinkite ir redaguokite duomenis:")
                    redaguotas_df = st.data_editor(
                        edit_df,
                        use_container_width=True,
                        num_rows="dynamic",
                        column_config={
                            "Rūšis": st.column_config.SelectboxColumn(
                                options=["trąšos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "sėklos", "kita"]
                            ),
                            "Vienetas": st.column_config.SelectboxColumn(
                                options=["kg", "l", "vnt", "t"]
                            ),
                            "Kiekis": st.column_config.NumberColumn(format="%.3f"),
                            "Kaina €/vnt": st.column_config.NumberColumn(format="%.2f"),
                            "Vertė €": st.column_config.NumberColumn(format="%.2f"),
                        },
                        hide_index=True
                    )

                    bendra_verte = redaguotas_df["Vertė €"].sum()
                    st.info(f"**Viso produktų:** {len(redaguotas_df)} | **Bendra vertė:** {bendra_verte:,.2f} €")

                    if st.button("📦 Pridėti visus į sandėlį", type="primary", use_container_width=True):
                        prideta = 0
                        for _, row in redaguotas_df.iterrows():
                            if row["Produktas"] and row["Produktas"].strip():
                                sb.table("sandelis").insert({
                                    "produktas": row["Produktas"].strip(),
                                    "rusis": row["Rūšis"],
                                    "kiekis": float(row["Kiekis"]),
                                    "vienetas": row["Vienetas"],
                                    "kaina_uz_vnt_eur": float(row["Kaina €/vnt"]),
                                    "bendra_verte": round(float(row["Vertė €"]), 2),
                                    "data_prideta": date.today().strftime("%Y-%m-%d"),
                                    "pastaba": f"Importuota iš PDF: {ikeltas_pdf.name}"
                                }).execute()
                                prideta += 1
                        st.success(f"✅ Pridėta **{prideta}** produktų į sandėlį!")
                        st.balloons()
                        st.rerun()


# =====================================================
# 💰 PAJAMOS
# =====================================================

elif puslapis == "💰 Pajamos":
    st.title("💰 Pajamos")

    tab_add, tab_view = st.tabs(["➕ Registruoti pajamas", "📋 Peržiūra"])

    with tab_add:
        if laukai_df.empty:
            st.warning("⚠️ Pirma sukurkite laukus!")
        else:
            with st.form("pajamos_forma", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    p_data = st.date_input("📅 Pardavimo data", value=date.today())
                    p_laukas = st.selectbox(
                        "🗺️ Laukas",
                        laukai_df["id"].tolist(),
                        format_func=lambda x: f"{laukai_df[laukai_df['id']==x].iloc[0]['pavadinimas']} – {laukai_df[laukai_df['id']==x].iloc[0]['kultura']} ({laukai_df[laukai_df['id']==x].iloc[0]['plotas_ha']} ha)"
                    )
                with col2:
                    p_derlius = st.number_input("🌾 Derlius (t/ha)", min_value=0.0, value=0.0, step=0.1)
                    p_kaina = st.number_input("💶 Pardavimo kaina (€/t)", min_value=0.0, value=0.0, step=1.0)
                p_pastaba = st.text_input("📝 Pastaba", placeholder="(neprivaloma)")

                pateikti = st.form_submit_button("✅ Registruoti pajamas", use_container_width=True)

                if pateikti:
                    laukas_row = laukai_df[laukai_df["id"] == p_laukas].iloc[0]
                    bendras_derlius = laukas_row["plotas_ha"] * p_derlius
                    pajamu_suma = bendras_derlius * p_kaina

                    sb.table("pajamos").insert({
                        "data": p_data.strftime("%Y-%m-%d"),
                        "lauko_id": int(p_laukas),
                        "derlius_t_ha": p_derlius,
                        "bendras_derlius_t": round(bendras_derlius, 2),
                        "pardavimo_kaina_eur_t": p_kaina,
                        "pajamu_suma": round(pajamu_suma, 2),
                        "pastaba": p_pastaba or ""
                    }).execute()
                    st.success(f"✅ Pajamos: {pajamu_suma:,.2f} € ({bendras_derlius:.1f} t × {p_kaina:.0f} €/t)")

    with tab_view:
        paj_df = gauti_pajamas(sb)
        if paj_df.empty:
            st.info("Pajamų dar neregistruota.")
        else:
            rodymo_cols = ["data", "lauko_pavadinimas", "kultura", "derlius_t_ha",
                           "bendras_derlius_t", "pardavimo_kaina_eur_t", "pajamu_suma", "pastaba"]
            existing = [c for c in rodymo_cols if c in paj_df.columns]
            st.dataframe(paj_df[existing], use_container_width=True, hide_index=True)
            st.metric("💰 Visos pajamos", f"{paj_df['pajamu_suma'].sum():,.2f} €")


# =====================================================
# 📈 PELNINGUMAS
# =====================================================

elif puslapis == "📈 Pelningumas":
    st.title("📈 Pelningumas")

    isl_df = gauti_islaidas(sb, filtrai)
    paj_df = gauti_pajamas(sb)

    visos_islaidos = isl_df["suma"].sum() if not isl_df.empty else 0
    visos_pajamos = paj_df["pajamu_suma"].sum() if not paj_df.empty else 0
    pelnas = visos_pajamos - visos_islaidos
    marza = (pelnas / visos_pajamos * 100) if visos_pajamos > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💸 Išlaidos", f"{visos_islaidos:,.2f} €")
    with col2:
        st.metric("💰 Pajamos", f"{visos_pajamos:,.2f} €")
    with col3:
        st.metric("📊 Pelnas", f"{pelnas:,.2f} €", delta=f"{pelnas:,.2f} €")
    with col4:
        st.metric("📉 Marža", f"{marza:.1f}%")

    st.markdown("---")

    if not isl_df.empty or not paj_df.empty:
        fig = go.Figure()
        if not isl_df.empty:
            isl_men = isl_df.groupby("menuo")["suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=isl_men["menuo"], y=isl_men["suma"],
                                 name="Išlaidos", marker_color="#e74c3c"))
        if not paj_df.empty:
            paj_df["menuo"] = pd.to_datetime(paj_df["data"]).dt.strftime("%Y-%m")
            paj_men = paj_df.groupby("menuo")["pajamu_suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=paj_men["menuo"], y=paj_men["pajamu_suma"],
                                 name="Pajamos", marker_color="#2ecc71"))
        fig.update_layout(title="Išlaidos vs. Pajamos pagal mėnesį",
                          barmode="group", plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

        if not isl_df.empty and "lauko_pavadinimas" in isl_df.columns:
            st.subheader("🗺️ Pelningumas pagal lauką")
            isl_lauk = isl_df.groupby("lauko_pavadinimas")["suma"].sum().reset_index()
            isl_lauk.columns = ["Laukas", "Išlaidos"]

            if not paj_df.empty and "lauko_pavadinimas" in paj_df.columns:
                paj_lauk = paj_df.groupby("lauko_pavadinimas")["pajamu_suma"].sum().reset_index()
                paj_lauk.columns = ["Laukas", "Pajamos"]
                pelnas_df = isl_lauk.merge(paj_lauk, on="Laukas", how="outer").fillna(0)
            else:
                pelnas_df = isl_lauk.copy()
                pelnas_df["Pajamos"] = 0

            pelnas_df["Pelnas"] = pelnas_df["Pajamos"] - pelnas_df["Išlaidos"]
            st.dataframe(pelnas_df, use_container_width=True, hide_index=True)
    else:
        st.info("Pridėkite išlaidų ir pajamų duomenų.")


# =====================================================
# ✏️ REDAGUOTI / TRINTI
# =====================================================

elif puslapis == "✏️ Redaguoti / Trinti":
    st.title("✏️ Redaguoti arba ištrinti išlaidas")

    df = gauti_islaidas(sb)

    if df.empty:
        st.info("Nėra įrašų.")
    else:
        iraso_id = st.selectbox(
            "Pasirinkite įrašą",
            df["id"].tolist(),
            format_func=lambda x: f"#{x} | {df[df['id']==x].iloc[0]['data']} | {df[df['id']==x].iloc[0].get('lauko_pavadinimas', '')} | {df[df['id']==x].iloc[0]['produktas']} | {df[df['id']==x].iloc[0]['suma']:.2f} €"
        )

        irasas = df[df["id"] == iraso_id].iloc[0]

        tab_edit, tab_delete = st.tabs(["✏️ Redaguoti", "🗑️ Ištrinti"])

        with tab_edit:
            with st.form("redaguoti"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    try:
                        r_data_val = datetime.strptime(irasas["data"], "%Y-%m-%d").date()
                    except:
                        r_data_val = date.today()
                    r_data = st.date_input("Data", value=r_data_val)
                    if not laukai_df.empty:
                        lauku_ids = laukai_df["id"].tolist()
                        current_idx = lauku_ids.index(irasas["lauko_id"]) if irasas["lauko_id"] in lauku_ids else 0
                        r_laukas = st.selectbox("Laukas", lauku_ids, index=current_idx,
                            format_func=lambda x: laukai_df[laukai_df['id']==x].iloc[0]['pavadinimas'])
                    else:
                        r_laukas = irasas["lauko_id"]
                    r_darbas = st.text_input("Darbas", value=irasas["darbas"])
                with col2:
                    r_produktas = st.text_input("Produktas", value=irasas["produktas"])
                    r_rusis = st.text_input("Rūšis", value=irasas["rusis"])
                    r_norma = st.number_input("Norma", value=float(irasas["norma"]), step=0.01, format="%.3f")
                with col3:
                    r_vienetas = st.text_input("Vienetas", value=irasas["vienetas"])
                    r_kaina = st.number_input("Kaina €/vnt", value=float(irasas["kaina_uz_vnt_eur"]), step=0.01)
                    r_pastaba = st.text_input("Pastaba", value=irasas.get("pastaba", "") or "")

                issaugoti = st.form_submit_button("💾 Išsaugoti", use_container_width=True)

                if issaugoti:
                    laukas_row = laukai_df[laukai_df["id"] == r_laukas].iloc[0]
                    r_sunaudota = laukas_row["plotas_ha"] * r_norma
                    r_suma = r_sunaudota * r_kaina

                    sb.table("islaidos").update({
                        "data": r_data.strftime("%Y-%m-%d"),
                        "menuo": r_data.strftime("%Y-%m"),
                        "lauko_id": int(r_laukas),
                        "darbas": r_darbas,
                        "produktas": r_produktas,
                        "rusis": r_rusis,
                        "norma": r_norma,
                        "vienetas": r_vienetas,
                        "kaina_uz_vnt_eur": r_kaina,
                        "sunaudotas_kiekis": round(r_sunaudota, 4),
                        "suma": round(r_suma, 2),
                        "pastaba": r_pastaba
                    }).eq("id", iraso_id).execute()
                    st.success("✅ Įrašas atnaujintas!")
                    st.rerun()

        with tab_delete:
            st.warning(f"⚠️ Ar tikrai norite ištrinti įrašą #{iraso_id}?")
            st.write(f"**{irasas['data']}** | {irasas['produktas']} | {irasas['suma']:.2f} €")
            if st.button("🗑️ Taip, ištrinti", type="primary"):
                sb.table("islaidos").delete().eq("id", iraso_id).execute()
                st.success("✅ Įrašas ištrintas.")
                st.rerun()


# =====================================================
# 📤 EKSPORTAS
# =====================================================

elif puslapis == "📤 Eksportas":
    st.title("📤 Eksportas")

    df = gauti_islaidas(sb)

    if df.empty:
        st.info("Nėra duomenų eksportui.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, sep=";")
            st.download_button(
                "📄 Parsisiųsti CSV",
                data=csv_buffer.getvalue(),
                file_name=f"ukio_islaidos_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col2:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Išlaidos", index=False)

                suvestine = pd.DataFrame({
                    "Rodiklis": ["Bendra suma €", "Įrašų skaičius", "Laukų skaičius"],
                    "Reikšmė": [
                        f"{df['suma'].sum():.2f}",
                        str(len(df)),
                        str(laukai_df.shape[0]) if not laukai_df.empty else "0"
                    ]
                })
                suvestine.to_excel(writer, sheet_name="Suvestinė", index=False)

                sand_df = gauti_sandeli(sb)
                if not sand_df.empty:
                    sand_df.to_excel(writer, sheet_name="Sandėlis", index=False)

            st.download_button(
                "📊 Parsisiųsti Excel",
                data=excel_buffer.getvalue(),
                file_name=f"ukio_ataskaita_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
