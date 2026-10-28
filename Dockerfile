FROM python:3.11-slim

WORKDIR /app

RUN pip install --default-timeout=300 --retries=10 \
    flask \
    flask-cors \
    psycopg2-binary \
    scikit-learn \
    numpy

COPY api.py .

CMD ["python", "api.py"]