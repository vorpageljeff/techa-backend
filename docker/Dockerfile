FROM python:3.11-slim

# Garante UTF-8 no ambiente (evita double-encoding de strings não-ASCII)
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

# Instala GDAL (dependência do Rasterio)
RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
