"""Assistente de calibração do instrumento AD5933 (AMOSTRAS FRA 2.0).

O AD5933 não devolve ohms: ele devolve um par real/imaginário
proporcional à **corrente** que atravessa a amostra. Transformar isso em
impedância exige conhecer três coisas do caminho de medição:

* o **ganho** ``K(f)`` do estágio de transimpedância mais o conversor;
* a **fase do sistema**, que não é constante — ela varre dezenas de graus
  ao longo da banda por causa do atraso do caminho analógico e da DFT;
* a **resistência de saída do próprio chip** (``ROUT``), que fica em
  série com a amostra.

O modelo, validado em bancada, é::

    mag = K(f) / (ROUT + |Z|)

e **não** ``mag ~ 1/|Z|``. É por isso que a calibração precisa de **dois**
padrões: com um só, ganho e ``ROUT`` se confundem, a resposta vira afim e
o erro chega a dezenas de porcento nas impedâncias baixas — em 150 Ω o
``ROUT`` de ~230 Ω é *maior que a própria amostra*.

Este módulo implementa a matemática e a janela guiada que conduz o
usuário pela medição dos padrões, resolve os coeficientes e os grava na
memória não volátil da placa (comando ``W`` do firmware), dispensando
recompilar o firmware a cada calibração.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from plots import PlotCanvas

logger = logging.getLogger(__name__)

# Limites de sanidade da magnitude bruta (contagens da DFT). O teto real de
# ceifamento medido nesta placa fica perto de 20.200; abaixo de ~300 o ruído
# de quantização já domina.
MAG_SATURADA = 15000.0
MAG_FRACA = 300.0
MAG_ESCALA = 20200.0

_RE_RAW = re.compile(
    r"#\s*RAW\s+f=([\d.eE+-]+)\s+real=(-?\d+)\s+imag=(-?\d+)"
)


# ---------------------------------------------------------------------------
# Bandas de varredura (um clock por banda)
# ---------------------------------------------------------------------------
#: Quantidade de bandas prevista pelo firmware.
NUM_BANDAS = 3

#: Piso da banda: ``fmin = MCLK / 16384``. A DFT do AD5933 integra 1024
#: amostras tomadas a ``MCLK/16``; abaixo desse piso a janela não comporta
#: um ciclo inteiro da excitação e o par real/imaginário perde sentido.
FATOR_FMIN = 16384.0

#: Teto da banda: ``fmax = MCLK / 167,76`` — os 100 kHz especificados pelo
#: fabricante com o clock máximo de 16,776 MHz. Um clock cobre, portanto,
#: só cerca de 97:1, e é por isso que 100 Hz a 100 kHz exige mais de uma
#: banda.
FATOR_FMAX = 167.76

_RE_BANDA = re.compile(
    r"#\s*BAND\s*(?P<tipo>ok|ativa)?\s*:?\s*"
    r"i=(?P<i>\d+)\s+mclk=(?P<mclk>[-+\d.eE]+)\s+ext=(?P<ext>[01])"
    r"(?:\s+ativa=(?P<at>[01]))?"
    r"(?:\s+fmin=(?P<fmin>[-+\d.eE]+))?"
    r"(?:\s+fmax=(?P<fmax>[-+\d.eE]+))?"
)

_RE_CAL = re.compile(
    r"#\s*CAL\s+(?:banda=(?P<banda>\d+)\s+)?pga=(?P<pga>\d+)\s+(?P<resto>.*)"
)

_RE_PAR = re.compile(r"(\w+)=(\S+)")


def formata_hz(valor: float) -> str:
    """Escreve uma frequência no múltiplo mais legível.

    Args:
        valor: Frequência em hertz.

    Returns:
        Texto com vírgula decimal, como ``"16,78 MHz"`` ou
        ``"9,766 kHz"``; ``"—"`` quando o valor não é utilizável.
    """
    if not np.isfinite(valor) or valor <= 0.0:
        return "—"
    if valor >= 1e6:
        texto = f"{valor / 1e6:.4g} MHz"
    elif valor >= 1e3:
        texto = f"{valor / 1e3:.4g} kHz"
    else:
        texto = f"{valor:.4g} Hz"
    return texto.replace(".", ",")


@dataclass
class Banda:
    """Uma banda de varredura: o clock que a alimenta e sua faixa útil.

    A frequência de excitação do AD5933 é proporcional ao ``MCLK``, então
    trocar de banda desloca o eixo de frequência inteiro — por isso cada
    banda tem seu próprio jogo de coeficientes de calibração.

    Attributes:
        indice: Posição da banda no firmware (0 a ``NUM_BANDAS`` − 1).
        mclk_hz: Clock efetivo da banda, em hertz.
        externo: ``True`` quando o clock vem do gerador do ESP32.
        ativa: ``True`` quando é a banda selecionada na placa.
        fmin: Piso da faixa útil, em hertz.
        fmax: Teto da faixa útil, em hertz.
    """

    indice: int
    mclk_hz: float
    externo: bool
    ativa: bool = False
    fmin: float = 0.0
    fmax: float = 0.0

    def __post_init__(self) -> None:
        """Deduz a faixa útil quando a placa não a informou."""
        if self.fmin <= 0.0:
            self.fmin = self.mclk_hz / FATOR_FMIN
        if self.fmax <= 0.0:
            self.fmax = self.mclk_hz / FATOR_FMAX

    @property
    def rotulo(self) -> str:
        """Descrição de uma linha para combos: clock, origem e faixa."""
        origem = "externo" if self.externo else "interno"
        return (
            f"Banda {self.indice} — MCLK {formata_hz(self.mclk_hz)} "
            f"({origem}) — {formata_hz(self.fmin)} a "
            f"{formata_hz(self.fmax)}"
        )


def bandas_padrao() -> List[Banda]:
    """Bandas de fábrica previstas no firmware.

    Servem apenas de valor provisório enquanto a placa não responde ao
    comando ``B``: o clock realmente sintetizado nas bandas externas é o
    que o divisor do gerador do ESP32 consegue produzir, e não o nominal
    pedido.

    Returns:
        Lista nova de :class:`Banda`, segura para ser modificada.
    """
    return [
        Banda(0, 16776000.0, False, ativa=True),
        Banda(1, 1638400.0, True),
        Banda(2, 163840.0, True),
    ]


def analisa_linha_banda(linha: str) -> Optional[Tuple[str, Banda]]:
    """Interpreta uma linha ``# BAND`` vinda do firmware.

    Reconhece os três formatos: a listagem
    ``# BAND i=… mclk=… ext=… ativa=… fmin=… fmax=…``, a confirmação de
    configuração ``# BAND ok: i=… mclk=… ext=…`` e a troca de banda
    ``# BAND ativa: i=… mclk=… ext=…``.

    Args:
        linha: Linha crua recebida pela porta serial.

    Returns:
        Par ``(tipo, banda)`` com ``tipo`` em ``{"lista", "ok",
        "ativa"}``, ou ``None`` se a linha não for uma resposta de banda
        ou vier com números impossíveis.
    """
    m = _RE_BANDA.search(linha)
    if not m:
        return None
    try:
        indice = int(m.group("i"))
        mclk = float(m.group("mclk"))
        fmin = float(m.group("fmin") or 0.0)
        fmax = float(m.group("fmax") or 0.0)
    except (TypeError, ValueError):
        logger.warning("Linha de banda ilegível: %s", linha.strip())
        return None
    if not np.isfinite(mclk) or mclk <= 0.0:
        logger.warning("Banda com MCLK inválido: %s", linha.strip())
        return None
    tipo = m.group("tipo") or "lista"
    if m.group("at") is not None:
        ativa = m.group("at") == "1"
    else:
        # 'ok' só confirma a configuração e nada diz sobre estar ativa.
        ativa = tipo == "ativa"
    return (
        tipo,
        Banda(
            indice=indice,
            mclk_hz=mclk,
            externo=m.group("ext") == "1",
            ativa=ativa,
            fmin=max(fmin, 0.0),
            fmax=max(fmax, 0.0),
        ),
    )


def analisa_linha_cal(linha: str) -> Optional[Dict[str, object]]:
    """Interpreta uma linha ``# CAL`` do firmware.

    Aceita tanto o formato novo, com ``banda=``, quanto o antigo (uma
    linha por PGA, sem banda), que passa a valer para a banda ativa. A
    confirmação ``# CAL gravada: …`` não casa de propósito: ela não
    carrega coeficientes.

    Args:
        linha: Linha crua recebida pela porta serial.

    Returns:
        Dicionário com ``banda`` (``None`` no formato antigo), ``pga``,
        ``origem`` e os coeficientes numéricos encontrados; ``None`` se a
        linha não for uma resposta de calibração.
    """
    m = _RE_CAL.search(linha)
    if not m:
        return None
    try:
        dados: Dict[str, object] = {
            "banda": int(m.group("banda")) if m.group("banda") else None,
            "pga": int(m.group("pga")),
            "origem": "",
        }
    except ValueError:
        logger.warning("Linha de calibração ilegível: %s", linha.strip())
        return None
    for chave, valor in _RE_PAR.findall(m.group("resto")):
        if chave == "origem":
            dados["origem"] = valor
            continue
        try:
            dados[chave] = float(valor)
        except ValueError:
            continue
    return dados


def valida_faixa(
    banda: Optional[Banda], f0: float, f1: float
) -> Optional[str]:
    """Confere se a faixa de frequência pedida cabe na banda escolhida.

    Args:
        banda: Banda selecionada, ou ``None`` se ainda desconhecida.
        f0: Frequência inicial pedida, em hertz.
        f1: Frequência final pedida, em hertz.

    Returns:
        Texto explicando o extrapolamento e de onde vêm os limites, ou
        ``None`` se a faixa couber (ou se não houver como julgar).
    """
    if banda is None or banda.fmin <= 0.0 or banda.fmax <= 0.0:
        return None
    problemas = []
    if f0 < banda.fmin:
        problemas.append(
            f"a frequência inicial ({formata_hz(f0)}) fica abaixo do piso "
            f"de {formata_hz(banda.fmin)}"
        )
    if f1 > banda.fmax:
        problemas.append(
            f"a frequência final ({formata_hz(f1)}) passa do teto de "
            f"{formata_hz(banda.fmax)}"
        )
    if not problemas:
        return None
    return (
        f"A faixa pedida extrapola a banda {banda.indice} "
        f"(MCLK {formata_hz(banda.mclk_hz)}): "
        + " e ".join(problemas)
        + ".\n\n"
        "Uma banda cobre cerca de 97:1, e os dois limites saem do clock:\n"
        "• piso = MCLK / 16384 — a DFT integra 1024 amostras tomadas a "
        "MCLK/16, então abaixo do piso a janela não comporta um ciclo "
        "inteiro da excitação;\n"
        "• teto = MCLK / 167,76 — é o limite especificado pelo fabricante "
        "(100 kHz com o clock máximo de 16,776 MHz).\n\n"
        "Escolha outra banda ou reduza a faixa: os pontos fora dos limites "
        "não seriam medida, e sim ruído."
    )


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------
@dataclass
class Aquisicao:
    """Varredura em modo bruto sobre um padrão de valor conhecido."""

    valor_ohm: float
    f: np.ndarray
    real: np.ndarray
    imag: np.ndarray

    @property
    def mag(self) -> np.ndarray:
        """Módulo do par real/imaginário, em contagens da DFT."""
        return np.hypot(self.real.astype(float), self.imag.astype(float))

    @property
    def fase(self) -> np.ndarray:
        """Fase bruta desenrolada, em radianos."""
        return np.unwrap(
            np.arctan2(self.imag.astype(float), self.real.astype(float))
        )

    def diagnostico(self) -> Optional[str]:
        """Devolve um aviso se o nível do sinal for impróprio."""
        pico = float(self.mag.max())
        if pico > MAG_SATURADA:
            return (
                f"A magnitude chegou a {pico:.0f} contagens, perto do "
                "ceifamento. O padrão é pequeno demais para o resistor de "
                "transimpedância instalado na placa — use um valor maior "
                "ou reduza o ganho do PGA."
            )
        if pico < MAG_FRACA:
            return (
                f"A magnitude ficou em apenas {pico:.0f} contagens. O "
                "padrão é grande demais para a faixa atual — use um valor "
                "menor ou aumente o ganho do PGA."
            )
        return None


@dataclass
class Resultado:
    """Coeficientes resolvidos e as métricas de qualidade do ajuste."""

    rout: float
    ka: float
    kb: float
    kc: float
    fa: float
    fb: float
    fmin: float
    fmax: float
    residuo_k: float            # % rms do ajuste de K(f)
    residuo_fase: float         # graus rms do ajuste da fase
    atraso_us: float            # atraso equivalente do sistema
    reconstrucoes: List[tuple]  # (alvo, média medida, erro % rms)
    rout_medido: bool           # False quando veio de calibração anterior

    def comando_w(self, pga: int, banda: Optional[int] = None) -> str:
        """Monta o comando serial que grava esta calibração na placa.

        Args:
            pga: Ganho do PGA (1 ou 5) a que os coeficientes pertencem.
            banda: Índice da banda. ``None`` omite ``banda=`` e deixa o
                firmware usar a banda ativa, como no formato antigo.

        Returns:
            Linha pronta para ``send_text``.
        """
        alvo = "" if banda is None else f"banda={banda} "
        return (
            f"W {alvo}pga={pga} ka={self.ka:.12g} kb={self.kb:.12g} "
            f"kc={self.kc:.12g} fa={self.fa:.12g} fb={self.fb:.12g} "
            f"rout={self.rout:.12g} fmin={self.fmin:.12g} "
            f"fmax={self.fmax:.12g}"
        )

    def trecho_cpp(self, pga: int, banda: Optional[int] = None) -> str:
        """Mesmos coeficientes no formato do firmware, para colar no fonte.

        Args:
            pga: Ganho do PGA (1 ou 5).
            banda: Índice da banda, usado no nome da constante — cada
                banda tem seu próprio jogo de coeficientes. ``None``
                mantém o nome antigo, sem banda.

        Returns:
            Trecho em C++ para colar em ``src/main.cpp`` (adapte o nome do
            símbolo ao que o firmware usar).
        """
        nome = "X5" if pga == 5 else "X1"
        if banda is None:
            simbolo = f"CAL_FABRICA_{nome}"
            cabecalho = f"// banda ativa, PGA {nome}"
        else:
            simbolo = f"CAL_FABRICA_B{banda}_{nome}"
            cabecalho = f"// banda {banda}, PGA {nome}"
        return (
            f"{cabecalho}\n"
            f"static const Calibracao {simbolo} = {{\n"
            f"  {self.ka: .12e}, {self.kb: .12e}, {self.kc: .12e},\n"
            f"  {self.fa: .12e}, {self.fb: .12e}, "
            f"{self.fmin:.1f}, {self.fmax:.1f}\n"
            f"}};\n"
            f"// ROUT é do chip: vale para todas as bandas e ganhos.\n"
            f"static const double ROUT_FABRICA = {self.rout:.6f};"
        )


# ---------------------------------------------------------------------------
# Matemática da calibração
# ---------------------------------------------------------------------------
def resolve_calibracao(
    a1: Aquisicao,
    a2: Optional[Aquisicao] = None,
    rout_conhecido: Optional[float] = None,
) -> Resultado:
    """Resolve ``ROUT``, ``K(f)`` e a fase do sistema.

    Com dois padrões medidos na mesma configuração, por frequência::

        ROUT = (mag2*Z2 - mag1*Z1) / (mag1 - mag2)
        K    = mag1 * (ROUT + Z1)

    O ``ROUT`` é uma propriedade do chip e não depende da frequência nem do
    ganho do PGA, então toma-se a **mediana** sobre todas as frequências —
    o que também descarta pontos ruidosos. Com um padrão só é possível
    resolver apenas ``K``, e por isso ``rout_conhecido`` passa a ser
    obrigatório (é o caso de calibrar uma subfaixa adicional depois que o
    ``ROUT`` já foi determinado).

    Args:
        a1: Aquisição do primeiro padrão.
        a2: Aquisição do segundo padrão, ou ``None``.
        rout_conhecido: ``ROUT`` de uma calibração anterior, em ohm.

    Returns:
        Resultado com os coeficientes e as métricas de qualidade.

    Raises:
        ValueError: Se os dados forem insuficientes ou degenerados.
    """
    if a2 is None and rout_conhecido is None:
        raise ValueError(
            "Com um único padrão é preciso informar o ROUT de uma "
            "calibração anterior — senão ganho e ROUT ficam indistinguíveis."
        )

    f = a1.f
    if f.size < 3:
        raise ValueError("Poucos pontos válidos para ajustar a calibração.")

    if a2 is not None:
        if a2.f.size != f.size or not np.allclose(a2.f, f):
            raise ValueError(
                "As duas varreduras têm frequências diferentes. Refaça-as "
                "com exatamente a mesma configuração."
            )
        if abs(a1.valor_ohm - a2.valor_ohm) < 1e-9:
            raise ValueError("Os dois padrões têm o mesmo valor.")
        m1, m2 = a1.mag, a2.mag
        denom = m1 - m2
        if np.any(np.abs(denom) < 1e-6):
            raise ValueError(
                "As magnitudes dos dois padrões ficaram iguais em alguma "
                "frequência — os valores estão próximos demais para separar "
                "o ROUT. Use padrões mais distantes entre si."
            )
        rout_por_f = (m2 * a2.valor_ohm - m1 * a1.valor_ohm) / denom
        rout = float(np.median(rout_por_f))
        rout_medido = True
        if not np.isfinite(rout) or rout < 0.0 or rout > 100000.0:
            raise ValueError(
                f"O ROUT resolvido ({rout:.1f} Ω) está fora de qualquer "
                "faixa plausível. Confira os valores digitados dos padrões "
                "e se eles estavam mesmo conectados."
            )
    else:
        rout = float(rout_conhecido)
        rout_medido = False

    # Ganho: K = mag * (ROUT + Z). Havendo dois padrões, cada um dá uma
    # estimativa independente de K; a média das duas reduz o ruído e evita
    # que o resultado dependa de qual padrão foi medido primeiro.
    estimativas = [a1.mag * (rout + a1.valor_ohm)]
    if a2 is not None:
        estimativas.append(a2.mag * (rout + a2.valor_ohm))
    k_por_f = np.mean(np.vstack(estimativas), axis=0)
    ka, kb, kc = np.polyfit(f, k_por_f, 2)
    k_ajustado = np.polyval([ka, kb, kc], f)
    residuo_k = float(
        100.0 * np.sqrt(np.mean(((k_por_f - k_ajustado) / k_por_f) ** 2))
    )

    # Fase do sistema: média das fases brutas (os padrões são resistivos,
    # então a fase medida é a do instrumento), ajustada por reta em f.
    fases = [a1.fase] if a2 is None else [a1.fase, a2.fase]
    fase_media = np.mean(np.vstack(fases), axis=0)
    fa, fb = np.polyfit(f, fase_media, 1)
    residuo_fase = float(
        np.degrees(
            np.sqrt(np.mean((fase_media - np.polyval([fa, fb], f)) ** 2))
        )
    )
    atraso_us = float(fa / (2.0 * np.pi) * 1e6)

    # Reconstrução dos próprios padrões: confere se o modelo fecha.
    reconstrucoes = []
    for aq in [a for a in (a1, a2) if a is not None]:
        z = k_ajustado / aq.mag - rout
        erro = 100.0 * (z - aq.valor_ohm) / aq.valor_ohm
        reconstrucoes.append(
            (
                aq.valor_ohm,
                float(np.mean(z)),
                float(np.sqrt(np.mean(erro ** 2))),
            )
        )

    return Resultado(
        rout=rout,
        ka=float(ka),
        kb=float(kb),
        kc=float(kc),
        fa=float(fa),
        fb=float(fb),
        fmin=float(f.min()),
        fmax=float(f.max()),
        residuo_k=residuo_k,
        residuo_fase=residuo_fase,
        atraso_us=atraso_us,
        reconstrucoes=reconstrucoes,
        rout_medido=rout_medido,
    )


# ---------------------------------------------------------------------------
# Janela do assistente
# ---------------------------------------------------------------------------
class CalibracaoDialog(QDialog):
    """Assistente passo a passo de calibração do AD5933.

    Conduz o usuário por: explicação, configuração da varredura, medição
    de um ou dois padrões conhecidos, conferência do resultado e gravação
    dos coeficientes na placa.

    Args:
        parent: Widget pai.
        acquisition: Instância de :class:`serial_io.SerialAcquisition` já
            conectada à placa.
    """

    _PASSOS = (
        "1 de 5 — O que é a calibração",
        "2 de 5 — Configuração da varredura",
        "3 de 5 — Primeiro padrão",
        "4 de 5 — Segundo padrão",
        "5 de 5 — Resultado",
    )

    def __init__(self, parent, acquisition) -> None:
        super().__init__(parent)
        self.setWindowTitle("Calibração do instrumento")
        self.resize(900, 660)
        self._aq = acquisition

        self._aquisicoes: List[Optional[Aquisicao]] = [None, None]
        self._resultado: Optional[Resultado] = None
        self._coletando = False
        self._buffer: List[tuple] = []
        self._alvo_indice = 0
        self._n_esperado = 0
        self._respostas: List[str] = []
        self._watchdog: Optional[QTimer] = None
        #: Bandas conhecidas, por índice. Começam nos valores provisórios
        #: do firmware e são substituídas pelo que a placa responde ao 'B'.
        self._bandas: Dict[int, Banda] = {
            b.indice: b for b in bandas_padrao()
        }
        #: Perfis de calibração lidos do 'G', por (banda, pga).
        self._perfis: Dict[Tuple[int, int], Dict[str, object]] = {}
        #: Banda cujas frequências já foram sugeridas (evita sobrescrever
        #: o que o usuário digitou a cada resposta da placa).
        self._banda_sugerida: Optional[int] = None
        #: True depois que o usuário escolhe uma banda à mão. Até lá o
        #: combo segue a banda ativa que a placa reportar.
        self._banda_travada = False

        self._monta_interface()
        self._aq.rawLineReceived.connect(self._on_linha)
        # Pergunta como as bandas estão configuradas e qual é a calibração
        # vigente: é dela que sai o ROUT quando o usuário calibra só uma
        # subfaixa adicional.
        self._aq.send_text("B")
        QTimer.singleShot(300, lambda: self._aq.send_text("G"))
        self._atualiza_navegacao()

    # -- construção da interface ---------------------------------------
    def _monta_interface(self) -> None:
        raiz = QVBoxLayout(self)

        self.titulo = QLabel(self)
        fonte = self.titulo.font()
        fonte.setPointSize(fonte.pointSize() + 3)
        fonte.setBold(True)
        self.titulo.setFont(fonte)
        raiz.addWidget(self.titulo)

        self.paginas = QStackedWidget(self)
        self.paginas.addWidget(self._pagina_intro())
        self.paginas.addWidget(self._pagina_config())
        self.paginas.addWidget(self._pagina_padrao(0))
        self.paginas.addWidget(self._pagina_padrao(1))
        self.paginas.addWidget(self._pagina_resultado())
        raiz.addWidget(self.paginas, 1)

        rodape = QHBoxLayout()
        self.botao_fabrica = QPushButton(
            "Restaurar calibração de fábrica", self
        )
        self.botao_fabrica.clicked.connect(self._restaura_fabrica)
        rodape.addWidget(self.botao_fabrica)
        rodape.addStretch(1)
        self.botao_voltar = QPushButton("Voltar", self)
        self.botao_voltar.clicked.connect(self._voltar)
        self.botao_proximo = QPushButton("Próximo", self)
        self.botao_proximo.clicked.connect(self._proximo)
        self.botao_fechar = QPushButton("Fechar", self)
        self.botao_fechar.clicked.connect(self.reject)
        rodape.addWidget(self.botao_voltar)
        rodape.addWidget(self.botao_proximo)
        rodape.addWidget(self.botao_fechar)
        raiz.addLayout(rodape)

    def _pagina_intro(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        texto = QTextBrowser(w)
        texto.setOpenExternalLinks(False)
        texto.setHtml(
            """
            <h3>Por que calibrar</h3>
            <p>O AD5933 <b>não mede ohms</b>. Ele devolve um par de números
            (real e imaginário) proporcional à <b>corrente</b> que atravessa
            a amostra. Sem calibração esses números não são impedância —
            são apenas contagens do conversor.</p>

            <h3>O que a calibração determina</h3>
            <ul>
              <li>o <b>ganho</b> do caminho de medição, <code>K(f)</code>,
                  que depende do resistor de transimpedância da placa;</li>
              <li>a <b>fase do sistema</b>, que <i>não</i> é constante: ela
                  varre dezenas de graus ao longo da banda por causa do
                  atraso do caminho analógico e da DFT;</li>
              <li>a <b>resistência de saída do próprio chip</b>
                  (<code>ROUT</code>), que fica em série com a amostra.</li>
            </ul>

            <h3>Por que são dois padrões, e não um</h3>
            <p>O que o instrumento mede é
            <code>mag = K(f) / (ROUT + |Z|)</code>, e não
            <code>1/|Z|</code>. Com um padrão só, o ganho e o
            <code>ROUT</code> ficam <b>indistinguíveis</b>: a resposta vira
            uma reta afim e o erro cresce muito nas impedâncias baixas.
            Numa amostra de 150&nbsp;Ω, um <code>ROUT</code> de ~230&nbsp;Ω
            é <i>maior que a própria amostra</i> — supor o valor de catálogo
            em vez de medir custa dezenas de porcento de erro.</p>
            <p>Por isso o assistente pede dois padrões. A partir da segunda
            subfaixa você pode usar apenas um, porque o <code>ROUT</code> é
            do chip e já terá sido determinado.</p>

            <h3>O que você precisa ter em mãos</h3>
            <ul>
              <li>Dois resistores perto dos <b>extremos</b> da faixa que vai
                  medir, de filme metálico 1&nbsp;% e baixo coeficiente de
                  temperatura;</li>
              <li>o <b>valor medido no multímetro</b> de cada um — o valor
                  nominal impresso no corpo não serve;</li>
              <li>a placa conectada, com a amostra fora do circuito.</li>
            </ul>

            <h3>Por que existe uma calibração por banda</h3>
            <p>A frequência de excitação do AD5933 é <b>proporcional ao
            clock</b> (<code>MCLK</code>), e um clock só cobre cerca de
            <b>97:1</b>: o piso é <code>MCLK/16384</code> e o teto é
            <code>MCLK/167,76</code>. Para chegar de 100&nbsp;Hz a
            100&nbsp;kHz a varredura é dividida em <b>bandas</b>, cada uma
            com seu clock — nas bandas externas quem gera o clock é o
            ESP32. Como o caminho analógico responde de outro jeito em
            cada banda, <b>cada banda tem seu próprio jogo de
            coeficientes</b>: escolha no passo seguinte qual delas você
            está calibrando.</p>

            <p><b>Importante:</b> a calibração vale para uma combinação
            específica de resistor de transimpedância, faixa de excitação,
            ganho do PGA e banda (clock). Trocar qualquer um deles exige
            recalibrar. O <code>ROUT</code>, ao contrário, é do chip: vale
            para todas as bandas e ganhos.</p>
            """
        )
        lay.addWidget(texto)
        return w

    def _pagina_config(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        aviso = QLabel(
            "A calibração precisa ser feita com <b>exatamente a mesma "
            "configuração</b> que você vai usar para medir as amostras.",
            w,
        )
        aviso.setWordWrap(True)
        lay.addWidget(aviso)

        grupo_banda = QGroupBox("Banda de varredura", w)
        coluna_banda = QVBoxLayout(grupo_banda)
        self.banda_combo = QComboBox(grupo_banda)
        self.banda_combo.setToolTip(
            "Cada banda é um clock (MCLK) diferente para o AD5933. Um\n"
            "clock só cobre cerca de 97:1 — piso = MCLK/16384, teto =\n"
            "MCLK/167,76 —, então 100 Hz a 100 kHz é coberto por bandas,\n"
            "e cada banda tem sua própria calibração."
        )
        self.banda_combo.currentIndexChanged.connect(self._on_banda_alterada)
        # 'activated' só é emitido quando quem troca é o usuário;
        # 'currentIndexChanged' também dispara ao repovoar o combo.
        self.banda_combo.activated.connect(self._on_banda_escolhida)
        coluna_banda.addWidget(self.banda_combo)
        self.banda_info = QLabel("", grupo_banda)
        self.banda_info.setWordWrap(True)
        self.banda_info.setStyleSheet("color: #9a9a9a;")
        coluna_banda.addWidget(self.banda_info)
        lay.addWidget(grupo_banda)


        grupo = QGroupBox("Configuração da varredura", w)
        grade = QGridLayout(grupo)

        self.pga_combo = QComboBox(grupo)
        self.pga_combo.addItem("x1 — impedâncias baixas", 1)
        self.pga_combo.addItem("x5 — impedâncias altas", 5)
        self.pga_combo.setToolTip(
            "Ganho do lado da recepção. Cada valor tem sua própria\n"
            "calibração: use x1 na década baixa e x5 na alta."
        )

        self.vpp_combo = QComboBox(grupo)
        for rotulo, mv in (
            ("2 Vpp (offset 1,48 V)", 2000),
            ("1 Vpp (offset 0,76 V)", 1000),
            ("400 mVpp (offset 0,31 V)", 400),
            ("200 mVpp (offset 0,17 V)", 200),
        ):
            self.vpp_combo.addItem(rotulo, mv)
        self.vpp_combo.setToolTip(
            "A faixa de 2 Vpp tem a menor impedância de saída e o menor\n"
            "degrau de tensão contínua sobre a amostra. As outras só\n"
            "devem ser usadas com bloqueio de corrente contínua."
        )

        self.f0_spin = QDoubleSpinBox(grupo)
        self.f0_spin.setRange(1.0, 200000.0)
        self.f0_spin.setDecimals(1)
        self.f0_spin.setValue(2000.0)
        self.f0_spin.setSuffix(" Hz")
        self.f0_spin.setToolTip(
            "O piso de cada banda é MCLK/16384: abaixo dele a janela da\n"
            "DFT não comporta um ciclo inteiro e o dado perde sentido."
        )

        self.f1_spin = QDoubleSpinBox(grupo)
        self.f1_spin.setRange(1.0, 200000.0)
        self.f1_spin.setDecimals(1)
        self.f1_spin.setValue(100000.0)
        self.f1_spin.setSuffix(" Hz")

        self.n_spin = QSpinBox(grupo)
        self.n_spin.setRange(5, 512)
        self.n_spin.setValue(99)
        self.n_spin.setToolTip(
            "Mais pontos deixam o ajuste mais firme. 99 é um bom começo."
        )

        self.settle_spin = QSpinBox(grupo)
        self.settle_spin.setRange(1, 511)
        self.settle_spin.setValue(100)
        self.settle_spin.setToolTip(
            "Ciclos da excitação antes de cada medida, para a amostra\n"
            "chegar ao regime permanente. O tempo é N/f."
        )

        campos = (
            ("Ganho PGA:", self.pga_combo),
            ("Excitação:", self.vpp_combo),
            ("Frequência inicial:", self.f0_spin),
            ("Frequência final:", self.f1_spin),
            ("Nº de pontos:", self.n_spin),
            ("Acomodação:", self.settle_spin),
        )
        for i, (rotulo, widget) in enumerate(campos):
            grade.addWidget(QLabel(rotulo, grupo), i // 2, (i % 2) * 2)
            grade.addWidget(widget, i // 2, (i % 2) * 2 + 1)
        lay.addWidget(grupo)
        lay.addStretch(1)
        # Só aqui, com os campos de frequência já criados: preencher o
        # combo dispara o ajuste das sugestões de faixa.
        self._atualiza_combo_bandas()
        return w

    def _pagina_padrao(self, indice: int) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)

        if indice == 0:
            explica = (
                "Ligue o <b>primeiro padrão</b> entre os dois terminais da "
                "amostra e informe abaixo o valor <b>medido no "
                "multímetro</b>. Escolha um resistor perto do <b>extremo "
                "inferior</b> da faixa que pretende medir."
            )
        else:
            explica = (
                "Troque para o <b>segundo padrão</b>, perto do <b>extremo "
                "superior</b> da faixa, e informe o valor medido.<br><br>"
                "Se você já calibrou outra subfaixa nesta placa, pode "
                "<b>pular esta etapa</b>: o ROUT já é conhecido e um padrão "
                "basta para resolver só o ganho."
            )
        rotulo = QLabel(explica, w)
        rotulo.setWordWrap(True)
        lay.addWidget(rotulo)

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Valor do padrão:", w))
        spin = QDoubleSpinBox(w)
        spin.setRange(0.1, 10000000.0)
        spin.setDecimals(2)
        spin.setValue(147.6 if indice == 0 else 21920.0)
        spin.setSuffix(" Ω")
        linha.addWidget(spin)
        botao = QPushButton("Medir padrão", w)
        botao.clicked.connect(lambda: self._inicia_coleta(indice))
        linha.addWidget(botao)
        if indice == 1:
            pular = QPushButton("Pular (usar ROUT já conhecido)", w)
            pular.clicked.connect(self._pular_segundo)
            linha.addWidget(pular)
        linha.addStretch(1)
        lay.addLayout(linha)

        barra = QProgressBar(w)
        barra.setRange(0, 100)
        barra.setValue(0)
        lay.addWidget(barra)

        estado = QLabel("", w)
        estado.setWordWrap(True)
        lay.addWidget(estado)
        lay.addStretch(1)

        if indice == 0:
            self.padrao1_spin = spin
            self.padrao1_barra = barra
            self.padrao1_estado = estado
        else:
            self.padrao2_spin = spin
            self.padrao2_barra = barra
            self.padrao2_estado = estado
        return w

    def _pagina_resultado(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        self.resultado_texto = QTextBrowser(w)
        self.resultado_texto.setMaximumHeight(240)
        lay.addWidget(self.resultado_texto)
        self.resultado_canvas = PlotCanvas(w)
        lay.addWidget(self.resultado_canvas, 1)

        linha = QHBoxLayout()
        self.botao_gravar = QPushButton("Gravar na placa", w)
        self.botao_gravar.clicked.connect(self._grava_na_placa)
        self.botao_copiar = QPushButton("Copiar coeficientes", w)
        self.botao_copiar.clicked.connect(self._copia_coeficientes)
        linha.addWidget(self.botao_gravar)
        linha.addWidget(self.botao_copiar)
        linha.addStretch(1)
        lay.addLayout(linha)
        return w

    # -- bandas ---------------------------------------------------------
    def _atualiza_combo_bandas(self) -> None:
        """Repovoa o combo de bandas com o que se sabe da placa.

        Enquanto o usuário não escolher uma banda à mão, o combo **segue
        a banda ativa na placa** — assim a janela não fica apontando para
        a banda 0 enquanto o instrumento está em outra. Depois da
        primeira escolha manual (``_banda_travada``), a seleção do
        usuário é preservada a cada nova resposta ao ``B``.
        """
        if not hasattr(self, "banda_combo"):
            return
        anterior = self.banda_combo.currentData()
        bloqueado = self.banda_combo.blockSignals(True)
        self.banda_combo.clear()
        for banda in sorted(self._bandas.values(), key=lambda b: b.indice):
            self.banda_combo.addItem(banda.rotulo, banda.indice)
        self.banda_combo.blockSignals(bloqueado)
        if self.banda_combo.count() == 0:
            self._atualiza_info_banda()
            return
        indice = -1
        if self._banda_travada:
            indice = self.banda_combo.findData(anterior)
        if indice < 0:
            ativa = next(
                (b.indice for b in self._bandas.values() if b.ativa), None
            )
            indice = self.banda_combo.findData(ativa)
        if indice < 0:
            indice = max(0, self.banda_combo.findData(anterior))
        self.banda_combo.setCurrentIndex(indice)
        # setCurrentIndex não emite sinal quando o índice não muda, e o
        # rótulo pode ter mudado mesmo assim: atualiza à mão.
        self._on_banda_alterada()

    def _banda_selecionada(self) -> Optional[Banda]:
        """Banda escolhida no combo, ou ``None`` se nenhuma é conhecida."""
        if not hasattr(self, "banda_combo"):
            return None
        return self._bandas.get(self.banda_combo.currentData())

    def _on_banda_escolhida(self, _indice: int = -1) -> None:
        """Marca a banda como escolha explícita do usuário.

        A partir daqui as respostas ao comando ``B`` não movem mais o
        combo: quem manda é o que o usuário selecionou.

        Args:
            _indice: Índice do combo (ignorado; vem do sinal do Qt).
        """
        self._banda_travada = True

    def _on_banda_alterada(self, _indice: int = -1) -> None:
        """Reage à troca de banda ajustando a faixa sugerida.

        Args:
            _indice: Índice do combo (ignorado; vem do sinal do Qt).
        """
        banda = self._banda_selecionada()
        self._atualiza_info_banda()
        if banda is None or banda.indice == self._banda_sugerida:
            return
        self._banda_sugerida = banda.indice
        self._sugere_frequencias(banda)

    def _sugere_frequencias(self, banda: Banda) -> None:
        """Ajusta os campos de frequência aos limites da banda.

        A sugestão começa no **dobro** do piso: exatamente no piso a DFT
        enxerga um único ciclo da excitação e o ponto fica marginal. O
        topo é o próprio teto, arredondado para baixo para a casa decimal
        do campo não estourá-lo.

        Args:
            banda: Banda recém-escolhida.
        """
        if not hasattr(self, "f0_spin") or banda.fmin <= 0.0:
            return
        f0 = round(min(2.0 * banda.fmin, banda.fmax), 1)
        f1 = float(np.floor(banda.fmax * 10.0) / 10.0)
        if not np.isfinite(f0) or not np.isfinite(f1) or f1 <= f0:
            logger.warning(
                "Banda %d sem faixa utilizável (%.4g a %.4g Hz).",
                banda.indice,
                banda.fmin,
                banda.fmax,
            )
            self.banda_info.setText(
                f"<b>Banda {banda.indice} sem faixa utilizável</b> "
                f"({formata_hz(banda.fmin)} a {formata_hz(banda.fmax)}). "
                "Confira o MCLK configurado para ela."
            )
            return
        self.f0_spin.setValue(
            min(max(f0, self.f0_spin.minimum()), self.f0_spin.maximum())
        )
        self.f1_spin.setValue(
            min(max(f1, self.f1_spin.minimum()), self.f1_spin.maximum())
        )

    def _tem_calibracao(self, banda: int, pga: int) -> bool:
        """Diz se a placa já reportou coeficientes para ``(banda, pga)``.

        Um perfil de banda nunca calibrada volta do firmware com a faixa
        zerada e os coeficientes de ganho nulos; exigimos as duas coisas
        para não confundir um perfil vazio com um perfil real.

        Args:
            banda: Índice da banda.
            pga: Ganho do PGA (1 ou 5).

        Returns:
            ``True`` se houver coeficientes utilizáveis.
        """
        perfil = self._perfis.get((banda, pga))
        if perfil is None:
            return False
        fmax = perfil.get("fmax")
        if not isinstance(fmax, float) or fmax <= 0.0:
            return False
        return any(
            isinstance(perfil.get(chave), float) and perfil[chave] != 0.0
            for chave in ("ka", "kb", "kc")
        )

    def _atualiza_info_banda(self) -> None:
        """Descreve a banda escolhida e o estado da calibração dela."""
        if not hasattr(self, "banda_info"):
            return
        banda = self._banda_selecionada()
        if banda is None:
            self.banda_info.setText(
                "A placa ainda não informou as bandas (comando <b>B</b>). "
                "Confira a conexão e se o firmware é recente o bastante."
            )
            return
        origem = (
            "clock gerado pelo ESP32"
            if banda.externo
            else "oscilador interno do chip"
        )
        texto = (
            f"MCLK de {formata_hz(banda.mclk_hz)} ({origem}). Faixa útil de "
            f"<b>{formata_hz(banda.fmin)}</b> (piso = MCLK/16384) a "
            f"<b>{formata_hz(banda.fmax)}</b> (teto = MCLK/167,76). "
            "A banda é aplicada à placa ao medir e ao gravar."
        )
        pendentes = [
            f"x{pga}"
            for pga in (1, 5)
            if not self._tem_calibracao(banda.indice, pga)
        ]
        if pendentes:
            texto += (
                "<br><b>Esta banda ainda não está calibrada</b> para o PGA "
                + " e ".join(pendentes)
                + " — enquanto isso o firmware recusa a varredura nela, "
                "para não emitir ohms sem calibração."
            )
        self.banda_info.setText(texto)

    def _registra_banda(self, texto: str) -> None:
        """Atualiza a tabela de bandas com uma resposta ``# BAND``.

        Args:
            texto: Linha já sem espaços nas pontas.
        """
        analisada = analisa_linha_banda(texto)
        if analisada is None:
            return
        tipo, banda = analisada
        if banda.ativa:
            for outra in self._bandas.values():
                outra.ativa = False
        elif tipo != "lista" and banda.indice in self._bandas:
            # 'ok' não fala de banda ativa: preserva o que já se sabia.
            banda.ativa = self._bandas[banda.indice].ativa
        self._bandas[banda.indice] = banda
        self._atualiza_combo_bandas()

    def _registra_cal(self, texto: str) -> None:
        """Guarda um perfil de calibração informado pelo comando ``G``.

        Args:
            texto: Linha já sem espaços nas pontas.
        """
        dados = analisa_linha_cal(texto)
        if dados is None:
            return
        banda = dados.get("banda")
        if banda is None:
            # Formato antigo, sem banda=: vale para a banda ativa.
            banda = next(
                (b.indice for b in self._bandas.values() if b.ativa), 0
            )
        self._perfis[(int(banda), int(dados["pga"]))] = dados
        self._atualiza_info_banda()


    # -- navegação ------------------------------------------------------
    def _atualiza_navegacao(self) -> None:
        i = self.paginas.currentIndex()
        self.titulo.setText(self._PASSOS[i])
        self.botao_voltar.setEnabled(i > 0 and not self._coletando)
        ultimo = i == self.paginas.count() - 1
        self.botao_proximo.setVisible(not ultimo)
        pode = True
        if i == 2:
            pode = self._aquisicoes[0] is not None
        elif i == 3:
            pode = self._aquisicoes[1] is not None
        self.botao_proximo.setEnabled(pode and not self._coletando)

    def _voltar(self) -> None:
        self.paginas.setCurrentIndex(max(0, self.paginas.currentIndex() - 1))
        self._atualiza_navegacao()

    def _proximo(self) -> None:
        i = self.paginas.currentIndex()
        if i == 3:
            self._calcula()
        self.paginas.setCurrentIndex(min(self.paginas.count() - 1, i + 1))
        self._atualiza_navegacao()

    def _pular_segundo(self) -> None:
        """Segue com um padrão só, reaproveitando o ROUT já gravado."""
        if self._aquisicoes[0] is None:
            QMessageBox.warning(
                self,
                "Falta o primeiro padrão",
                "Meça o primeiro padrão antes de seguir.",
            )
            return
        if self._rout_da_placa() is None:
            QMessageBox.warning(
                self,
                "ROUT desconhecido",
                "Não consegui ler o ROUT da placa, então não dá para pular "
                "o segundo padrão: com um só, o ganho e o ROUT ficam "
                "indistinguíveis. Meça o segundo padrão.",
            )
            return
        self._aquisicoes[1] = None
        self._calcula()
        self.paginas.setCurrentIndex(self.paginas.count() - 1)
        self._atualiza_navegacao()

    # -- aquisição ------------------------------------------------------
    def _inicia_coleta(self, indice: int) -> None:
        if self._coletando:
            return
        f0 = float(self.f0_spin.value())
        f1 = float(self.f1_spin.value())
        if f1 <= f0:
            QMessageBox.warning(
                self,
                "Faixa inválida",
                "A frequência final deve ser maior que a inicial.",
            )
            return
        banda = self._banda_selecionada()
        aviso_faixa = valida_faixa(banda, f0, f1)
        if aviso_faixa is not None:
            resposta = QMessageBox.question(
                self,
                "Faixa fora da banda",
                aviso_faixa + "\n\nMedir assim mesmo?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        n = int(self.n_spin.value())
        df = (f1 - f0) / (n - 1)
        pga = int(self.pga_combo.currentData())
        vpp = int(self.vpp_combo.currentData())
        st = int(self.settle_spin.value())

        self._alvo_indice = indice
        self._buffer = []
        self._coletando = True
        self._n_esperado = n
        barra, estado = self._widgets_padrao(indice)
        barra.setRange(0, n)
        barra.setValue(0)
        estado.setText("Medindo…")
        self._atualiza_navegacao()

        # A banda tem de ser aplicada ANTES da configuração: é o MCLK que
        # define a palavra de frequência calculada para f0 e df. As duas
        # linhas vão juntas de propósito — o protocolo é orientado a linha
        # e o firmware drena o buffer da serial em ordem; um temporizador
        # entre elas só criaria uma corrida se o usuário clicasse duas
        # vezes em "Medir padrão".
        if banda is not None:
            self._aq.send_text(f"B sel={banda.indice}")
        self._aq.send_text(
            f"C f0={f0:.3f} df={df:.6f} n={n} vpp={vpp} pga={pga} "
            f"st={st} dly=0 raw=1"
        )
        QTimer.singleShot(400, lambda: self._aq.send_text("S"))

        # Guarda de segurança: o tempo por ponto é acomodação/f, então uma
        # varredura de baixa frequência é legitimamente lenta. Damos o triplo
        # do tempo teórico mais uma folga fixa.
        teorico_ms = n * (1000.0 * st / max(f0, 1.0) + 1.0)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._coleta_expirou)
        self._watchdog.start(int(3.0 * teorico_ms) + 8000)

    def _widgets_padrao(self, indice: int):
        if indice == 0:
            return self.padrao1_barra, self.padrao1_estado
        return self.padrao2_barra, self.padrao2_estado

    def _on_linha(self, linha: str) -> None:
        """Recebe cada linha crua da serial enquanto a janela está aberta."""
        texto = linha.strip()
        if texto.startswith("# CAL") or texto.startswith("# ERRO"):
            self._respostas.append(texto)
            self._registra_cal(texto)
        elif texto.startswith("# BAND"):
            self._registra_banda(texto)
        if not self._coletando:
            return
        m = _RE_RAW.match(texto)
        if not m:
            return
        self._buffer.append(
            (float(m.group(1)), int(m.group(2)), int(m.group(3)))
        )
        barra, _ = self._widgets_padrao(self._alvo_indice)
        barra.setValue(len(self._buffer))
        if len(self._buffer) >= self._n_esperado:
            self._finaliza_coleta()

    def _coleta_expirou(self) -> None:
        if not self._coletando:
            return
        if len(self._buffer) >= 5:
            self._finaliza_coleta()
            return
        self._coletando = False
        _, estado = self._widgets_padrao(self._alvo_indice)
        estado.setText(
            "<b>A placa não respondeu a tempo.</b> Confira se ela está "
            "conectada e se o firmware é recente o bastante para aceitar "
            "o modo bruto (chave <code>raw=1</code>)."
        )
        self._atualiza_navegacao()

    def _finaliza_coleta(self) -> None:
        if self._watchdog is not None:
            self._watchdog.stop()
        self._coletando = False
        dados = np.array(self._buffer, dtype=float)
        indice = self._alvo_indice
        spin = self.padrao1_spin if indice == 0 else self.padrao2_spin
        aq = Aquisicao(
            valor_ohm=float(spin.value()),
            f=dados[:, 0],
            real=dados[:, 1],
            imag=dados[:, 2],
        )
        self._aquisicoes[indice] = aq

        _, estado = self._widgets_padrao(indice)
        m = aq.mag
        aviso = aq.diagnostico()
        msg = (
            f"<b>{len(aq.f)} pontos medidos.</b> Magnitude de "
            f"{m.min():.0f} a {m.max():.0f} contagens "
            f"({100.0 * m.max() / MAG_ESCALA:.0f} % da escala do conversor)."
        )
        if aviso:
            msg += f"<br><br><b>Atenção:</b> {aviso}"
        estado.setText(msg)
        self._atualiza_navegacao()

    # -- cálculo e gravação ---------------------------------------------
    def _rout_da_placa(self) -> Optional[float]:
        """Lê o ROUT da calibração já gravada, se houver.

        O ``ROUT`` é do chip: não depende da banda nem do ganho, então
        qualquer perfil informado pelo comando ``G`` serve. A varredura
        pelas linhas cruas fica de reserva, para firmwares antigos.

        Returns:
            Resistência de saída em ohm, ou ``None`` se a placa não a
            informou.
        """
        for perfil in reversed(list(self._perfis.values())):
            valor = perfil.get("rout")
            if (
                isinstance(valor, float)
                and np.isfinite(valor)
                and valor > 0.0
            ):
                return valor
        for linha in reversed(self._respostas):
            m = re.search(r"rout=([\d.eE+-]+)", linha)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    continue
        return None

    def _calcula(self) -> None:
        a1, a2 = self._aquisicoes
        if a1 is None:
            return
        try:
            self._resultado = resolve_calibracao(
                a1, a2, rout_conhecido=self._rout_da_placa()
            )
        except ValueError as exc:
            self._resultado = None
            self.resultado_texto.setHtml(
                "<p><b>Não foi possível calcular a calibração.</b></p>"
                f"<p>{exc}</p>"
            )
            self.botao_gravar.setEnabled(False)
            self.botao_copiar.setEnabled(False)
            self.resultado_canvas.clear()
            self.resultado_canvas.draw()
            return

        r = self._resultado
        self.botao_gravar.setEnabled(True)
        self.botao_copiar.setEnabled(True)

        linhas = "".join(
            f"<li>padrão de {alvo:.4g} Ω → medido {media:.4g} Ω "
            f"(erro {erro:.2f} % rms)</li>"
            for alvo, media, erro in r.reconstrucoes
        )
        origem = (
            "medido agora com os dois padrões"
            if r.rout_medido
            else "reaproveitado de uma calibração anterior"
        )
        self.resultado_texto.setHtml(
            f"""
            <h3>Resultado</h3>
            <ul>
              <li><b>ROUT = {r.rout:.1f} Ω</b> ({origem})</li>
              <li>ajuste do ganho: resíduo de
                  <b>{r.residuo_k:.2f} %</b> rms</li>
              <li>ajuste da fase: resíduo de
                  <b>{r.residuo_fase:.2f}°</b> rms, atraso equivalente de
                  {r.atraso_us:.2f} µs</li>
              <li>banda calibrada: {r.fmin:.0f} a {r.fmax:.0f} Hz</li>
            </ul>
            <p>Reconstrução dos padrões:</p>
            <ul>{linhas}</ul>
            <p><i>Reproduzir os próprios padrões é parcialmente circular —
            eles foram usados no ajuste. Para uma verificação independente,
            meça depois um <b>terceiro</b> resistor que não participou
            daqui.</i></p>
            """
        )
        self._desenha(r)

    def _desenha(self, r: Resultado) -> None:
        self.resultado_canvas.clear()
        fig = self.resultado_canvas.figure
        ax = fig.add_subplot(111)
        for aq in [a for a in self._aquisicoes if a is not None]:
            z = np.polyval([r.ka, r.kb, r.kc], aq.f) / aq.mag - r.rout
            erro = 100.0 * (z - aq.valor_ohm) / aq.valor_ohm
            ax.plot(
                aq.f / 1000.0,
                erro,
                "o-",
                ms=3,
                lw=1,
                label=f"{aq.valor_ohm:.4g} Ω",
            )
        ax.axhline(0.0, color="0.5", ls="--", lw=1)
        ax.set_xlabel("frequência (kHz)")
        ax.set_ylabel("erro de |Z| (%)")
        ax.set_title("Erro da calibração sobre os padrões")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        self.resultado_canvas.draw()

    def _grava_na_placa(self) -> None:
        """Grava os coeficientes no perfil (banda, PGA) escolhido."""
        if self._resultado is None:
            return
        pga = int(self.pga_combo.currentData())
        banda = self._banda_selecionada()
        indice = None if banda is None else banda.indice
        self._respostas = []
        if indice is not None:
            # A placa fica na banda calibrada logo após gravar, que é o
            # estado em que o usuário vai conferir com o terceiro padrão.
            self._aq.send_text(f"B sel={indice}")
        self._aq.send_text(self._resultado.comando_w(pga, indice))
        QTimer.singleShot(500, lambda: self._aq.send_text("G"))
        QTimer.singleShot(1200, self._confere_gravacao)

    def _confere_gravacao(self) -> None:
        gravou = any("CAL gravada" in linha for linha in self._respostas)
        erro = next(
            (linha for linha in self._respostas if linha.startswith("# ERRO")),
            None,
        )
        if gravou and not erro:
            QMessageBox.information(
                self,
                "Calibração gravada",
                "Os coeficientes foram gravados na memória não volátil da "
                "placa e continuam valendo após desligar.\n\n"
                "Recomendo conferir agora com um terceiro resistor, que não "
                "participou da calibração.",
            )
        else:
            QMessageBox.warning(
                self,
                "Não foi possível gravar",
                "A placa não confirmou a gravação."
                + (f"\n\nResposta: {erro}" if erro else ""),
            )

    def _copia_coeficientes(self) -> None:
        if self._resultado is None:
            return
        pga = int(self.pga_combo.currentData())
        banda = self._banda_selecionada()
        QGuiApplication.clipboard().setText(
            self._resultado.trecho_cpp(
                pga, None if banda is None else banda.indice
            )
        )
        QMessageBox.information(
            self,
            "Coeficientes copiados",
            "O trecho em C++ está na área de transferência; cole-o em "
            "src/main.cpp se quiser fixá-lo como valor de fábrica.",
        )

    def _restaura_fabrica(self) -> None:
        resposta = QMessageBox.question(
            self,
            "Restaurar calibração de fábrica",
            "Isso apaga a calibração gravada na placa — de <b>todas as "
            "bandas e ganhos</b> — e volta aos coeficientes compilados no "
            "firmware. Só a banda 0 vem calibrada de fábrica; as bandas "
            "externas ficarão sem calibração até você refazê-la, e o "
            "firmware recusará a varredura nelas. Continuar?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._aq.send_text("X")
        # O que estava em memória virou mentira: relê tudo do zero, senão
        # o aviso "esta banda ainda não está calibrada" fica desatualizado.
        self._perfis.clear()
        QTimer.singleShot(400, lambda: self._aq.send_text("G"))

    # -- ciclo de vida ---------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 (API do Qt)
        if self._watchdog is not None:
            self._watchdog.stop()
        try:
            self._aq.rawLineReceived.disconnect(self._on_linha)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)
