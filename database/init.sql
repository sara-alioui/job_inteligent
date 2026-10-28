-- ============================================================
-- SCHÉMA ÉTOILE - JOB INTELLIGENT
-- ============================================================

-- ============================================================
-- DIMENSIONS
-- ============================================================

-- DIM SOURCE : france_travail, adzuna, indeed
CREATE TABLE IF NOT EXISTS dim_source (
    source_id   SERIAL PRIMARY KEY,
    source_name VARCHAR(50) UNIQUE NOT NULL,
    source_url  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- DIM LOCALISATION
CREATE TABLE IF NOT EXISTS dim_location (
    location_id SERIAL PRIMARY KEY,
    city        VARCHAR(255),
    department  VARCHAR(255),
    region      VARCHAR(255),
    country     VARCHAR(100) DEFAULT 'France',
    full_label  VARCHAR(255) UNIQUE NOT NULL
);

-- DIM ENTREPRISE
CREATE TABLE IF NOT EXISTS dim_company (
    company_id          SERIAL PRIMARY KEY,
    company_name        VARCHAR(255) UNIQUE NOT NULL,
    company_description TEXT
);

-- DIM CONTRAT
CREATE TABLE IF NOT EXISTS dim_contract (
    contract_id   SERIAL PRIMARY KEY,
    contract_type VARCHAR(100) UNIQUE NOT NULL
);

-- DIM DATE
CREATE TABLE IF NOT EXISTS dim_date (
    date_id     SERIAL PRIMARY KEY,
    full_date   DATE UNIQUE NOT NULL,
    day         INTEGER,
    month       INTEGER,
    year        INTEGER,
    quarter     INTEGER,
    day_of_week INTEGER,
    week_number INTEGER
);

-- DIM COMPÉTENCE
CREATE TABLE IF NOT EXISTS dim_skill (
    skill_id   SERIAL PRIMARY KEY,
    skill_name VARCHAR(100) UNIQUE NOT NULL,
    category   VARCHAR(50)  -- ex: 'Langage', 'Cloud', 'BI', 'Big Data'
);

-- DIM CATÉGORIE MÉTIER
CREATE TABLE IF NOT EXISTS dim_job_category (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(100) UNIQUE NOT NULL
);

-- ============================================================
-- TABLE DE FAITS CENTRALE
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_jobs (
    job_id          SERIAL PRIMARY KEY,
    external_id     VARCHAR(255) UNIQUE,

    -- Clés étrangères vers les dimensions
    source_id       INTEGER REFERENCES dim_source(source_id),
    location_id     INTEGER REFERENCES dim_location(location_id),
    company_id      INTEGER REFERENCES dim_company(company_id),
    contract_id     INTEGER REFERENCES dim_contract(contract_id),
    category_id     INTEGER REFERENCES dim_job_category(category_id),
    date_id         INTEGER REFERENCES dim_date(date_id),

    -- Attributs dégénérés (pas de dimension propre)
    title           TEXT,
    title_normalized TEXT,
    description     TEXT,
    salary          TEXT,
    qualification   TEXT,
    experience      TEXT,
    url             TEXT,

    -- Métriques
    skills_count    INTEGER DEFAULT 0,

    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE DE LIAISON FAITS <-> COMPÉTENCES (Many-to-Many)
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_job_skills (
    job_id    INTEGER REFERENCES fact_jobs(job_id) ON DELETE CASCADE,
    skill_id  INTEGER REFERENCES dim_skill(skill_id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, skill_id)
);

-- ============================================================
-- HISTORIQUE DES RECOMMANDATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_recommendations (
    rec_id          SERIAL PRIMARY KEY,
    profile_skills  TEXT,
    profile_title   TEXT,
    recommended_job_ids TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES POUR LES PERFORMANCES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_fact_jobs_source     ON fact_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_fact_jobs_location   ON fact_jobs(location_id);
CREATE INDEX IF NOT EXISTS idx_fact_jobs_company    ON fact_jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_fact_jobs_category   ON fact_jobs(category_id);
CREATE INDEX IF NOT EXISTS idx_fact_jobs_date       ON fact_jobs(date_id);
CREATE INDEX IF NOT EXISTS idx_fact_jobs_scraped    ON fact_jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_fact_job_skills_job  ON fact_job_skills(job_id);
CREATE INDEX IF NOT EXISTS idx_fact_job_skills_skill ON fact_job_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_dim_location_city    ON dim_location(city);
CREATE INDEX IF NOT EXISTS idx_dim_company_name     ON dim_company(company_name);

-- ============================================================
-- DONNÉES INITIALES DES DIMENSIONS STATIQUES
-- ============================================================

INSERT INTO dim_source (source_name, source_url) VALUES
    ('france_travail', 'https://api.francetravail.io'),
    ('adzuna',         'https://api.adzuna.com'),
    ('indeed_jsearch', 'https://jsearch.p.rapidapi.com')
ON CONFLICT (source_name) DO NOTHING;

INSERT INTO dim_contract (contract_type) VALUES
    ('CDI'), ('CDD'), ('Intérim'), ('Stage'),
    ('Alternance'), ('Freelance'), ('Non précisé')
ON CONFLICT (contract_type) DO NOTHING;

INSERT INTO dim_job_category (category_name) VALUES
    ('Data Engineer'), ('Data Scientist'), ('Data Analyst'),
    ('Data Architect'), ('Data Manager'), ('Autre')
ON CONFLICT (category_name) DO NOTHING;

-- ============================================================
-- VUE PRATIQUE (équivalent de jobs_cleaned pour l'API)
-- ============================================================

CREATE OR REPLACE VIEW jobs_cleaned AS
SELECT
    fj.job_id           AS id,
    ds.source_name      AS source,
    fj.external_id,
    fj.title,
    fj.title_normalized,
    djc.category_name   AS job_category,
    dc.company_name     AS company,
    dl.full_label       AS location,
    dl.city,
    dl.department,
    fj.url,
    fj.description,
    dct.contract_type,
    fj.salary,
    dd.full_date        AS publication_date,
    fj.qualification,
    fj.experience,
    fj.scraped_at,
    fj.skills_count
FROM fact_jobs fj
LEFT JOIN dim_source       ds  ON fj.source_id   = ds.source_id
LEFT JOIN dim_company      dc  ON fj.company_id  = dc.company_id
LEFT JOIN dim_location     dl  ON fj.location_id = dl.location_id
LEFT JOIN dim_contract     dct ON fj.contract_id = dct.contract_id
LEFT JOIN dim_job_category djc ON fj.category_id = djc.category_id
LEFT JOIN dim_date         dd  ON fj.date_id     = dd.date_id;