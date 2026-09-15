FROM python:3.11-slim
RUN pip install -q --disable-pip-version-check --root-user-action=ignore \
    fastapi==0.115.5 uvicorn==0.34.0 beanie==1.26.0 motor==3.6.0 boto3 duckdb==1.1.3 slowapi httpx
# 품질 검사가 매번 받는 DuckDB 확장을 미리 받아 둔다 — 측정에 다운로드 시간이 섞이지 않게
RUN python -c "import duckdb; c=duckdb.connect(); c.execute('INSTALL httpfs; INSTALL aws')"
