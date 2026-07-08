"""Ajuste do modelo de diodo único à curva I-V (AMOSTRAS FRA 2.0).

Modelo de célula/módulo fotovoltaico real (diodo único, cinco
parâmetros):

.. math::

    I = I_L - I_0\\left[\\exp\\!\\left(\\frac{V + I R_s}{a}\\right)
        - 1\\right] - \\frac{V + I R_s}{R_p}

onde:

* :math:`I_L` — fotocorrente (corrente gerada pela luz);  ≈ 0 para
  curvas medidas no escuro (*dark I-V*);
* :math:`I_0` — corrente de saturação reversa do diodo;
* :math:`R_s` — resistência série;
* :math:`R_p` — resistência paralela (*shunt*);
* :math:`a = n\\,N_s\\,k\\,T_c / q` — tensão térmica modificada, que
  reúne o fator de idealidade ``n``, o número de células em série
  ``Ns`` e a temperatura ``Tc``.

A equação é **implícita** (``I`` aparece dos dois lados); a corrente é
obtida explicitamente pela função W de Lambert.  O ajuste usa mínimos
quadrados não lineares (:func:`scipy.optimize.least_squares`) e detecta
automaticamente a convenção de sinal dos dados (curva iluminada, que
decresce, ou escura, que cresce).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.special import lambertw

from util import IVCurve

logger = logging.getLogger(__name__)

#: Constante de Boltzmann sobre carga elementar (V/K): k/q.
_K_OVER_Q: float = 8.617333262e-5

#: Nomes dos parâmetros do modelo, na ordem do ajuste.
PARAM_NAMES: tuple[str, ...] = ("I_L", "I_0", "R_s", "R_p", "a")

#: Unidades dos parâmetros.
PARAM_UNITS: tuple[str, ...] = ("A", "A", "Ω", "Ω", "V")

#: Descrições legíveis dos parâmetros.
PARAM_LABELS: dict[str, str] = {
    "I_L": "I_L — fotocorrente",
    "I_0": "I₀ — corrente de saturação",
    "R_s": "Rs — resistência série",
    "R_p": "Rp — resistência paralela (shunt)",
    "a": "a — tensão térmica modificada (n·Ns·kT/q)",
}


def single_diode_current(
    voltage: np.ndarray,
    i_ph: float,
    i_0: float,
    r_s: float,
    r_p: float,
    a: float,
) -> np.ndarray:
    """Corrente do modelo de diodo único (convenção geradora).

    Resolve a equação implícita pela função W de Lambert, de forma
    numericamente estável (usa a assíntota ``W(e^L) ≈ L − ln L`` para
    argumentos muito grandes).

    Args:
        voltage: Tensões (V).
        i_ph: Fotocorrente ``I_L`` (A).
        i_0: Corrente de saturação ``I_0`` (A).
        r_s: Resistência série (Ω).
        r_p: Resistência paralela (Ω).
        a: Tensão térmica modificada (V).

    Returns:
        Corrente terminal (A) para cada tensão.
    """
    v = np.asarray(voltage, dtype=float)
    r_s = max(float(r_s), 1e-9)
    r_p = max(float(r_p), 1e-6)
    a = max(float(a), 1e-9)
    i_0 = max(float(i_0), 1e-30)

    denom = a * (r_s + r_p)
    log_c = np.log(r_s * i_0 * r_p / denom)
    d = r_p * (r_s * i_ph + r_s * i_0 + v) / denom
    log_arg = d + log_c

    w = np.empty_like(v)
    small = log_arg <= 690.0
    if np.any(small):
        w[small] = np.real(lambertw(np.exp(log_arg[small])))
    if np.any(~small):
        big = log_arg[~small]
        # Assíntota de W para argumento grande: W(e^L) ≈ L − ln(L).
        w[~small] = big - np.log(big)

    return (r_p * (i_ph + i_0) - v) / (r_s + r_p) - (a / r_s) * w


@dataclass
class IVFitResult:
    """Resultado do ajuste do modelo de diodo único.

    Attributes:
        curve_name: Nome da curva ajustada.
        param_values: Valores ajustados (``I_L, I_0, R_s, R_p, a``).
        param_errors: Incertezas (1σ), ou ``nan`` quando indisponíveis.
        voltage: Tensões da curva (V).
        current_exp: Corrente experimental (A).
        current_fit: Corrente do modelo ajustado (A).
        rmse: Raiz do erro quadrático médio (A).
        r_squared: Coeficiente de determinação R².
        dark: ``True`` se a curva foi tratada como escura (crescente).
        sign: Sinal aplicado para converter os dados à convenção do
            modelo (+1 iluminada, −1 escura/carga).
    """

    curve_name: str
    param_values: np.ndarray
    param_errors: np.ndarray
    voltage: np.ndarray
    current_exp: np.ndarray
    current_fit: np.ndarray
    rmse: float = 0.0
    r_squared: float = 0.0
    dark: bool = False
    sign: float = 1.0
    extra: dict[str, float] = field(default_factory=dict)

    def ideality_factor(
        self, n_cells: int = 1, temperature_c: float = 25.0
    ) -> float:
        """Fator de idealidade ``n`` a partir de ``a``.

        ``n = a·q / (Ns·k·Tc)``.

        Args:
            n_cells: Número de células em série (``Ns``).
            temperature_c: Temperatura da célula em °C.

        Returns:
            Fator de idealidade estimado.
        """
        a = float(self.param_values[4])
        t_k = temperature_c + 273.15
        return a / (max(n_cells, 1) * _K_OVER_Q * t_k)

    def summary_rows(self) -> list[tuple[str, str, str]]:
        """Linhas (nome, valor, incerteza) para exibição em tabela."""
        rows: list[tuple[str, str, str]] = []
        for name, unit, value, error in zip(
            PARAM_NAMES, PARAM_UNITS, self.param_values,
            self.param_errors,
        ):
            value_text = f"{value:.6g} {unit}".strip()
            error_text = (
                f"± {error:.3g} {unit}".strip()
                if np.isfinite(error)
                else "—"
            )
            rows.append((PARAM_LABELS[name], value_text, error_text))
        return rows


def _initial_guess(
    voltage: np.ndarray, current_gen: np.ndarray
) -> tuple[float, float, float, float, float]:
    """Estimativas iniciais dos parâmetros (convenção geradora).

    ``current_gen`` já está na convenção do modelo (fotocorrente
    positiva em V=0, corrente decrescente).
    """
    i_ph0 = float(max(np.max(current_gen), 1e-6))
    # Corrente do diodo (magnitude) ao longo da curva.
    diode_mag = np.abs(i_ph0 - current_gen)
    order = np.argsort(voltage)
    v_sorted = voltage[order]
    mag_sorted = diode_mag[order]

    # Estima 'a' e I0 pela cauda exponencial: ln(I_diodo) ≈ ln(I0)+V/a.
    threshold = 0.05 * np.max(mag_sorted) if mag_sorted.size else 0.0
    mask = mag_sorted > max(threshold, 1e-12)
    a0 = 1.0
    i_00 = 1e-9
    if np.count_nonzero(mask) >= 2:
        v_tail = v_sorted[mask]
        log_mag = np.log(mag_sorted[mask])
        slope, intercept = np.polyfit(v_tail, log_mag, 1)
        if slope > 1e-6:
            a0 = float(1.0 / slope)
            i_00 = float(np.exp(intercept))

    span_v = float(np.max(voltage) - np.min(voltage)) or 1.0
    r_p0 = float(max(span_v / max(np.max(diode_mag) * 0.02, 1e-6), 100.0))
    r_s0 = 0.5
    return i_ph0, i_00, r_s0, r_p0, a0


def fit_single_diode(curve: IVCurve) -> IVFitResult:
    """Ajusta o modelo de diodo único a uma curva I-V.

    Args:
        curve: Curva I-V a ajustar (mínimo de 5 pontos).

    Returns:
        :class:`IVFitResult` com os parâmetros e as métricas.

    Raises:
        ValueError: Se a curva tiver poucos pontos.
        RuntimeError: Se o ajuste não convergir.
    """
    voltage = np.asarray(curve.voltage, dtype=float)
    current = np.asarray(curve.current, dtype=float)
    if voltage.size < 5:
        raise ValueError(
            "O ajuste do modelo de diodo requer pelo menos 5 pontos "
            f"(a curva '{curve.name}' tem {voltage.size})."
        )

    order = np.argsort(voltage)
    voltage = voltage[order]
    current = current[order]

    # Convenção: a corrente do modelo é alta em V baixo e cai com V.
    # Se os dados crescem com V (diodo direto no escuro), inverte-se o
    # sinal para levá-los à convenção geradora do modelo.
    dark = current[-1] > current[0]
    sign = -1.0 if dark else 1.0
    current_gen = sign * current

    guess = _initial_guess(voltage, current_gen)
    lower = [0.0, 1e-30, 1e-6, 1.0, 1e-6]
    upper = [
        max(10.0 * abs(guess[0]), 100.0),
        1.0,
        1e4,
        1e12,
        50.0,
    ]
    x0 = [
        min(max(guess[i], lower[i]), upper[i]) for i in range(5)
    ]

    def residuals(params: np.ndarray) -> np.ndarray:
        model = single_diode_current(voltage, *params)
        return model - current_gen

    try:
        result = least_squares(
            residuals,
            x0,
            bounds=(lower, upper),
            method="trf",
            x_scale="jac",
            max_nfev=8000,
        )
    except Exception as exc:  # pragma: no cover - proteção geral
        logger.exception("Falha no ajuste do modelo de diodo.")
        raise RuntimeError(
            f"O ajuste do modelo de diodo não convergiu para a curva "
            f"'{curve.name}': {exc}"
        ) from exc

    if not result.success and result.status <= 0:
        raise RuntimeError(
            f"O ajuste do modelo de diodo não convergiu para a curva "
            f"'{curve.name}' (status {result.status})."
        )

    params = result.x
    errors = _parameter_errors(result)
    current_fit = sign * single_diode_current(voltage, *params)

    residual = current - current_fit
    rmse = float(np.sqrt(np.mean(residual**2)))
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((current - np.mean(current)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else float("nan")

    logger.info(
        "Ajuste diodo '%s': I_L=%.4g A, I_0=%.4g A, Rs=%.4g Ω, "
        "Rp=%.4g Ω, a=%.4g V | RMSE=%.4g A | R²=%.6f | escura=%s",
        curve.name, params[0], params[1], params[2], params[3],
        params[4], rmse, r_squared, dark,
    )

    return IVFitResult(
        curve_name=curve.name,
        param_values=params,
        param_errors=errors,
        voltage=voltage,
        current_exp=current,
        current_fit=current_fit,
        rmse=rmse,
        r_squared=r_squared,
        dark=dark,
        sign=sign,
    )


def _parameter_errors(result) -> np.ndarray:
    """Incertezas (1σ) dos parâmetros a partir do jacobiano.

    Usa a matriz de covariância aproximada
    ``cov = σ² (JᵀJ)⁻¹``.  Retorna ``nan`` quando indeterminada.
    """
    try:
        jac = result.jac
        residual = result.fun
        dof = max(jac.shape[0] - jac.shape[1], 1)
        sigma_sq = float(np.sum(residual**2)) / dof
        cov = np.linalg.inv(jac.T @ jac) * sigma_sq
        return np.sqrt(np.abs(np.diag(cov)))
    except (np.linalg.LinAlgError, ValueError):
        return np.full(len(result.x), np.nan)
