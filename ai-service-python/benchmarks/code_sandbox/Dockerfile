FROM python:3.10-slim

RUN useradd --system --uid 10001 --no-create-home sandbox
COPY --chown=root:root probe.py /bench/probe.py
USER 10001:10001
ENTRYPOINT ["python", "/bench/probe.py"]
