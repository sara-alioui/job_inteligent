import time
import re
import sys
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

sys.path.insert(0, '/opt/airflow/scripts')
from db import get_connection

SELENIUM_HUB = 'http://job_selenium:4444/wd/hub'
BASE_URL = 'https://www.hellowork.com/fr-fr/emploi/recherche.html'
KEYWORDS = ['Data Engineer', 'Data Scientist', 'Data Analyst']
LOCATION = 'France'
MAX_PAGES = 5

def parse_date_relative(text):
    now = datetime.now()
    if not text:
        return now
    text = text.lower().strip()
    m = re.search(r'il y a (\d+)\s*(heure|jour|semaine|mois)', text)
    if not m:
        return now
    n, unit = int(m.group(1)), m.group(2)
    if 'heure'   in unit: return now - timedelta(hours=n)
    if 'jour'    in unit: return now - timedelta(days=n)
    if 'semaine' in unit: return now - timedelta(weeks=n)
    if 'mois'    in unit: return now - timedelta(days=n*30)
    return now

def parse_card(lines):
    lines = [l.strip() for l in lines if l.strip()]
    lines = [l for l in lines if "Voir l" not in l]
    titre = lines[0] if len(lines) > 0 else 'N/A'
    idx = 1
    if len(lines) > idx and 'super recruteur' in lines[idx].lower():
        idx += 1
    entreprise = lines[idx] if len(lines) > idx else 'N/A'; idx += 1
    lieu       = lines[idx] if len(lines) > idx else 'Non précisé'; idx += 1
    contrat    = lines[idx] if len(lines) > idx else 'Non précisé'; idx += 1
    salaire = 'Non précisé'
    if len(lines) > idx and '€' in lines[idx]:
        salaire = lines[idx].replace('\u202f', ' '); idx += 1
    pub_date = parse_date_relative(lines[idx] if len(lines) > idx else '')
    return titre, entreprise, lieu, contrat, salaire, pub_date

def scrape_hellowork_keyword(driver, keyword, conn):
    cur = conn.cursor()
    total_inseres = 0
    total_doublons = 0

    print(f"\n{'='*60}")
    print(f"🔍 HelloWork Scraping : {keyword}")
    print(f"{'='*60}")

    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}?k={keyword.replace(' ', '+')}&l={LOCATION}&p={page}"
        driver.get(url)
        time.sleep(4)

        if page == 1:
            try:
                btn = driver.find_element(By.XPATH, '//button[contains(text(),"Continuer sans accepter")]')
                btn.click()
                time.sleep(2)
            except:
                pass

        cards_btn = driver.find_elements(By.XPATH, '//*[contains(text(),"Voir l")]')
        if not cards_btn:
            print(f"  ⚠️ Page {page} : plus d'offres")
            break

        print(f"  📡 Page {page} : {len(cards_btn)} offres")

        for btn in cards_btn:
            try:
                card = btn.find_element(By.XPATH, '../..')
                try:
                    lien = card.find_element(By.XPATH, './/a')
                    url_offre = lien.get_attribute('href') or ''
                except:
                    url_offre = ''

                # external_id depuis l'URL
                m = re.search(r'/emplois/(\d+)', url_offre)
                external_id = m.group(1) if m else url_offre

                if not external_id:
                    continue

                cur.execute("SELECT id FROM jobs_raw WHERE external_id=%s AND source='hellowork'", (external_id,))
                if cur.fetchone():
                    total_doublons += 1
                    continue

                lines = card.text.strip().split('\n')
                titre, entreprise, lieu, contrat, salaire, pub_date = parse_card(lines)

                cur.execute("""
                    INSERT INTO jobs_raw (
                        source, external_id, title, company,
                        location, city, department, url,
                        description, contract_type, salary,
                        publication_date, scraped_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    'hellowork', external_id, titre, entreprise,
                    lieu, lieu, '', url_offre,
                    '', contrat, salaire,
                    pub_date, datetime.now()
                ))
                total_inseres += 1

            except Exception as e:
                conn.rollback()
                print(f"  ⚠️ Erreur carte : {e}")

        conn.commit()
        print(f"  ✅ {total_inseres} insérées | 🔁 {total_doublons} doublons")
        time.sleep(2)

    cur.close()
    return total_inseres

def main():
    opts = Options()
    driver = webdriver.Remote(command_executor=SELENIUM_HUB, options=opts)
    conn = get_connection()
    if not conn:
        print("❌ Connexion DB impossible")
        driver.quit()
        return 0

    total = 0
    try:
        for kw in KEYWORDS:
            total += scrape_hellowork_keyword(driver, kw, conn)
    finally:
        driver.quit()
        conn.close()

    print(f"\n🎉 Total HelloWork : {total} offres insérées")
    return total

if __name__ == "__main__":
    main()