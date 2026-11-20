FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY sql/ sql/
COPY tests/ tests/
COPY pytest.ini .
ENV PYTHONPATH=/app/src MPLBACKEND=Agg
CMD ["sh", "-c", "python -m pytest -q && python -m bus_network.pipeline --regenerate"]
