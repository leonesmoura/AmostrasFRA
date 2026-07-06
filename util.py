"""Utilidades centrais do AMOSTRAS FRA 2.0.

Este módulo concentra:

* A estrutura de dados :class:`Measurement`, que representa uma medição
  de Espectroscopia de Impedância (EIS/FRA).
* Rotinas robustas de interpretação de texto colado (Excel, Metrohm
  NOVA, arquivos TXT) com detecção automática de delimitadores e de
  separador decimal (ponto ou vírgula).
* Leitura de arquivos CSV, TXT, XLSX e ODS com mapeamento automático
  de colunas.
* Configuração de logging da aplicação.

Todo o processamento numérico é vetorizado com NumPy.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

APP_NAME: str = "AMOSTRAS FRA 2.0"
APP_VERSION: str = "2.0.0"

#: Rótulos canônicos das colunas da tabela de entrada de dados.
#: Tensão e corrente ficam ao final para preservar a ordem clássica
#: das colunas de impedância (colagens posicionais continuam válidas).
COLUMN_LABELS: tuple[str, ...] = (
    "Frequência (Hz)",
    "Z' (Ω)",
    "-Z'' (Ω)",
    "|Z| (Ω)",
    "Fase (°)",
    "Tensão (V)",
    "Corrente (A)",
)

#: Índices das colunas canônicas.
COL_FREQ: int = 0
COL_ZREAL: int = 1
COL_MINUS_ZIMAG: int = 2
COL_ZMOD: int = 3
COL_PHASE: int = 4
COL_VOLT: int = 5
COL_CURR: int = 6

#: Padrões (regex, em minúsculas) da coluna imaginária.  Rótulos SEM o
#: prefixo "-" (ex.: "Z''", "Zim", "Im(Z)") indicam Z'' assinado
#: (negativo para sistemas capacitivos, convenção de ZView/Gamry) e
#: podem exigir inversão de sinal ao entrar na coluna canônica -Z''.
_IMAG_PATTERNS: tuple[str, ...] = (
    r"z''", r"z\"", r"zim", r"z_im", r"im\(z\)", r"imagin", r"\bimag\b",
)

#: Padrões (regex, em minúsculas) das demais colunas canônicas.
_HEADER_PATTERNS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (COL_FREQ, (r"freq", r"^f\b", r"^f$", r"\bhz\b")),
    (COL_ZREAL, (r"z'", r"zre", r"z_re", r"re\(z\)", r"\breal\b")),
    (COL_ZMOD, (r"\|z\|", r"zmod", r"z_mod", r"\bmod\b", r"magnitude",
                r"\bmag\b", r"zabs")),
    (COL_PHASE, (r"fase", r"phase", r"phi", r"ângulo", r"angulo",
                 r"\bang\b", r"°", r"deg")),
    (COL_VOLT, (r"tens", r"volt", r"\bv\b", r"\bvrms\b", r"\be\s*\(v")),
    (COL_CURR, (r"corrente", r"current", r"\bi\b", r"\birms\b",
                r"\bamp")),
)

#: Mapeamento de cabeçalho: coluna de origem → (coluna canônica,
#: flag "rótulo imaginário sem sinal").
HeaderMap = dict[int, tuple[int, bool]]

_UNICODE_MINUS: str = "−"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def configure_logging(level: int = logging.INFO) -> None:
    """Configura o logging global da aplicação.

    Os registros são enviados ao console e a um arquivo rotativo em
    ``~/.amostras_fra/amostras_fra.log``.

    Args:
        level: Nível mínimo de logging (padrão: ``logging.INFO``).
    """
    root = logging.getLogger()
    if root.handlers:
        # Logging já configurado (evita handlers duplicados).
        return
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        log_dir = Path.home() / ".amostras_fra"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "amostras_fra.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - depende do sistema
        root.warning("Não foi possível criar arquivo de log: %s", exc)


# ---------------------------------------------------------------------------
# Estrutura de dados principal
# ---------------------------------------------------------------------------
@dataclass
class Measurement:
    """Uma medição de impedância (espectro completo).

    A convenção interna é a convenção física usual: a impedância
    complexa é ``Z = z_real + 1j * z_imag``.  Para sistemas capacitivos
    ``z_imag`` é negativo; a tabela e os gráficos de Nyquist exibem
    ``-Z''`` (valor positivo no primeiro quadrante).

    Attributes:
        name: Nome da medição (por exemplo, ``"FRA0F"``).
        frequency: Frequências em Hz (array 1-D, valores positivos).
        z_real: Parte real da impedância, em ohms.
        z_imag: Parte imaginária da impedância, em ohms (com sinal).
        corrected: Indica se a medição já recebeu correção do
            instrumento.
        notes: Observações livres do usuário.
    """

    name: str
    frequency: np.ndarray
    z_real: np.ndarray
    z_imag: np.ndarray
    corrected: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        self.frequency = np.asarray(self.frequency, dtype=float)
        self.z_real = np.asarray(self.z_real, dtype=float)
        self.z_imag = np.asarray(self.z_imag, dtype=float)
        if not (
            self.frequency.shape == self.z_real.shape == self.z_imag.shape
        ):
            raise ValueError(
                "frequency, z_real e z_imag devem ter o mesmo tamanho "
                f"(obtidos: {self.frequency.shape}, {self.z_real.shape}, "
                f"{self.z_imag.shape})."
            )
        if self.frequency.ndim != 1:
            raise ValueError("Os dados devem ser vetores 1-D.")
        if self.frequency.size < 2:
            raise ValueError("A medição precisa de pelo menos 2 pontos.")
        if np.any(~np.isfinite(self.frequency)) or np.any(
            self.frequency <= 0.0
        ):
            raise ValueError(
                "Todas as frequências devem ser finitas e positivas."
            )
        if np.any(~np.isfinite(self.z_real)) or np.any(
            ~np.isfinite(self.z_imag)
        ):
            raise ValueError("Z' e Z'' devem conter apenas valores finitos.")

    # -- Propriedades derivadas ---------------------------------------
    @property
    def n_points(self) -> int:
        """Número de pontos do espectro."""
        return int(self.frequency.size)

    @property
    def z_complex(self) -> np.ndarray:
        """Impedância complexa ``Z = Z' + jZ''``."""
        return self.z_real + 1j * self.z_imag

    @property
    def minus_z_imag(self) -> np.ndarray:
        """Parte imaginária com sinal trocado (``-Z''``)."""
        return -self.z_imag

    @property
    def magnitude(self) -> np.ndarray:
        """Módulo da impedância ``|Z|``."""
        return np.abs(self.z_complex)

    @property
    def phase_deg(self) -> np.ndarray:
        """Fase de ``Z`` em graus."""
        return np.degrees(np.angle(self.z_complex))

    @property
    def omega(self) -> np.ndarray:
        """Frequência angular ``ω = 2πf`` em rad/s."""
        return 2.0 * np.pi * self.frequency

    # -- Construtores -------------------------------------------------
    @classmethod
    def from_components(
        cls,
        name: str,
        frequency: Sequence[float] | np.ndarray,
        z_real: Optional[Sequence[Optional[float]]] = None,
        minus_z_imag: Optional[Sequence[Optional[float]]] = None,
        magnitude: Optional[Sequence[Optional[float]]] = None,
        phase_deg: Optional[Sequence[Optional[float]]] = None,
        voltage: Optional[Sequence[Optional[float]]] = None,
        current: Optional[Sequence[Optional[float]]] = None,
    ) -> "Measurement":
        """Cria uma medição a partir das componentes disponíveis.

        Cada ponto é resolvido preferindo o par cartesiano
        ``(Z', -Z'')``; quando ausente, usa-se o par polar
        ``(|Z|, fase)``.  Se ``|Z|`` estiver ausente mas houver tensão
        e corrente, o módulo é calculado como ``|Z| = V / I``.  Pontos
        sem nenhum conjunto completo geram :class:`ValueError`
        indicando as linhas problemáticas.

        Args:
            name: Nome da medição.
            frequency: Frequências em Hz.
            z_real: Parte real (Ω) ou ``None`` por ponto.
            minus_z_imag: ``-Z''`` (Ω) ou ``None`` por ponto.
            magnitude: ``|Z|`` (Ω) ou ``None`` por ponto.
            phase_deg: Fase em graus ou ``None`` por ponto.
            voltage: Tensão (V) ou ``None`` por ponto.
            current: Corrente (A) ou ``None`` por ponto.

        Returns:
            A medição construída, ordenada por frequência crescente.

        Raises:
            ValueError: Se houver pontos sem dados suficientes.
        """
        freq = np.asarray(
            [np.nan if v is None else float(v) for v in frequency],
            dtype=float,
        )
        n = freq.size

        def _to_array(
            values: Optional[Sequence[Optional[float]]],
        ) -> np.ndarray:
            if values is None:
                return np.full(n, np.nan)
            arr = np.asarray(
                [np.nan if v is None else float(v) for v in values],
                dtype=float,
            )
            if arr.size != n:
                raise ValueError(
                    "Todas as colunas devem ter o mesmo número de linhas."
                )
            return arr

        re_arr = _to_array(z_real)
        mim_arr = _to_array(minus_z_imag)
        mag_arr = _to_array(magnitude)
        ph_arr = _to_array(phase_deg)
        volt_arr = _to_array(voltage)
        curr_arr = _to_array(current)

        # |Z| ausente com tensão e corrente presentes: |Z| = V / I.
        vi_ok = (
            np.isfinite(volt_arr)
            & np.isfinite(curr_arr)
            & (curr_arr != 0.0)
        )
        fill_vi = ~np.isfinite(mag_arr) & vi_ok
        if np.any(fill_vi):
            with np.errstate(divide="ignore", invalid="ignore"):
                mag_arr = np.where(
                    fill_vi, np.abs(volt_arr / curr_arr), mag_arr
                )

        cart_ok = np.isfinite(re_arr) & np.isfinite(mim_arr)
        polar_ok = np.isfinite(mag_arr) & np.isfinite(ph_arr)
        freq_ok = np.isfinite(freq) & (freq > 0.0)

        usable = freq_ok & (cart_ok | polar_ok)
        bad = ~usable & (
            freq_ok
            | np.isfinite(re_arr)
            | np.isfinite(mim_arr)
            | np.isfinite(mag_arr)
            | np.isfinite(ph_arr)
            | np.isfinite(volt_arr)
            | np.isfinite(curr_arr)
        )
        if np.any(bad):
            rows = ", ".join(str(i + 1) for i in np.nonzero(bad)[0][:10])
            raise ValueError(
                "Linhas incompletas ou inválidas (é necessária frequência "
                "positiva e um conjunto completo: Z'/-Z'', |Z|/Fase ou "
                f"Tensão/Corrente/Fase): linhas {rows}."
            )
        if int(np.count_nonzero(usable)) < 2:
            raise ValueError(
                "São necessários pelo menos 2 pontos válidos para criar "
                "uma medição."
            )

        freq_u = freq[usable]
        re_u = re_arr[usable]
        mim_u = mim_arr[usable]
        mag_u = mag_arr[usable]
        ph_u = ph_arr[usable]
        cart_u = cart_ok[usable]

        phase_rad = np.radians(ph_u)
        z_re = np.where(cart_u, re_u, mag_u * np.cos(phase_rad))
        z_im = np.where(cart_u, -mim_u, mag_u * np.sin(phase_rad))

        order = np.argsort(freq_u)
        return cls(
            name=name,
            frequency=freq_u[order],
            z_real=z_re[order],
            z_imag=z_im[order],
        )

    # -- Operações ----------------------------------------------------
    def sorted_by_frequency(self) -> "Measurement":
        """Retorna cópia ordenada por frequência crescente."""
        order = np.argsort(self.frequency)
        return Measurement(
            name=self.name,
            frequency=self.frequency[order].copy(),
            z_real=self.z_real[order].copy(),
            z_imag=self.z_imag[order].copy(),
            corrected=self.corrected,
            notes=self.notes,
        )

    def copy(self, new_name: Optional[str] = None) -> "Measurement":
        """Retorna uma cópia profunda, opcionalmente renomeada."""
        return Measurement(
            name=new_name if new_name is not None else self.name,
            frequency=self.frequency.copy(),
            z_real=self.z_real.copy(),
            z_imag=self.z_imag.copy(),
            corrected=self.corrected,
            notes=self.notes,
        )

    def to_dataframe(self) -> pd.DataFrame:
        """Converte a medição em :class:`pandas.DataFrame` canônico."""
        return pd.DataFrame(
            {
                COLUMN_LABELS[COL_FREQ]: self.frequency,
                COLUMN_LABELS[COL_ZREAL]: self.z_real,
                COLUMN_LABELS[COL_MINUS_ZIMAG]: self.minus_z_imag,
                COLUMN_LABELS[COL_ZMOD]: self.magnitude,
                COLUMN_LABELS[COL_PHASE]: self.phase_deg,
            }
        )


