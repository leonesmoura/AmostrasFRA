"""Aquisição de dados por porta serial (AMOSTRAS FRA 2.0).

Permite receber pontos de medição de um sistema embarcado (Arduino,
ESP32, STM32, etc.) por uma porta serial (USB/UART).  Usa a
``QtSerialPort`` embutida no PySide6 — não requer dependências extras.

O software aceita **dois formatos** de linha (um ponto por linha,
terminada por ``\\n``; vírgula decimal é aceita):

* **Posicional** — só os valores, na ordem definida na interface::

      1000,1.0,0.01,-30
      100,1.0,0.005,-45

* **Rotulado** (auto-descritivo, ordem livre) — cada valor com um
  rótulo ``chave=valor``::

      f=10000 V=10,2 I=0,00012 pha=-80,2

  Rótulos reconhecidos (sem distinção de maiúsculas): ``f``/``freq``
  (frequência), ``v``/``tensao`` (tensão), ``i``/``corrente``
  (corrente), ``pha``/``fase`` (fase), ``|z|``/``zmod``,
  ``z'``/``zre`` e ``z''``/``zim``.  As chaves podem ser separadas
  por espaço, tabulação ou ``;``.

Um marcador opcional no início da linha (``#``, ``$``, ``>`` ou
``*``) é ignorado — útil para o firmware distinguir os dados das
mensagens de depuração.

A camada de parsing (:class:`SerialLineParser`) é independente do
transporte e totalmente testável sem hardware.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

import util
from util import (
    COL_CURR,
    COL_FREQ,
    COL_MINUS_ZIMAG,
    COL_PHASE,
    COL_VOLT,
    COL_ZMOD,
    COL_ZREAL,
    COLUMN_LABELS,
)

logger = logging.getLogger(__name__)

#: Número de colunas canônicas (Freq, Z', -Z'', |Z|, Fase, V, I).
_N_COLS: int = len(COLUMN_LABELS)

#: Mapeamento posicional padrão (frequência, tensão, corrente, fase).
DEFAULT_MAPPING: tuple[int, ...] = (
    COL_FREQ, COL_VOLT, COL_CURR, COL_PHASE,
)

#: Chaves de rótulo (minúsculas) → coluna canônica.
_LABEL_TO_COLUMN: dict[str, int] = {
    "f": COL_FREQ, "freq": COL_FREQ, "frequencia": COL_FREQ,
    "frequência": COL_FREQ, "frequency": COL_FREQ, "hz": COL_FREQ,
    "w": COL_FREQ,
    "v": COL_VOLT, "u": COL_VOLT, "volt": COL_VOLT, "tensao": COL_VOLT,
    "tensão": COL_VOLT, "voltage": COL_VOLT, "vrms": COL_VOLT,
    "i": COL_CURR, "corrente": COL_CURR, "current": COL_CURR,
    "curr": COL_CURR, "amp": COL_CURR, "irms": COL_CURR,
    "pha": COL_PHASE, "phase": COL_PHASE, "fase": COL_PHASE,
    "phi": COL_PHASE, "deg": COL_PHASE, "ang": COL_PHASE,
    "angulo": COL_PHASE, "ângulo": COL_PHASE, "θ": COL_PHASE,
    "zr": COL_ZREAL, "zre": COL_ZREAL, "z'": COL_ZREAL, "re": COL_ZREAL,
    "zi": COL_MINUS_ZIMAG, "zim": COL_MINUS_ZIMAG,
    "z''": COL_MINUS_ZIMAG, "-z''": COL_MINUS_ZIMAG, "im": COL_MINUS_ZIMAG,
    "zmod": COL_ZMOD, "|z|": COL_ZMOD, "mag": COL_ZMOD, "z": COL_ZMOD,
    "modulo": COL_ZMOD, "módulo": COL_ZMOD, "abs": COL_ZMOD,
}

#: Caracteres de marcador de início de linha ignorados.
_MARKER_CHARS: str = "#$>*"

#: Regex de um par ``chave=valor`` (aceita ``=`` ou ``:``).
_PAIR_RE = re.compile(
    r"([^\s=:;]+)\s*[=:]\s*([+\-]?\d[\d.,eE+\-]*)"
)


def _strip_marker(line: str) -> str:
    """Remove um marcador de início de linha (``#``, ``$``, ...)."""
    return re.sub(rf"^\s*[{re.escape(_MARKER_CHARS)}]+\s*", "", line)


def parse_labeled(line: str) -> Optional[dict[int, float]]:
    """Interpreta uma linha rotulada ``chave=valor``.

    Args:
        line: Linha de texto (o marcador inicial é removido).

    Returns:
        Dicionário ``{coluna_canônica: valor}`` com os pares
        reconhecidos, ou ``None`` se nenhum rótulo conhecido for
        encontrado.
    """
    result: dict[int, float] = {}
    for key, raw_value in _PAIR_RE.findall(_strip_marker(line)):
        column = _LABEL_TO_COLUMN.get(key.strip().lower())
        if column is None:
            continue
        value = util.parse_number(raw_value)
        if value is not None:
            result[column] = value
    return result or None

#: Velocidades (baud) comuns; 115200 é o padrão do projeto.
COMMON_BAUD_RATES: tuple[int, ...] = (
    9600, 19200, 38400, 57600, 115200, 230400, 250000, 500000, 921600,
)

#: Baud padrão.
DEFAULT_BAUD_RATE: int = 115200


def list_serial_ports() -> list[tuple[str, str]]:
    """Lista as portas seriais disponíveis no computador.

    Returns:
        Lista de tuplas ``(nome, descrição)`` — por exemplo
        ``("COM3", "USB-SERIAL CH340")`` — ordenada por nome.
    """
    ports: list[tuple[str, str]] = []
    for info in QSerialPortInfo.availablePorts():
        name = info.portName()
        description = info.description() or ""
        manufacturer = info.manufacturer() or ""
        label = " — ".join(p for p in (description, manufacturer) if p)
        ports.append((name, label))
    ports.sort(key=lambda item: item[0])
    logger.debug("Portas seriais disponíveis: %s", ports)
    return ports


class SerialLineParser:
    """Acumula bytes recebidos e extrai linhas de dados canônicas.

    Mantém um buffer de texto; a cada chamada de :meth:`feed`, separa
    as linhas completas (terminadas em ``\\n``) e interpreta cada uma
    em uma linha canônica de 7 colunas (Freq, Z', -Z'', |Z|, Fase,
    Tensão, Corrente).

    Linhas **rotuladas** (``f=... V=...``) são reconhecidas
    automaticamente e mapeadas pelos rótulos; as demais usam o
    mapeamento posicional (:attr:`mapping`).  Linhas sem nenhum número
    (cabeçalhos, mensagens de log do firmware) são ignoradas.  Uma
    linha parcial permanece no buffer até completar.
    """

    _MAX_BUFFER: int = 64 * 1024

    def __init__(
        self, mapping: tuple[int, ...] = DEFAULT_MAPPING
    ) -> None:
        self._buffer: str = ""
        self._mapping: tuple[int, ...] = tuple(mapping)

    def set_mapping(self, mapping: tuple[int, ...]) -> None:
        """Define o mapeamento posicional (formato sem rótulos)."""
        self._mapping = tuple(mapping)

    def reset(self) -> None:
        """Descarta qualquer dado parcial no buffer."""
        self._buffer = ""

    def feed(self, data: bytes) -> list[list[Optional[float]]]:
        """Alimenta o parser com bytes e retorna as linhas canônicas.

        Args:
            data: Bytes recebidos da porta serial.

        Returns:
            Lista de linhas canônicas (7 colunas cada, ``float`` ou
            ``None``).  Vazia se ainda não houver linha completa com
            números.
        """
        # Números são ASCII; latin-1 nunca falha na decodificação.
        self._buffer += data.decode("latin-1")
        if len(self._buffer) > self._MAX_BUFFER:
            # Protege contra fluxo sem terminador de linha.
            self._buffer = self._buffer[-self._MAX_BUFFER:]

        self._buffer = self._buffer.replace("\r\n", "\n").replace(
            "\r", "\n"
        )
        rows: list[list[Optional[float]]] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            parsed = self.parse_line(line)
            if parsed is not None:
                rows.append(parsed)
        return rows

    def parse_line(self, line: str) -> Optional[list[Optional[float]]]:
        """Interpreta uma linha em uma linha canônica de 7 colunas.

        Args:
            line: Linha (sem o terminador).

        Returns:
            Linha canônica (7 valores ``float``/``None``), ou ``None``
            se a linha não contiver dados numéricos reconhecíveis.
        """
        clean = _strip_marker(line)
        if not clean.strip():
            return None

        labeled = parse_labeled(clean)
        if labeled is not None:
            row: list[Optional[float]] = [None] * _N_COLS
            for column, value in labeled.items():
                row[column] = value
            return row

        delimiter = util.detect_delimiter(clean)
        tokens = util._split_line(clean, delimiter)
        values = [util.parse_number(token) for token in tokens]
        if not any(value is not None for value in values):
            return None
        row = [None] * _N_COLS
        for position, column in enumerate(self._mapping):
            if position < len(values):
                row[column] = values[position]
        return row


class SerialAcquisition(QObject):
    """Aquisição de pontos por porta serial (transporte QtSerialPort).

    Sinais:
        rowReceived(object): emitido para cada linha de dados
            recebida, já mapeada para as 7 colunas canônicas
            (``float``/``None``).
        rawLineReceived(str): emitido com o texto bruto de cada linha
            (para o log da interface).
        opened(): emitido quando a porta é aberta com sucesso.
        closed(): emitido quando a porta é fechada.
        errorOccurred(str): emitido em caso de erro de comunicação.
    """

    rowReceived = Signal(object)
    rawLineReceived = Signal(str)
    opened = Signal()
    closed = Signal()
    errorOccurred = Signal(str)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        mapping: tuple[int, ...] = DEFAULT_MAPPING,
    ) -> None:
        super().__init__(parent)
        self._port = QSerialPort(self)
        self._parser = SerialLineParser(mapping)
        self._port.readyRead.connect(self._on_ready_read)
        self._port.errorOccurred.connect(self._on_error)
        self._pending_line: str = ""

    def set_mapping(self, mapping: tuple[int, ...]) -> None:
        """Define o mapeamento posicional (formato sem rótulos)."""
        self._parser.set_mapping(mapping)

    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        """Indica se a porta está aberta."""
        return self._port.isOpen()

    @property
    def port_name(self) -> str:
        """Nome da porta atual."""
        return self._port.portName()

    def open(self, port_name: str, baud_rate: int) -> None:
        """Abre a porta serial indicada.

        Args:
            port_name: Nome da porta (ex.: ``"COM3"``).
            baud_rate: Velocidade em baud (ex.: 115200).

        Raises:
            RuntimeError: Se a porta não puder ser aberta.
        """
        if self._port.isOpen():
            self.close()
        self._parser.reset()
        self._pending_line = ""
        self._port.setPortName(port_name)
        self._port.setBaudRate(int(baud_rate))
        self._port.setDataBits(QSerialPort.DataBits.Data8)
        self._port.setParity(QSerialPort.Parity.NoParity)
        self._port.setStopBits(QSerialPort.StopBits.OneStop)
        self._port.setFlowControl(QSerialPort.FlowControl.NoFlowControl)
        if not self._port.open(QSerialPort.OpenModeFlag.ReadOnly):
            message = self._port.errorString() or "erro desconhecido"
            raise RuntimeError(
                f"Não foi possível abrir a porta {port_name}: {message}."
            )
        logger.info(
            "Porta serial %s aberta a %d baud.", port_name, baud_rate
        )
        self.opened.emit()

    def close(self) -> None:
        """Fecha a porta serial, se aberta."""
        if self._port.isOpen():
            self._port.close()
            logger.info("Porta serial %s fechada.", self._port.portName())
            self.closed.emit()

    def send_text(self, text: str) -> None:
        """Envia um texto pela porta (comando ao embarcado).

        Args:
            text: Texto a enviar (um ``\\n`` é acrescentado).
        """
        if self._port.isOpen():
            self._port.write((text + "\n").encode("latin-1"))

    # ------------------------------------------------------------------
    def _on_ready_read(self) -> None:
        """Lê os bytes disponíveis e processa as linhas completas."""
        data = bytes(self._port.readAll())
        if data:
            self.process_bytes(data)

    def process_bytes(self, data: bytes) -> None:
        """Processa um bloco de bytes (emite as linhas encontradas).

        Exposto para permitir testes sem hardware.

        Args:
            data: Bytes recebidos.
        """
        text_before = self._pending_line
        rows = self._parser.feed(data)
        combined = text_before + data.decode("latin-1")
        combined = combined.replace("\r\n", "\n").replace("\r", "\n")
        *complete, self._pending_line = combined.split("\n")
        for line in complete:
            if line.strip():
                self.rawLineReceived.emit(line)
        for row in rows:
            self.rowReceived.emit(row)

    def _on_error(self, error: QSerialPort.SerialPortError) -> None:
        """Reage a erros da porta serial."""
        if error == QSerialPort.SerialPortError.NoError:
            return
        message = self._port.errorString() or str(error)
        logger.warning("Erro na porta serial: %s", message)
        self.errorOccurred.emit(message)
        # Erros de recurso (desconexão do cabo) fecham a porta.
        if error in (
            QSerialPort.SerialPortError.ResourceError,
            QSerialPort.SerialPortError.DeviceNotFoundError,
        ):
            self.close()
