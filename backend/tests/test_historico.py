"""Histórico de tráfico: tramos de las gráficas en hora local."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.monitor.traffic_queries import bucket_starts, fill_buckets, range_start_utc

TZ = ZoneInfo("Europe/Madrid")


def test_24h_por_horas_y_la_ultima_es_la_actual():
    now = datetime(2026, 10, 26, 14, 37, tzinfo=timezone.utc)          # 15:37 en Madrid
    starts = bucket_starts("24h", now, TZ)
    assert len(starts) == 24
    assert starts[-1] == datetime(2026, 10, 26, 15, 0)
    assert starts[0] == datetime(2026, 10, 25, 16, 0)


def test_30d_por_dias_y_1y_por_meses_cruzando_el_ano():
    now = datetime(2026, 2, 10, 12, tzinfo=timezone.utc)
    days = bucket_starts("30d", now, TZ)
    assert len(days) == 30 and days[-1] == datetime(2026, 2, 10) and days[0] == datetime(2026, 1, 12)
    months = bucket_starts("1y", now, TZ)
    assert len(months) == 12 and months[0] == datetime(2025, 3, 1) and months[-1] == datetime(2026, 2, 1)


def test_el_dia_lo_marca_la_hora_local():
    # 23:30 UTC del 25 son las 00:30 del 26 en Madrid (verano): el tramo es el día 26
    now = datetime(2026, 7, 25, 23, 30, tzinfo=timezone.utc)
    assert bucket_starts("30d", now, TZ)[-1] == datetime(2026, 7, 26)


def test_inicio_del_rango_en_utc():
    # El 25 de octubre de 2026 a las 3:00 acaba el horario de verano: las 16:00
    # de ese día en Madrid ya son UTC+1
    now = datetime(2026, 10, 26, 14, 37, tzinfo=timezone.utc)
    assert range_start_utc("24h", now, TZ) == datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
    # En verano (UTC+2): son las 16:37, el primer tramo empieza a las 17:00 del día anterior
    now = datetime(2026, 7, 26, 14, 37, tzinfo=timezone.utc)
    assert bucket_starts("24h", now, TZ)[0] == datetime(2026, 7, 25, 17, 0)
    assert range_start_utc("24h", now, TZ) == datetime(2026, 7, 25, 15, 0, tzinfo=timezone.utc)


def test_dia_del_cambio_de_hora():
    # Las 24 h que acaban el 25 de octubre a mediodía cruzan el cambio: los
    # tramos son horas locales, así que la 2:00 aparece una sola vez
    now = datetime(2026, 10, 25, 11, 30, tzinfo=timezone.utc)       # 12:30 en Madrid (ya UTC+1)
    starts = bucket_starts("24h", now, TZ)
    assert starts[-1] == datetime(2026, 10, 25, 12, 0) and starts[0] == datetime(2026, 10, 24, 13, 0)
    assert len(set(starts)) == 24


def test_tramos_sin_datos_a_cero():
    starts = [datetime(2026, 10, 26, h) for h in range(3)]
    buckets = fill_buckets(starts, {datetime(2026, 10, 26, 1): (10, 20)}, TZ)
    assert [(b.bytes_sent, b.bytes_recv) for b in buckets] == [(0, 0), (10, 20), (0, 0)]
    assert buckets[0].start.tzinfo == TZ
