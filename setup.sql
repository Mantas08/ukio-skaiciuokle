
-- =====================================================
-- ŪKIO SKAIČIUOKLĖ – SUPABASE LENTELIŲ KŪRIMAS (V2)
-- Paleiskite šį SQL Supabase SQL Editor'e
-- =====================================================

CREATE TABLE IF NOT EXISTS laukai (
    id BIGSERIAL PRIMARY KEY,
    pavadinimas TEXT NOT NULL,
    plotas_ha REAL NOT NULL DEFAULT 0,
    kultura TEXT NOT NULL DEFAULT '',
    pastaba TEXT DEFAULT '',
    sukurta TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS islaidos (
    id BIGSERIAL PRIMARY KEY,
    data TEXT NOT NULL,
    menuo TEXT,
    lauko_id BIGINT REFERENCES laukai(id) ON DELETE SET NULL,
    darbas TEXT NOT NULL DEFAULT '',
    produktas TEXT NOT NULL DEFAULT '',
    rusis TEXT NOT NULL DEFAULT '',
    norma REAL NOT NULL DEFAULT 0,
    vienetas TEXT NOT NULL DEFAULT 'kg',
    kaina_uz_vnt_eur REAL NOT NULL DEFAULT 0,
    sunaudotas_kiekis REAL DEFAULT 0,
    suma REAL DEFAULT 0,
    pastaba TEXT DEFAULT '',
    sukurta TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sandelis (
    id BIGSERIAL PRIMARY KEY,
    produktas TEXT NOT NULL,
    rusis TEXT NOT NULL DEFAULT '',
    kiekis REAL NOT NULL DEFAULT 0,
    vienetas TEXT NOT NULL DEFAULT 'kg',
    kaina_uz_vnt_eur REAL NOT NULL DEFAULT 0,
    bendra_verte REAL DEFAULT 0,
    data_prideta TEXT,
    pastaba TEXT DEFAULT '',
    sukurta TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pajamos (
    id BIGSERIAL PRIMARY KEY,
    data TEXT NOT NULL,
    lauko_id BIGINT REFERENCES laukai(id) ON DELETE SET NULL,
    derlius_t_ha REAL NOT NULL DEFAULT 0,
    bendras_derlius_t REAL DEFAULT 0,
    pardavimo_kaina_eur_t REAL NOT NULL DEFAULT 0,
    pajamu_suma REAL DEFAULT 0,
    pastaba TEXT DEFAULT '',
    sukurta TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS saskaitos (
    id BIGSERIAL PRIMARY KEY,
    failo_pavadinimas TEXT NOT NULL,
    saskaitos_numeris TEXT DEFAULT '',
    data_ikelta TEXT,
    produktu_skaicius INTEGER DEFAULT 0,
    parserio_rezimas TEXT DEFAULT '',
    tiekejas TEXT DEFAULT '',
    sukurta TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE laukai ENABLE ROW LEVEL SECURITY;
ALTER TABLE islaidos ENABLE ROW LEVEL SECURITY;
ALTER TABLE sandelis ENABLE ROW LEVEL SECURITY;
ALTER TABLE pajamos ENABLE ROW LEVEL SECURITY;
ALTER TABLE saskaitos ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'laukai' AND policyname = 'Leisti viską laukai') THEN
        CREATE POLICY "Leisti viską laukai" ON laukai FOR ALL USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'islaidos' AND policyname = 'Leisti viską islaidos') THEN
        CREATE POLICY "Leisti viską islaidos" ON islaidos FOR ALL USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'sandelis' AND policyname = 'Leisti viską sandelis') THEN
        CREATE POLICY "Leisti viską sandelis" ON sandelis FOR ALL USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'pajamos' AND policyname = 'Leisti viską pajamos') THEN
        CREATE POLICY "Leisti viską pajamos" ON pajamos FOR ALL USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'saskaitos' AND policyname = 'Leisti viską saskaitos') THEN
        CREATE POLICY "Leisti viską saskaitos" ON saskaitos FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_islaidos_data ON islaidos(data);
CREATE INDEX IF NOT EXISTS idx_islaidos_lauko_id ON islaidos(lauko_id);
CREATE INDEX IF NOT EXISTS idx_islaidos_menuo ON islaidos(menuo);
CREATE INDEX IF NOT EXISTS idx_pajamos_lauko_id ON pajamos(lauko_id);
CREATE INDEX IF NOT EXISTS idx_saskaitos_failo_pavadinimas ON saskaitos(failo_pavadinimas);
