FROM python:3.13.9-slim@sha256:326df678c20c78d465db501563f3492d17c42a4afe33a1f2bf5406a1d56b0e86

RUN useradd --system --uid 10001 --no-create-home worker
COPY --chown=root:root fixed_template.py /worker/fixed_template.py
USER 10001:10001
ENTRYPOINT ["env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "python", "-I", "/worker/fixed_template.py"]
