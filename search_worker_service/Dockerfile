# CafresoHQ search-network worker — standalone, minimal image.
#
# Deliberately NOT oci-fleet/Dockerfile: no Node, no build-essential, no
# ripgrep, no hermes-agent, no UI build stage. This service is worker.py and
# nothing else — see worker.py's module docstring for why.
FROM python:3.11-slim-bookworm

WORKDIR /app
COPY search_worker_service/worker.py ./worker.py

ENV CAFRESOHQ_HQ_STATE_DIR=/data/hq-state
ENV PYTHONUNBUFFERED=1
RUN mkdir -p /data/hq-state

EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8788/health',timeout=5).status==200 else 1)"

ENTRYPOINT ["python3", "worker.py"]