# ---------------------------------------------------------------------------
# Curva I-V do módulo fotovoltaico
# ---------------------------------------------------------------------------
@dataclass
class IVCurve:
    """Curva corrente-tensão (I-V) de um módulo fotovoltaico.

    Entrada composta apenas por pares tensão/corrente (sem
    frequência), usada para caracterização estática do módulo.

    Attributes:
        name: Nome da curva (por exemplo, ``"IV 0 pancadas"``).
        voltage: Tensões em volts (array 1-D).
        current: Correntes em ampères (array 1-D).
        notes: Observações livres do usuário.
    """

    name: str
    voltage: np.ndarray
    current: np.ndarray
    notes: str = ""

    def __post_init__(self) -> None:
        self.voltage = np.asarray(self.voltage, dtype=float)
        self.current = np.asarray(self.current, dtype=float)
        if self.voltage.shape != self.current.shape:
            raise ValueError(
                "Tensão e corrente devem ter o mesmo tamanho."
            )
        if self.voltage.ndim != 1:
            raise ValueError("Os dados devem ser vetores 1-D.")
        if self.voltage.size < 3:
            raise ValueError(
                "A curva I-V precisa de pelo menos 3 pontos."
            )
        if np.any(~np.isfinite(self.voltage)) or np.any(
            ~np.isfinite(self.current)
        ):
            raise ValueError(
                "Tensão e corrente devem conter apenas valores finitos."
            )
        order = np.argsort(self.voltage, kind="stable")
        self.voltage = self.voltage[order]
        self.current = self.current[order]

    # -- Propriedades derivadas ------------------------------------------
    @property
    def n_points(self) -> int:
        """Número de pontos da curva."""
        return int(self.voltage.size)

    @property
    def power(self) -> np.ndarray:
        """Potência ``P = V·I`` em watts."""
        return self.voltage * self.current

    @property
    def isc(self) -> float:
        """Corrente de curto-circuito (I em V = 0), interpolada.

        Se a varredura não cruzar V = 0, retorna a corrente do ponto
        de menor tensão em módulo (aproximação).
        """
        if self.voltage[0] <= 0.0 <= self.voltage[-1]:
            return float(np.interp(0.0, self.voltage, self.current))
        return float(self.current[int(np.argmin(np.abs(self.voltage)))])

    @property
    def voc(self) -> float:
        """Tensão de circuito aberto (V em I = 0), interpolada.

        Retorna ``nan`` se a corrente não cruzar zero na varredura.
        """
        current = self.current
        sign_change = np.nonzero(
            np.sign(current[:-1]) * np.sign(current[1:]) < 0.0
        )[0]
        zero_hits = np.nonzero(current == 0.0)[0]
        if zero_hits.size:
            return float(self.voltage[zero_hits[0]])
        if not sign_change.size:
            return float("nan")
        i = int(sign_change[0])
        v1, v2 = self.voltage[i], self.voltage[i + 1]
        c1, c2 = current[i], current[i + 1]
        return float(v1 - c1 * (v2 - v1) / (c2 - c1))

    @property
    def p_max(self) -> float:
        """Potência máxima da curva (W)."""
        return float(np.max(self.power))

    @property
    def v_mp(self) -> float:
        """Tensão no ponto de máxima potência (V)."""
        return float(self.voltage[int(np.argmax(self.power))])

    @property
    def i_mp(self) -> float:
        """Corrente no ponto de máxima potência (A)."""
        return float(self.current[int(np.argmax(self.power))])

    @property
    def fill_factor(self) -> float:
        """Fator de forma ``FF = Pmax / (Voc · Isc)`` (ou ``nan``)."""
        isc = self.isc
        voc = self.voc
        if not np.isfinite(voc) or isc == 0.0 or voc == 0.0:
            return float("nan")
        return float(self.p_max / (isc * voc))

    # -- Construtores / conversões -----------------------------------------
    @classmethod
    def from_rows(
        cls,
        name: str,
        rows: Sequence[Sequence[Optional[float]]],
    ) -> "IVCurve":
        """Cria a curva a partir de linhas ``[tensão, corrente]``.

        Linhas incompletas geram :class:`ValueError` com os números
        das linhas problemáticas.
        """
        voltage: list[float] = []
        current: list[float] = []
        bad: list[int] = []
        for index, row in enumerate(rows):
            values = list(row) + [None] * (2 - len(row))
            v, i = values[0], values[1]
            if v is None and i is None:
                continue
            if v is None or i is None:
                bad.append(index + 1)
                continue
            voltage.append(float(v))
            current.append(float(i))
        if bad:
            listed = ", ".join(str(b) for b in bad[:10])
            raise ValueError(
                "Linhas incompletas (tensão E corrente são "
                f"obrigatórias): linhas {listed}."
            )
        if len(voltage) < 3:
            raise ValueError(
                "São necessários pelo menos 3 pontos (tensão e "
                "corrente) para criar a curva I-V."
            )
        return cls(name=name, voltage=np.asarray(voltage),
                   current=np.asarray(current))

    def copy(self, new_name: Optional[str] = None) -> "IVCurve":
        """Retorna uma cópia profunda, opcionalmente renomeada."""
        return IVCurve(
            name=new_name if new_name is not None else self.name,
            voltage=self.voltage.copy(),
            current=self.current.copy(),
            notes=self.notes,
        )

    def metrics(self) -> dict[str, float]:
        """Parâmetros característicos da curva."""
        return {
            "isc": self.isc,
            "voc": self.voc,
            "p_max": self.p_max,
            "v_mp": self.v_mp,
            "i_mp": self.i_mp,
            "fill_factor": self.fill_factor,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Converte a curva em :class:`pandas.DataFrame`."""
        return pd.DataFrame(
            {
                "Tensão (V)": self.voltage,
                "Corrente (A)": self.current,
                "Potência (W)": self.power,
            }
        )


#: Rótulos legíveis (pt-BR) das métricas de :class:`IVCurve`.
IV_METRIC_LABELS: dict[str, str] = {
    "isc": "Isc (A)",
    "voc": "Voc (V)",
    "p_max": "Pmáx (W)",
    "v_mp": "Vmp (V)",
    "i_mp": "Imp (A)",
    "fill_factor": "FF",
}


# ---------------------------------------------------------------------------
# Interpretação de números e texto tabular
# ---------------------------------------------------------------------------
def parse_number(token: str) -> Optional[float]:
    """Converte um token textual em ``float``.

    Aceita separador decimal com ponto ou vírgula, separadores de
    milhar (vírgula, ponto, espaço inseparável), sinal de menos
    Unicode e notação científica (inclusive com vírgula decimal, como
    ``1,23E+03``).  Tokens com espaço comum interno são rejeitados —
    quase sempre indicam dois valores unidos por erro de delimitador.

    Args:
        token: Texto de uma célula.

    Returns:
        O valor numérico, ou ``None`` se o token não for numérico.
    """
    text = token.strip().replace(_UNICODE_MINUS, "-")
    # Espaço inseparável e espaço fino são separadores de milhar.
    text = text.replace("\u00a0", "").replace("\u202f", "")
    if not text:
        return None
    if " " in text:
        return None
    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        # O separador mais à direita é o decimal; o outro é de milhar.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        if text.count(",") == 1:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_dot and text.count(".") > 1:
        # Milhar pt-BR sem casa decimal: "1.234.567".
        if re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
        else:
            return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not np.isfinite(value):
        return None
    return value


def _split_line(line: str, delimiter: str) -> list[str]:
    """Divide uma linha usando o delimitador indicado.

    O delimitador ``"ws"`` representa qualquer sequência de espaços.
    """
    if delimiter == "ws":
        return line.split()
    return line.split(delimiter)


def _delimiter_score(lines: Sequence[str], delimiter: str) -> tuple[int, int]:
    """Pontua um delimitador candidato sobre as linhas do texto.

    A pontuação é ``(total de tokens numéricos, nº de linhas com a
    contagem de colunas mais frequente)`` — quanto mais valores
    reconhecidos e mais consistentes as colunas, melhor o candidato.

    Args:
        lines: Linhas não vazias do texto.
        delimiter: Delimitador candidato (``","`` ou ``"ws"``).

    Returns:
        Tupla de pontuação comparável lexicograficamente.
    """
    numeric_total = 0
    column_counts: list[int] = []
    for line in lines:
        tokens = _split_line(line, delimiter)
        numeric = sum(parse_number(tok) is not None for tok in tokens)
        if numeric == 0:
            continue
        numeric_total += numeric
        column_counts.append(numeric)
    if not column_counts:
        return (0, 0)
    consistency = Counter(column_counts).most_common(1)[0][1]
    return (numeric_total, consistency)


def detect_delimiter(text: str) -> str:
    """Detecta o delimitador de colunas de um texto tabular.

    Regras (em ordem de prioridade):

    1. Tabulação, se presente (padrão do Excel e do Metrohm NOVA).
    2. Ponto e vírgula, se presente (CSV pt-BR).
    3. Se não houver ponto e cada linha tiver no máximo uma vírgula,
       a vírgula é separador decimal → espaços.
    4. Caso contrário, vírgula e espaços são pontuados por
       :func:`_delimiter_score` (quantidade de valores numéricos
       reconhecidos e consistência de colunas) e vence o candidato de
       maior pontuação.  Isso evita que um ponto no cabeçalho ou uma
       vírgula em uma linha de título corrompam dados separados por
       espaços.

    Args:
        text: Texto tabular bruto.

    Returns:
        ``"\\t"``, ``";"``, ``","`` ou ``"ws"``.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "ws"
    body = "\n".join(lines)
    if "\t" in body:
        return "\t"
    if ";" in body:
        return ";"
    if "," not in body:
        return "ws"
    if "." not in body and all(ln.count(",") <= 1 for ln in lines):
        # Uma vírgula por linha, sem pontos: separador decimal pt-BR.
        return "ws"
    comma_score = _delimiter_score(lines, ",")
    ws_score = _delimiter_score(lines, "ws")
    if comma_score > ws_score:
        return ","
    if ws_score > comma_score:
        return "ws"
    return "ws" if any(len(ln.split()) > 1 for ln in lines) else ","


def parse_table_text(
    text: str,
) -> list[list[Optional[float]]]:
    """Interpreta texto tabular colado (Excel, NOVA, TXT).

    Linhas de cabeçalho (sem nenhum valor numérico) são ignoradas.
    Células não numéricas em linhas de dados tornam-se ``None``.

    Args:
        text: Texto bruto vindo da área de transferência ou de arquivo.

    Returns:
        Lista de linhas, cada uma com os valores das colunas
        (``float`` ou ``None``).
    """
    delimiter = detect_delimiter(text)
    rows: list[list[Optional[float]]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        tokens = _split_line(raw_line, delimiter)
        parsed = [parse_number(tok) for tok in tokens]
        if not any(v is not None for v in parsed):
            # Linha de cabeçalho ou comentário.
            continue
        rows.append(parsed)
    logger.debug(
        "parse_table_text: delimitador=%r, %d linha(s) de dados.",
        delimiter,
        len(rows),
    )
    return rows


def _match_header_column(header_text: str) -> Optional[tuple[int, bool]]:
    """Mapeia um texto de cabeçalho para a coluna canônica.

    Returns:
        Tupla ``(coluna, imag_sem_sinal)`` ou ``None``.  O segundo
        elemento é ``True`` quando o rótulo indica a coluna imaginária
        SEM o prefixo de sinal (``"Z''"``, ``"Zim"``, ``"Im(Z)"``) —
        formato de ZView/Gamry em que os valores são o Z'' assinado
        (negativo para sistemas capacitivos) e podem precisar de
        inversão para entrar na coluna ``-Z''``.
    """
    lowered = header_text.strip().lower().replace(_UNICODE_MINUS, "-")
    if not lowered:
        return None
    for pattern in _IMAG_PATTERNS:
        match = re.search(pattern, lowered)
        if match is not None:
            signed = "-" in lowered[: match.start()]
            return (COL_MINUS_ZIMAG, not signed)
    for col_index, patterns in _HEADER_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return (col_index, False)
    return None


def map_header_to_columns(
    header_tokens: Sequence[str],
    require_freq: bool = True,
) -> Optional[HeaderMap]:
    """Cria o mapeamento *coluna de origem → coluna canônica*.

    Args:
        header_tokens: Textos do cabeçalho, na ordem original.
        require_freq: Exige a coluna de frequência (padrão dos dados
            de impedância).  Use ``False`` para tabelas sem
            frequência, como curvas I-V.

    Returns:
        Dicionário ``{índice_origem: (índice_canônico,
        imag_sem_sinal)}`` ou ``None`` se nenhuma coluna exigida for
        reconhecida.
    """
    mapping: HeaderMap = {}
    used: set[int] = set()
    for src_index, token in enumerate(header_tokens):
        target = _match_header_column(str(token))
        if target is not None and target[0] not in used:
            mapping[src_index] = target
            used.add(target[0])
    if require_freq and COL_FREQ not in used:
        return None
    return mapping or None


def arrange_rows_to_canonical(
    rows: list[list[Optional[float]]],
    column_map: Optional[HeaderMap] = None,
) -> list[list[Optional[float]]]:
    """Reorganiza linhas de dados nas 5 colunas canônicas.

    Sem ``column_map``, assume a ordem posicional
    ``Frequência, Z', -Z'' [, |Z|, Fase]``.

    Quando o cabeçalho da coluna imaginária não traz o sinal
    (``"Z''"``/``"Zim"``, convenção de ZView/Gamry) e a maioria dos
    valores é negativa, os valores são invertidos ao entrar na coluna
    ``-Z''`` — caso contrário o espectro seria importado espelhado.

    Args:
        rows: Linhas de dados interpretadas.
        column_map: Mapeamento origem → canônico (opcional).

    Returns:
        Linhas com exatamente 5 colunas (``float`` ou ``None``).
    """
    negate_sources: set[int] = set()
    if column_map:
        for src, (dst, unsigned_imag) in column_map.items():
            if dst != COL_MINUS_ZIMAG or not unsigned_imag:
                continue
            values = [
                row[src]
                for row in rows
                if src < len(row) and row[src] is not None
            ]
            negatives = sum(1 for v in values if v < 0.0)
            if values and negatives * 2 > len(values):
                negate_sources.add(src)
                logger.info(
                    "Coluna imaginária com rótulo sem sinal e valores "
                    "majoritariamente negativos (Z'' assinado, "
                    "convenção ZView/Gamry): sinal invertido ao "
                    "importar para a coluna '-Z'''."
                )

    canonical: list[list[Optional[float]]] = []
    for row in rows:
        out: list[Optional[float]] = [None] * len(COLUMN_LABELS)
        if column_map:
            for src, (dst, _unsigned) in column_map.items():
                if src < len(row):
                    value = row[src]
                    if value is not None and src in negate_sources:
                        value = -value
                    out[dst] = value
        else:
            for i, value in enumerate(row[: len(COLUMN_LABELS)]):
                out[i] = value
        canonical.append(out)
    return canonical


# ---------------------------------------------------------------------------
# Leitura de arquivos
# ---------------------------------------------------------------------------
def _rows_from_dataframe(
    df: pd.DataFrame,
    require_freq: bool = True,
) -> tuple[list[list[Optional[float]]], Optional[HeaderMap]]:
    """Converte um DataFrame bruto (sem cabeçalho) em linhas + mapa.

    Todas as linhas não numéricas anteriores aos dados são examinadas
    como possível cabeçalho (linhas de título acima do cabeçalho real
    não descartam o mapeamento).
    """
    raw_rows: list[list[str]] = [
        ["" if pd.isna(cell) else str(cell) for cell in record]
        for record in df.itertuples(index=False, name=None)
    ]
    column_map: Optional[HeaderMap] = None
    data_rows: list[list[Optional[float]]] = []
    data_started = False
    for tokens in raw_rows:
        parsed = [parse_number(tok) for tok in tokens]
        if not any(v is not None for v in parsed):
            if (
                not data_started
                and column_map is None
                and any(tok.strip() for tok in tokens)
            ):
                column_map = map_header_to_columns(
                    tokens, require_freq
                )
            continue
        data_started = True
        data_rows.append(parsed)
    return data_rows, column_map


def load_table_from_file_ex(
    path: str | Path,
) -> tuple[list[list[Optional[float]]], bool]:
    """Lê um arquivo de dados e retorna linhas canônicas + origem.

    Formatos suportados: ``.csv``, ``.txt``, ``.dat``, ``.xlsx``,
    ``.xlsm``, ``.ods``.

    Args:
        path: Caminho do arquivo.

    Returns:
        Tupla ``(linhas, cabecalho_reconhecido)``: linhas com as 5
        colunas canônicas e um booleano indicando se as colunas foram
        atribuídas por cabeçalho reconhecido (``True``) ou por ordem
        posicional (``False``).

    Raises:
        ValueError: Se a extensão não for suportada ou o arquivo não
            contiver dados numéricos.
        OSError: Se o arquivo não puder ser lido.
    """
    rows, column_map = _read_rows_and_map(Path(path))
    return (
        arrange_rows_to_canonical(rows, column_map),
        column_map is not None,
    )


def _read_rows_and_map(
    file_path: Path,
    require_freq: bool = True,
) -> tuple[list[list[Optional[float]]], Optional[HeaderMap]]:
    """Lê as linhas brutas e o mapeamento de cabeçalho de um arquivo.

    Raises:
        ValueError: Se a extensão não for suportada ou não houver
            dados numéricos.
    """
    suffix = file_path.suffix.lower()
    logger.info("Importando arquivo: %s", file_path)

    if suffix in {".csv", ".txt", ".dat"}:
        text = _read_text_any_encoding(file_path)
        rows = parse_table_text(text)
        column_map = _header_map_from_text(text, require_freq)
    elif suffix in {".xlsx", ".xlsm"}:
        df = pd.read_excel(file_path, header=None, dtype=object)
        rows, column_map = _rows_from_dataframe(df, require_freq)
    elif suffix == ".ods":
        df = pd.read_excel(file_path, header=None, dtype=object,
                           engine="odf")
        rows, column_map = _rows_from_dataframe(df, require_freq)
    else:
        raise ValueError(
            f"Extensão de arquivo não suportada: '{suffix}'. Use CSV, "
            "TXT, XLSX ou ODS."
        )

    if not rows:
        raise ValueError(
            "Nenhuma linha de dados numéricos foi encontrada no arquivo."
        )
    return rows, column_map


def load_iv_table_from_file(
    path: str | Path,
) -> list[list[Optional[float]]]:
    """Lê um arquivo de curva I-V e retorna linhas ``[tensão, corrente]``.

    Se o cabeçalho identificar as colunas de tensão e corrente
    (``Tensão``/``V`` e ``Corrente``/``I``), elas são usadas em
    qualquer ordem; caso contrário, assume-se a ordem posicional
    ``tensão, corrente`` (duas primeiras colunas).

    Args:
        path: Caminho do arquivo (CSV, TXT, XLSX ou ODS).

    Returns:
        Linhas com 2 colunas (``float`` ou ``None``).

    Raises:
        ValueError: Se a extensão não for suportada ou não houver
            dados numéricos.
    """
    rows, column_map = _read_rows_and_map(
        Path(path), require_freq=False
    )
    src_volt: Optional[int] = None
    src_curr: Optional[int] = None
    if column_map:
        for src, (dst, _unsigned) in column_map.items():
            if dst == COL_VOLT:
                src_volt = src
            elif dst == COL_CURR:
                src_curr = src
    result: list[list[Optional[float]]] = []
    if src_volt is not None and src_curr is not None:
        for row in rows:
            volt = row[src_volt] if src_volt < len(row) else None
            curr = row[src_curr] if src_curr < len(row) else None
            result.append([volt, curr])
    else:
        for row in rows:
            padded = list(row) + [None] * (2 - len(row))
            result.append([padded[0], padded[1]])
    return result


def load_table_from_file(path: str | Path) -> list[list[Optional[float]]]:
    """Lê um arquivo de dados e retorna linhas nas colunas canônicas.

    Atalho para :func:`load_table_from_file_ex` que descarta a
    informação de origem do mapeamento.
    """
    return load_table_from_file_ex(path)[0]


def _read_text_any_encoding(file_path: Path) -> str:
    """Lê texto detectando UTF-8, UTF-16 (com/sem BOM) e Latin-1.

    Arquivos "Texto Unicode" do Excel/Windows são UTF-16; sem esta
    detecção, o Latin-1 os "decodificaria" com NULs intercalados e
    nenhum número seria reconhecido.
    """
    data = file_path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    sample = data[:4096]
    if sample and sample.count(0) > len(sample) // 10:
        # Alta densidade de bytes nulos: UTF-16 sem BOM.
        for encoding in ("utf-16-le", "utf-16-be"):
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                continue
            if "\x00" not in text:
                logger.info(
                    "Arquivo '%s' decodificado como %s (sem BOM).",
                    file_path.name,
                    encoding,
                )
                return text
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def header_map_from_text(text: str) -> Optional[HeaderMap]:
    """Procura uma linha de cabeçalho no texto e monta o mapeamento.

    Versão pública de :func:`_header_map_from_text`, usada pela
    colagem inteligente da tabela de dados.
    """
    return _header_map_from_text(text)


def _header_map_from_text(
    text: str, require_freq: bool = True
) -> Optional[HeaderMap]:
    """Procura uma linha de cabeçalho no texto e monta o mapeamento.

    Todas as linhas não numéricas anteriores aos dados são examinadas
    (linhas de título acima do cabeçalho real são ignoradas).
    """
    delimiter = detect_delimiter(text)
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        tokens = _split_line(raw_line, delimiter)
        parsed = [parse_number(tok) for tok in tokens]
        if any(v is not None for v in parsed):
            # Primeira linha de dados: não há (mais) cabeçalho.
            return None
        mapping = map_header_to_columns(tokens, require_freq)
        if mapping is not None:
            return mapping
    return None


# ---------------------------------------------------------------------------
# Auxiliares diversos
# ---------------------------------------------------------------------------
def unique_name(base: str, existing: Sequence[str]) -> str:
    """Gera um nome único acrescentando sufixo numérico se necessário.

    Args:
        base: Nome desejado.
        existing: Nomes já em uso.

    Returns:
        ``base`` ou ``base (n)`` com o menor ``n`` livre.
    """
    if base not in existing:
        return base
    index = 2
    while f"{base} ({index})" in existing:
        index += 1
    return f"{base} ({index})"


def format_engineering(value: float, unit: str = "") -> str:
    """Formata um valor em notação de engenharia (k, M, m, µ, ...).

    Args:
        value: Valor numérico.
        unit: Unidade a ser anexada (por exemplo, ``"Ω"``).

    Returns:
        Texto formatado, por exemplo ``"1.234 kΩ"``.
    """
    if not np.isfinite(value):
        return f"{value} {unit}".strip()
    if value == 0.0:
        return f"0 {unit}".strip()
    prefixes = {
        -15: "f", -12: "p", -9: "n", -6: "µ", -3: "m",
        0: "", 3: "k", 6: "M", 9: "G", 12: "T",
    }
    exponent = int(np.floor(np.log10(abs(value)) / 3.0) * 3)
    exponent = max(-15, min(12, exponent))
    scaled = value / (10.0 ** exponent)
    return f"{scaled:.4g} {prefixes[exponent]}{unit}".strip()


@dataclass
class SessionState:
    """Estado agregado da sessão de análise (para relatórios).

    Attributes:
        measurements: Medições ativas, indexadas por nome.
        observations: Texto livre de observações do usuário.
    """

    measurements: dict[str, Measurement] = field(default_factory=dict)
    observations: str = ""
