import os
import requests
import time
import random
from datetime import datetime

try:
    from db import get_connection
except ImportError:
    print("⚠️ Module 'db' introuvable")
    def get_connection(): return None

# ============================================
# CONFIGURATION
# ============================================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "jsearch.p.rapidapi.com"

KEYWORDS = ["Data Engineer", "Data Scientist", "Data Analyst"]
LOCATIONS = ["France", "Paris", "Lyon", "Marseille"]
MAX_PAGES = 3  # 10 offres par page → 30 offres par keyword/location

# ============================================
# APPEL API JSEARCH
# ============================================

def fetch_jobs(keyword, location, page=1):
    """
    Appelle JSearch API et retourne les offres brutes.
    """
    url = "https://jsearch.p.rapidapi.com/search"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    params = {
        "query": f"{keyword} in {location}",
        "page": str(page),
        "num_pages": "1",
        "date_posted": "month",   # Offres du dernier mois
        "language": "fr"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            jobs = data.get("data", [])
            print(f"    ✅ {len(jobs)} offres récupérées (page {page})")
            return jobs

        elif response.status_code == 429:
            print("    ⚠️ Rate limit atteint — pause 60s...")
            time.sleep(60)
            return []

        else:
            print(f"    ❌ Erreur API: {response.status_code} — {response.text[:200]}")
            return []

    except requests.exceptions.Timeout:
        print("    ⏱️ Timeout API")
        return []
    except Exception as e:
        print(f"    ❌ Erreur requête: {e}")
        return []

# ============================================
# TRANSFORMATION DES DONNÉES
# ============================================

def transform_job(raw_job, keyword):
    """
    Transforme une offre JSearch au format de notre table jobs_raw.
    """
    try:
        return {
            "title":      raw_job.get("job_title", "N/A"),
            "company":    raw_job.get("employer_name", "N/A"),
            "location":   raw_job.get("job_city") or raw_job.get("job_country") or "N/A",
            "url":        raw_job.get("job_apply_link") or raw_job.get("job_google_link", ""),
            "source":     "indeed_jsearch",
            "keyword":    keyword,
            "scraped_at": datetime.now(),
        }
    except Exception as e:
        print(f"    ⚠️ Erreur transformation: {e}")
        return None

# ============================================
# INSERTION EN BASE
# ============================================

def insert_jobs(jobs):
    if not jobs:
        return 0, 0

    conn = get_connection()
    if not conn:
        print("    ❌ Connexion DB impossible")
        return 0, 0

    cur = conn.cursor()
    inserted, duplicates = 0, 0

    for job in jobs:
        if not job or not job.get("url"):
            continue
        try:
            # Vérifier doublon via URL
            cur.execute("SELECT id FROM jobs_raw WHERE url = %s", (job["url"],))
            if cur.fetchone():
                duplicates += 1
                continue

            cur.execute("""
                INSERT INTO jobs_raw (title, company, location, url, source, scraped_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                job["title"],
                job["company"],
                job["location"],
                job["url"],
                job["source"],
                job["scraped_at"]
            ))
            inserted += 1

        except Exception as e:
            print(f"    ⚠️ Erreur insert: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()
    return inserted, duplicates

# ============================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================

def scrape_indeed_jsearch():
    print("🚀 Démarrage scraper Indeed via JSearch API...")
    print(f"   Keywords : {KEYWORDS}")
    print(f"   Locations: {LOCATIONS}")
    print(f"   Pages    : {MAX_PAGES} par combinaison\n")

    total_inserted = 0
    total_duplicates = 0

    for keyword in KEYWORDS:
        for location in LOCATIONS:
            print(f"🔍 {keyword} — {location}")

            for page in range(1, MAX_PAGES + 1):
                print(f"  Page {page}/{MAX_PAGES}")

                # Appel API
                raw_jobs = fetch_jobs(keyword, location, page)

                if not raw_jobs:
                    print("  ⏭️ Aucune offre, passage au suivant")
                    break

                # Transformation
                jobs = [transform_job(j, keyword) for j in raw_jobs]
                jobs = [j for j in jobs if j]  # Filtrer les None

                # Insertion
                ins, dup = insert_jobs(jobs)
                total_inserted += ins
                total_duplicates += dup
                print(f"  💾 {ins} insérées, {dup} doublons")

                # Pause pour respecter le rate limit
                time.sleep(random.uniform(3, 5))

            print()

    print(f"🏁 Terminé !")
    print(f"   Total insérées  : {total_inserted}")
    print(f"   Total doublons  : {total_duplicates}")

if __name__ == "__main__":
    scrape_indeed_jsearch()
