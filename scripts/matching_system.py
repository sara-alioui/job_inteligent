import pandas as pd
import psycopg2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
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
# CHARGEMENT DES DONNÉES
# ============================================
def load_jobs():
    conn = get_connection()
    query = """
        SELECT id, title, company, location, job_category, 
               description, skills, contract_type, salary
        FROM jobs_cleaned
        WHERE description != '' AND skills != ''
    """
    df = pd.read_sql(query, conn)
    conn.close()
    print(f"✅ {len(df)} offres chargées pour le matching")
    return df

# ============================================
# VECTORISATION TF-IDF
# ============================================
def build_tfidf_matrix(df):
    """Crée la matrice TF-IDF à partir des descriptions + compétences"""
    
    # Combiner description + compétences pour enrichir le texte
    df['text_combined'] = (
        df['title'].fillna('') + ' ' +
        df['description'].fillna('') + ' ' +
        df['skills'].fillna('')
    )
    
    # Nettoyer le texte combiné
    df['text_clean'] = df['text_combined'].apply(clean_text)
    
    # TF-IDF avec paramètres optimisés pour le français
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words=['de', 'la', 'le', 'les', 'et', 'des', 'du', 'un', 'une',
                     'en', 'dans', 'pour', 'par', 'au', 'aux', 'avec', 'est',
                     'sur', 'son', 'sa', 'ses', 'nous', 'vous', 'ils', 'elle',
                     'qui', 'que', 'ce', 'se', 'ne', 'pas', 'plus', 'ou',
                     'but', 'the', 'and', 'for', 'with', 'are', 'is', 'in',
                     'to', 'of', 'a', 'an', 'this', 'that', 'it', 'you',
                     'will', 'your', 'our', 'we', 'as', 'be', 'has', 'have'],
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.85
    )
    
    tfidf_matrix = vectorizer.fit_transform(df['text_clean'])
    print(f"✅ Matrice TF-IDF créée : {tfidf_matrix.shape[0]} offres × {tfidf_matrix.shape[1]} termes")
    
    return vectorizer, tfidf_matrix

def clean_text(text):
    if not text:
        return ''
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

# ============================================
# SYSTÈME DE RECOMMANDATION
# ============================================
def recommend_jobs(profile_text, df, vectorizer, tfidf_matrix, top_n=10, 
                   category=None, location=None):
    """
    Recommande des offres basées sur un profil utilisateur.
    
    Args:
        profile_text: Compétences et expérience du candidat (ex: "Python SQL Spark Azure")
        df: DataFrame des offres
        vectorizer: Vectorizer TF-IDF entraîné
        tfidf_matrix: Matrice TF-IDF des offres
        top_n: Nombre de résultats à retourner
        category: Filtrer par catégorie (Data Engineer, Data Scientist, etc.)
        location: Filtrer par localisation
    """
    
    # Vectoriser le profil utilisateur
    profile_clean = clean_text(profile_text)
    profile_vector = vectorizer.transform([profile_clean])
    
    # Calculer la similarité cosinus
    similarities = cosine_similarity(profile_vector, tfidf_matrix).flatten()
    
    # Ajouter le score au DataFrame
    df_result = df.copy()
    df_result['match_score'] = similarities
    
    # Filtrer par catégorie si demandé
    if category:
        df_result = df_result[df_result['job_category'] == category]
    
    # Filtrer par localisation si demandé
    if location:
        location_lower = location.lower()
        df_result = df_result[df_result['location'].str.lower().str.contains(location_lower, na=False)]
    
    # Trier par score et prendre top_n
    df_result = df_result.sort_values('match_score', ascending=False).head(top_n)
    
    return df_result

