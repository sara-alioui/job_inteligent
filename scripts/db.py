import psycopg2

# Configuration Docker
# IMPORTANT : On utilise "postgres" (nom du service) et non "postgres"
DB_CONFIG = {
    "host": "postgres",       
    "database": "job_intelligent",
    "user": "admin",
    "password": "admin123",
    "port": "5432"
}

def get_connection():
    """Établit la connexion avec PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connexion à la base de données réussie.")
        return conn
    except Exception as e:
        print(f"❌ Erreur de connexion DB : {e}")
        return None

def init_db():
    """Crée la table principale si elle n'existe pas (Structure complète pour le scraper)"""
    conn = get_connection()
    if not conn: return

    cur = conn.cursor()
    
    # Structure complète correspondant à scrape_indeed.py
    create_table_query = """
    CREATE TABLE IF NOT EXISTS jobs_raw (
        id SERIAL PRIMARY KEY,
        source VARCHAR(50) NOT NULL,
        external_id VARCHAR(255) UNIQUE,
        title TEXT,
        company TEXT,
        company_description TEXT,
        location TEXT,
        city TEXT,
        department TEXT,
        url TEXT,
        description TEXT,
        contract_type TEXT,
        salary TEXT,
        publication_date DATE,
        qualification TEXT,
        experience TEXT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    try:
        cur.execute(create_table_query)
        conn.commit()
        print("✅ Table 'jobs_raw' vérifiée/créée avec succès.")
    except Exception as e:
        print(f"⚠️ Erreur lors de la création de table : {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_db()
