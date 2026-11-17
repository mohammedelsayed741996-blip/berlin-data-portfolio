FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY sql/ sql/
COPY data/ data/
COPY tests/ tests/

ENV PYTHONPATH=/app/src MPLBACKEND=Agg
# Run the tests, then the full pipeline. Outputs land in /app/outputs.
CMD ["sh", "-c", "python -m pytest -q && python -m solar_credit.pipeline"]
