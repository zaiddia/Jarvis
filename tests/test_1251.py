"""Pruebas de la 12.51: techos de versión, revisión de librerías antes de compilar y conexión fijada (anti DNS rebinding)."""
import os
import socket
import ssl
import sys

import pytest

import confianza

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
import verificar_dependencias as vd  # noqa: E402


def test_cada_libreria_tiene_modulo_y_techo():
    reqs = vd.requirements()
    assert reqs and all(r in vd.MODULES for r in reqs)              # si agregas una a requirements.txt, dile su módulo
    caps = {ln.split("<")[0].strip().lower() for ln in open(os.path.join(HERE, "restricciones.txt"), encoding="utf-8")
            if "<" in ln and not ln.startswith("#")}
    sin = [r for r in reqs if r.lower() not in caps and r not in ("tzdata", "pywin32")]
    assert not sin, f"sin techo de versión: {sin}"
    assert vd.missing(["flask"]) == [] and vd.missing(["pywin32"], is_win=False) == []
    vd.MODULES["paquete-falso"] = "no_existe_este_modulo"
    try:
        assert vd.missing(["paquete-falso"])[0][0] == "paquete-falso"
    finally:
        del vd.MODULES["paquete-falso"]
    for wf in ("python-exe.yml", "python-app.yml"):
        src = open(os.path.join(HERE, ".github", "workflows", wf), encoding="utf-8").read()
        assert "restricciones.txt" in src and "verificar_dependencias.py" in src
    assert "-c restricciones.txt" in open(os.path.join(HERE, "instalar.bat"), encoding="utf-8").read()


def _dns(ip):
    return lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def test_no_se_conecta_a_tu_red_aunque_el_nombre_cambie(monkeypatch):
    monkeypatch.setattr(confianza.socket, "getaddrinfo", _dns("192.168.1.1"))
    called = []
    monkeypatch.setattr(confianza.socket, "create_connection", lambda *a, **k: called.append(a))
    with pytest.raises(confianza.PrivateAddress):
        confianza._PinnedHTTPConnection("pagina-mala.com", 80).connect()
    assert not called                                                # ni siquiera intentó conectarse


def test_se_conecta_justo_a_la_direccion_revisada(monkeypatch):
    monkeypatch.setattr(confianza.socket, "getaddrinfo", _dns("93.184.216.34"))
    got = []

    def conn(addr, timeout=None, source=None):
        got.append(addr)
        raise ConnectionRefusedError("prueba")
    monkeypatch.setattr(confianza.socket, "create_connection", conn)
    with pytest.raises(ConnectionRefusedError):
        confianza._PinnedHTTPConnection("ejemplo.com", 80).connect()
    assert got == [("93.184.216.34", 80)]
    # HTTPS: el certificado se pide para el nombre original, no para la IP
    seen = {}

    class Ctx(ssl.SSLContext):
        def wrap_socket(self, sock, server_hostname=None, **k):
            seen["name"] = server_hostname
            return sock
    monkeypatch.setattr(confianza.socket, "create_connection", lambda addr, *a: seen.update(addr=addr) or object())
    c = confianza._PinnedHTTPSConnection("ejemplo.com", 443, context=Ctx(ssl.PROTOCOL_TLS_CLIENT))
    c.connect()
    assert seen == {"addr": ("93.184.216.34", 443), "name": "ejemplo.com"}


def test_el_lector_de_paginas_usa_la_conexion_fijada(jv):
    import inspect
    from nucleo import avisos
    assert "PinnedHTTPSHandler" in inspect.getsource(avisos._get_public)
