"""Salvar e abrir projetos do AMOSTRAS FRA 2.0 (sessão completa).

Um **projeto** (``.fra`` — JSON) guarda a sessão inteira, de modo que
reabrir restaura tudo exatamente como estava:

* medições FRA/EIS (com a marca de **corrigido** e as observações);
* curvas I-V;
* a biblioteca de **correções do instrumento**;
* os **ajustes de circuito equivalente** (FRA);
* os **ajustes do modelo de diodo** (curva I-V);
* as validações de **Kramers-Kronig**;
* as **cores** por curva, a **ordem** e o estado de **marcação** das
  amostras.

Ao contrário do CSV (dados tabulares, interoperável com Excel), o
projeto preserva os metadados e os objetos ricos da sessão.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from circuitos import FitResult
from correcao import InstrumentCorrection
from iv_model import IVFitResult
from kk import KKResult
from util import APP_NAME, APP_VERSION, IVCurve, Measurement

logger = logging.getLogger(__name__)

#: Versão do formato do arquivo de projeto.
FORMAT_VERSION: int = 1

#: Extensão sugerida para arquivos de projeto.
PROJECT_SUFFIX: str = ".fra"


# ---------------------------------------------------------------------------
# Conversão de arrays (com tratamento de valores não finitos → null)
# ---------------------------------------------------------------------------
def _num(value: float) -> float | None:
    """Número finito, ou ``None`` para NaN/Inf (JSON válido)."""
    v = float(value)
    return v if math.isfinite(v) else None


def _arr(values) -> list[float | None]:
    """Array 1-D como lista de floats (não finitos viram ``None``)."""
    return [_num(x) for x in np.asarray(values, dtype=float).ravel()]


def _to_np(values) -> np.ndarray:
    """Lista (possivelmente com ``None``) em array de floats (None→NaN)."""
    return np.asarray(
        [np.nan if v is None else float(v) for v in values], dtype=float
    )


def _carr(z) -> dict[str, list[float | None]]:
    """Array complexo como ``{"re": [...], "im": [...]}``."""
    z = np.asarray(z, dtype=complex).ravel()
    return {"re": _arr(z.real), "im": _arr(z.imag)}


def _to_complex(data: dict) -> np.ndarray:
    """Reconstrói um array complexo de ``{"re": ..., "im": ...}``."""
    return _to_np(data["re"]) + 1j * _to_np(data["im"])


# ---------------------------------------------------------------------------
# (De)serialização de cada tipo
# ---------------------------------------------------------------------------
def _measurement_to(m: Measurement) -> dict:
    return {
        "name": m.name,
        "frequency": _arr(m.frequency),
        "z_real": _arr(m.z_real),
        "z_imag": _arr(m.z_imag),
        "corrected": bool(m.corrected),
        "notes": m.notes,
    }


def _measurement_from(d: dict) -> Measurement:
    return Measurement(
        name=d["name"],
        frequency=_to_np(d["frequency"]),
        z_real=_to_np(d["z_real"]),
        z_imag=_to_np(d["z_imag"]),
        corrected=bool(d.get("corrected", False)),
        notes=d.get("notes", ""),
    )


def _iv_to(c: IVCurve) -> dict:
    return {
        "name": c.name,
        "voltage": _arr(c.voltage),
        "current": _arr(c.current),
        "notes": getattr(c, "notes", ""),
    }


def _iv_from(d: dict) -> IVCurve:
    return IVCurve(
        name=d["name"],
        voltage=_to_np(d["voltage"]),
        current=_to_np(d["current"]),
        notes=d.get("notes", ""),
    )


def _correction_to(k: InstrumentCorrection) -> dict:
    return {
        "name": k.name,
        "frequency": _arr(k.frequency),
        "magnitude": _arr(k.magnitude),
        "phase_deg": _arr(k.phase_deg),
        "r_nominal": float(k.r_nominal),
    }


def _correction_from(d: dict) -> InstrumentCorrection:
    return InstrumentCorrection(
        frequency=_to_np(d["frequency"]),
        magnitude=_to_np(d["magnitude"]),
        phase_deg=_to_np(d["phase_deg"]),
        r_nominal=float(d["r_nominal"]),
        name=d.get("name", "Correção"),
    )


def _fit_to(r: FitResult) -> dict:
    return {
        "measurement_name": r.measurement_name,
        "model_key": r.model_key,
        "model_name": r.model_name,
        "circuit_string": r.circuit_string,
        "param_names": list(r.param_names),
        "param_units": list(r.param_units),
        "param_values": _arr(r.param_values),
        "param_errors": _arr(r.param_errors),
        "frequency": _arr(r.frequency),
        "z_exp": _carr(r.z_exp),
        "z_fit": _carr(r.z_fit),
        "chi_squared": _num(r.chi_squared),
        "chi_squared_reduced": _num(r.chi_squared_reduced),
        "rmse": _num(r.rmse),
        "r_squared": _num(r.r_squared),
        "extra": {k: _num(v) for k, v in r.extra.items()},
    }


def _fit_from(d: dict) -> FitResult:
    return FitResult(
        measurement_name=d["measurement_name"],
        model_key=d["model_key"],
        model_name=d["model_name"],
        circuit_string=d["circuit_string"],
        param_names=tuple(d["param_names"]),
        param_units=tuple(d["param_units"]),
        param_values=_to_np(d["param_values"]),
        param_errors=_to_np(d["param_errors"]),
        frequency=_to_np(d["frequency"]),
        z_exp=_to_complex(d["z_exp"]),
        z_fit=_to_complex(d["z_fit"]),
        chi_squared=float(d.get("chi_squared") or 0.0),
        chi_squared_reduced=float(d.get("chi_squared_reduced") or 0.0),
        rmse=float(d.get("rmse") or 0.0),
        r_squared=float(d.get("r_squared") or 0.0),
        extra={k: (v if v is not None else float("nan"))
               for k, v in d.get("extra", {}).items()},
    )


def _iv_fit_to(r: IVFitResult) -> dict:
    return {
        "curve_name": r.curve_name,
        "param_values": _arr(r.param_values),
        "param_errors": _arr(r.param_errors),
        "voltage": _arr(r.voltage),
        "current_exp": _arr(r.current_exp),
        "current_fit": _arr(r.current_fit),
        "rmse": _num(r.rmse),
        "r_squared": _num(r.r_squared),
        "dark": bool(r.dark),
        "sign": float(r.sign),
    }


def _iv_fit_from(d: dict) -> IVFitResult:
    return IVFitResult(
        curve_name=d["curve_name"],
        param_values=_to_np(d["param_values"]),
        param_errors=_to_np(d["param_errors"]),
        voltage=_to_np(d["voltage"]),
        current_exp=_to_np(d["current_exp"]),
        current_fit=_to_np(d["current_fit"]),
        rmse=float(d.get("rmse") or 0.0),
        r_squared=float(d.get("r_squared") or 0.0),
        dark=bool(d.get("dark", False)),
        sign=float(d.get("sign", 1.0)),
    )


def _kk_to(r: KKResult) -> dict:
    return {
        "measurement_name": r.measurement_name,
        "frequency": _arr(r.frequency),
        "z_real_exp": _arr(r.z_real_exp),
        "z_imag_exp": _arr(r.z_imag_exp),
        "z_real_kk": _arr(r.z_real_kk),
        "z_imag_kk": _arr(r.z_imag_kk),
        "r_inf": _num(r.r_inf),
        "metrics": {k: _num(v) for k, v in r.metrics.items()},
    }


def _kk_from(d: dict) -> KKResult:
    return KKResult(
        measurement_name=d["measurement_name"],
        frequency=_to_np(d["frequency"]),
        z_real_exp=_to_np(d["z_real_exp"]),
        z_imag_exp=_to_np(d["z_imag_exp"]),
        z_real_kk=_to_np(d["z_real_kk"]),
        z_imag_kk=_to_np(d["z_imag_kk"]),
        r_inf=float(d.get("r_inf") or 0.0),
        metrics={k: (v if v is not None else float("nan"))
                 for k, v in d.get("metrics", {}).items()},
    )


# ---------------------------------------------------------------------------
# Estrutura do projeto e leitura/escrita
# ---------------------------------------------------------------------------
@dataclass
class ProjectData:
    """Conteúdo completo de um projeto (sessão) do AMOSTRAS FRA."""

    samples: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    measurements: dict[str, Measurement] = field(default_factory=dict)
    iv_curves: dict[str, IVCurve] = field(default_factory=dict)
    curve_colors: dict[str, str] = field(default_factory=dict)
    corrections: dict[str, InstrumentCorrection] = field(default_factory=dict)
    fit_results: dict[str, FitResult] = field(default_factory=dict)
    iv_fit_results: dict[str, IVFitResult] = field(default_factory=dict)
    kk_results: dict[str, KKResult] = field(default_factory=dict)


def save_project(path: str | Path, data: ProjectData) -> None:
    """Grava um projeto em JSON.

    Args:
        path: Caminho de destino (``.fra``).
        data: Conteúdo da sessão a salvar.
    """
    payload = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "format": FORMAT_VERSION,
        "samples": list(data.samples),
        "checked": list(data.checked),
        "measurements": [
            _measurement_to(m) for m in data.measurements.values()
        ],
        "iv_curves": [_iv_to(c) for c in data.iv_curves.values()],
        "curve_colors": dict(data.curve_colors),
        "corrections": [
            _correction_to(k) for k in data.corrections.values()
        ],
        "fit_results": [_fit_to(r) for r in data.fit_results.values()],
        "iv_fit_results": [
            _iv_fit_to(r) for r in data.iv_fit_results.values()
        ],
        "kk_results": [_kk_to(r) for r in data.kk_results.values()],
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    logger.info(
        "Projeto salvo: %s (%d medição(ões), %d curva(s) I-V).",
        path,
        len(data.measurements),
        len(data.iv_curves),
    )


def load_project(path: str | Path) -> ProjectData:
    """Lê um projeto de JSON.

    Args:
        path: Caminho do arquivo ``.fra``.

    Returns:
        :class:`ProjectData` reconstruído.

    Raises:
        ValueError: Se o arquivo não for um projeto válido do
            AMOSTRAS FRA.
        OSError: Se o arquivo não puder ser lido.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"'{Path(path).name}' não é um projeto válido: {exc}"
        ) from exc
    if not isinstance(payload, dict) or "format" not in payload:
        raise ValueError(
            f"'{Path(path).name}' não é um projeto do AMOSTRAS FRA."
        )

    def _dict_by_name(items, builder, key):
        out = {}
        for item in items:
            try:
                obj = builder(item)
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("Item ignorado ao abrir projeto: %s", exc)
                continue
            out[getattr(obj, key)] = obj
        return out

    measurements = _dict_by_name(
        payload.get("measurements", []), _measurement_from, "name"
    )
    iv_curves = _dict_by_name(
        payload.get("iv_curves", []), _iv_from, "name"
    )
    corrections = _dict_by_name(
        payload.get("corrections", []), _correction_from, "name"
    )
    fit_results = _dict_by_name(
        payload.get("fit_results", []), _fit_from, "measurement_name"
    )
    iv_fit_results = _dict_by_name(
        payload.get("iv_fit_results", []), _iv_fit_from, "curve_name"
    )
    kk_results = _dict_by_name(
        payload.get("kk_results", []), _kk_from, "measurement_name"
    )

    samples = payload.get("samples") or list(
        dict.fromkeys(list(measurements) + list(iv_curves))
    )
    logger.info(
        "Projeto aberto: %s (%d amostra(s)).", Path(path).name, len(samples)
    )
    return ProjectData(
        samples=list(samples),
        checked=list(payload.get("checked", samples)),
        measurements=measurements,
        iv_curves=iv_curves,
        curve_colors=dict(payload.get("curve_colors", {})),
        corrections=corrections,
        fit_results=fit_results,
        iv_fit_results=iv_fit_results,
        kk_results=kk_results,
    )
