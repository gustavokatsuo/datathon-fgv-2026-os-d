"""Cliente HTTP com cache local em disco.

Toda resposta bruta é salva em data/raw/ (JSON comprimido com gzip). Se o
arquivo já existe, ele é lido do disco e nenhuma requisição é feita.
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

USER_AGENT = "datathon-fgv-2026-research/0.1"
MIN_INTERVAL_S = 0.2  # intervalo mínimo entre o início de duas requisições (rate limit)
MAX_RETRIES = 5
N_WORKERS = 8  # downloads simultâneos

_local = threading.local()
_lock = threading.Lock()
_last_request = 0.0

T = TypeVar("T")
R = TypeVar("R")


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        _local.session = s
    return _local.session


class HTTPFailure(RuntimeError):
    """Falha definitiva (status 4xx que não é 429, ou retries esgotados)."""

    def __init__(self, url: str, status: int | None, body: str):
        super().__init__(f"{status} {url}: {body[:200]}")
        self.status = status


def _throttle() -> None:
    """Espaça o início das requisições entre todas as threads."""
    global _last_request
    with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def parallel_map(fn: Callable[[T], R], items: Iterable[T], label: str = "") -> list[R]:
    """Aplica fn em paralelo preservando a ordem e registrando o progresso."""
    items = list(items)
    out: list[R] = []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        for i, res in enumerate(ex.map(fn, items), 1):
            out.append(res)
            if i % 50 == 0 or i == len(items):
                log.info("%s %d/%d", label, i, len(items))
    return out


def fetch_json(url: str, params: dict | None = None, timeout: int = 120) -> Any:
    """GET com retry exponencial para 429 e 5xx."""
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            r = _session().get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            log.warning("erro de rede em %s (%s), tentativa %d", url, exc, attempt + 1)
            time.sleep(2**attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429 or r.status_code >= 500:
            log.warning("status %s em %s, tentativa %d", r.status_code, url, attempt + 1)
            time.sleep(2 ** (attempt + 1))
            continue
        raise HTTPFailure(r.url, r.status_code, r.text)
    raise HTTPFailure(url, None, "retries esgotados")


def read_cache(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_cache(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    tmp.replace(path)


def cached_json(url: str, path: Path, params: dict | None = None) -> Any:
    """Retorna o JSON do cache se existir, senão baixa e salva."""
    if path.exists():
        return read_cache(path)
    data = fetch_json(url, params=params)
    write_cache(path, data)
    return data
