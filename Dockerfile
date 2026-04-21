FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app/data/home \
    HF_HOME=/app/data/hf-home \
    TRANSFORMERS_CACHE=/app/data/transformers-cache

RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN mkdir -p /app/data /app/opa/policies /app/data/home /app/data/hf-home /app/data/transformers-cache
RUN chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
