# Draft Room for Fly.io (see gui/README.md, "Host it online").
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir espn-api==0.38.0

WORKDIR /app
COPY gui/ gui/
COPY library/ library/

# The password and ESPN cookies come from `fly secrets`; the pool and your draft live on the /data volume.
ENV DRAFTROOM_DATA=/data
EXPOSE 8080
CMD ["python", "-m", "gui", "--no-browser", "--host", "0.0.0.0", "--port", "8080"]
