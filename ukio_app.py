import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import io
import os
import re

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


def gauti_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


# =============================================================================
# KONFIG + CSS
# =============================================================================

st.set_page_config(page_title="Ukio skaiciuokle", page_icon="leaf",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #f5f5f5; }
    section[data-testid="stSidebar"] {
        background-color: #fafafa; border-right: 1px solid #e8e8e8;
    }
    h1 { color: #222; font-weight: 600; font-size: 1.6rem !important; }
    h2, h3 { color: #333; font-weight: 500; }
    div[data-testid="stMetric"] {
        background-color: #fff; border: 1px solid #e8e8e8;
        border-radius: 8px; padding: 14px 18px;
    }
    div[data-testid="stMetric"] label { color: #888; font-size: 13px; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: #222; font-weight: 600; }
    .stButton > button { border-radius: 6px; font-weight: 500; }
    .stTabs [data-baseweb="tab"] { color: #666; }
    .stTabs [aria-selected="true"] { color: #333; font-weight: 500; }
    [data-testid="stForm"] {
        background-color: #fff; border: 1px solid #e8e8e8;
        border-radius: 8px; padding: 20px;
    }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

COLORS = ["#5a7d9a", "#7da87b", "#c4956a", "#b07aa1", "#9c9c9c", "#d4a574"]

RUSIS_MAP = {
    "herbicidas": ["mustang","axial","derby","corum","dash","pantera","butisan",
                   "herold","lentipur","sekator","biathlon","husar","stomp","starane"],
    "fungicidas": ["prosaro","osiris","adexar","fandango","skyway","input","navura",
                   "caramba","tilt","amistar","acanto","falcon","opus","signum"],
    "insekticidas": ["karate","decis","fastac","fury","biscaya","proteus","mavrik","pirimor"],
    "reguliatorius": ["moddus","ccc","terpal","medax","cerone","prodax","manipulator"],
    "trasos": ["npk","amonio","kas","karbamidas","urea","saletra","superfosfat","kalio","dap","map"],
    "seklos": ["sekla","seed"]
}


def nustatyti_rusi(pav):
    p = pav.lower()
    for r, kw in RUSIS_MAP.items():
        for k in kw:
            if k in p:
                return r
    return "kita"


def isvalyti_pav(pav):
    s = re.sub(r"\s*\([A-Z0-9]+\)", "", str(pav))
    s = re.sub(r"\s*\([^)]*[A-Z]{2,}[^)]*\)", "", s)
    return s.strip()


# =============================================================================
# DB FUNKCIJOS
# =============================================================================

def gauti_laukus(sb):
    r = sb.table("laukai").select("*").order("pavadinimas").execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

def gauti_islaidas(sb, f=None):
    q = sb.table("islaidos").select("*, laukai(pavadinimas, kultura, plotas_ha)")
    if f:
        if f.get("lauko_id"): q = q.eq("lauko_id", f["lauko_id"])
        if f.get("nuo"): q = q.gte("data", f["nuo"])
        if f.get("iki"): q = q.lte("data", f["iki"])
    r = q.order("data").execute()
    if not r.data: return pd.DataFrame()
    df = pd.DataFrame(r.data)
    if "laukai" in df.columns:
        li = df["laukai"].apply(pd.Series)
        li.columns = ["lauko_pavadinimas", "kultura", "plotas_ha_laukas"]
        df = pd.concat([df.drop(columns=["laukai"]), li], axis=1)
    return df

def gauti_sandeli(sb):
    r = sb.table("sandelis").select("*").order("produktas").execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

def gauti_pajamas(sb):
    r = sb.table("pajamos").select("*, laukai(pavadinimas, kultura)").order("data").execute()
    if not r.data: return pd.DataFrame()
    df = pd.DataFrame(r.data)
    if "laukai" in df.columns:
        li = df["laukai"].apply(pd.Series)
        li.columns = ["lauko_pavadinimas", "kultura"]
        df = pd.concat([df.drop(columns=["laukai"]), li], axis=1)
    return df


# =============================================================================
# PDF SKAITYMAS
# =============================================================================

def nuskaityti_pdf(failas):
    produktai = []
    with pdfplumber.open(failas) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2: continue
                hdr_idx = 0
                for i, row in enumerate(table):
                    txt = " ".join(str(c or "").lower() for c in row)
                    if any(k in txt for k in ["preke", "paslauga", "pavadinimas"]):
                        hdr_idx = i; break

                hdr = [str(c or "").strip().lower() for c in table[hdr_idx]]
                pi = vi = ki = kai = si = None
                for j, c in enumerate(hdr):
                    if any(k in c for k in ["preke", "paslauga", "pavadinimas"]): pi = j
                    elif any(k in c for k in ["mato", "vnt", "matav"]): vi = j
                    elif "kiekis" in c or "kiek" in c: ki = j
                    elif "kaina" in c and si is None: kai = j
                    elif "suma" in c: si = j
                if pi is None: continue

                for row in table[hdr_idx+1:]:
                    if not row or len(row) <= pi: continue
                    preke = str(row[pi] or "").strip()
                    if not preke: continue
                    if any(k in preke.lower() for k in ["suma be","pvm","viso","moketi","i\u0161 viso",""]): continue

                    def num(v):
                        if v is None: return 0.0
                        try: return float(str(v).strip().replace(" ","").replace(",","."))
                        except: return 0.0

                    pav = isvalyti_pav(preke)
                    if not pav or pav.lower() == "none": continue
                    vnt = str(row[vi] or "").strip() if vi and vi < len(row) else "vnt"
                    kiekis = num(row[ki]) if ki and ki < len(row) else 0
                    kaina = num(row[kai]) if kai and kai < len(row) else 0
                    suma = num(row[si]) if si and si < len(row) else kiekis * kaina

                    produktai.append({
                        "Produktas": pav,
                        "Rusis": nustatyti_rusi(pav),
                        "Kiekis": kiekis,
                        "Vienetas": vnt if vnt and vnt.lower() != "none" else "vnt",
                        "Kaina": kaina,
                        "Verte": round(suma, 2)
                    })
    # Filtruoti tuscias eilutes
    produktai = [p for p in produktai if p["Produktas"] and p["Produktas"].lower() not in ["none", "", "nan"]]
    return produktai


# =============================================================================
# INIT
# =============================================================================

if not SUPABASE_OK:
    st.error("Neidiegta supabase biblioteka.")
    st.stop()

sb = gauti_supabase()
if sb is None:
    st.title("Konfig\u016bracija")
    st.markdown("""
### Reikia sukonfiguruoti Supabase.

1. [supabase.com](https://supabase.com) - sukurkite projekta
2. SQL Editor - paleiskite setup.sql
3. Streamlit Cloud - Settings - Secrets:

```toml
SUPABASE_URL = "https://jusu-projektas.supabase.co"
SUPABASE_KEY = "jusu-anon-key"
```
4. Perkraukite app.
    """)
    st.stop()


# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.markdown("#### Ukio skaiciuokle")
    st.markdown("---")
    puslapis = st.radio("Nav", [
        "Suvestine", "Laukai", "Islaidos", "Naujas darbas",
        "Sandelis", "Pajamos", "Pelningumas", "Redaguoti", "Eksportas"
    ], label_visibility="collapsed")
    st.markdown("---")
    st.markdown("###### Filtrai")

    laukai_df = gauti_laukus(sb)
    lauku_opt = {"Visi": None}
    if not laukai_df.empty:
        for _, r in laukai_df.iterrows():
            lauku_opt[r["pavadinimas"] + " (" + r["kultura"] + ")"] = r["id"]
    pas_laukas = st.selectbox("Laukas", list(lauku_opt.keys()))

    c1, c2 = st.columns(2)
    with c1: d_nuo = st.date_input("Nuo", value=date(2024,1,1), format="YYYY-MM-DD")
    with c2: d_iki = st.date_input("Iki", value=date(2026,12,31), format="YYYY-MM-DD")

    st.markdown("---")
    st.caption("v3.3")

filtrai = {}
if lauku_opt.get(pas_laukas): filtrai["lauko_id"] = lauku_opt[pas_laukas]
if d_nuo: filtrai["nuo"] = d_nuo.strftime("%Y-%m-%d")
if d_iki: filtrai["iki"] = d_iki.strftime("%Y-%m-%d")


# =============================================================================
# SUVESTINE
# =============================================================================

if puslapis == "Suvestine":
    st.title("Suvestine")
    df = gauti_islaidas(sb, filtrai)
    if df.empty:
        st.info("Nera islaidu duomenu.")
    else:
        bs = df["suma"].sum()
        bp = laukai_df["plotas_ha"].sum() if not laukai_df.empty else 0
        kh = bs / bp if bp > 0 else 0

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Bendra suma", f"{bs:,.2f} EUR")
        c2.metric("Kaina / ha", f"{kh:,.2f} EUR")
        c3.metric("Irasu", len(df))
        c4.metric("Lauku", len(laukai_df) if not laukai_df.empty else 0)

        st.markdown("---")
        cl, cr = st.columns(2)
        with cl:
            md = df.groupby("menuo")["suma"].sum().reset_index()
            f1 = px.bar(md, x="menuo", y="suma", title="Pagal menesi",
                        labels={"menuo":"Menuo","suma":"Suma EUR"}, color_discrete_sequence=[COLORS[0]])
            f1.update_layout(plot_bgcolor="white", paper_bgcolor="white", xaxis_tickangle=-35, title_font_size=14)
            st.plotly_chart(f1, use_container_width=True)
        with cr:
            if "lauko_pavadinimas" in df.columns:
                ld = df.groupby("lauko_pavadinimas")["suma"].sum().reset_index()
                f2 = px.bar(ld, x="lauko_pavadinimas", y="suma", title="Pagal lauka",
                            labels={"lauko_pavadinimas":"Laukas","suma":"Suma EUR"}, color_discrete_sequence=[COLORS[1]])
                f2.update_layout(plot_bgcolor="white", paper_bgcolor="white", xaxis_tickangle=-35, title_font_size=14)
                st.plotly_chart(f2, use_container_width=True)
        cl2, cr2 = st.columns(2)
        with cl2:
            rd = df.groupby("rusis")["suma"].sum().reset_index()
            f3 = px.pie(rd, values="suma", names="rusis", title="Pagal rusi", color_discrete_sequence=COLORS)
            f3.update_layout(paper_bgcolor="white", title_font_size=14)
            st.plotly_chart(f3, use_container_width=True)
        with cr2:
            dd = df.groupby("darbas")["suma"].sum().reset_index().sort_values("suma", ascending=False)
            f4 = px.bar(dd, x="darbas", y="suma", title="Pagal darba",
                        labels={"darbas":"Darbas","suma":"Suma EUR"}, color_discrete_sequence=[COLORS[2]])
            f4.update_layout(plot_bgcolor="white", paper_bgcolor="white", xaxis_tickangle=-35, title_font_size=14)
            st.plotly_chart(f4, use_container_width=True)


# =============================================================================
# LAUKAI
# =============================================================================

elif puslapis == "Laukai":
    st.title("Laukai")
    t1, t2 = st.tabs(["Perziura", "Prideti lauka"])

    with t1:
        if laukai_df.empty:
            st.info("Nera lauku.")
        else:
            el = laukai_df[["id","pavadinimas","plotas_ha","kultura","pastaba"]].copy()
            el.insert(0, "X", False)
            st.caption("Redaguokite tiesiai lenteleje.")
            red = st.data_editor(el, use_container_width=True, hide_index=True,
                column_config={
                    "X": st.column_config.CheckboxColumn("X", default=False, width="small"),
                    "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "pavadinimas": st.column_config.TextColumn("Pavadinimas"),
                    "plotas_ha": st.column_config.NumberColumn("Plotas ha", format="%.2f"),
                    "kultura": st.column_config.TextColumn("Kultura"),
                    "pastaba": st.column_config.TextColumn("Pastaba"),
                }, disabled=["id"])

            st.caption("Lauku: " + str(len(red)) + " | Plotas: " + str(round(red["plotas_ha"].sum(), 2)) + " ha")

            cs, cd = st.columns(2)
            with cs:
                if st.button("Issaugoti lauku pakeitimus", use_container_width=True):
                    n = 0
                    for i, row in red.iterrows():
                        o = el.iloc[i]
                        changed = any(str(row[c]) != str(o[c]) for c in ["pavadinimas","plotas_ha","kultura","pastaba"])
                        if changed:
                            sb.table("laukai").update({
                                "pavadinimas": row["pavadinimas"],
                                "plotas_ha": float(row["plotas_ha"]),
                                "kultura": row["kultura"],
                                "pastaba": row.get("pastaba","") or ""
                            }).eq("id", int(row["id"])).execute()
                            n += 1
                    if n: st.success("Atnaujinta: " + str(n)); st.rerun()
                    else: st.info("Pakeitimu nerasta.")
            with cd:
                tr = red[red["X"] == True]
                if st.button("Istrinti pazymetus (" + str(len(tr)) + ")", use_container_width=True, disabled=len(tr)==0, key="dl"):
                    for _, r in tr.iterrows(): sb.table("laukai").delete().eq("id", int(r["id"])).execute()
                    st.success("Istrinta: " + str(len(tr))); st.rerun()

    with t2:
        with st.form("nl", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                lp = st.text_input("Pavadinimas", placeholder="pvz. 1 laukas")
                lh = st.number_input("Plotas (ha)", min_value=0.0, value=0.0, step=0.1)
            with c2:
                lk = st.text_input("Kultura", placeholder="pvz. Kvieciai zieminiai")
                lpast = st.text_input("Pastaba", placeholder="(neprivaloma)")
            if st.form_submit_button("Prideti", use_container_width=True):
                if not lp or not lk: st.error("Iveskite pavadinima ir kultura.")
                else:
                    sb.table("laukai").insert({"pavadinimas":lp,"plotas_ha":lh,"kultura":lk,"pastaba":lpast or ""}).execute()
                    st.success("Laukas pridetas: " + lp); st.rerun()


# =============================================================================
# ISLAIDOS
# =============================================================================

elif puslapis == "Islaidos":
    st.title("Islaidos")
    df = gauti_islaidas(sb, filtrai)
    if df.empty: st.info("Nera irasu.")
    else:
        cols = ["data","lauko_pavadinimas","darbas","produktas","rusis","norma","vienetas","kaina_uz_vnt_eur","sunaudotas_kiekis","suma","pastaba"]
        ex = [c for c in cols if c in df.columns]
        rd = df[ex].copy(); rd.columns = [c.replace("_"," ").title() for c in ex]
        st.dataframe(rd, use_container_width=True, hide_index=True, height=500)
        st.caption("Irasu: " + str(len(df)) + " | Suma: " + str(round(df["suma"].sum(), 2)) + " EUR")


# =============================================================================
# NAUJAS DARBAS
# =============================================================================

elif puslapis == "Naujas darbas":
    st.title("Naujas darbas")
    if laukai_df.empty: st.warning("Pirma sukurkite lauku.")
    else:
        sdf = gauti_sandeli(sb)
        if sdf.empty: st.warning("Sandelis tuscias. Pridekite produktu.")
        else:
            with st.form("nd", clear_on_submit=True):
                c1,c2,c3 = st.columns(3)
                with c1:
                    idata = st.date_input("Data", value=date.today(), format="YYYY-MM-DD")
                    ilaukas = st.selectbox("Laukas", laukai_df["id"].tolist(),
                        format_func=lambda x: laukai_df[laukai_df["id"]==x].iloc[0]["pavadinimas"] + " - " + laukai_df[laukai_df["id"]==x].iloc[0]["kultura"] + " (" + str(laukai_df[laukai_df["id"]==x].iloc[0]["plotas_ha"]) + " ha)")
                    idarbas = st.text_input("Darbas", placeholder="pvz. Tresimas, Purskimas")
                with c2:
                    iprod = st.selectbox("Produktas", sdf["id"].tolist(),
                        format_func=lambda x: sdf[sdf["id"]==x].iloc[0]["produktas"] + " (" + str(sdf[sdf["id"]==x].iloc[0]["kiekis"]) + " " + sdf[sdf["id"]==x].iloc[0]["vienetas"] + ")")
                    pr = sdf[sdf["id"]==iprod].iloc[0]
                    st.caption("Rusis: " + pr["rusis"] + " | Kaina: " + str(pr["kaina_uz_vnt_eur"]) + " EUR/" + pr["vienetas"] + " | Likutis: " + str(pr["kiekis"]) + " " + pr["vienetas"])
                    inorma = st.number_input("Norma (vnt/ha)", min_value=0.0, value=0.0, step=0.01, format="%.3f")
                with c3:
                    ipast = st.text_input("Pastaba", placeholder="(neprivaloma)")
                    li = laukai_df[laukai_df["id"]==ilaukas].iloc[0]
                    plotas = li["plotas_ha"]
                    sun = plotas * inorma
                    suma = sun * pr["kaina_uz_vnt_eur"]
                    if inorma > 0:
                        st.markdown("**" + str(plotas) + " ha x " + str(inorma) + " = " + str(round(sun,2)) + " " + pr["vienetas"] + " | Suma: " + str(round(suma,2)) + " EUR**")
                        if sun > pr["kiekis"]:
                            st.error("Nepakanka sandelyje! Reikia " + str(round(sun,1)) + ", yra " + str(pr["kiekis"]))

                if st.form_submit_button("Registruoti darba", use_container_width=True):
                    if not idarbas: st.error("Iveskite darba.")
                    elif inorma <= 0: st.error("Iveskite norma.")
                    else:
                        sb.table("islaidos").insert({
                            "data": idata.strftime("%Y-%m-%d"), "menuo": idata.strftime("%Y-%m"),
                            "lauko_id": int(ilaukas), "darbas": idarbas,
                            "produktas": pr["produktas"], "rusis": pr["rusis"],
                            "norma": inorma, "vienetas": pr["vienetas"],
                            "kaina_uz_vnt_eur": pr["kaina_uz_vnt_eur"],
                            "sunaudotas_kiekis": round(sun,4), "suma": round(suma,2),
                            "pastaba": ipast or ""
                        }).execute()
                        nk = max(0, pr["kiekis"] - sun)
                        nv = nk * pr["kaina_uz_vnt_eur"]
                        sb.table("sandelis").update({"kiekis":round(nk,4),"bendra_verte":round(nv,2)}).eq("id",int(iprod)).execute()
                        st.success("Darbas registruotas: " + idarbas + " - " + pr["produktas"] + " - " + str(round(suma,2)) + " EUR. Sandelyje liko: " + str(round(nk,1)) + " " + pr["vienetas"])


# =============================================================================
# SANDELIS
# =============================================================================

elif puslapis == "Sandelis":
    st.title("Sandelis")
    t1, t2, t3 = st.tabs(["Atsargos", "Prideti rankiniu", "Importas is PDF"])

    with t1:
        sdf = gauti_sandeli(sb)
        if sdf.empty: st.info("Sandelis tuscias.")
        else:
            es = sdf[["id","produktas","rusis","kiekis","vienetas","kaina_uz_vnt_eur","bendra_verte","pastaba"]].copy()
            es.insert(0, "X", False)
            st.caption("Redaguokite tiesiai lenteleje.")
            rs = st.data_editor(es, use_container_width=True, hide_index=True,
                column_config={
                    "X": st.column_config.CheckboxColumn("X", default=False, width="small"),
                    "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "produktas": st.column_config.TextColumn("Produktas"),
                    "rusis": st.column_config.SelectboxColumn("Rusis", options=["trasos","herbicidas","fungicidas","insekticidas","reguliatorius","seklos","kita"]),
                    "kiekis": st.column_config.NumberColumn("Kiekis", format="%.2f"),
                    "vienetas": st.column_config.SelectboxColumn("Vnt", options=["kg","l","vnt","t"]),
                    "kaina_uz_vnt_eur": st.column_config.NumberColumn("Kaina EUR", format="%.2f"),
                    "bendra_verte": st.column_config.NumberColumn("Verte EUR", format="%.2f", disabled=True),
                    "pastaba": st.column_config.TextColumn("Pastaba"),
                }, disabled=["id","bendra_verte"])

            st.caption("Produktu: " + str(len(rs)) + " | Verte: " + str(round(rs["bendra_verte"].sum(),2)) + " EUR")

            cs, cd = st.columns(2)
            with cs:
                if st.button("Issaugoti sandelio pakeitimus", use_container_width=True):
                    n = 0
                    for i, row in rs.iterrows():
                        o = es.iloc[i]
                        changed = any(str(row[c]) != str(o[c]) for c in ["produktas","rusis","kiekis","vienetas","kaina_uz_vnt_eur","pastaba"])
                        if changed:
                            nv = float(row["kiekis"]) * float(row["kaina_uz_vnt_eur"])
                            sb.table("sandelis").update({
                                "produktas":row["produktas"],"rusis":row["rusis"],
                                "kiekis":float(row["kiekis"]),"vienetas":row["vienetas"],
                                "kaina_uz_vnt_eur":float(row["kaina_uz_vnt_eur"]),
                                "bendra_verte":round(nv,2),"pastaba":row.get("pastaba","") or ""
                            }).eq("id",int(row["id"])).execute()
                            n += 1
                    if n: st.success("Atnaujinta: " + str(n)); st.rerun()
                    else: st.info("Pakeitimu nerasta.")
            with cd:
                tr = rs[rs["X"]==True]
                if st.button("Istrinti pazymetus (" + str(len(tr)) + ")", use_container_width=True, disabled=len(tr)==0, key="ds"):
                    for _, r in tr.iterrows(): sb.table("sandelis").delete().eq("id",int(r["id"])).execute()
                    st.success("Istrinta: " + str(len(tr))); st.rerun()

    with t2:
        with st.form("sp", clear_on_submit=True):
            c1,c2 = st.columns(2)
            with c1:
                sp = st.text_input("Produktas", placeholder="pvz. Amonio salietra")
                sr = st.selectbox("Rusis", ["trasos","herbicidas","fungicidas","insekticidas","reguliatorius","seklos","kita"])
                sk = st.number_input("Kiekis", min_value=0.0, value=0.0, step=0.1)
            with c2:
                sv = st.selectbox("Vienetas", ["kg","l","vnt","t"])
                skn = st.number_input("Kaina uz vnt (EUR)", min_value=0.0, value=0.0, step=0.01)
                spast = st.text_input("Pastaba", placeholder="(neprivaloma)")
            if st.form_submit_button("Prideti", use_container_width=True):
                if not sp: st.error("Iveskite produkto pavadinima.")
                else:
                    bv = sk * skn
                    sb.table("sandelis").insert({
                        "produktas":sp,"rusis":sr,"kiekis":sk,"vienetas":sv,
                        "kaina_uz_vnt_eur":skn,"bendra_verte":round(bv,2),
                        "data_prideta":date.today().strftime("%Y-%m-%d"),"pastaba":spast or ""
                    }).execute()
                    st.success("Produktas pridetas: " + sp); st.rerun()

    with t3:
        st.markdown("###### Importas is PDF saskaitos")
        st.caption("Ikelkite saskaita - programa atpazins produktus. Galite istrinti nereikalingas eilutes prieš pridedant.")

        if not PDF_OK: st.error("Reikia pdfplumber bibliotekos.")
        else:
            pdf_file = st.file_uploader("Pasirinkite PDF", type=["pdf"])
            if pdf_file is not None:
                with st.spinner("Nuskaitoma..."):
                    produktai = nuskaityti_pdf(pdf_file)

                if not produktai:
                    st.warning("Nepavyko rasti produktu lenteles.")
                else:
                    st.success("Rasta produktu: " + str(len(produktai)))
                    edf = pd.DataFrame(produktai)

                    st.markdown("###### Patikrinkite duomenis (istrinkite nereikalingas eilutes su - mygtuku):")
                    red_pdf = st.data_editor(edf, use_container_width=True, hide_index=True,
                        num_rows="dynamic",
                        column_config={
                            "Produktas": st.column_config.TextColumn("Produktas"),
                            "Rusis": st.column_config.SelectboxColumn("Rusis",
                                options=["trasos","herbicidas","fungicidas","insekticidas","reguliatorius","seklos","kita"]),
                            "Kiekis": st.column_config.NumberColumn("Kiekis", format="%.3f"),
                            "Vienetas": st.column_config.SelectboxColumn("Vienetas", options=["kg","l","vnt","t"]),
                            "Kaina": st.column_config.NumberColumn("Kaina EUR/vnt", format="%.2f"),
                            "Verte": st.column_config.NumberColumn("Verte EUR", format="%.2f"),
                        })

                    # Filtruoti tuscias/none eilutes
                    valid = red_pdf[red_pdf["Produktas"].notna() & (red_pdf["Produktas"].astype(str).str.strip() != "") & (red_pdf["Produktas"].astype(str).str.lower() != "none")]
                    st.caption("Produktu bus prideta: " + str(len(valid)) + " | Verte: " + str(round(valid["Verte"].sum(),2)) + " EUR")

                    if st.button("Prideti i sandeli", type="primary", use_container_width=True):
                        prideta = 0; atnaujinta = 0
                        for _, row in valid.iterrows():
                            pav = str(row["Produktas"]).strip()
                            if not pav or pav.lower() in ["none","nan",""]: continue
                            esamas = sb.table("sandelis").select("*").eq("produktas", pav).execute()
                            if esamas.data:
                                e = esamas.data[0]
                                nk = e["kiekis"] + float(row["Kiekis"])
                                nv = nk * e["kaina_uz_vnt_eur"]
                                sb.table("sandelis").update({"kiekis":round(nk,4),"bendra_verte":round(nv,2)}).eq("id",e["id"]).execute()
                                atnaujinta += 1
                            else:
                                sb.table("sandelis").insert({
                                    "produktas":pav, "rusis":row["Rusis"],
                                    "kiekis":float(row["Kiekis"]), "vienetas":row["Vienetas"],
                                    "kaina_uz_vnt_eur":float(row["Kaina"]),
                                    "bendra_verte":round(float(row["Verte"]),2),
                                    "data_prideta":date.today().strftime("%Y-%m-%d"),
                                    "pastaba": "Is: " + pdf_file.name
                                }).execute()
                                prideta += 1
                        st.success("Nauju: " + str(prideta) + ", atnaujinta: " + str(atnaujinta))
                        st.rerun()


# =============================================================================
# PAJAMOS
# =============================================================================

elif puslapis == "Pajamos":
    st.title("Pajamos")
    t1, t2 = st.tabs(["Registruoti", "Perziura"])

    with t1:
        if laukai_df.empty: st.warning("Pirma sukurkite lauku.")
        else:
            with st.form("pf", clear_on_submit=True):
                c1,c2 = st.columns(2)
                with c1:
                    pd_ = st.date_input("Pardavimo data", value=date.today())
                    pl = st.selectbox("Laukas", laukai_df["id"].tolist(),
                        format_func=lambda x: laukai_df[laukai_df["id"]==x].iloc[0]["pavadinimas"] + " (" + str(laukai_df[laukai_df["id"]==x].iloc[0]["plotas_ha"]) + " ha)")
                with c2:
                    pder = st.number_input("Derlius (t/ha)", min_value=0.0, value=0.0, step=0.1)
                    pkaina = st.number_input("Pardavimo kaina (EUR/t)", min_value=0.0, value=0.0, step=1.0)
                ppast = st.text_input("Pastaba", placeholder="(neprivaloma)")
                if st.form_submit_button("Registruoti", use_container_width=True):
                    lr = laukai_df[laukai_df["id"]==pl].iloc[0]
                    bd = lr["plotas_ha"] * pder; ps = bd * pkaina
                    sb.table("pajamos").insert({
                        "data":pd_.strftime("%Y-%m-%d"),"lauko_id":int(pl),
                        "derlius_t_ha":pder,"bendras_derlius_t":round(bd,2),
                        "pardavimo_kaina_eur_t":pkaina,"pajamu_suma":round(ps,2),
                        "pastaba":ppast or ""
                    }).execute()
                    st.success("Pajamos: " + str(round(ps,2)) + " EUR")

    with t2:
        pdf2 = gauti_pajamas(sb)
        if pdf2.empty: st.info("Pajamu nera.")
        else:
            cols = ["data","lauko_pavadinimas","kultura","derlius_t_ha","bendras_derlius_t","pardavimo_kaina_eur_t","pajamu_suma","pastaba"]
            ex = [c for c in cols if c in pdf2.columns]
            st.dataframe(pdf2[ex], use_container_width=True, hide_index=True)
            st.caption("Visos pajamos: " + str(round(pdf2["pajamu_suma"].sum(),2)) + " EUR")


# =============================================================================
# PELNINGUMAS
# =============================================================================

elif puslapis == "Pelningumas":
    st.title("Pelningumas")
    idf = gauti_islaidas(sb, filtrai); pdf3 = gauti_pajamas(sb)
    vi = idf["suma"].sum() if not idf.empty else 0
    vp = pdf3["pajamu_suma"].sum() if not pdf3.empty else 0
    pel = vp - vi; mar = (pel/vp*100) if vp > 0 else 0

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Islaidos", str(round(vi,2)) + " EUR")
    c2.metric("Pajamos", str(round(vp,2)) + " EUR")
    c3.metric("Pelnas", str(round(pel,2)) + " EUR", delta=str(round(pel,2)) + " EUR")
    c4.metric("Marza", str(round(mar,1)) + "%")

    st.markdown("---")
    if not idf.empty or not pdf3.empty:
        fig = go.Figure()
        if not idf.empty:
            im = idf.groupby("menuo")["suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=im["menuo"],y=im["suma"],name="Islaidos",marker_color="#c0392b"))
        if not pdf3.empty:
            pdf3["menuo"] = pd.to_datetime(pdf3["data"]).dt.strftime("%Y-%m")
            pm = pdf3.groupby("menuo")["pajamu_suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=pm["menuo"],y=pm["pajamu_suma"],name="Pajamos",marker_color="#27ae60"))
        fig.update_layout(title="Islaidos ir pajamos", barmode="group", plot_bgcolor="white",paper_bgcolor="white",title_font_size=14)
        st.plotly_chart(fig, use_container_width=True)

        if not idf.empty and "lauko_pavadinimas" in idf.columns:
            st.markdown("##### Pagal lauka")
            il = idf.groupby("lauko_pavadinimas")["suma"].sum().reset_index(); il.columns=["Laukas","Islaidos"]
            if not pdf3.empty and "lauko_pavadinimas" in pdf3.columns:
                plk = pdf3.groupby("lauko_pavadinimas")["pajamu_suma"].sum().reset_index(); plk.columns=["Laukas","Pajamos"]
                peld = il.merge(plk,on="Laukas",how="outer").fillna(0)
            else: peld = il.copy(); peld["Pajamos"] = 0
            peld["Pelnas"] = peld["Pajamos"] - peld["Islaidos"]
            st.dataframe(peld, use_container_width=True, hide_index=True)
    else: st.info("Pridekite duomenu.")


# =============================================================================
# REDAGUOTI
# =============================================================================

elif puslapis == "Redaguoti":
    st.title("Redaguoti islaidas")
    df = gauti_islaidas(sb)
    if df.empty: st.info("Nera irasu.")
    else:
        ecols = ["id","data","lauko_pavadinimas","darbas","produktas","rusis","norma","vienetas","kaina_uz_vnt_eur","pastaba"]
        ex = [c for c in ecols if c in df.columns]
        edf = df[ex].copy(); edf.insert(0, "X", False)
        st.caption("Redaguokite tiesiai lenteleje. Pazymekite X kuriuos istrinti.")

        red = st.data_editor(edf, use_container_width=True, hide_index=True, height=500,
            column_config={
                "X": st.column_config.CheckboxColumn("X", default=False, width="small"),
                "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "data": st.column_config.TextColumn("Data"),
                "lauko_pavadinimas": st.column_config.TextColumn("Laukas", disabled=True),
                "darbas": st.column_config.TextColumn("Darbas"),
                "produktas": st.column_config.TextColumn("Produktas"),
                "rusis": st.column_config.SelectboxColumn("Rusis",
                    options=["trasos","herbicidas","fungicidas","insekticidas","reguliatorius","seklos","kita"]),
                "norma": st.column_config.NumberColumn("Norma", format="%.3f"),
                "vienetas": st.column_config.SelectboxColumn("Vnt", options=["kg","l","vnt","t"]),
                "kaina_uz_vnt_eur": st.column_config.NumberColumn("Kaina EUR", format="%.2f"),
                "pastaba": st.column_config.TextColumn("Pastaba"),
            }, disabled=["id","lauko_pavadinimas"])

        cs, cd = st.columns(2)
        with cs:
            if st.button("Issaugoti pakeitimus", use_container_width=True):
                n = 0
                for i, row in red.iterrows():
                    o = edf.iloc[i]
                    changed = any(str(row[c]) != str(o[c]) for c in ["data","darbas","produktas","rusis","norma","vienetas","kaina_uz_vnt_eur","pastaba"])
                    if changed:
                        rid = int(row["id"])
                        orig = df[df["id"]==rid].iloc[0]
                        lid = orig["lauko_id"]
                        lr = laukai_df[laukai_df["id"]==lid]
                        plotas = lr.iloc[0]["plotas_ha"] if not lr.empty else 0
                        norma = float(row["norma"]); kaina = float(row["kaina_uz_vnt_eur"])
                        sun = plotas * norma; suma = sun * kaina
                        ds = str(row["data"]); menuo = ds[:7] if len(ds)>=7 else ""
                        sb.table("islaidos").update({
                            "data":ds,"menuo":menuo,"darbas":row["darbas"],
                            "produktas":row["produktas"],"rusis":row["rusis"],
                            "norma":norma,"vienetas":row["vienetas"],
                            "kaina_uz_vnt_eur":kaina,"sunaudotas_kiekis":round(sun,4),
                            "suma":round(suma,2),"pastaba":row.get("pastaba","") or ""
                        }).eq("id",rid).execute()
                        n += 1
                if n: st.success("Atnaujinta: " + str(n)); st.rerun()
                else: st.info("Pakeitimu nerasta.")
        with cd:
            tr = red[red["X"]==True]
            if st.button("Istrinti pazymetus (" + str(len(tr)) + ")", use_container_width=True, disabled=len(tr)==0, key="di"):
                for _, r in tr.iterrows(): sb.table("islaidos").delete().eq("id",int(r["id"])).execute()
                st.success("Istrinta: " + str(len(tr))); st.rerun()


# =============================================================================
# EKSPORTAS
# =============================================================================

elif puslapis == "Eksportas":
    st.title("Eksportas")
    df = gauti_islaidas(sb)
    if df.empty: st.info("Nera duomenu.")
    else:
        c1,c2 = st.columns(2)
        with c1:
            buf = io.StringIO(); df.to_csv(buf, index=False, sep=";")
            st.download_button("Parsiusti CSV", data=buf.getvalue(),
                file_name="ukio_islaidos_" + datetime.now().strftime("%Y%m%d") + ".csv",
                mime="text/csv", use_container_width=True)
        with c2:
            buf2 = io.BytesIO()
            with pd.ExcelWriter(buf2, engine="openpyxl") as w:
                df.to_excel(w, sheet_name="Islaidos", index=False)
                suv = pd.DataFrame({"Rodiklis":["Bendra suma","Irasu","Lauku"],
                    "Reiksme":[str(round(df["suma"].sum(),2)),str(len(df)),str(len(laukai_df)) if not laukai_df.empty else "0"]})
                suv.to_excel(w, sheet_name="Suvestine", index=False)
                sdf = gauti_sandeli(sb)
                if not sdf.empty: sdf.to_excel(w, sheet_name="Sandelis", index=False)
            st.download_button("Parsiusti Excel", data=buf2.getvalue(),
                file_name="ukio_ataskaita_" + datetime.now().strftime("%Y%m%d") + ".xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
