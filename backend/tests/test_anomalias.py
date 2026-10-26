"""Anomalías de tráfico: lo habitual de cada dispositivo y cuándo una hora es un pico."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.monitor.anomalies import MB, Baseline, baseline, describe, human, is_spike, threshold

FACTOR, MIN_UP = 5.0, 100 * MB


def test_baseline_necesita_historia():
    assert baseline([1, 2, 3], min_samples=48) is None
    b = baseline(list(range(1, 101)), min_samples=48)
    assert b.samples == 100 and b.median == 50.5 and b.p95 == 96


def test_mediana_y_mad_resisten_a_horas_raras():
    # Una cámara que sube ~20 MB/h, con un par de horas raras (no mueven la mediana)
    values = [20 * MB] * 60 + [21 * MB] * 20 + [900 * MB, 1200 * MB]
    b = baseline(values, 48)
    assert b.median == 20 * MB
    assert b.mad == 0
    # Umbral: el mayor de 100 MB, 5 × 20 MB y 20 MB + 6σ (σ = 0) → 100 MB
    assert threshold(b, FACTOR, MIN_UP) == 100 * MB


def test_pico_de_subida_en_un_dispositivo_estable():
    b = baseline([20 * MB] * 60 + [22 * MB] * 20, 48)
    assert is_spike(850 * MB, b, FACTOR, MIN_UP)
    assert not is_spike(60 * MB, b, FACTOR, MIN_UP)          # triple de lo normal, pero poco
    assert not is_spike(99 * MB, b, FACTOR, MIN_UP)


def test_un_dispositivo_que_ya_varia_mucho_necesita_mas():
    # Un portátil: unas horas sube poco y otras mucho
    values = [5 * MB] * 30 + [200 * MB] * 30 + [600 * MB] * 20
    b = baseline(values, 48)
    t = threshold(b, FACTOR, MIN_UP)
    assert t > 600 * MB                                        # sus horas normales no saltan
    assert not is_spike(600 * MB, b, FACTOR, MIN_UP)
    assert is_spike(int(t) + 1, b, FACTOR, MIN_UP)


def test_sin_historia_no_hay_pico():
    assert not is_spike(10_000 * MB, None, FACTOR, MIN_UP)


def test_dispositivo_que_casi_no_sube():
    # Mediana 0 (un sensor que casi nunca sube): solo cuenta el mínimo absoluto
    b = Baseline(samples=60, median=0, mad=0, p95=1 * MB)
    assert threshold(b, FACTOR, MIN_UP) == MIN_UP
    assert is_spike(150 * MB, b, FACTOR, MIN_UP)


def test_textos():
    assert human(850 * MB) == "850,0 MB" and human(3 * 1024 ** 3) == "3,0 GB" and human(512) == "512 B"
    b = Baseline(samples=80, median=20 * MB, mad=1 * MB, p95=24 * MB)
    text = describe("upload", 850 * MB, b, datetime(2026, 10, 26, 14, 0, tzinfo=ZoneInfo("Europe/Madrid")))
    assert text.startswith("Ha subido 850,0 MB entre las 14:00 y las 15:00")
    assert "unos 20,0 MB por hora" in text and "copia de seguridad" in text
    assert describe("download", 3 * 1024 ** 3, b, datetime(2026, 10, 26, 23, 0)).startswith(
        "Ha descargado 3,0 GB entre las 23:00 y las 00:00")
