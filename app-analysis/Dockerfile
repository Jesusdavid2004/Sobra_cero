# Build context is the repository root (it reuses the pure modules of app-backend):
#   docker build -f app-analysis/Dockerfile -t sobracero-analysis .
FROM python:3.12-slim
WORKDIR /srv
COPY app-analysis/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app-backend/app/__init__.py app/__init__.py
COPY app-backend/app/domain app/domain
COPY app-backend/app/application app/application
COPY app-backend/app/infrastructure/__init__.py app/infrastructure/__init__.py
COPY app-backend/app/infrastructure/prediction app/infrastructure/prediction
COPY app-backend/app/infrastructure/analysis app/infrastructure/analysis
COPY app-analysis/server.py server.py
ENV PYTHONPATH=/srv PYTHONUNBUFFERED=1
EXPOSE 50051
CMD ["python", "server.py"]
