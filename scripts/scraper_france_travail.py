import os
import requests
import re
from datetime import datetime
from db import get_connection

# ============================================
# CONFIGURATION
# ============================================
CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")

API_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
API_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

# Mots-clés à scraper
KEYWORDS = ["Data Engineer", "Data Scientist", "Data Analyst"]

# Nombre maximum de résultats par mot-clé (pagination automatique)
MAX_RESULTS_PER_KEYWORD = 500

# Taille de chaque page d'appel API (max autorisé = 150)
PAGE_SIZE = 150

# Temporisation entre les pages pour ne pas spammer l'API (en secondes)
REQUEST_DELAY = 1


# ============================================
# FONCTIONS UTILITAIRES
# ============================================

def clean_html(text):
    """Supprime les balises HTML d'un texte"""
    if not text or text == "N/A":
        return text
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_text(text):
    """Nettoie un texte : supprime les espaces multiples, les retours à la ligne excessifs"""
    if not text or text == "N/A":
        return text
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================
# AUTHENTIFICATION
# ============================================

def get_token():
    """Obtient un token d'accès depuis l'API France-Travail"""
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre"
    }
    try:
        response = requests.post(API_TOKEN_URL, data=data, timeout=10)
        if response.status_code == 200:
            token = response.json().get("access_token")
            if token:
                print("✅ Token obtenu")
                return token
            else:
                print("❌ Token absent de la réponse")
                return None
        else:
            print(f"❌ Erreur auth ({response.status_code}) : {response.text[:150]}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Timeout lors de l'authentification")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ Impossible de se connecter à l'API France-Travail")
        return None
    except Exception as e:
        print(f"❌ Erreur token : {e}")
        return None


# ============================================
# EXTRACTION DES DONNÉES
# ============================================

