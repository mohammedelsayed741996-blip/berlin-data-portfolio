FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY contracts/ contracts/
COPY dbt_project/ dbt_project/
COPY tests/ tests/
ENV PYTHONPATH=/app/src MPLBACKEND=Agg
# The hash salt must come from the runtime environment, never from the image.
CMD ["sh", "-c", "python -m pytest -q && python -m saas_elt.cli simulate --workdir /tmp/workdir --fresh --output /app/outputs"]
