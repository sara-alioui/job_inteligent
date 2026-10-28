import os
import requests
import time
from datetime import datetime
from db import get_connection


# ============================================
# CONFIGURATION
# ============================================
APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
COUNTRY = "fr"               # France → "fr" | UK → "gb"
PAGE_SIZE = 50               # Max par page
MAX_PAGES = 10               # 10 pages × 50 = 500 offres max

KEYWORDS = ["Data Engineer", "Data Scientist", "Data Analyst"]

# ============================================
# SCRAPER
# ============================================
def scrape_adzuna(keyword, max_pages=MAX_PAGES):
    print(f"\n{'='*60}")
    print(f"🔍 Adzuna Scraping : {keyword}")
    print(f"{'='*60}")

    conn = get_connection()
    if not conn:
        print("❌ Connexion DB impossible")
        return 0

    cur = conn.cursor()
    total_inseres = 0
    total_doublons = 0

    for page in range(1, max_pages + 1):
        params = {
            "app_id": APP_ID,
            "app_key": APP_KEY,
            "results_per_page": PAGE_SIZE,
            "what": keyword,
            "content-type": "application/json"
        }

        try:
            url = f"{BASE_URL}/{COUNTRY}/search/{page}"
            response = requests.get(url, params=params, timeout=15)
            print(f"  📡 Page {page} | Status : {response.status_code}")

            if response.status_code != 200:
                print(f"  ❌ Erreur : {response.text[:200]}")
                break

            data = response.json()
            offres = data.get("results", [])

            if not offres:
                print("  ⚠️ Plus d'offres")
                break

            for offre in offres:
                try:
                    external_id = str(offre.get("id", ""))
                    
                    # Vérifier doublon
                    cur.execute("""
                        SELECT id FROM jobs_raw
                        WHERE external_id = %s AND source = 'adzuna'
                    """, (external_id,))
                    
                    if cur.fetchone():
                        total_doublons += 1
                        continue

                    # Extraire les données
                    location_data = offre.get("location", {})
                    location_str = ", ".join(location_data.get("area", ["France"])[-2:])
                    
                    company = offre.get("company", {}).get("display_name", "N/A")
                    
                    salary_min = offre.get("salary_min")
                    salary_max = offre.get("salary_max")
                    salary = f"{salary_min}€ - {salary_max}€" if salary_min else "Non précisé"
                    
                    pub_date = offre.get("created", None)
                    if pub_date:
                        pub_date = datetime.strptime(pub_date[:10], "%Y-%m-%d")

                    cur.execute("""
                        INSERT INTO jobs_raw (
                            source, external_id, title, company,
                            location, city, department, url,
                            description, contract_type, salary,
                            publication_date, scraped_at
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s
                        )
                    """, (
                        "adzuna",
                        external_id,
                        offre.get("title", "N/A"),
                        company,
                        location_str,
                        location_str,
                        location_str,
                        offre.get("redirect_url", ""),
                        offre.get("description", ""),
                        offre.get("contract_type", "Non précisé"),
                        salary,
                        pub_date,
                        datetime.now()
                    ))
                    total_inseres += 1

                except Exception as e:
                    conn.rollback()
                    print(f"  ⚠️ Erreur insertion : {e}")

            conn.commit()
            print(f"  ✅ {total_inseres} insérées | 🔁 {total_doublons} doublons")

            # Pause pour respecter le rate limit
            time.sleep(1)

        except Exception as e:
            print(f"  ❌ Erreur page {page} : {e}")
            break

    cur.close()
    conn.close()
    print(f"\n📊 RÉSUMÉ Adzuna '{keyword}' : {total_inseres} insérées")
    return total_inseres


# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    total = 0
    for kw in KEYWORDS:
        total += scrape_adzuna(kw)
    print(f"\n🎉 Total Adzuna : {total} offres insérées")
