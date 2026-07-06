"""Correção do instrumento (AMOSTRAS FRA 2.0).

A correção baseia-se na medição de um resistor padrão de valor nominal
conhecido.  A partir do espectro medido do resistor
(:math:`Z_{med}(f) = |Z|e^{j\\varphi}`) calcula-se a função de
transferência do instrumento:

.. math::

    H(f) = \\frac{Z_{med}(f)}{R_{nominal}}

Como o resistor ideal tem impedância real e constante
(:math:`Z_{ideal} = R_{nominal}`), qualquer desvio de módulo ou fase em
``H(f)`` representa erro sistemático do instrumento (cabos, ganho,
atraso de fase).  A correção de uma medição arbitrária é:

.. math::

    Z_{corr}(f) = \\frac{Z_{med}(f)}{H(f)}

``H`` é interpolado em módulo e fase sobre ``log10(f)`` para as
frequências da medição-alvo.  Toda a implementação é vetorizada com
NumPy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from util import Measurement

logger = logging.getLogger(__name__)


@dataclass
class InstrumentCorrection:
    """Dados do resistor padrão e função de transferência do instrumento.

    Attributes:
        frequency: Frequências da medição do resistor padrão (Hz).
        magnitude: Módulo medido ``|Z|`` do resistor padrão (Ω).
        phase_deg: Fase medida do resistor padrão (graus).
        r_nominal: Resistência nominal do resistor padrão (Ω).
    """

    frequency: np.ndarray
    magnitude: np.ndarray
    phase_deg: np.ndarray
    r_nominal: float
    _log_freq: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.frequency = np.asarray(self.frequency, dtype=float)
        self.magnitude = np.asarray(self.magnitude, dtype=float)
        self.phase_deg = np.asarray(self.phase_deg, dtype=float)

        if not (
            self.frequency.shape
            == self.magnitude.shape
            == self.phase_deg.shape
        ):
            raise ValueError(
                "Frequência, magnitude e fase devem ter o mesmo tamanho."
            )
        if self.frequency.ndim != 1 or self.frequency.size < 2:
            raise ValueError(
                "A correção precisa de pelo menos 2 pontos de frequência."
            )
        if np.any(~np.isfinite(self.frequency)) or np.any(
            self.frequency <= 0.0
        ):
            raise ValueError(
                "As frequências do resistor padrão devem ser positivas."
            )
        if np.any(~np.isfinite(self.magnitude)) or np.any(
            self.magnitude <= 0.0
        ):
            raise ValueError(
                "As magnitudes do resistor padrão devem ser positivas."
            )
        if np.any(~np.isfinite(self.phase_deg)):
            raise ValueError("As fases do resistor padrão devem ser finitas.")
        if not np.isfinite(self.r_nominal) or self.r_nominal <= 0.0:
            raise ValueError("A resistência nominal deve ser positiva.")

        order = np.argsort(self.frequency)
        self.frequency = self.frequency[order]
        self.magnitude = self.magnitude[order]
        self.phase_deg = self.phase_deg[order]
        if np.any(np.diff(self.frequency) == 0.0):
            raise ValueError(
                "Há frequências duplicadas nos dados do resistor padrão."
            )
        self._log_freq = np.log10(self.frequency)

    # ------------------------------------------------------------------
    @property
    def z_measured(self) -> np.ndarray:
        """Impedância complexa medida do resistor padrão."""
        phase_rad = np.radians(self.phase_deg)
        return self.magnitude * np.exp(1j * phase_rad)

    @property
    def h(self) -> np.ndarray:
        """Função de transferência ``H(f) = Z_med / R_nominal``."""
        return self.z_measured / self.r_nominal

    @property
    def n_points(self) -> int:
        """Número de pontos da medição do resistor padrão."""
        return int(self.frequency.size)

    # ------------------------------------------------------------------
    def interpolate_h(self, frequency: np.ndarray) -> np.ndarray:
        """Interpola ``H(f)`` nas frequências desejadas.

        A interpolação é linear em ``log10(f)``, feita separadamente em
        módulo e fase (evita erros de interpolação cartesiana quando a
        fase varia).  Fora do intervalo medido, os valores das bordas
        são mantidos (extrapolação constante).

        Args:
            frequency: Frequências-alvo em Hz (array 1-D, positivas).

        Returns:
            Array complexo com ``H`` interpolado.
        """
        freq = np.asarray(frequency, dtype=float)
        if np.any(~np.isfinite(freq)) or np.any(freq <= 0.0):
            raise ValueError("As frequências-alvo devem ser positivas.")

        log_target = np.log10(freq)
        h_mag = np.abs(self.h)
        h_phase = np.unwrap(np.angle(self.h))

        mag_interp = np.interp(log_target, self._log_freq, h_mag)
        phase_interp = np.interp(log_target, self._log_freq, h_phase)

        outside = (log_target < self._log_freq[0]) | (
            log_target > self._log_freq[-1]
        )
        if np.any(outside):
            logger.warning(
                "Correção: %d ponto(s) fora da faixa do resistor padrão "
                "(%.3g Hz a %.3g Hz); usando extrapolação constante.",
                int(np.count_nonzero(outside)),
                self.frequency[0],
                self.frequency[-1],
            )
        return mag_interp * np.exp(1j * phase_interp)

    def apply(
        self, measurement: Measurement, new_name: Optional[str] = None
    ) -> Measurement:
        """Aplica a correção a uma medição.

        Args:
            measurement: Medição a corrigir.
            new_name: Nome da medição corrigida.  Se omitido, usa
                ``"<nome> (corrigida)"``.

        Returns:
            Nova :class:`Measurement` com ``Z_corr = Z_med / H(f)``.
        """
        h_interp = self.interpolate_h(measurement.frequency)
        z_corrected = measurement.z_complex / h_interp
        name = (
            new_name
            if new_name is not None
            else f"{measurement.name} (corrigida)"
        )
        logger.info(
            "Correção aplicada em '%s' (%d pontos, R nominal = %.6g Ω).",
            measurement.name,
            measurement.n_points,
            self.r_nominal,
        )
        return Measurement(
            name=name,
            frequency=measurement.frequency.copy(),
            z_real=np.real(z_corrected),
            z_imag=np.imag(z_corrected),
            corrected=True,
            notes=measurement.notes,
        )

    # ------------------------------------------------------------------
    def to_dataframe(self) -> pd.DataFrame:
        """Exporta os dados do resistor padrão como DataFrame."""
        h = self.h
        return pd.DataFrame(
            {
                "Frequência (Hz)": self.frequency,
                "Magnitude (Ω)": self.magnitude,
                "Fase (°)": self.phase_deg,
                "Re{H}": np.real(h),
                "Im{H}": np.imag(h),
                "|H|": np.abs(h),
                "Fase H (°)": np.degrees(np.angle(h)),
            }
        )

    @classmethod
    def from_rows(
        cls,
        rows: Sequence[Sequence[Optional[float]]],
        r_nominal: float,
    ) -> "InstrumentCorrection":
        """Cria a correção a partir de linhas ``[freq, mag, fase]``.

        Linhas incompletas são descartadas com aviso no log.

        Args:
            rows: Linhas com frequência, magnitude e fase.
            r_nominal: Resistência nominal do resistor padrão (Ω).

        Returns:
            Instância validada de :class:`InstrumentCorrection`.

        Raises:
            ValueError: Se restarem menos de 2 pontos válidos.
        """
        freq: list[float] = []
        mag: list[float] = []
        phase: list[float] = []
        discarded = 0
        for row in rows:
            values = list(row) + [None] * (3 - len(row))
            f, m, p = values[0], values[1], values[2]
            if f is None or m is None or p is None:
                discarded += 1
                continue
            freq.append(float(f))
            mag.append(float(m))
            phase.append(float(p))
        if discarded:
            logger.warning(
                "Correção: %d linha(s) incompleta(s) descartada(s).",
                discarded,
            )
        if len(freq) < 2:
            raise ValueError(
                "São necessários pelo menos 2 pontos completos "
                "(frequência, magnitude e fase) do resistor padrão."
            )
        return cls(
            frequency=np.asarray(freq),
            magnitude=np.asarray(mag),
            phase_deg=np.asarray(phase),
            r_nominal=float(r_nominal),
        )
