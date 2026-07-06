"""Ajuste de circuitos equivalentes (AMOSTRAS FRA 2.0).

Modelos implementados (sintaxe do ``impedance.py``):

* **Randles** — ``R0-p(R1,C1)``
* **Randles + CPE** — ``R0-p(R1,CPE1)``
* **Randles + Warburg** — ``R0-p(R1-W1,C1)``
* **Randles + CPE + Warburg** — ``R0-p(R1-W1,CPE1)``

O ajuste usa mínimos quadrados não lineares
(:class:`impedance.models.circuits.CustomCircuit`, baseado em
``scipy.optimize.curve_fit``) com ponderação pelo módulo da
impedância.  As estimativas iniciais são derivadas automaticamente dos
dados (Rs pela alta frequência, Rp pelo diâmetro do semicírculo, C
pela frequência de pico de ``-Z''``).

Métricas reportadas: χ² (ponderado pelo módulo), χ² reduzido, RMSE e
R² (calculado sobre as partes real e imaginária concatenadas).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np
from impedance.models.circuits import CustomCircuit

from util import Measurement

logger = logging.getLogger(__name__)

#: Menor valor admissível para estimativas iniciais (evita zeros).
_EPS: float = 1e-12


@dataclass(frozen=True)
class CircuitModel:
    """Descrição de um modelo de circuito equivalente.

    Attributes:
        key: Identificador interno do modelo.
        display_name: Nome exibido na interface.
        circuit_string: Definição do circuito na sintaxe do
            ``impedance.py``.
        param_names: Nomes físicos dos parâmetros, na ordem do ajuste.
        param_units: Unidades dos parâmetros, na mesma ordem.
        initial_guess_func: Função que gera estimativas iniciais a
            partir da medição.
    """

    key: str
    display_name: str
    circuit_string: str
    param_names: tuple[str, ...]
    param_units: tuple[str, ...]
    initial_guess_func: Callable[[Measurement], list[float]]


@dataclass
class FitResult:
    """Resultado do ajuste de circuito equivalente.

    Attributes:
        measurement_name: Nome da medição ajustada.
        model_key: Identificador do modelo usado.
        model_name: Nome legível do modelo.
        circuit_string: Definição do circuito ajustado.
        param_names: Nomes dos parâmetros.
        param_units: Unidades dos parâmetros.
        param_values: Valores ajustados.
        param_errors: Incertezas (1σ) dos parâmetros, quando
            disponíveis (``nan`` caso contrário).
        frequency: Frequências da medição (Hz).
        z_exp: Impedância experimental (complexa).
        z_fit: Impedância do modelo ajustado (complexa).
        chi_squared: χ² ponderado pelo módulo de Z.
        chi_squared_reduced: χ² dividido pelos graus de liberdade.
        rmse: Raiz do erro quadrático médio (Ω).
        r_squared: Coeficiente de determinação R².
    """

    measurement_name: str
    model_key: str
    model_name: str
    circuit_string: str
    param_names: tuple[str, ...]
    param_units: tuple[str, ...]
    param_values: np.ndarray
    param_errors: np.ndarray
    frequency: np.ndarray
    z_exp: np.ndarray
    z_fit: np.ndarray
    chi_squared: float = 0.0
    chi_squared_reduced: float = 0.0
    rmse: float = 0.0
    r_squared: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)

    def summary_rows(self) -> list[tuple[str, str, str]]:
        """Linhas (nome, valor, incerteza) para exibição em tabela."""
        rows: list[tuple[str, str, str]] = []
        for name, unit, value, error in zip(
            self.param_names,
            self.param_units,
            self.param_values,
            self.param_errors,
        ):
            value_text = f"{value:.6g} {unit}".strip()
            error_text = (
                f"± {error:.3g} {unit}".strip()
                if np.isfinite(error)
                else "—"
            )
            rows.append((name, value_text, error_text))
        return rows


# ---------------------------------------------------------------------------
# Estimativas iniciais derivadas dos dados
# ---------------------------------------------------------------------------
def _basic_estimates(
    measurement: Measurement,
) -> tuple[float, float, float, float]:
    """Estimativas de Rs, Rp, C e A_W a partir do espectro.

    Returns:
        Tupla ``(rs, rp, c, a_w)`` com valores estritamente positivos.
    """
    m = measurement.sorted_by_frequency()
    z_re = m.z_real
    minus_z_im = -m.z_imag

    # Rs: parte real na maior frequência (aproximação de R∞).
    rs = float(max(z_re[-1], _EPS))

    # Rp: diâmetro aparente do semicírculo.
    rp = float(max(np.max(z_re) - np.min(z_re), abs(rs) * 0.1, _EPS))

    # C: da frequência do pico capacitivo, ω_pico = 1/(Rp·C).
    peak_index = int(np.argmax(minus_z_im))
    f_peak = float(m.frequency[peak_index])
    c = float(max(1.0 / (2.0 * np.pi * f_peak * rp), _EPS))

    # A_W: coeficiente de Warburg estimado da menor frequência,
    # |Z''| ≈ A_W / sqrt(2πf).
    a_w = float(
        max(abs(m.z_imag[0]) * np.sqrt(2.0 * np.pi * m.frequency[0]), _EPS)
    )
    return rs, rp, c, a_w


def _guess_randles(measurement: Measurement) -> list[float]:
    """Estimativa inicial para o modelo Randles ``R0-p(R1,C1)``."""
    rs, rp, c, _ = _basic_estimates(measurement)
    return [rs, rp, c]


def _guess_randles_cpe(measurement: Measurement) -> list[float]:
    """Estimativa inicial para Randles + CPE ``R0-p(R1,CPE1)``."""
    rs, rp, c, _ = _basic_estimates(measurement)
    return [rs, rp, c, 0.9]


def _guess_randles_warburg(measurement: Measurement) -> list[float]:
    """Estimativa inicial para Randles + Warburg ``R0-p(R1-W1,C1)``."""
    rs, rp, c, a_w = _basic_estimates(measurement)
    return [rs, rp, a_w, c]


def _guess_randles_cpe_warburg(measurement: Measurement) -> list[float]:
    """Estimativa inicial para ``R0-p(R1-W1,CPE1)``."""
    rs, rp, c, a_w = _basic_estimates(measurement)
    return [rs, rp, a_w, c, 0.9]


#: Modelos disponíveis, indexados pela chave interna.
MODELS: dict[str, CircuitModel] = {
    "randles": CircuitModel(
        key="randles",
        display_name="Randles (Rs + Rp‖C)",
        circuit_string="R0-p(R1,C1)",
        param_names=("Rs", "Rp", "C"),
        param_units=("Ω", "Ω", "F"),
        initial_guess_func=_guess_randles,
    ),
    "randles_cpe": CircuitModel(
        key="randles_cpe",
        display_name="Randles + CPE (Rs + Rp‖CPE)",
        circuit_string="R0-p(R1,CPE1)",
        param_names=("Rs", "Rp", "CPE (Q)", "n"),
        param_units=("Ω", "Ω", "S·sⁿ", ""),
        initial_guess_func=_guess_randles_cpe,
    ),
    "randles_warburg": CircuitModel(
        key="randles_warburg",
        display_name="Randles + Warburg (Rs + (Rp+W)‖C)",
        circuit_string="R0-p(R1-W1,C1)",
        param_names=("Rs", "Rp", "Warburg (A_W)", "C"),
        param_units=("Ω", "Ω", "Ω·s⁻¹ᐟ²", "F"),
        initial_guess_func=_guess_randles_warburg,
    ),
    "randles_cpe_warburg": CircuitModel(
        key="randles_cpe_warburg",
        display_name="Randles + CPE + Warburg (Rs + (Rp+W)‖CPE)",
        circuit_string="R0-p(R1-W1,CPE1)",
        param_names=("Rs", "Rp", "Warburg (A_W)", "CPE (Q)", "n"),
        param_units=("Ω", "Ω", "Ω·s⁻¹ᐟ²", "S·sⁿ", ""),
        initial_guess_func=_guess_randles_cpe_warburg,
    ),
}


# ---------------------------------------------------------------------------
# Ajuste
# ---------------------------------------------------------------------------
def fit_circuit(
    measurement: Measurement,
    model_key: str,
    initial_guess: Optional[Sequence[float]] = None,
) -> FitResult:
    """Ajusta um circuito equivalente a uma medição.

    Args:
        measurement: Medição experimental.
        model_key: Chave de um dos modelos em :data:`MODELS`.
        initial_guess: Estimativas iniciais opcionais (sobrepõem as
            estimativas automáticas).

    Returns:
        :class:`FitResult` com parâmetros, incertezas e métricas.

    Raises:
        KeyError: Se ``model_key`` não existir.
        ValueError: Se a medição tiver poucos pontos para o modelo.
        RuntimeError: Se o algoritmo de mínimos quadrados não
            convergir.
    """
    if model_key not in MODELS:
        raise KeyError(
            f"Modelo desconhecido: '{model_key}'. "
            f"Disponíveis: {', '.join(MODELS)}."
        )
    model = MODELS[model_key]
    m = measurement.sorted_by_frequency()

    n_params = len(model.param_names)
    if m.n_points <= n_params:
        raise ValueError(
            f"O modelo '{model.display_name}' tem {n_params} parâmetros "
            f"e a medição '{m.name}' tem apenas {m.n_points} pontos. "
            "São necessários mais pontos que parâmetros."
        )

    guess = (
        [float(v) for v in initial_guess]
        if initial_guess is not None
        else model.initial_guess_func(m)
    )
    if len(guess) != n_params:
        raise ValueError(
            f"A estimativa inicial tem {len(guess)} valores; o modelo "
            f"'{model.display_name}' requer {n_params}."
        )

    return _execute_fit(
        m,
        model.circuit_string,
        guess,
        model_key=model.key,
        model_name=model.display_name,
        param_names=model.param_names,
        param_units=model.param_units,
    )


def _execute_fit(
    m: Measurement,
    circuit_string: str,
    guess: list[float],
    model_key: str,
    model_name: str,
    param_names: tuple[str, ...],
    param_units: tuple[str, ...],
) -> FitResult:
    """Executa o ajuste por mínimos quadrados de um circuito qualquer.

    Núcleo compartilhado entre :func:`fit_circuit` (modelos
    pré-definidos) e :func:`fit_custom_circuit` (circuitos montados no
    editor).

    Args:
        m: Medição já ordenada por frequência.
        circuit_string: Circuito na sintaxe do ``impedance.py``.
        guess: Estimativas iniciais, na ordem dos parâmetros.
        model_key: Identificador do modelo (para o resultado).
        model_name: Nome legível do modelo.
        param_names: Nomes dos parâmetros.
        param_units: Unidades dos parâmetros.

    Returns:
        :class:`FitResult` com parâmetros, incertezas e métricas.

    Raises:
        ValueError: Se houver pontos com ``|Z| = 0``.
        RuntimeError: Se o ajuste não convergir.
    """
    n_params = len(param_names)
    z_mod = np.abs(m.z_complex)
    if np.any(z_mod == 0.0):
        bad = np.nonzero(z_mod == 0.0)[0][:5]
        freqs = ", ".join(f"{m.frequency[i]:.6g} Hz" for i in bad)
        raise ValueError(
            f"A medição '{m.name}' contém ponto(s) com |Z| = 0 (em "
            f"{freqs}) — normalmente indicam sobrecarga ou falha do "
            "instrumento. Remova-os antes do ajuste, pois a ponderação "
            "pelo módulo não admite |Z| nulo."
        )

    logger.info(
        "Ajuste de circuito: '%s' com modelo %s, estimativa inicial %s.",
        m.name,
        circuit_string,
        np.array2string(np.asarray(guess), precision=3),
    )

    circuit = CustomCircuit(circuit=circuit_string, initial_guess=guess)
    frequency = m.frequency.astype(float)
    z_exp = m.z_complex.astype(complex)

    try:
        circuit.fit(frequency, z_exp, weight_by_modulus=True)
    except Exception as exc:
        logger.exception("Falha no ajuste de '%s'.", m.name)
        raise RuntimeError(
            f"O ajuste do modelo '{model_name}' não convergiu "
            f"para a medição '{m.name}': {exc}"
        ) from exc

    param_values = np.asarray(circuit.parameters_, dtype=float)
    if circuit.conf_ is not None:
        param_errors = np.asarray(circuit.conf_, dtype=float)
    else:
        param_errors = np.full(n_params, np.nan)

    z_fit = np.asarray(circuit.predict(frequency), dtype=complex)
    metrics = _fit_metrics(z_exp, z_fit, n_params)

    result = FitResult(
        measurement_name=m.name,
        model_key=model_key,
        model_name=model_name,
        circuit_string=circuit_string,
        param_names=param_names,
        param_units=param_units,
        param_values=param_values,
        param_errors=param_errors,
        frequency=frequency,
        z_exp=z_exp,
        z_fit=z_fit,
        chi_squared=metrics["chi_squared"],
        chi_squared_reduced=metrics["chi_squared_reduced"],
        rmse=metrics["rmse"],
        r_squared=metrics["r_squared"],
    )
    logger.info(
        "Ajuste concluído: %s | χ²=%.4g | χ²ᵣ=%.4g | RMSE=%.4g Ω | "
        "R²=%.6f",
        _format_params(result),
        result.chi_squared,
        result.chi_squared_reduced,
        result.rmse,
        result.r_squared,
    )
    return result


def _fit_metrics(
    z_exp: np.ndarray, z_fit: np.ndarray, n_params: int
) -> dict[str, float]:
    """Calcula χ², χ² reduzido, RMSE e R² do ajuste.

    O χ² usa ponderação pelo módulo (convenção usual em EIS):

    .. math::

        \\chi^2 = \\sum_i \\frac{(Z'_i - \\hat{Z}'_i)^2 +
                  (Z''_i - \\hat{Z}''_i)^2}{|Z_i|^2}

    O R² é calculado sobre o vetor concatenado ``[Z', Z'']``.
    """
    residual = z_exp - z_fit
    res_re = np.real(residual)
    res_im = np.imag(residual)
    z_mod_sq = np.abs(z_exp) ** 2
    # Proteção extra (fit_circuit já rejeita |Z| = 0): exclui pontos
    # de módulo nulo do χ² em vez de gerar infinito.
    z_mod_sq = np.where(z_mod_sq > 0.0, z_mod_sq, np.nan)

    chi_squared = float(np.nansum((res_re**2 + res_im**2) / z_mod_sq))
    dof = max(2 * z_exp.size - n_params, 1)
    chi_squared_reduced = chi_squared / dof

    rmse = float(np.sqrt(np.mean(res_re**2 + res_im**2)))

    observed = np.concatenate([np.real(z_exp), np.imag(z_exp)])
    predicted = np.concatenate([np.real(z_fit), np.imag(z_fit)])
    ss_res = float(np.sum((observed - predicted) ** 2))
    ss_tot = float(np.sum((observed - np.mean(observed)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else float("nan")

    return {
        "chi_squared": chi_squared,
        "chi_squared_reduced": chi_squared_reduced,
        "rmse": rmse,
        "r_squared": r_squared,
    }


def _format_params(result: FitResult) -> str:
    """Formata os parâmetros ajustados para logging."""
    pairs = [
        f"{name}={value:.5g}"
        for name, value in zip(result.param_names, result.param_values)
    ]
    return ", ".join(pairs)


def simulate_circuit(
    model_key: str,
    parameters: Sequence[float],
    frequency: np.ndarray,
) -> np.ndarray:
    """Simula a impedância de um modelo com parâmetros dados.

    Args:
        model_key: Chave de um dos modelos em :data:`MODELS`.
        parameters: Valores dos parâmetros, na ordem do modelo.
        frequency: Frequências de avaliação (Hz).

    Returns:
        Impedância complexa simulada.

    Raises:
        KeyError: Se ``model_key`` não existir.
        ValueError: Se o número de parâmetros estiver incorreto.
    """
    if model_key not in MODELS:
        raise KeyError(f"Modelo desconhecido: '{model_key}'.")
    model = MODELS[model_key]
    values = [float(v) for v in parameters]
    if len(values) != len(model.param_names):
        raise ValueError(
            f"O modelo '{model.display_name}' requer "
            f"{len(model.param_names)} parâmetros; foram fornecidos "
            f"{len(values)}."
        )
    circuit = CustomCircuit(
        circuit=model.circuit_string, initial_guess=values
    )
    with warnings.catch_warnings():
        # O impedance.py avisa (por design) que está simulando com os
        # parâmetros iniciais — exatamente o que se deseja aqui.
        warnings.simplefilter("ignore", category=UserWarning)
        z_sim = circuit.predict(
            np.asarray(frequency, dtype=float), use_initial=True
        )
    return np.asarray(z_sim, dtype=complex)


# ---------------------------------------------------------------------------
# Editor de circuito livre (estilo NOVA 2 / ZView)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ElementInfo:
    """Descrição de um elemento de circuito do ``impedance.py``.

    Attributes:
        code: Código do elemento na sintaxe do ``impedance.py``
            (``"R"``, ``"CPE"``, ``"Wo"``, ...).
        display_name: Nome exibido na interface (pt-BR).
        param_labels: Rótulos curtos dos parâmetros do elemento.
        param_units: Unidades dos parâmetros, na mesma ordem.
        default_guess: Função que gera estimativas iniciais a partir
            do dicionário de :func:`spectrum_estimates`.
    """

    code: str
    display_name: str
    param_labels: tuple[str, ...]
    param_units: tuple[str, ...]
    default_guess: Callable[[dict[str, float]], list[float]]


#: Elementos disponíveis no editor, indexados pelo código.
ELEMENTS: dict[str, ElementInfo] = {
    "R": ElementInfo(
        "R", "Resistor", ("R",), ("Ω",),
        lambda e: [e["rp"]],
    ),
    "C": ElementInfo(
        "C", "Capacitor", ("C",), ("F",),
        lambda e: [e["c"]],
    ),
    "L": ElementInfo(
        "L", "Indutor", ("L",), ("H",),
        lambda e: [1e-6],
    ),
    "CPE": ElementInfo(
        "CPE", "Elemento de fase constante (CPE)",
        ("Q", "n"), ("S·sⁿ", ""),
        lambda e: [e["c"], 0.9],
    ),
    "W": ElementInfo(
        "W", "Warburg semi-infinito", ("A_W",), ("Ω·s⁻¹ᐟ²",),
        lambda e: [e["a_w"]],
    ),
    "Wo": ElementInfo(
        "Wo", "Warburg finito aberto (O)", ("Z₀", "τ"), ("Ω", "s"),
        lambda e: [e["rp"], e["tau"]],
    ),
    "Ws": ElementInfo(
        "Ws", "Warburg finito curto (T)", ("Z₀", "τ"), ("Ω", "s"),
        lambda e: [e["rp"], e["tau"]],
    ),
    "G": ElementInfo(
        "G", "Gerischer", ("Z₀", "τ"), ("Ω", "s"),
        lambda e: [e["rp"], e["tau"]],
    ),
    "Gs": ElementInfo(
        "Gs", "Gerischer finito", ("Z₀", "τ", "n"), ("Ω", "s", ""),
        lambda e: [e["rp"], e["tau"], 0.5],
    ),
    "La": ElementInfo(
        "La", "Indutância modificada", ("L", "n"), ("H·s", ""),
        lambda e: [1e-6, 0.9],
    ),
    "Zarc": ElementInfo(
        "Zarc", "Arco RQ (Zarc)", ("R", "τ", "n"), ("Ω", "s", ""),
        lambda e: [e["rp"], e["tau"], 0.9],
    ),
    "TLMQ": ElementInfo(
        "TLMQ", "Linha de transmissão (TLMQ)",
        ("R", "Q", "γ"), ("Ω", "F·s^(γ−1)", ""),
        lambda e: [e["rp"], e["c"], 0.9],
    ),
    "K": ElementInfo(
        "K", "Elemento RC (lin-KK)", ("R", "τ"), ("Ω", "s"),
        lambda e: [e["rp"], e["tau"]],
    ),
    "T": ElementInfo(
        "T", "Eletrodo poroso (Paasch)",
        ("R₁", "R₂", "β", "τ"), ("Ω·m²", "Ω·m²", "", "s"),
        lambda e: [e["rp"], e["rp"], 0.5, e["tau"]],
    ),
}

#: Estimativas genéricas usadas quando não há medição de referência.
_GENERIC_ESTIMATES: dict[str, float] = {
    "rs": 100.0,
    "rp": 1000.0,
    "c": 1e-6,
    "a_w": 100.0,
    "tau": 1e-3,
}


def spectrum_estimates(measurement: Measurement) -> dict[str, float]:
    """Estimativas características do espectro para chutes iniciais.

    Args:
        measurement: Medição de referência.

    Returns:
        Dicionário com ``rs``, ``rp``, ``c``, ``a_w`` e ``tau``.
    """
    m = measurement.sorted_by_frequency()
    rs, rp, c, a_w = _basic_estimates(m)
    peak_index = int(np.argmax(-m.z_imag))
    f_peak = float(m.frequency[peak_index])
    tau = float(max(1.0 / (2.0 * np.pi * f_peak), _EPS))
    return {"rs": rs, "rp": rp, "c": c, "a_w": a_w, "tau": tau}


@dataclass
class CircuitNode:
    """Nó da árvore de um circuito montado no editor.

    Attributes:
        kind: ``"series"``, ``"parallel"`` ou ``"element"``.
        element_code: Código do elemento (apenas para
            ``kind == "element"``).
        children: Nós filhos (apenas para grupos).
    """

    kind: str
    element_code: Optional[str] = None
    children: list["CircuitNode"] = field(default_factory=list)


@dataclass
class CircuitSpec:
    """Circuito montado, pronto para ajuste e desenho.

    Attributes:
        tree: Árvore do circuito.
        circuit_string: Circuito na sintaxe do ``impedance.py``.
        element_labels: Rótulos dos elementos (``R1``, ``CPE1``, ...),
            na ordem em que aparecem na string.
        element_codes: Códigos dos elementos, na mesma ordem.
        param_names: Nomes legíveis dos parâmetros, na ordem do ajuste.
        param_units: Unidades dos parâmetros.
        param_element: Índice do elemento de cada parâmetro.
    """

    tree: CircuitNode
    circuit_string: str
    element_labels: list[str]
    element_codes: list[str]
    param_names: list[str]
    param_units: list[str]
    param_element: list[int]

    @property
    def n_params(self) -> int:
        """Número total de parâmetros do circuito."""
        return len(self.param_names)


def build_circuit_spec(tree: CircuitNode) -> CircuitSpec:
    """Valida a árvore e gera a especificação completa do circuito.

    Args:
        tree: Árvore raiz (normalmente um grupo em série).

    Returns:
        :class:`CircuitSpec` com string, rótulos e parâmetros.

    Raises:
        ValueError: Se a árvore tiver grupos vazios, grupos paralelos
            com menos de 2 ramos, elementos desconhecidos ou nenhum
            elemento.
    """
    counters: dict[str, int] = {}
    labels: list[str] = []
    codes: list[str] = []
    param_names: list[str] = []
    param_units: list[str] = []
    param_element: list[int] = []

    def render(node: CircuitNode) -> str:
        if node.kind == "element":
            code = node.element_code or ""
            if code not in ELEMENTS:
                raise ValueError(f"Elemento desconhecido: '{code}'.")
            counters[code] = counters.get(code, 0) + 1
            label = f"{code}{counters[code]}"
            info = ELEMENTS[code]
            index = len(labels)
            labels.append(label)
            codes.append(code)
            single = len(info.param_labels) == 1
            for p_label, p_unit in zip(
                info.param_labels, info.param_units
            ):
                param_names.append(
                    label if single else f"{label} ({p_label})"
                )
                param_units.append(p_unit)
                param_element.append(index)
            return label
        if node.kind == "series":
            if not node.children:
                raise ValueError("Há um grupo em série vazio.")
            return "-".join(render(child) for child in node.children)
        if node.kind == "parallel":
            if len(node.children) < 2:
                raise ValueError(
                    "Um grupo paralelo precisa de pelo menos 2 ramos."
                )
            return (
                "p(" + ",".join(render(c) for c in node.children) + ")"
            )
        raise ValueError(f"Nó de circuito inválido: '{node.kind}'.")

    circuit_string = render(tree)
    if not labels:
        raise ValueError("O circuito não possui nenhum elemento.")
    return CircuitSpec(
        tree=tree,
        circuit_string=circuit_string,
        element_labels=labels,
        element_codes=codes,
        param_names=param_names,
        param_units=param_units,
        param_element=param_element,
    )


def default_guesses(
    spec: CircuitSpec,
    measurement: Optional[Measurement] = None,
) -> list[float]:
    """Gera estimativas iniciais para um circuito do editor.

    O primeiro resistor do circuito recebe a estimativa de ``Rs``
    (resistência série); os demais recebem ``Rp``.

    Args:
        spec: Especificação do circuito.
        measurement: Medição de referência para as estimativas; se
            ``None``, usa valores genéricos.

    Returns:
        Lista de estimativas na ordem dos parâmetros.
    """
    estimates = (
        spectrum_estimates(measurement)
        if measurement is not None
        else dict(_GENERIC_ESTIMATES)
    )
    guesses: list[float] = []
    first_resistor = True
    for code in spec.element_codes:
        values = ELEMENTS[code].default_guess(estimates)
        if code == "R" and first_resistor:
            values = [estimates["rs"]]
            first_resistor = False
        guesses.extend(float(v) for v in values)
    return guesses


def preset_tree(model_key: str) -> CircuitNode:
    """Árvore de circuito de um dos modelos pré-definidos.

    Args:
        model_key: Chave de um dos modelos em :data:`MODELS`.

    Returns:
        Árvore equivalente ao ``circuit_string`` do modelo.

    Raises:
        KeyError: Se ``model_key`` não existir.
    """
    if model_key not in MODELS:
        raise KeyError(f"Modelo desconhecido: '{model_key}'.")

    def element(code: str) -> CircuitNode:
        return CircuitNode(kind="element", element_code=code)

    if model_key == "randles":
        branch = CircuitNode(
            kind="parallel", children=[element("R"), element("C")]
        )
    elif model_key == "randles_cpe":
        branch = CircuitNode(
            kind="parallel", children=[element("R"), element("CPE")]
        )
    elif model_key == "randles_warburg":
        rw = CircuitNode(
            kind="series", children=[element("R"), element("W")]
        )
        branch = CircuitNode(kind="parallel", children=[rw, element("C")])
    else:  # randles_cpe_warburg
        rw = CircuitNode(
            kind="series", children=[element("R"), element("W")]
        )
        branch = CircuitNode(
            kind="parallel", children=[rw, element("CPE")]
        )
    return CircuitNode(kind="series", children=[element("R"), branch])


def fit_custom_circuit(
    measurement: Measurement,
    spec: CircuitSpec,
    initial_guess: Optional[Sequence[float]] = None,
) -> FitResult:
    """Ajusta um circuito montado no editor a uma medição.

    Args:
        measurement: Medição experimental.
        spec: Especificação do circuito
            (:func:`build_circuit_spec`).
        initial_guess: Estimativas iniciais opcionais (sobrepõem
            :func:`default_guesses`).

    Returns:
        :class:`FitResult` com parâmetros, incertezas e métricas.

    Raises:
        ValueError: Se a medição tiver poucos pontos, pontos com
            ``|Z| = 0`` ou estimativas com tamanho errado.
        RuntimeError: Se o ajuste não convergir.
    """
    m = measurement.sorted_by_frequency()
    n_params = spec.n_params
    if m.n_points <= n_params:
        raise ValueError(
            f"O circuito '{spec.circuit_string}' tem {n_params} "
            f"parâmetros e a medição '{m.name}' tem apenas "
            f"{m.n_points} pontos. São necessários mais pontos que "
            "parâmetros."
        )
    guess = (
        [float(v) for v in initial_guess]
        if initial_guess is not None
        else default_guesses(spec, m)
    )
    if len(guess) != n_params:
        raise ValueError(
            f"A estimativa inicial tem {len(guess)} valores; o "
            f"circuito '{spec.circuit_string}' requer {n_params}."
        )
    return _execute_fit(
        m,
        spec.circuit_string,
        guess,
        model_key="custom",
        model_name=f"Personalizado ({spec.circuit_string})",
        param_names=tuple(spec.param_names),
        param_units=tuple(spec.param_units),
    )
