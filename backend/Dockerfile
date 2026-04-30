FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema: nmap, iptables, tcpdump para captura de paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    iptables \
    tcpdump \
    net-tools \
    iproute2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
