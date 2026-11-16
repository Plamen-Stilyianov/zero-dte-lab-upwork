FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pyproject.toml /app/
COPY src/ /app/src/
RUN pip install --no-cache-dir ".[audit]"
COPY config.example.json config.synthetic.json /app/
COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
RUN mkdir -p /app/data /app/results && useradd -u 10001 -m bot && chown -R bot:bot /app
USER bot
CMD ["python", "-m", "zerodte.paper_watch", "--config", "config.example.json"]