def extract_offre_data(offre):
    """Extrait et nettoie les champs d'une offre d'emploi"""
    lieu = offre.get("lieuTravail", {}) or {}
    entreprise = offre.get("entreprise", {}) or {}
    origine = offre.get("origineOffre", {}) or {}
    salaire = offre.get("salaire", {}) or {}

    # Type de contrat
    type_contrat = offre.get("typeContrat", "N/A")
    if isinstance(type_contrat, dict):
        type_contrat = type_contrat.get("libelle", "N/A")

    # Salaire
    libelle_salaire = salaire.get("libelle", "N/A")

    # Date de création (format : "2024-01-15T10:30:00.000Z")
    date_creation = offre.get("dateCreation", "N/A")
    if date_creation and date_creation != "N/A":
        try:
            date_creation = datetime.strptime(date_creation[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            date_creation = "N/A"

    # Description nettoyée (sans HTML)
    description = clean_html(offre.get("description", "N/A"))

    # Qualification (ex: Cadre, Non cadre)
    qualification = offre.get("qualification", "N/A")
    if isinstance(qualification, dict):
        qualification = qualification.get("libelle", "N/A")

    # Expérience requise
    experience = offre.get("experienceExigee", "N/A")
    if isinstance(experience, dict):
        experience = experience.get("libelle", "N/A")

    return {
        "source": "france_travail",
        "external_id": offre.get("id", "N/A"),
        "title": clean_text(offre.get("intitule", "N/A")),
        "company": clean_text(entreprise.get("nom", "N/A")),
        "company_description": clean_text(entreprise.get("description", "N/A")),
        "location": clean_text(lieu.get("libelle", "N/A")),
        "city": clean_text(lieu.get("commune", "N/A")),
        "department": clean_text(lieu.get("libelle", "N/A")),
        "url": origine.get("urlOrigine", "N/A"),
        "description": description,
        "contract_type": clean_text(type_contrat),
        "salary": clean_text(libelle_salaire),
        "publication_date": date_creation,
        "qualification": clean_text(qualification),
        "experience": clean_text(experience),
        "scraped_at": datetime.now()
    }


# ============================================
# SCRAPER AVEC PAGINATION
# ============================================

def scrape_france_travail(keyword, max_results=MAX_RESULTS_PER_KEYWORD):
    """
    Scrape les offres France-Travail avec pagination automatique.
    L'API limite chaque requête à 150 résultats maximum.
    On pagine donc tant qu'il y a des résultats.
    """
    print(f"\n{'='*60}")
    print(f"🔍 Scraping : {keyword}")
    print(f"{'='*60}")

    # 1. Authentification
    token = get_token()
    if not token:
        print("⚠️ Scraping annulé (pas de token)")
        return 0

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    conn = get_connection()
    if not conn:
        print("⚠️ Scraping annulé (pas de connexion DB)")
        return 0

    cur = conn.cursor()
    total_inserees = 0
    total_doublons = 0
    page = 0

    # 2. Pagination
    while total_inserees + total_doublons < max_results:
        debut = page * PAGE_SIZE
        fin = min(debut + PAGE_SIZE - 1, max_results - 1)

        params = {
            "motsCles": keyword,
            "range": f"{debut}-{fin}",
            "sort": 1  # Tri par date décroissante (les plus récentes d'abord)
        }

        try:
            response = requests.get(
                API_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=15
            )
            print(f"  📡 Page {page + 1} | Range {debut}-{fin} | Status : {response.status_code}")

            if response.status_code not in (200, 206):
                print(f"  ❌ Erreur API : {response.status_code} - {response.text[:200]}")
                break

            data = response.json()
            offres = data.get("resultats", [])

            if not offres:
                print("  ⚠️ Plus d'offres disponibles")
                break

            # 3. Insertion en base
            for offre in offres:
                try:
                    d = extract_offre_data(offre)

                    # Vérifie si l'offre existe déjà (par external_id + source)
                    cur.execute("""
                        SELECT id FROM jobs_raw
                        WHERE external_id = %s AND source = %s
                    """, (d["external_id"], d["source"]))

                    existing = cur.fetchone()
                    if existing:
                        total_doublons += 1
                        continue

                    # Insertion avec tous les champs
                    cur.execute("""
                        INSERT INTO jobs_raw (
                            source, external_id, title, company, company_description,
                            location, city, department, url, description,
                            contract_type, salary, publication_date,
                            qualification, experience, scraped_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s
                        )
                    """, (
                        d["source"], d["external_id"], d["title"], d["company"],
                        d["company_description"], d["location"], d["city"], d["department"],
                        d["url"], d["description"], d["contract_type"], d["salary"],
                        d["publication_date"], d["qualification"], d["experience"],
                        d["scraped_at"]
                    ))
                    total_inserees += 1

                except Exception as e:
                    conn.rollback()
                    print(f"  ⚠️ Erreur insertion (ID: {offre.get('id', '?')}) : {e}")

            conn.commit()
            print(f"  📦 {len(offres)} offres traitées | ✅ {total_inserees} nouvelles | 🔁 {total_doublons} doublons")

            # Si l'API retourne moins de PAGE_SIZE résultats, on est à la dernière page
            if len(offres) < PAGE_SIZE:
                print("  ℹ️ Dernière page atteinte")
                break

            page += 1

            # Temporisation entre les pages
            if REQUEST_DELAY > 0:
                import time
                time.sleep(REQUEST_DELAY)

        except requests.exceptions.Timeout:
            print(f"  ❌ Timeout à la page {page + 1}, fin du scraping")
            break
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Perte de connexion à la page {page + 1}, fin du scraping")
            break
        except Exception as e:
            print(f"  ❌ Erreur inattendue : {e}")
            break

    cur.close()
    conn.close()

    print(f"\n  📊 RÉSUMÉ pour '{keyword}' :")
    print(f"     ✅ {total_inserees} offres insérées")
    print(f"     🔁 {total_doublons} doublons évités")
    print(f"     📄 {page + 1} page(s) traitée(s)")

    return total_inserees


# ============================================
# MISE À JOUR DE LA BASE DE DONNÉES
# ============================================

def ensure_db_columns():
    """Vérifie et ajoute les colonnes manquantes à la table jobs_raw"""
    conn = get_connection()
    if not conn:
        return

    cur = conn.cursor()

    # Liste des colonnes à vérifier/ajouter
    columns_to_add = {
        "external_id": "VARCHAR(255) DEFAULT 'N/A'",
        "company_description": "TEXT DEFAULT NULL",
        "city": "VARCHAR(255) DEFAULT 'N/A'",
        "department": "VARCHAR(255) DEFAULT 'N/A'",
        "contract_type": "VARCHAR(100) DEFAULT 'N/A'",
        "salary": "VARCHAR(255) DEFAULT 'N/A'",
        "publication_date": "TIMESTAMP DEFAULT NULL",
        "qualification": "VARCHAR(100) DEFAULT 'N/A'",
        "experience": "VARCHAR(100) DEFAULT 'N/A'",
        "scraped_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    }

    for col_name, col_def in columns_to_add.items():
        try:
            cur.execute(f"""
                ALTER TABLE jobs_raw ADD COLUMN IF NOT EXISTS {col_name} {col_def}
            """)
            print(f"  ✅ Colonne '{col_name}' vérifiée")
        except Exception as e:
            # La colonne existe peut-être déjà avec IF NOT EXISTS non supporté
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  ✅ Colonne '{col_name}' déjà existante")
            else:
                print(f"  ⚠️ Colonne '{col_name}' : {e}")

    # Création d'un index pour accélérer la vérification des doublons
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_raw_source_extid
            ON jobs_raw (source, external_id)
        """)
        print("  ✅ Index de déduplication créé")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("  ✅ Index de déduplication déjà existant")
        else:
            print(f"  ⚠️ Index : {e}")

    conn.commit()
    cur.close()
    conn.close()


# ============================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 SCRAPER FRANCE-TRAVAIL - PROJET JOB INTELLIGENT")
    print("=" * 60)

    # 0. Vérifier/mettre à jour la structure de la base
    print("\n🔧 Vérification de la base de données...")
    ensure_db_columns()

    # 1. Scraper chaque mot-clé
    total_general = 0
    start_time = datetime.now()

    for keyword in KEYWORDS:
        nb = scrape_france_travail(keyword, max_results=MAX_RESULTS_PER_KEYWORD)
        total_general += nb

    # 2. Résumé global
    elapsed = (datetime.now() - start_time).total_seconds()

    print(f"\n{'='*60}")
    print(f"📊 RÉSUMÉ GÉNÉRAL")
    print(f"{'='*60}")
    print(f"  Mots-clés  : {len(KEYWORDS)} ({', '.join(KEYWORDS)})")
    print(f"  Total inséré : {total_general} offres")
    print(f"  Temps total  : {elapsed:.1f} secondes")
    print(f"  Terminé à    : {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
