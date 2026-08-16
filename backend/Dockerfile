FROM python:3.11.11-slim

WORKDIR /app

# Build dependencies: gcc for numpy/scikit-learn, libpq-dev for asyncpg/psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install all deps including numpy/node2vec (builds fine on Python 3.11 + gcc)
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
