"""Gunicorn settings for the backend. Read by: gunicorn -c gunicorn.conf.py app:app"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Fixed at 1: each process has its own Prometheus registry, so scale with replicas (D-012).
workers = 1
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))

timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "30"))

# Control socket (gunicorn >= 25.1) is not used: scaling is via Kubernetes replicas, and
# UID 10001 has no writable home folder for the socket file.
control_socket_disable = True