# ============================================
# AFFICHAGE DES RÉSULTATS
# ============================================
def display_results(results, profile_text):
    if len(results) == 0:
        print("❌ Aucune offre trouvée pour ces critères.")
        return
    
    print("\n" + "="*70)
    print(f"🎯 RÉSULTATS POUR : \"{profile_text}\"")
    print(f"📊 {len(results)} offres trouvées")
    print("="*70)
    
    for i, (_, row) in enumerate(results.iterrows(), 1):
        score_pct = row['match_score'] * 100
        # Barre visuelle du score
        bar = "█" * int(score_pct / 5) + "░" * (20 - int(score_pct / 5))
        
        print(f"\n{'─'*70}")
        print(f"#{i}  [{bar}] {score_pct:.1f}%")
        print(f"    📌 {row['title']}")
        print(f"    🏢 {row['company']}  |  📍 {row['location']}")
        print(f"    🏷️  {row['job_category']}  |  💼 {row['contract_type']}")
        print(f"    🛠️  {row['skills'][:80]}{'...' if len(str(row['skills'])) > 80 else ''}")
    
    print(f"\n{'='*70}")

# ============================================
# MODE INTERACTIF
# ============================================
def interactive_mode(df, vectorizer, tfidf_matrix):
    """Mode interactif pour tester le système"""
    
    print("\n" + "🧠 SYSTÈME DE RECOMMANDATION JOB INTELLIGENT ".center(70, "="))
    print("Tape 'quit' pour quitter")
    print("="*70)
    
    while True:
        print("\n🔍 Entrez votre profil (compétences, expérience) :")
        profile = input("> ").strip()
        
        if profile.lower() == 'quit':
            print("👋 Au revoir !")
            break
        
        if not profile:
            continue
        
        print("\n🏷️ Catégorie ? (laisser vide pour toutes)")
        print("    Data Engineer / Data Scientist / Data Analyst / Autre")
        category = input("> ").strip() or None
        
        print("\n📍 Localisation ? (laisser vide pour toutes)")
        location = input("> ").strip() or None
        
        results = recommend_jobs(
            profile, df, vectorizer, tfidf_matrix,
            top_n=5, category=category, location=location
        )
        
        display_results(results, profile)

# ============================================
# MODE DÉMO
# ============================================
def demo_mode(df, vectorizer, tfidf_matrix):
    """Lance des démos automatiques"""
    
    demos = [
        {
            "profile": "Python SQL Spark Hadoop DataLake ETL streaming",
            "category": "Data Engineer",
            "location": None,
            "label": "🔥 Profil Data Engineer Senior"
        },
        {
            "profile": "Python Machine Learning Deep Learning NLP TensorFlow modèle prédictif",
            "category": "Data Scientist",
            "location": None,
            "label": "🔥 Profil Data Scientist ML"
        },
        {
            "profile": "Power BI Tableau SQL Excel reporting dashboard KPI",
            "category": "Data Analyst",
            "location": "paris",
            "label": "🔥 Profil Data Analyst BI à Paris"
        },
    ]
    
    for demo in demos:
        print(f"\n\n{'🌟'*35}")
        print(f"  {demo['label']}")
        print(f"{'🌟'*35}")
        
        results = recommend_jobs(
            demo['profile'], df, vectorizer, tfidf_matrix,
            top_n=5, category=demo['category'], location=demo['location']
        )
        display_results(results, demo['profile'])

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    # Charger les données
    df = load_jobs()
    
    # Construire la matrice TF-IDF
    vectorizer, tfidf_matrix = build_tfidf_matrix(df)
    
    # Lancer la démo
    demo_mode(df, vectorizer, tfidf_matrix)
    
    # Proposer le mode interactif
    print("\n\n" + "="*70)
    print("🎮 Tu veux tester avec ton propre profil ?")
    print("="*70)
    choice = input("Tape 'oui' pour le mode interactif, sinon Entrée : ").strip().lower()
    
    if choice == 'oui':
        interactive_mode(df, vectorizer, tfidf_matrix)
    
    print("\n🎉 Merci d'avoir utilisé Job Intelligent !")
