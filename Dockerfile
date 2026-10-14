FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# Corrige vulnerabilidades do pip herdado da imagem base antes do audit.
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
