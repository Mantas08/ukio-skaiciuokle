import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import os
import io
import csv

# =====================================================
# KONFIGŪRACIJA
# =====================================================

st.set_page_config(
    page_title="🌾 Ūkio išlaidų skaičiuoklė",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FAILAS = "ukio_duomenys.db"
CSV_FAILAS = "kvieciai_15ha_duomenys.csv"


# =====================================================
# DUOMENŲ BAZĖ (SQLite)
# =====================================================

def gauti_prisijungima():
    """Sukurti arba gauti SQLite prisijungimą."""
    conn = sqlite3.connect(DB_FAILAS)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def sukurti_lenteles(conn):
    """Sukurti duomenų bazės lenteles, jei neegzistuoja."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS islaidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            menuo TEXT,
            kultura TEXT NOT NULL,
            plotas_ha REAL NOT NULL,
            darbas TEXT NOT NULL,
            produktas TEXT NOT NULL,
            rusis TEXT NOT NULL,
            norma REAL NOT NULL,
            vienetas TEXT NOT NULL,
            kaina_uz_vnt_eur REAL NOT NULL,
            sunaudotas_kiekis REAL,
            suma REAL,
            pastaba TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pajamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            kultura TEXT NOT NULL,
            plotas_ha REAL NOT NULL,
            derlius_t_ha REAL NOT NULL,
            bendras_derlius_t REAL,
            pardavimo_kaina_eur_t REAL NOT NULL,
            pajamu_suma REAL,
            pastaba TEXT DEFAULT ''
        )
    """)

    conn.commit()


def skaicius(reiksme):
    """Konvertuoti tekstą į skaičių."""
    if reiksme is None or str(reiksme).strip() == "":
        return 0.0
    return float(str(reiksme).strip().replace(",", "."))


