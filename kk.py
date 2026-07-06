"""Validação de Kramers-Kronig (AMOSTRAS FRA 2.0).

As relações de Kramers-Kronig (KK) conectam as partes real e
imaginária de qualquer função de transferência causal, linear e
estável.  Na convenção de engenharia elétrica (:math:`e^{+j\\omega t}`,
capacitores com :math:`Z'' < 0`), a impedância
:math:`Z(\\omega) = Z'(\\omega) + jZ''(\\omega)` é analítica no
semiplano inferior de :math:`\\omega` e as relações são:

.. math::

    Z'(\\omega) = R_\\infty - \\frac{2}{\\pi}\\,
        \\mathrm{PV}\\!\\int_0^{\\infty}
        \\frac{x\\,Z''(x) - \\omega\\,Z''(\\omega)}{x^2 - \\omega^2}\\,dx

.. math::

    Z''(\\omega) = +\\frac{2\\omega}{\\pi}\\,
        \\mathrm{PV}\\!\\int_0^{\\infty}
        \\frac{Z'(x) - Z'(\\omega)}{x^2 - \\omega^2}\\,dx

(Textos que adotam a convenção temporal oposta, :math:`e^{-i\\omega t}`,
apresentam as mesmas relações com os sinais trocados.  A validade dos
sinais acima foi verificada analiticamente com o circuito
:math:`Z = R/(1 + j\\omega RC)`.)  Os termos subtraídos
:math:`\\omega Z''(\\omega)` e :math:`Z'(\\omega)` integram-se a zero
no intervalo completo (:math:`\\mathrm{PV}\\int_0^\\infty
dx/(x^2-\\omega^2) = 0`) e apenas regularizam a singularidade.

O Valor Principal de Cauchy (PV) é tratado analiticamente: ao
subtrair o valor do integrando no ponto singular (:math:`x = \\omega`),
a singularidade torna-se removível e o limite é obtido pela regra de
L'Hôpital:

.. math::

    \\lim_{x\\to\\omega}\\frac{x\\,Z''(x) - \\omega\\,Z''(\\omega)}
        {x^2-\\omega^2}
    = \\frac{Z''(\\omega) + \\omega\\,\\dfrac{dZ''}{dx}(\\omega)}
        {2\\omega}

.. math::

    \\lim_{x\\to\\omega}\\frac{Z'(x) - Z'(\\omega)}{x^2-\\omega^2}
    = \\frac{1}{2\\omega}\\,\\frac{dZ'}{dx}(\\omega)

A integração usa **todas** as frequências medidas (nenhuma é
eliminada), com a regra do trapézio sobre a malha experimental.  Como
o espectro medido é finito (a integral teórica vai de 0 a ∞), o nível
constante :math:`R_\\infty` é determinado por mínimos quadrados
(deslocamento que minimiza o resíduo da parte real) — procedimento
padrão em validação KK de dados experimentais.

A implementação é totalmente vetorizada com NumPy (matriz N×N,
processada em blocos para espectros muito longos).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from util import Measurement

logger = logging.getLogger(__name__)

#: Número máximo de linhas processadas por bloco na matriz N×N.
_CHUNK_ROWS: int = 2048


@dataclass
class KKResult:
    """Resultado da validação de Kramers-Kronig de uma medição.

    Attributes:
        measurement_name: Nome da medição validada.
        frequency: Frequências (Hz), em ordem crescente.
        z_real_exp: Parte real experimental (Ω).
        z_imag_exp: Parte imaginária experimental (Ω).
        z_real_kk: Parte real reconstruída via KK (Ω).
        z_imag_kk: Parte imaginária reconstruída via KK (Ω).
        r_inf: Resistência de alta frequência ajustada (Ω).
        metrics: Métricas de erro (RMSE, erro médio, erro máximo e
            erro percentual, para as partes real e imaginária).
    """

    measurement_name: str
    frequency: np.ndarray
    z_real_exp: np.ndarray
    z_imag_exp: np.ndarray
    z_real_kk: np.ndarray
    z_imag_kk: np.ndarray
    r_inf: float
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def residual_real_pct(self) -> np.ndarray:
        """Resíduo relativo da parte real, em % de ``|Z|``.

        Pontos com ``|Z| = 0`` produzem ``nan`` (excluídos do gráfico).
        """
        z_mod = np.hypot(self.z_real_exp, self.z_imag_exp)
        z_mod = np.where(z_mod > 0.0, z_mod, np.nan)
        return 100.0 * (self.z_real_exp - self.z_real_kk) / z_mod

    @property
    def residual_imag_pct(self) -> np.ndarray:
        """Resíduo relativo da parte imaginária, em % de ``|Z|``.

        Pontos com ``|Z| = 0`` produzem ``nan`` (excluídos do gráfico).
        """
        z_mod = np.hypot(self.z_real_exp, self.z_imag_exp)
        z_mod = np.where(z_mod > 0.0, z_mod, np.nan)
        return 100.0 * (self.z_imag_exp - self.z_imag_kk) / z_mod


def _pv_integral(
    omega: np.ndarray,
    values: np.ndarray,
    diagonal_limits: np.ndarray,
) -> np.ndarray:
    """Calcula a integral PV pela regra do trapézio, vetorizada.

    Para cada frequência-alvo ``omega[i]`` integra-se sobre toda a
    malha ``x = omega`` o integrando
    ``(values[j] - values[i]) / (x_j**2 - omega_i**2)``, substituindo
    o ponto singular ``j == i`` pelo limite analítico
    ``diagonal_limits[i]``.

    A matriz do integrando é construída em blocos de linhas
    (:data:`_CHUNK_ROWS`), de modo que o pico de memória cresce como
    ``O(_CHUNK_ROWS × N)`` — nunca ``O(N²)`` — permitindo espectros
    muito longos.

    Args:
        omega: Malha de frequências angulares (rad/s), crescente.
        values: Função avaliada na malha (``x·Z''(x)`` ou ``Z'(x)``).
        diagonal_limits: Limite analítico do integrando em ``x = ω``.

    Returns:
        Vetor com o valor da integral para cada frequência-alvo.
    """
    n = omega.size
    result = np.empty(n, dtype=float)
    omega_sq = omega * omega

    for start in range(0, n, _CHUNK_ROWS):
        stop = min(start + _CHUNK_ROWS, n)
        rows = slice(start, stop)
        numerator = values[np.newaxis, :] - values[rows, np.newaxis]
        denominator = omega_sq[np.newaxis, :] - omega_sq[rows, np.newaxis]
        integrand = np.empty_like(denominator)
        mask = denominator != 0.0
        np.divide(numerator, denominator, out=integrand, where=mask)
        # Pontos singulares (x == ω): limite analítico (L'Hôpital).
        local_idx = np.arange(start, stop)
        integrand[~mask] = 0.0
        integrand[local_idx - start, local_idx] = diagonal_limits[rows]
        result[rows] = np.trapezoid(integrand, omega, axis=1)
    return result


def kk_transform(measurement: Measurement) -> KKResult:
    """Executa a validação de Kramers-Kronig de uma medição.

    Reconstrói a parte real a partir da imaginária e a parte
    imaginária a partir da real, usando todas as frequências medidas e
    o Valor Principal de Cauchy com tratamento analítico da
    singularidade.

    Args:
        measurement: Medição a validar (mínimo de 8 pontos).

    Returns:
        :class:`KKResult` com os espectros reconstruídos e as métricas
        de erro.

    Raises:
        ValueError: Se a medição tiver menos de 8 pontos ou
            frequências duplicadas.
    """
    m = measurement.sorted_by_frequency()
    if m.n_points < 8:
        raise ValueError(
            "A validação de Kramers-Kronig requer pelo menos 8 pontos "
            f"(a medição '{m.name}' tem {m.n_points})."
        )
    if np.any(np.diff(m.frequency) == 0.0):
        raise ValueError(
            f"A medição '{m.name}' possui frequências duplicadas; "
            "remova-as antes de validar."
        )

    omega = m.omega
    z_re = m.z_real
    z_im = m.z_imag
    n = omega.size
    logger.info(
        "Kramers-Kronig: '%s' com %d pontos (%.4g Hz a %.4g Hz).",
        m.name,
        n,
        m.frequency[0],
        m.frequency[-1],
    )

    dz_im = np.gradient(z_im, omega)
    dz_re = np.gradient(z_re, omega)

    # ------------------------------------------------------------------
    # Reconstrução da parte real a partir de Z'':
    #   Z'_kk(ωi) = R∞ − (2/π) ∫ [x Z''(x) − ωi Z''(ωi)] / (x² − ωi²) dx
    # ------------------------------------------------------------------
    x_zim = omega * z_im  # x·Z''(x), avaliado na malha
    diag_re = (z_im + omega * dz_im) / (2.0 * omega)
    integral_re = _pv_integral(omega, x_zim, diag_re)
    z_re_kk_shape = -(2.0 / np.pi) * integral_re

    # R∞ por mínimos quadrados: deslocamento constante ótimo entre a
    # forma reconstruída e a parte real experimental.
    r_inf = float(np.mean(z_re - z_re_kk_shape))
    z_re_kk = r_inf + z_re_kk_shape

    # ------------------------------------------------------------------
    # Reconstrução da parte imaginária a partir de Z':
    #   Z''_kk(ωi) = +(2ωi/π) ∫ [Z'(x) − Z'(ωi)] / (x² − ωi²) dx
    # ------------------------------------------------------------------
    diag_im = dz_re / (2.0 * omega)
    integral_im = _pv_integral(omega, z_re, diag_im)
    z_im_kk = (2.0 * omega / np.pi) * integral_im

    metrics = _compute_metrics(z_re, z_im, z_re_kk, z_im_kk)
    logger.info(
        "Kramers-Kronig: '%s' concluído. RMSE(Z')=%.4g Ω, "
        "RMSE(Z'')=%.4g Ω, erro percentual médio=%.3g %%.",
        m.name,
        metrics["rmse_real"],
        metrics["rmse_imag"],
        metrics["pct_error_mean"],
    )

    return KKResult(
        measurement_name=m.name,
        frequency=m.frequency,
        z_real_exp=z_re,
        z_imag_exp=z_im,
        z_real_kk=z_re_kk,
        z_imag_kk=z_im_kk,
        r_inf=r_inf,
        metrics=metrics,
    )


def _compute_metrics(
    z_re_exp: np.ndarray,
    z_im_exp: np.ndarray,
    z_re_kk: np.ndarray,
    z_im_kk: np.ndarray,
) -> dict[str, float]:
    """Calcula as métricas de comparação experimental × reconstruído.

    Args:
        z_re_exp: Parte real experimental.
        z_im_exp: Parte imaginária experimental.
        z_re_kk: Parte real reconstruída.
        z_im_kk: Parte imaginária reconstruída.

    Returns:
        Dicionário com RMSE, erro médio absoluto, erro máximo e erro
        percentual (relativo a ``|Z|``) por componente, além do erro
        percentual médio global.  Pontos com ``|Z| = 0`` são excluídos
        das métricas percentuais (com aviso no log).
    """
    z_mod = np.hypot(z_re_exp, z_im_exp)
    if np.any(z_mod == 0.0):
        logger.warning(
            "Kramers-Kronig: %d ponto(s) com |Z| = 0 excluído(s) das "
            "métricas percentuais.",
            int(np.count_nonzero(z_mod == 0.0)),
        )
    z_mod_safe = np.where(z_mod > 0.0, z_mod, np.nan)
    res_re = z_re_exp - z_re_kk
    res_im = z_im_exp - z_im_kk

    pct_re = 100.0 * np.abs(res_re) / z_mod_safe
    pct_im = 100.0 * np.abs(res_im) / z_mod_safe

    return {
        "rmse_real": float(np.sqrt(np.mean(res_re**2))),
        "rmse_imag": float(np.sqrt(np.mean(res_im**2))),
        "mean_error_real": float(np.mean(np.abs(res_re))),
        "mean_error_imag": float(np.mean(np.abs(res_im))),
        "max_error_real": float(np.max(np.abs(res_re))),
        "max_error_imag": float(np.max(np.abs(res_im))),
        "pct_error_real": float(np.nanmean(pct_re)),
        "pct_error_imag": float(np.nanmean(pct_im)),
        "pct_error_max": float(
            max(np.nanmax(pct_re), np.nanmax(pct_im))
        ),
        "pct_error_mean": float(np.nanmean(0.5 * (pct_re + pct_im))),
    }


#: Rótulos legíveis (pt-BR) para as métricas de :func:`kk_transform`.
METRIC_LABELS: dict[str, str] = {
    "rmse_real": "RMSE — parte real (Ω)",
    "rmse_imag": "RMSE — parte imaginária (Ω)",
    "mean_error_real": "Erro médio — parte real (Ω)",
    "mean_error_imag": "Erro médio — parte imaginária (Ω)",
    "max_error_real": "Erro máximo — parte real (Ω)",
    "max_error_imag": "Erro máximo — parte imaginária (Ω)",
    "pct_error_real": "Erro percentual — parte real (%)",
    "pct_error_imag": "Erro percentual — parte imaginária (%)",
    "pct_error_max": "Erro percentual máximo (%)",
    "pct_error_mean": "Erro percentual médio (%)",
}
