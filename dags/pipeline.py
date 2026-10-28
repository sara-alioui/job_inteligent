from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule
from datetime import datetime, timedelta
import logging

default_args = {
    'owner': 'job_intelligent',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0,
    'retry_delay': timedelta(minutes=5),
}

SCRAPER_TIMEOUTS = {
    'france_travail': timedelta(minutes=30),
    'indeed':         timedelta(minutes=20),
    'adzuna':         timedelta(minutes=20),
    'hellowork':      timedelta(minutes=40),
}

with DAG(
    dag_id='job_intelligent_pipeline',
    default_args=default_args,
    description='Pipeline resilient : Scraping parallele → Nettoyage → Skills',
    schedule_interval='0 8 * * *',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['scraping', 'data', 'pipeline', 'resilient'],
) as dag:

    init_db = BashOperator(
        task_id='init_db',
        bash_command='cd /opt/airflow/scripts && python db.py',
        env={'DB_HOST': 'postgres'},
    )

    def run_scraper_safe(scraper_module: str, task_id: str, **context):
        import subprocess
        import traceback
        import time
        import sys
        sys.path.insert(0, '/opt/airflow/scripts')
        ti = context['ti']
        start = time.time()
        logging.info(f"[{task_id}] ▶ Demarrage scraper '{scraper_module}'")
        try:
            proc = subprocess.run(
                ['python', f'/opt/airflow/scripts/{scraper_module}.py'],
                capture_output=True,
                text=True,
                timeout=None
            )
            stdout_tail = proc.stdout[-3000:] if len(proc.stdout) > 3000 else proc.stdout
            logging.info(stdout_tail)
            if proc.returncode != 0:
                raise RuntimeError(f"Exit code {proc.returncode}: {proc.stderr[-1000:]}")
            elapsed = round(time.time() - start, 1)
            logging.info(f"[{task_id}] ✅ Termine en {elapsed}s")
            ti.xcom_push(key=f'{task_id}_status', value={'status': 'success', 'elapsed_s': elapsed})
        except Exception as exc:
            elapsed = round(time.time() - start, 1)
            logging.error(f"[{task_id}] ❌ ERREUR apres {elapsed}s : {traceback.format_exc()}")
            ti.xcom_push(key=f'{task_id}_status', value={'status': 'failed', 'elapsed_s': elapsed, 'error': str(exc)[:500]})
            return f"SKIPPED:{task_id}"

    scrape_france_travail = PythonOperator(
        task_id='scrape_france_travail',
        python_callable=run_scraper_safe,
        op_kwargs={'scraper_module': 'scraper_france_travail', 'task_id': 'scrape_france_travail'},
        execution_timeout=SCRAPER_TIMEOUTS['france_travail'],
    )

    scrape_indeed = PythonOperator(
        task_id='scrape_indeed',
        python_callable=run_scraper_safe,
        op_kwargs={'scraper_module': 'scraper_indeed', 'task_id': 'scrape_indeed'},
        execution_timeout=SCRAPER_TIMEOUTS['indeed'],
    )

    scrape_adzuna = PythonOperator(
        task_id='scrape_adzuna',
        python_callable=run_scraper_safe,
        op_kwargs={'scraper_module': 'scraper_adzuna', 'task_id': 'scrape_adzuna'},
        execution_timeout=SCRAPER_TIMEOUTS['adzuna'],
    )

    scrape_hellowork = PythonOperator(
        task_id='scrape_hellowork',
        python_callable=run_scraper_safe,
        op_kwargs={'scraper_module': 'scraper_hellowork', 'task_id': 'scrape_hellowork'},
        execution_timeout=SCRAPER_TIMEOUTS['hellowork'],
    )

    ALL_SCRAPERS = [
        scrape_france_travail,
        scrape_indeed,
        scrape_adzuna,
        scrape_hellowork,
    ]

    def check_scraper_results(**context):
        ti = context['ti']
        scraper_ids = [
            'scrape_france_travail', 'scrape_indeed',
            'scrape_adzuna', 'scrape_hellowork',
        ]
        results = {}
        for sid in scraper_ids:
            val = ti.xcom_pull(task_ids=sid, key=f'{sid}_status')
            results[sid] = val or {'status': 'timeout_or_killed'}

        success = [k for k, v in results.items() if isinstance(v, dict) and v.get('status') == 'success']
        failed  = [k for k, v in results.items() if not (isinstance(v, dict) and v.get('status') == 'success')]

        logging.info("=" * 60)
        logging.info("📊 BILAN SCRAPERS")
        logging.info("=" * 60)
        for sid, res in results.items():
            icon = "✅" if isinstance(res, dict) and res.get('status') == 'success' else "❌"
            elapsed = res.get('elapsed_s', '?') if isinstance(res, dict) else '?'
            logging.info(f"  {icon} {sid:30s} ({elapsed}s)")
        logging.info(f"Resultat : {len(success)}/{len(scraper_ids)} scrapers OK")
        logging.info("=" * 60)

        if len(success) == 0:
            raise RuntimeError("Aucun scraper n'a reussi ! Pipeline arrete.")

        ti.xcom_push(key='scraper_summary', value={'success': success, 'failed': failed, 'total': len(scraper_ids)})
        return f"{len(success)}/{len(scraper_ids)} scrapers OK"

    check_scrapers = PythonOperator(
        task_id='check_scrapers',
        python_callable=check_scraper_results,
        trigger_rule=TriggerRule.ALL_DONE,
    )

    clean_data = BashOperator(
        task_id='clean_data',
        bash_command='cd /opt/airflow/scripts && python clean_data.py',
        env={'DB_HOST': 'postgres'},
        execution_timeout=timedelta(minutes=15),
    )

    extract_skills = BashOperator(
        task_id='extract_skills',
        bash_command='cd /opt/airflow/scripts && python extract_skills.py',
        env={'DB_HOST': 'postgres'},
        execution_timeout=timedelta(minutes=15),
    )

    generate_embeddings = BashOperator(
        task_id='generate_embeddings',
        bash_command='cd /opt/airflow/scripts && python generate_embeddings.py',
    )

    recommend_jobs = BashOperator(
        task_id='recommend_jobs',
        bash_command='cd /opt/airflow/scripts && python recommend_jobs.py',
    )

    def build_rapport(**context):
        import psycopg2, os
        ti = context['ti']
        scraper_summary = ti.xcom_pull(task_ids='check_scrapers', key='scraper_summary') or {}
        try:
            conn = psycopg2.connect(host=os.getenv('DB_HOST', 'postgres'), database='job_intelligent', user='admin', password='admin123', port='5432')
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM jobs_raw');    raw     = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM jobs_cleaned'); cleaned = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM job_skills');   skills  = cur.fetchone()[0]
            cur.execute('SELECT source, COUNT(*) FROM jobs_raw GROUP BY source ORDER BY COUNT(*) DESC')
            sources = cur.fetchall()
            cur.close(); conn.close()
        except Exception as e:
            logging.error(f"Erreur rapport DB : {e}")
            raw = cleaned = skills = 0; sources = []

        success_list = scraper_summary.get('success', [])
        failed_list  = scraper_summary.get('failed', [])
        total        = scraper_summary.get('total', 0)

        print('=' * 60)
        print('📊 RAPPORT PIPELINE JOB INTELLIGENT')
        print('=' * 60)
        print(f'jobs_raw    : {raw} offres')
        print(f'jobs_cleaned: {cleaned} offres')
        print(f'job_skills  : {skills} liens')
        print('Par source :')
        for s in sources: print(f'  {s[0]}: {s[1]}')
        print(f'  ✅ Reussis ({len(success_list)}/{total}): {", ".join(success_list) or "aucun"}')
        print(f'  ❌ Ignores ({len(failed_list)}/{total}): {", ".join(failed_list) or "aucun"}')
        print('=' * 60)
        print('✅ Pipeline termine !')

    rapport_final = PythonOperator(
        task_id='rapport_final',
        python_callable=build_rapport,
    )

    init_db >> ALL_SCRAPERS >> check_scrapers
    check_scrapers >> clean_data >> extract_skills >> rapport_final
    rapport_final >> generate_embeddings >> recommend_jobs