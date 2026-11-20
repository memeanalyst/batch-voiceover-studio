FROM apify/actor-python:3.12
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
USER myuser
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=myuser:myuser . ./
# Bake the Phonon 31M model + English voice catalog into the image
# (runs must never download the model at startup).
USER root
RUN PHONON_ASSETS_DIR=/opt/phonon python fetch_assets.py \
    && chmod -R a+rX /opt/phonon
USER myuser
ENV PHONON_MODEL_DIR=/opt/phonon/model PHONON_CATALOG_DIR=/opt/phonon/catalog PYTHONWARNINGS=ignore
RUN python -m compileall -q bvs/ && python -m bvs.warm
CMD ["python", "-m", "bvs"]
