# Build from the repo root: docker build -f apps/frontend/Dockerfile .
ARG PYTHON_IMAGE=python:3.12.16-slim-trixie
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements/constraints.txt apps/frontend/requirements.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

COPY apps/frontend/app.py apps/frontend/gunicorn.conf.py ./
COPY apps/frontend/templates/ ./templates/

# Numeric UID, so Kubernetes runAsNonRoot can verify it. Files stay owned by root.
RUN useradd --uid 10001 --no-create-home app
USER 10001

EXPOSE 8080
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
