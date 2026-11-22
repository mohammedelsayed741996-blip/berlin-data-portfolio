FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PORT=8000
WORKDIR /app
COPY requirements.txt requirements-aws.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-aws.txt
COPY src ./src
COPY docs/policies ./docs/policies
COPY lake/gold ./lake/gold
RUN useradd --create-home --uid 10001 app && mkdir -p /app/outputs && chown -R app /app/outputs
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["python", "-m", "agentlake.api"]
