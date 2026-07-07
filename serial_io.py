"""Aquisição de dados por porta serial (AMOSTRAS FRA 2.0).

Permite receber pontos de medição de um sistema embarcado (Arduino,
ESP32, STM32, etc.) por uma porta serial (USB/UART).  Usa a
``QtSerialPort`` embutida no PySide6 — não requer dependências extras.

Protocolo esperado (texto): uma linha por ponto de dados, com os
valores separados por vírgula, ponto e vírgula, tabulação ou espaços,
terminada por ``\\n``.  Vírgula decimal é aceita.  Exemplo (frequência,
tensão, corrente, fase)::

    1000,1.0,0.01,-30
    100,1.0,0.005,-45

Cada linha vira uma linha de dados; o mapeamento das colunas é
definido pelo formato escolhido na interface.

A camada de parsing (:class:`SerialLineParser`) é independente do
transporte e totalmente testável sem hardware.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

import util

logger = logging.getLogger(__name__)

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
    """Acumula bytes recebidos e extrai linhas de dados numéricos.

    Mantém um buffer de texto; a cada chamada de :meth:`feed`, separa
    as linhas completas (terminadas em ``\\n``) e interpreta cada uma
    em uma lista de valores (``float`` ou ``None``).  Linhas sem
    nenhum número (cabeçalhos, mensagens de log do firmware) são
    ignoradas.  Uma linha parcial permanece no buffer até completar.
    """

    _MAX_BUFFER: int = 64 * 1024

    def __init__(self) -> None:
        self._buffer: str = ""

    def reset(self) -> None:
        """Descarta qualquer dado parcial no buffer."""
        self._buffer = ""

    def feed(self, data: bytes) -> list[list[Optional[float]]]:
        """Alimenta o parser com bytes e retorna as linhas completas.

        Args:
            data: Bytes recebidos da porta serial.

        Returns:
            Lista de linhas de dados (cada uma com valores ``float`` ou
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

    @staticmethod
    def parse_line(line: str) -> Optional[list[Optional[float]]]:
        """Interpreta uma linha de texto em valores numéricos.

        Args:
            line: Linha (sem o terminador).

        Returns:
            Lista de valores, ou ``None`` se a linha não contiver
            nenhum número.
        """
        if not line.strip():
            return None
        delimiter = util.detect_delimiter(line)
        tokens = util._split_line(line, delimiter)
        parsed = [util.parse_number(token) for token in tokens]
        if not any(value is not None for value in parsed):
            return None
        return parsed


class SerialAcquisition(QObject):
    """Aquisição de pontos por porta serial (transporte QtSerialPort).

    Sinais:
        rowReceived(object): emitido para cada linha de dados
            recebida, com a lista de valores (``float``/``None``).
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

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._port = QSerialPort(self)
        self._parser = SerialLineParser()
        self._port.readyRead.connect(self._on_ready_read)
        self._port.errorOccurred.connect(self._on_error)
        self._pending_line: str = ""

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
