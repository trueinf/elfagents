# The elfagent API.
#
# This is a long-lived container, not a function. The run endpoint holds an SSE
# connection open for a minute or more while four agents reason in parallel,
# which is why the API cannot live on the same platform as the front end.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY elfagent/ elfagent/
COPY api/ api/
COPY dbt/ dbt/
COPY data/seed/ data/seed/

# Build the warehouse at image-build time. The seed CSVs are the source of
# truth and the .duckdb file is a build artefact — baking it in means the
# container starts with a warehouse already there, and `dbt build` failing is
# a build failure rather than a runtime surprise.
RUN cd dbt && dbt build --profiles-dir . --target dev

# Move the warehouse OUT of /app/data. That path is where a persistence volume
# gets mounted, and a mount replaces the directory wholesale — taking the
# baked-in warehouse with it. Build artefact and runtime state get their own
# directories so mounting one cannot destroy the other.
RUN mkdir -p /app/warehouse && mv /app/data/elfagent.duckdb /app/warehouse/
ENV ELFAGENT_WAREHOUSE=/app/warehouse/elfagent.duckdb

# Checkpoints are runtime state. Mount a volume here to keep paused runs
# across redeploys; without one the filesystem is ephemeral and they are lost.
ENV ELFAGENT_CHECKPOINTS=/app/data/checkpoints.sqlite

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