def importuoti_is_csv(conn, csv_failas):
    """Importuoti duomenis iš CSV failo į SQLite."""
    if not os.path.exists(csv_failas):
        return 0

    with open(csv_failas, "r", encoding="utf-8-sig", newline="") as f:
        tekstas = f.read()

    if not tekstas.strip():
        return 0

    pirma_eilute = tekstas.splitlines()[0]
    if ";" in pirma_eilute:
        skirtukas = ";"
    elif "\t" in pirma_eilute:
        skirtukas = "\t"
    else:
        skirtukas = ","

    importuota = 0
    with open(csv_failas, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=skirtukas)

        privalomi = ["data", "kultura", "plotas_ha", "darbas", "produktas",
                     "rusis", "norma", "vienetas", "kaina_uz_vnt_eur", "pastaba"]

        if reader.fieldnames is None:
            return 0

        trukstami = [s for s in privalomi if s not in reader.fieldnames]
        if trukstami:
            st.error(f"CSV faile trūksta stulpelių: {', '.join(trukstami)}")
            return 0

        for eilute in reader:
            data = eilute["data"].strip()
            plotas_ha = skaicius(eilute["plotas_ha"])
            norma = skaicius(eilute["norma"])
            kaina = skaicius(eilute["kaina_uz_vnt_eur"])
            sunaudota = plotas_ha * norma
            suma = sunaudota * kaina

            # Nustatyti mėnesį
            galimi_formatai = ["%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%d/%m/%Y", "%d/%m/%y"]
            menuo = ""
            for fmt in galimi_formatai:
                try:
                    menuo = datetime.strptime(data, fmt).strftime("%Y-%m")
                    break
                except ValueError:
                    pass

            conn.execute("""
                INSERT INTO islaidos (data, menuo, kultura, plotas_ha, darbas, produktas,
                    rusis, norma, vienetas, kaina_uz_vnt_eur, sunaudotas_kiekis, suma, pastaba)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data, menuo, eilute["kultura"], plotas_ha, eilute["darbas"],
                  eilute["produktas"], eilute["rusis"], norma, eilute["vienetas"],
                  kaina, sunaudota, suma, eilute["pastaba"]))
            importuota += 1

    conn.commit()
    return importuota


def gauti_islaidas(conn, filtrai=None):
    """Gauti visas išlaidas su filtrais."""
    uzklausa = "SELECT * FROM islaidos WHERE 1=1"
    parametrai = []

    if filtrai:
        if filtrai.get("kultura"):
            uzklausa += " AND kultura = ?"
            parametrai.append(filtrai["kultura"])
        if filtrai.get("darbas"):
            uzklausa += " AND darbas = ?"
            parametrai.append(filtrai["darbas"])
        if filtrai.get("data_nuo"):
            uzklausa += " AND data >= ?"
            parametrai.append(filtrai["data_nuo"])
        if filtrai.get("data_iki"):
            uzklausa += " AND data <= ?"
            parametrai.append(filtrai["data_iki"])

    uzklausa += " ORDER BY data"
    return pd.read_sql_query(uzklausa, conn, params=parametrai)


def gauti_pajamas(conn, kultura=None):
    """Gauti visas pajamų duomenis."""
    if kultura:
        return pd.read_sql_query("SELECT * FROM pajamos WHERE kultura = ? ORDER BY data", conn, params=[kultura])
    return pd.read_sql_query("SELECT * FROM pajamos ORDER BY data", conn)


def gauti_unikalias_reiksmes(conn, stulpelis):
    """Gauti unikalias reikšmes iš stulpelio."""
    df = pd.read_sql_query(f"SELECT DISTINCT {stulpelis} FROM islaidos ORDER BY {stulpelis}", conn)
    return df[stulpelis].tolist()


# =====================================================
# INICIALIZACIJA
# =====================================================

conn = gauti_prisijungima()
sukurti_lenteles(conn)

# Importuoti CSV jei DB tuščia
irasu_sk = pd.read_sql_query("SELECT COUNT(*) as cnt FROM islaidos", conn).iloc[0]["cnt"]
if irasu_sk == 0 and os.path.exists(CSV_FAILAS):
    importuota = importuoti_is_csv(conn, CSV_FAILAS)
    if importuota > 0:
        st.toast(f"✅ Importuota {importuota} įrašų iš CSV", icon="📥")


# =====================================================
# ŠONINĖ JUOSTA (SIDEBAR)
# =====================================================

with st.sidebar:
    st.image("https://img.icons8.com/emoji/96/sheaf-of-rice.png", width=60)
    st.title("🌾 Ūkio skaičiuoklė")
    st.markdown("---")

    puslapis = st.radio(
        "📂 Navigacija",
        [
            "📊 Suvestinė",
            "📋 Visi įrašai",
            "➕ Naujas įrašas",
            "✏️ Redaguoti / Trinti",
            "💰 Pajamos",
            "📈 Pelningumas",
            "📥 Importas / Eksportas",
        ],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Filtrai
    st.subheader("🔍 Filtrai")

    kulturos = gauti_unikalias_reiksmes(conn, "kultura")
    pasirinkta_kultura = st.selectbox("Kultūra", ["Visos"] + kulturos)

    darbai = gauti_unikalias_reiksmes(conn, "darbas")
    pasirinktas_darbas = st.selectbox("Darbas", ["Visi"] + darbai)

    col1, col2 = st.columns(2)
    with col1:
        data_nuo = st.date_input("Nuo", value=date(2024, 1, 1), format="YYYY-MM-DD")
    with col2:
        data_iki = st.date_input("Iki", value=date(2026, 12, 31), format="YYYY-MM-DD")

# Paruošti filtrus
filtrai = {}
if pasirinkta_kultura != "Visos":
    filtrai["kultura"] = pasirinkta_kultura
if pasirinktas_darbas != "Visi":
    filtrai["darbas"] = pasirinktas_darbas
if data_nuo:
    filtrai["data_nuo"] = data_nuo.strftime("%Y-%m-%d")
if data_iki:
    filtrai["data_iki"] = data_iki.strftime("%Y-%m-%d")


# =====================================================
# 📊 SUVESTINĖ (DASHBOARD)
# =====================================================

if puslapis == "📊 Suvestinė":
    st.title("📊 Ūkio išlaidų suvestinė")

    df = gauti_islaidas(conn, filtrai)

    if df.empty:
        st.warning("Nėra duomenų pagal pasirinktus filtrus.")
    else:
        # KPI kortelės
        bendra_suma = df["suma"].sum()
        plotas_ha = df["plotas_ha"].iloc[0] if len(df) > 0 else 0
        kaina_ha = bendra_suma / plotas_ha if plotas_ha > 0 else 0
        irasu_skaicius = len(df)
        kulturu_sk = df["kultura"].nunique()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("💰 Bendra suma", f"{bendra_suma:,.2f} €")
        with col2:
            st.metric("🌾 Kaina/ha", f"{kaina_ha:,.2f} €/ha")
        with col3:
            st.metric("📝 Įrašų skaičius", irasu_skaicius)
        with col4:
            st.metric("🌿 Kultūrų skaičius", kulturu_sk)

        st.markdown("---")

        # Grafikai
        col_left, col_right = st.columns(2)

        with col_left:
            # Išlaidos pagal mėnesį
            menesiai_df = df.groupby("menuo")["suma"].sum().reset_index()
            fig1 = px.bar(
                menesiai_df, x="menuo", y="suma",
                title="📅 Išlaidos pagal mėnesį",
                labels={"menuo": "Mėnuo", "suma": "Suma, €"},
                color_discrete_sequence=["#4472C4"]
            )
            fig1.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig1, use_container_width=True)

        with col_right:
            # Išlaidos pagal darbą
            darbai_df = df.groupby("darbas")["suma"].sum().reset_index().sort_values("suma", ascending=False)
            fig2 = px.bar(
                darbai_df, x="darbas", y="suma",
                title="🔧 Išlaidos pagal darbą",
                labels={"darbas": "Darbas", "suma": "Suma, €"},
                color_discrete_sequence=["#ED7D31"]
            )
            fig2.update_layout(xaxis_tickangle=-35)
            st.plotly_chart(fig2, use_container_width=True)

        col_left2, col_right2 = st.columns(2)

        with col_left2:
            # Išlaidos pagal rūšį (skritulinė)
            rusys_df = df.groupby("rusis")["suma"].sum().reset_index()
            fig3 = px.pie(
                rusys_df, values="suma", names="rusis",
                title="🏷️ Išlaidos pagal produkto rūšį",
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            st.plotly_chart(fig3, use_container_width=True)

        with col_right2:
            # Sunaudoti kiekiai pagal produktą
            prod_df = df.groupby(["produktas", "vienetas"])["sunaudotas_kiekis"].sum().reset_index()
            prod_df["label"] = prod_df["produktas"] + " (" + prod_df["vienetas"] + ")"
            fig4 = px.bar(
                prod_df.sort_values("sunaudotas_kiekis", ascending=True),
                x="sunaudotas_kiekis", y="label",
                title="📦 Sunaudoti kiekiai pagal produktą",
                labels={"sunaudotas_kiekis": "Kiekis", "label": "Produktas"},
                orientation="h",
                color_discrete_sequence=["#70AD47"]
            )
            st.plotly_chart(fig4, use_container_width=True)


# =====================================================
# 📋 VISI ĮRAŠAI
# =====================================================

elif puslapis == "📋 Visi įrašai":
    st.title("📋 Visi išlaidų įrašai")

    df = gauti_islaidas(conn, filtrai)

    if df.empty:
        st.info("Nėra įrašų.")
    else:
        # Formatuoti
        rodymo_df = df[[
            "id", "data", "kultura", "plotas_ha", "darbas", "produktas",
            "rusis", "norma", "vienetas", "kaina_uz_vnt_eur",
            "sunaudotas_kiekis", "suma", "pastaba"
        ]].copy()
        rodymo_df.columns = [
            "ID", "Data", "Kultūra", "Plotas (ha)", "Darbas", "Produktas",
            "Rūšis", "Norma", "Vienetas", "Kaina €/vnt",
            "Sunaudota", "Suma €", "Pastaba"
        ]

        st.dataframe(rodymo_df, use_container_width=True, height=500)
        st.info(f"Iš viso: **{len(df)}** įrašų | Bendra suma: **{df['suma'].sum():,.2f} €**")


# =====================================================
# ➕ NAUJAS ĮRAŠAS
# =====================================================

elif puslapis == "➕ Naujas įrašas":
    st.title("➕ Pridėti naują įrašą")

    with st.form("naujas_irasas", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data = st.date_input("📅 Data", value=date.today(), format="YYYY-MM-DD")
            kultura = st.text_input("🌾 Kultūra", placeholder="pvz. Kviečiai žieminiai")
            plotas_ha = st.number_input("📐 Plotas (ha)", min_value=0.0, value=15.0, step=0.1)
        with col2:
            darbas = st.text_input("🔧 Darbas", placeholder="pvz. Tręšimas")
            produktas = st.text_input("🧪 Produktas", placeholder="pvz. Amonio salietra")
            rusis = st.selectbox("🏷️ Rūšis", ["trąšos", "herbicidas", "fungicidas", "insekticidas", "reguliatorius", "kita"])
        with col3:
            norma = st.number_input("⚖️ Norma (vnt/ha)", min_value=0.0, value=0.0, step=0.01, format="%.3f")
            vienetas = st.selectbox("📏 Vienetas", ["kg", "l", "vnt"])
            kaina = st.number_input("💶 Kaina už vnt (€)", min_value=0.0, value=0.0, step=0.01)

        pastaba = st.text_input("📝 Pastaba", placeholder="(neprivaloma)")

        pateikti = st.form_submit_button("✅ Pridėti įrašą", use_container_width=True)

        if pateikti:
            if not kultura or not darbas or not produktas:
                st.error("❌ Užpildykite privalomus laukus: Kultūra, Darbas, Produktas")
            else:
                data_str = data.strftime("%Y-%m-%d")
                menuo = data.strftime("%Y-%m")
                sunaudota = plotas_ha * norma
                suma = sunaudota * kaina

                conn.execute("""
                    INSERT INTO islaidos (data, menuo, kultura, plotas_ha, darbas, produktas,
                        rusis, norma, vienetas, kaina_uz_vnt_eur, sunaudotas_kiekis, suma, pastaba)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data_str, menuo, kultura, plotas_ha, darbas, produktas,
                      rusis, norma, vienetas, kaina, sunaudota, suma, pastaba))
                conn.commit()
                st.success(f"✅ Įrašas pridėtas: {produktas} – {suma:.2f} €")
                st.balloons()


