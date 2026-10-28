import pandas as pd
import psycopg2
import re

# ============================================
# CONNEXION
# ============================================
DB_CONFIG = {
    "host": "postgres",
    "database": "job_intelligent",
    "user": "admin",
    "password": "admin123",
    "port": "5432"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# ============================================
# DICTIONNAIRE DE COMPÉTENCES DATA
# ============================================
SKILLS_DICT = {
    # Langages de programmation
    "Python": [r'\bpython\b'],
    "R": [r'\b\br\b(?!\s*&)|\blangage r\b'],
    "Java": [r'\bjava\b(?!script)'],
    "Scala": [r'\bscala\b'],
    "SQL": [r'\bsql\b'],
    "NoSQL": [r'\bnosql\b', r'\bmongodb\b', r'\bcassandra\b', r'\bcouchdb\b'],
    "JavaScript": [r'\bjavascript\b', r'\bjs\b'],
    
    # Big Data & Processing
    "Spark": [r'\bspark\b', r'\bapache spark\b', r'\bpySpark\b', r'\bpyspark\b'],
    "Hadoop": [r'\bhadoop\b'],
    "Hive": [r'\bhive\b'],
    "Kafka": [r'\bkafka\b'],
    "Flink": [r'\bflink\b'],
    "Airflow": [r'\bairflow\b'],
    "Sqoop": [r'\bsqoop\b'],
    "NiFi": [r'\bnifi\b'],
    
    # Cloud
    "AWS": [r'\baws\b', r'\bamazon web services\b', r'\bs3\b', r'\bglue\b', r'\bemr\b', r'\bredshift\b'],
    "Azure": [r'\bazure\b', r'\bazure hd insight\b', r'\bdatabricks\b'],
    "GCP": [r'\bgcp\b', r'\bgoogle cloud\b', r'\bbigquery\b', r'\bdataflow\b', r'\bgcs\b'],
    
    # Bases de données
    "PostgreSQL": [r'\bpostgres\b', r'\bpostgresql\b'],
    "MySQL": [r'\bmysql\b'],
    "MongoDB": [r'\bmongodb\b', r'\bmongo\b'],
    "Elasticsearch": [r'\belastic\b', r'\belasticsearch\b'],
    "Redis": [r'\bredis\b'],
    "Snowflake": [r'\bsnowflake\b'],
    "Delta Lake": [r'\bdelta lake\b', r'\bdelta\b'],
    
    # ETL & Orchestration
    "Talend": [r'\btalend\b'],
    "Informatica": [r'\binformatica\b'],
    "DataStage": [r'\bdatastage\b'],
    "Stambia": [r'\bstambia\b'],
    "SSIS": [r'\bssis\b'],
    "Luigi": [r'\bluigi\b'],
    "Prefect": [r'\bprefect\b'],
    
    # Data Science & ML
    "Machine Learning": [r'\bmachine learning\b', r'\bml\b(?!\s*flow)', r'\bapprentissage automatique\b'],
    "Deep Learning": [r'\bdeep learning\b', r'\bapprentissage profond\b'],
    "NLP": [r'\bnlp\b', r'\bnatural language processing\b', r'\btraitement du langage\b'],
    "TensorFlow": [r'\btensorflow\b', r'\btf\b'],
    "PyTorch": [r'\bpytorch\b'],
    "Scikit-learn": [r'\bscikit.learn\b', r'\bsklearn\b'],
    "Keras": [r'\bkeras\b'],
    
    # BI & Visualisation
    "Power BI": [r'\bpower bi\b', r'\bpowerbi\b'],
    "Tableau": [r'\btableau\b'],
    "Qlik": [r'\bqlik\b', r'\bqlikview\b', r'\bqliksense\b'],
    "SAP BI": [r'\bsap bi\b', r'\bsap businessobjects\b', r'\bsap bo\b'],
    "Looker": [r'\blooker\b'],
    "Metabase": [r'\bmetabase\b'],
    
    # Data Engineering concepts
    "DataLake": [r'\bdatalake\b', r'\bdata lake\b'],
    "DataWarehouse": [r'\bdatawarehouse\b', r'\bdata warehouse\b', r'\bentrepôt de données\b'],
    "ETL": [r'\betl\b', r'\bextract.transform.load\b'],
    "CI/CD": [r'\bci/cd\b', r'\bci cd\b', r'\bintégration continue\b'],
    "Streaming": [r'\bstreaming\b', r'\btemps réel\b', r'\breal.time\b'],
    "Batch": [r'\bbatch\b'],
    "API": [r'\bapi\b', r'\brest\b', r'\bgraphql\b'],
    "Docker": [r'\bdocker\b', r'\bcontainerisation\b'],
    "Kubernetes": [r'\bkubernetes\b', r'\bk8s\b'],
    "Git": [r'\bgit\b', r'\bgithub\b', r'\bgitlab\b'],
    
    # Outils Data
    "SAS": [r'\bsas\b'],
    "DataIku": [r'\bdataiku\b'],
    "Databricks": [r'\bdatabricks\b'],
    "Cloudera": [r'\bcloudera\b'],
    "Jupyter": [r'\bjupyter\b'],
    "Spark": [r'\bspark\b'],
}

# ============================================
# EXTRACTION
# ============================================
def extract_skills(text):
    """Extrait les compétences d'un texte"""
    if not text:
        return []
    found = []
    text_lower = text.lower()
    for skill, patterns in SKILLS_DICT.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                if skill not in found:
                    found.append(skill)
                break
    return found

def process_all_jobs():
    """Extrait les compétences de toutes les offres"""
    conn = get_connection()
    df = pd.read_sql("SELECT id, title, description FROM jobs_cleaned", conn)
    conn.close()
    
    print(f"📊 {len(df)} offres à analyser")
    
    # Extraire les compétences
    df['skills'] = df['description'].apply(extract_skills)
    df['skills_text'] = df['skills'].apply(lambda x: ', '.join(x) if x else '')
    df['skills_count'] = df['skills'].apply(len)
    
    # Stats
    with_skills = (df['skills_count'] > 0).sum()
    print(f"✅ {with_skills}/{len(df)} offres ont des compétences extraites")
    print(f"📊 Moyenne : {df['skills_count'].mean():.1f} compétences par offre")
    
    return df

# ============================================
# SAUVEGARDE
# ============================================
def save_results(df):
    conn = get_connection()
    cur = conn.cursor()
    
    # Ajouter colonne skills à jobs_cleaned
    try:
        cur.execute("ALTER TABLE jobs_cleaned ADD COLUMN skills TEXT;")
        print("✅ Colonne 'skills' ajoutée à jobs_cleaned")
    except Exception as e:
        conn.rollback()
        print("✅ Colonne 'skills' existe déjà")
    
    # Mettre à jour les skills
    updated = 0
    for _, row in df.iterrows():
        cur.execute(
            "UPDATE jobs_cleaned SET skills = %s WHERE id = %s",
            (row['skills_text'], row['id'])
        )
        updated += 1
    
    conn.commit()
    
    # Créer table de mapping job_skills
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_skills (
            job_id INTEGER REFERENCES jobs_cleaned(id),
            skill VARCHAR(100),
            PRIMARY KEY (job_id, skill)
        );
    """)
    cur.execute("TRUNCATE TABLE job_skills")
    
    inserted = 0
    for _, row in df.iterrows():
        for skill in row['skills']:
            cur.execute(
                "INSERT INTO job_skills (job_id, skill) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (row['id'], skill)
            )
            inserted += 1
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {updated} offres mises à jour")
    print(f"✅ {inserted} liens compétence-offre insérés")

# ============================================
# RAPPORT
# ============================================
def print_report(df):
    # Top 20 compétences les plus demandées
    all_skills = []
    for skills in df['skills']:
        all_skills.extend(skills)
    
    from collections import Counter
    skill_counts = Counter(all_skills)
    
    print("\n" + "="*50)
    print("🔥 TOP 20 COMPÉTENCES LES PLUS DEMANDÉES")
    print("="*50)
    for skill, count in skill_counts.most_common(20):
        bar = "█" * (count // 5)
        print(f"{skill:<25} {count:>4} {bar}")
    print("="*50)

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    df = process_all_jobs()
    print_report(df)
    save_results(df)
    print("\n🎉 Extraction NLP terminée avec succès !")
