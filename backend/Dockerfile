FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema: nmap, iptables, ipset (listas de amenazas), conntrack (conexiones por
# dispositivo), dnsmasq (DHCP y DNS en modo router), tcpdump para captura
# de paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    nmap \
    iptables \
    ipset \
    conntrack \
    dnsmasq-base \
    tcpdump \
    net-tools \
    iproute2 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Cliente de PostgreSQL 16 para las copias de seguridad, del repositorio
# oficial de PostgreSQL: el de Debian 13 es el 17, y una copia hecha con él no
# la puede restaurar el pg_restore del contenedor de la base de datos (16).
# Si se cambia la versión de la imagen de la base de datos, cambiar también esta.
RUN install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
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