# =====================================================
# ✏️ REDAGUOTI / TRINTI
# =====================================================

elif puslapis == "✏️ Redaguoti / Trinti":
    st.title("✏️ Redaguoti arba ištrinti įrašą")

    df = gauti_islaidas(conn)

    if df.empty:
        st.info("Nėra įrašų.")
    else:
        iraso_id = st.selectbox(
            "Pasirinkite įrašą",
            df["id"].tolist(),
            format_func=lambda x: f"#{x} | {df[df['id']==x].iloc[0]['data']} | {df[df['id']==x].iloc[0]['produktas']} | {df[df['id']==x].iloc[0]['suma']:.2f} €"
        )

        irasas = df[df["id"] == iraso_id].iloc[0]

        tab_edit, tab_delete = st.tabs(["✏️ Redaguoti", "🗑️ Ištrinti"])

        with tab_edit:
            with st.form("redaguoti_forma"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    r_data = st.date_input("Data", value=datetime.strptime(irasas["data"], "%Y-%m-%d").date() if irasas["data"] else date.today())
                    r_kultura = st.text_input("Kultūra", value=irasas["kultura"])
                    r_plotas = st.number_input("Plotas (ha)", value=float(irasas["plotas_ha"]), step=0.1)
                with col2:
                    r_darbas = st.text_input("Darbas", value=irasas["darbas"])
                    r_produktas = st.text_input("Produktas", value=irasas["produktas"])
                    r_rusis = st.text_input("Rūšis", value=irasas["rusis"])
                with col3:
                    r_norma = st.number_input("Norma", value=float(irasas["norma"]), step=0.01, format="%.3f")
                    r_vienetas = st.text_input("Vienetas", value=irasas["vienetas"])
                    r_kaina = st.number_input("Kaina €/vnt", value=float(irasas["kaina_uz_vnt_eur"]), step=0.01)

                r_pastaba = st.text_input("Pastaba", value=irasas["pastaba"] or "")

                issaugoti = st.form_submit_button("💾 Išsaugoti pakeitimus", use_container_width=True)

                if issaugoti:
                    r_data_str = r_data.strftime("%Y-%m-%d")
                    r_menuo = r_data.strftime("%Y-%m")
                    r_sunaudota = r_plotas * r_norma
                    r_suma = r_sunaudota * r_kaina

                    conn.execute("""
                        UPDATE islaidos SET
                            data=?, menuo=?, kultura=?, plotas_ha=?, darbas=?, produktas=?,
                            rusis=?, norma=?, vienetas=?, kaina_uz_vnt_eur=?,
                            sunaudotas_kiekis=?, suma=?, pastaba=?
                        WHERE id=?
                    """, (r_data_str, r_menuo, r_kultura, r_plotas, r_darbas, r_produktas,
                          r_rusis, r_norma, r_vienetas, r_kaina,
                          r_sunaudota, r_suma, r_pastaba, iraso_id))
                    conn.commit()
                    st.success("✅ Įrašas atnaujintas!")
                    st.rerun()

        with tab_delete:
            st.warning(f"⚠️ Ar tikrai norite ištrinti įrašą #{iraso_id}?")
            st.write(f"**{irasas['data']}** | {irasas['produktas']} | {irasas['suma']:.2f} €")

            if st.button("🗑️ Taip, ištrinti", type="primary"):
                conn.execute("DELETE FROM islaidos WHERE id = ?", (iraso_id,))
                conn.commit()
                st.success("✅ Įrašas ištrintas.")
                st.rerun()


# =====================================================
# 💰 PAJAMOS
# =====================================================

elif puslapis == "💰 Pajamos":
    st.title("💰 Pajamų modulis")
    st.markdown("Registruokite derlių ir pardavimo pajamas.")

    tab_add, tab_view = st.tabs(["➕ Pridėti pajamas", "📋 Peržiūrėti"])

    with tab_add:
        with st.form("pajamos_forma", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                p_data = st.date_input("📅 Pardavimo data", value=date.today())
                p_kultura = st.text_input("🌾 Kultūra", placeholder="pvz. Kviečiai žieminiai")
                p_plotas = st.number_input("📐 Plotas (ha)", min_value=0.0, value=15.0, step=0.1)
            with col2:
                p_derlius = st.number_input("🌾 Derlius (t/ha)", min_value=0.0, value=0.0, step=0.1)
                p_kaina = st.number_input("💶 Pardavimo kaina (€/t)", min_value=0.0, value=0.0, step=1.0)
                p_pastaba = st.text_input("📝 Pastaba", placeholder="(neprivaloma)")

            p_pateikti = st.form_submit_button("✅ Registruoti pajamas", use_container_width=True)

            if p_pateikti:
                if not p_kultura:
                    st.error("❌ Įveskite kultūrą.")
                else:
                    bendras_derlius = p_plotas * p_derlius
                    pajamu_suma = bendras_derlius * p_kaina

                    conn.execute("""
                        INSERT INTO pajamos (data, kultura, plotas_ha, derlius_t_ha,
                            bendras_derlius_t, pardavimo_kaina_eur_t, pajamu_suma, pastaba)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (p_data.strftime("%Y-%m-%d"), p_kultura, p_plotas, p_derlius,
                          bendras_derlius, p_kaina, pajamu_suma, p_pastaba))
                    conn.commit()
                    st.success(f"✅ Pajamos registruotos: {pajamu_suma:,.2f} €")

    with tab_view:
        pajamos_df = gauti_pajamas(conn)
        if pajamos_df.empty:
            st.info("Pajamų įrašų dar nėra.")
        else:
            st.dataframe(pajamos_df, use_container_width=True)
            st.metric("💰 Visos pajamos", f"{pajamos_df['pajamu_suma'].sum():,.2f} €")


# =====================================================
# 📈 PELNINGUMAS
# =====================================================

elif puslapis == "📈 Pelningumas":
    st.title("📈 Pelningumas")

    islaidos_df = gauti_islaidas(conn, filtrai)
    pajamos_df = gauti_pajamas(conn)

    visos_islaidos = islaidos_df["suma"].sum() if not islaidos_df.empty else 0
    visos_pajamos = pajamos_df["pajamu_suma"].sum() if not pajamos_df.empty else 0
    pelnas = visos_pajamos - visos_islaidos
    marza = (pelnas / visos_pajamos * 100) if visos_pajamos > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💸 Išlaidos", f"{visos_islaidos:,.2f} €")
    with col2:
        st.metric("💰 Pajamos", f"{visos_pajamos:,.2f} €")
    with col3:
        st.metric("📊 Pelnas/Nuostolis", f"{pelnas:,.2f} €",
                  delta=f"{pelnas:,.2f} €")
    with col4:
        st.metric("📉 Marža", f"{marza:.1f}%")

    st.markdown("---")

    if not islaidos_df.empty or not pajamos_df.empty:
        # Grafiku palyginimas
        fig = go.Figure()

        if not islaidos_df.empty:
            isl_men = islaidos_df.groupby("menuo")["suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=isl_men["menuo"], y=isl_men["suma"], name="Išlaidos", marker_color="#E74C3C"))

        if not pajamos_df.empty:
            pajamos_df["menuo"] = pd.to_datetime(pajamos_df["data"]).dt.strftime("%Y-%m")
            paj_men = pajamos_df.groupby("menuo")["pajamu_suma"].sum().reset_index()
            fig.add_trace(go.Bar(x=paj_men["menuo"], y=paj_men["pajamu_suma"], name="Pajamos", marker_color="#2ECC71"))

        fig.update_layout(
            title="Išlaidos vs. Pajamos pagal mėnesį",
            xaxis_title="Mėnuo",
            yaxis_title="Suma, €",
            barmode="group"
        )
        st.plotly_chart(fig, use_container_width=True)

        # Pelningumas pagal kultūrą
        if not islaidos_df.empty and not pajamos_df.empty:
            st.subheader("🌾 Pelningumas pagal kultūrą")

            islaidos_kult = islaidos_df.groupby("kultura")["suma"].sum().reset_index()
            islaidos_kult.columns = ["kultura", "islaidos"]

            pajamos_kult = pajamos_df.groupby("kultura")["pajamu_suma"].sum().reset_index()
            pajamos_kult.columns = ["kultura", "pajamos"]

            pelnas_df = islaidos_kult.merge(pajamos_kult, on="kultura", how="outer").fillna(0)
            pelnas_df["pelnas"] = pelnas_df["pajamos"] - pelnas_df["islaidos"]

            pelnas_df.columns = ["Kultūra", "Išlaidos €", "Pajamos €", "Pelnas €"]
            st.dataframe(pelnas_df, use_container_width=True)
    else:
        st.info("Pridėkite išlaidų ir pajamų įrašų, kad matytumėte pelningumą.")


# =====================================================
# 📥 IMPORTAS / EKSPORTAS
# =====================================================

elif puslapis == "📥 Importas / Eksportas":
    st.title("📥 Importas / Eksportas")

    tab_imp, tab_exp = st.tabs(["📥 Importas", "📤 Eksportas"])

    with tab_imp:
        st.subheader("📥 Importuoti iš CSV")
        ikeltas_failas = st.file_uploader("Pasirinkite CSV failą", type=["csv"])

        if ikeltas_failas is not None:
            if st.button("📥 Importuoti"):
                # Išsaugoti laikinai
                laikinas = "temp_import.csv"
                with open(laikinas, "wb") as f:
                    f.write(ikeltas_failas.getvalue())
                importuota = importuoti_is_csv(conn, laikinas)
                os.remove(laikinas)
                if importuota > 0:
                    st.success(f"✅ Importuota {importuota} įrašų!")
                    st.rerun()
                else:
                    st.warning("Nepavyko importuoti duomenų.")

    with tab_exp:
        st.subheader("📤 Eksportuoti duomenis")

        df = gauti_islaidas(conn)

        if df.empty:
            st.info("Nėra duomenų eksportui.")
        else:
            col1, col2 = st.columns(2)

            with col1:
                # CSV eksportas
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8")
                st.download_button(
                    "📄 Parsisiųsti CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"ukio_islaidos_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col2:
                # Excel eksportas
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                    df.to_excel(writer, sheet_name="Visi įrašai", index=False)

                    # Suvestinė
                    suvestine = pd.DataFrame({
                        "Rodiklis": ["Bendra suma €", "Kaina/ha €", "Įrašų skaičius"],
                        "Reikšmė": [
                            f"{df['suma'].sum():.2f}",
                            f"{df['suma'].sum() / df['plotas_ha'].iloc[0]:.2f}" if df['plotas_ha'].iloc[0] > 0 else "0",
                            str(len(df))
                        ]
                    })
                    suvestine.to_excel(writer, sheet_name="Suvestinė", index=False)

                st.download_button(
                    "📊 Parsisiųsti Excel",
                    data=excel_buffer.getvalue(),
                    file_name=f"ukio_ataskaita_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )


# =====================================================
# FOOTER
# =====================================================

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div style=\'text-align: center; color: #888;\'>"    "🌾 Ūkio skaičiuoklė v2.0<br>"    f"© {datetime.now().year}"    "</div>",
    unsafe_allow_html=True
)
