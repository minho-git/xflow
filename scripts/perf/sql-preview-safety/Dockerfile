# Build with the backend folder as context: docker build -t xflow-sqlprev -f Dockerfile ../../../backend
FROM python:3.10-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY requirements.txt .
# pymysql is imported by the MySQL paths but missing from requirements.txt
RUN uv pip install --system -r requirements.txt pymysql httpx
RUN python -c "import duckdb; c=duckdb.connect(); c.execute('INSTALL httpfs')"
