from db import init_db
from scrapers import scrape_france_travail

def run_pipeline():
    print("=== DÉMARRAGE DU PIPELINE DATA SCIENTIST ===\n")
    
    # Étape 1 : S'assurer que la base de données est prête
    print("Étape 1/2 : Initialisation de la Base de Données...")
    init_db()
    
    # Étape 2 : Lancer la collecte de données
    print("\nÉtape 2/2 : Lancement du Scraping...")
    # Tu peux changer "Data Engineer" par "Data Analyst" pour tester
    scrape_france_travail(keyword="Data Engineer") 
    
    print("\n=== PIPELINE TERMINÉ AVEC SUCCÈS ===")
    print("Vérifie tes données sur PgAdmin : http://localhost:5050")

if __name__ == "__main__":
    run_pipeline()
