FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema: nmap, iptables, conntrack (conexiones por
# dispositivo), dnsmasq (DHCP y DNS en modo router), tcpdump para captura
# de paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    nmap \
    iptables \
    conntrack \
    dnsmasq-base \
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

# Solo en 127.0.0.1: el contenedor usa la red del equipo, y así la API no
# queda abierta en la LAN por HTTP. Desde fuera se llega por el nginx del
# frontend, con HTTPS (panel, /api y /docs).
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
