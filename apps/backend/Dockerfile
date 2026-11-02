# Build from the repo root: docker build -f apps/backend/Dockerfile .
ARG PYTHON_IMAGE=python:3.12.16-slim-trixie
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements/constraints.txt apps/backend/requirements.txt ./
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

COPY apps/backend/app.py apps/backend/gunicorn.conf.py ./

# Numeric UID, so Kubernetes runAsNonRoot can verify it. Files stay owned by root.
RUN useradd --uid 10001 --no-create-home app
USER 10001

EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
