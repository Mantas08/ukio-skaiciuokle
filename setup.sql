-- =====================================================
-- ŪKIO SKAIČIUOKLĖ – SUPABASE LENTELIŲ KŪRIMAS
-- Paleiskite šį SQL Supabase SQL Editor'e
-- =====================================================

-- 1. LAUKAI
CREATE TABLE IF NOT EXISTS laukai (
    id BIGSERIAL PRIMARY KEY,
    pavadinimas TEXT NOT NULL,
    plotas_ha REAL NOT NULL DEFAULT 0,
    kultura TEXT NOT NULL DEFAULT '',
    pastaba TEXT DEFAULT '',
    sukurta TIMESTAMPTZ DEFAULT NOW()
);

-- 2. IŠLAIDOS
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

-- 3. SANDĖLIS
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

-- 4. PAJAMOS
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

-- =====================================================
-- ROW LEVEL SECURITY (RLS) – leidžia viską anon vartotojui
-- =====================================================

ALTER TABLE laukai ENABLE ROW LEVEL SECURITY;
ALTER TABLE islaidos ENABLE ROW LEVEL SECURITY;
ALTER TABLE sandelis ENABLE ROW LEVEL SECURITY;
ALTER TABLE pajamos ENABLE ROW LEVEL SECURITY;

-- Politikos – leisti viską (vieno vartotojo app)
CREATE POLICY "Leisti viską laukai" ON laukai FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Leisti viską islaidos" ON islaidos FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Leisti viską sandelis" ON sandelis FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Leisti viską pajamos" ON pajamos FOR ALL USING (true) WITH CHECK (true);

-- =====================================================
-- INDEKSAI (greitesnės užklausos)
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_islaidos_data ON islaidos(data);
CREATE INDEX IF NOT EXISTS idx_islaidos_lauko_id ON islaidos(lauko_id);
CREATE INDEX IF NOT EXISTS idx_islaidos_menuo ON islaidos(menuo);
CREATE INDEX IF NOT EXISTS idx_pajamos_lauko_id ON pajamos(lauko_id);
