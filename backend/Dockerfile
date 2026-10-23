FROM python:3.11-slim

WORKDIR /app

# System deps occasionally needed by Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the app as an unprivileged user (UID 1000 matches the first user on most Ubuntu hosts,
# so you can still read ./backups from the host without sudo).
ARG APP_UID=1000
RUN groupadd --gid "$APP_UID" app \
 && useradd --uid "$APP_UID" --gid app --no-create-home --shell /usr/sbin/nologin app \
 && chmod 755 /app/docker-entrypoint.sh

EXPOSE 8001

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
