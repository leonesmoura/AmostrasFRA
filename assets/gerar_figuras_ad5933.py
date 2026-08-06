"""Gera as figuras técnicas do tópico "O analisador AD5933" do guia F1.

Ao contrário de ``gerar_ajuda.py``, que captura telas do próprio
programa, este script **desenha** diagramas e gráficos derivados do
datasheet do AD5933 e das medições feitas nesta bancada. Todos os
números aqui são rastreáveis: ou vêm do datasheet (Rev. B) ou foram
medidos com os padrões de 147,6 Ω, 332,5 Ω e 21,92 kΩ.

Cada figura é salva em duas versões, como o guia espera:

* ``<nome>_full.png`` — resolução original, aberta ao clicar na imagem;
* ``<nome>.png`` — reduzida à largura do guia (780 px).

Uso::

    python assets/gerar_figuras_ad5933.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

DESTINO = Path(__file__).resolve().parent / "ajuda"
DPI_GUIA = 100
DPI_FULL = 200

# Constantes do instrumento (datasheet Rev. B e medições desta bancada).
MCLK_HZ = 16_776_000.0        # oscilador interno
AMOSTRAS_DFT = 1024           # janela da DFT
DIVISOR_ADC = 16              # taxa de amostragem = MCLK/16
TETO_CONTAGENS = 20_200.0     # ceifamento medido nesta placa
ROUT_OHM = 230.3              # resistência de saída medida do exemplar


def _salva(fig, nome: str) -> None:
    """Grava a figura nas duas resoluções que o guia usa."""
    DESTINO.mkdir(parents=True, exist_ok=True)
    fig.savefig(DESTINO / f"{nome}_full.png", dpi=DPI_FULL,
                facecolor="white", bbox_inches="tight")
    fig.savefig(DESTINO / f"{nome}.png", dpi=DPI_GUIA,
                facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  {nome}.png + {nome}_full.png")


def _caixa(ax, x, y, w, h, texto, cor="#e8eef7", borda="#33506e", fs=8):
    """Desenha um bloco rotulado do diagrama."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.012",
            linewidth=1.2, edgecolor=borda, facecolor=cor,
        )
    )
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center",
            fontsize=fs, color="#12233a", linespacing=1.35)


def _seta(ax, x1, y1, x2, y2, cor="#33506e"):
    ax.add_patch(
        FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                        mutation_scale=11, linewidth=1.1, color=cor)
    )


# ---------------------------------------------------------------------------
def diagrama_blocos() -> None:
    """Cadeia de transmissão e recepção do AD5933."""
    fig, ax = plt.subplots(figsize=(7.8, 4.3))
    ax.set_xlim(0, 100)
    ax.set_ylim(-6, 58)
    ax.axis("off")

    ax.text(50, 55.5, "AD5933 — cadeia de medição",
            ha="center", fontsize=11, weight="bold", color="#12233a")

    # Transmissão
    ax.text(2, 47.5, "TRANSMISSÃO", fontsize=8, weight="bold", color="#7a5000")
    _caixa(ax, 2, 36, 15, 8, "Oscilador\nMCLK\n16,776 MHz", cor="#fdf0d8",
           borda="#a07a20")
    _caixa(ax, 21, 36, 14, 8, "DDS\n(síntese\ndigital)", cor="#fdf0d8",
           borda="#a07a20")
    _caixa(ax, 39, 36, 14, 8, "DAC +\nfaixa de\nsaída", cor="#fdf0d8",
           borda="#a07a20")
    _seta(ax, 17, 40, 21, 40)
    _seta(ax, 35, 40, 39, 40)
    _seta(ax, 53, 40, 60, 40)
    ax.text(56.5, 41.4, "VOUT", fontsize=7.5, ha="center", color="#7a5000")

    # Amostra
    _caixa(ax, 60, 33, 17, 14,
           "AMOSTRA\n$Z$ desconhecida\n\n+ $R_{OUT}$ em série\n(≈ 230 Ω)",
           cor="#e6f3e6", borda="#2f7a3f", fs=8)

    # Recepção
    ax.text(2, 28.5, "RECEPÇÃO", fontsize=8, weight="bold", color="#33506e")
    _seta(ax, 68.5, 33, 68.5, 27.5)
    ax.text(70.5, 29.5, "VIN", fontsize=7.5, color="#33506e")
    _seta(ax, 68.5, 27.5, 62, 22)

    _caixa(ax, 45, 17, 17, 10,
           "Amp. trans-\nimpedância\n$R_{FB}$ define a faixa")
    _caixa(ax, 30, 17, 13, 10, "PGA\n×1 ou ×5")
    _caixa(ax, 16, 17, 12, 10, "Filtro\npassa-\nbaixas")
    _caixa(ax, 2, 17, 12, 10, "ADC\n12 bits\nMCLK/16")
    _seta(ax, 45, 22, 43, 22)
    _seta(ax, 30, 22, 28, 22)
    _seta(ax, 16, 22, 14, 22)

    _seta(ax, 8, 17, 8, 12)
    _caixa(ax, 2, 3, 30, 9,
           "DFT de 1024 pontos\n(janela fixa de "
           f"{1000 * AMOSTRAS_DFT * DIVISOR_ADC / MCLK_HZ:.2f} ms)",
           cor="#e3e0f2", borda="#4b3f8f")
    _seta(ax, 32, 7.5, 38, 7.5)
    _caixa(ax, 38, 3, 26, 9,
           "Registradores\nREAL e IMAG (16 bits)", cor="#e3e0f2",
           borda="#4b3f8f")
    _seta(ax, 64, 7.5, 70, 7.5)
    _caixa(ax, 70, 3, 28, 9,
           "Calibração →\n$|Z|$ e fase", cor="#f7e3e3", borda="#8f3f3f")

    ax.text(
        50, -4,
        "O chip entrega REAL e IMAG proporcionais à corrente. "
        "Converter em ohms exige calibração.",
        ha="center", fontsize=8, style="italic", color="#555555",
    )
    _salva(fig, "ad5933_blocos")


# ---------------------------------------------------------------------------
def janela_dft() -> None:
    """Ciclos da excitação que cabem na janela da DFT, versus frequência."""
    janela_s = AMOSTRAS_DFT * DIVISOR_ADC / MCLK_HZ
    f = np.logspace(0, 5.4, 600)
    ciclos = f * janela_s
    f_min = 1.0 / janela_s

    fig, ax = plt.subplots(figsize=(7.8, 3.9))
    ax.loglog(f, ciclos, lw=2, color="#1f5fa8")
    ax.axhline(1.0, color="#b03030", ls="--", lw=1.3)
    ax.axvline(f_min, color="#b03030", ls="--", lw=1.3)
    ax.fill_between(f, 1e-3, 1.0, where=(ciclos < 1.0),
                    color="#b03030", alpha=0.10)

    ax.annotate(
        f"abaixo de {f_min:.0f} Hz não cabe\nnem um ciclo: o par real/imag\n"
        "deixa de ser uma medida",
        xy=(f_min * 0.02, 0.05), fontsize=8, color="#8a2020", ha="left",
    )
    ax.annotate(
        f"janela fixa de {janela_s * 1000:.2f} ms\n"
        "(1024 amostras a MCLK/16)",
        xy=(3e3, 2e2), fontsize=8, color="#1f5fa8", ha="left",
    )
    ax.set_xlabel("frequência de excitação (Hz)")
    ax.set_ylabel("ciclos dentro da janela da DFT")
    ax.set_title("Por que existe um piso de frequência (clock interno)",
                 fontsize=10)
    ax.grid(True, which="both", alpha=0.25)
    ax.set_ylim(1e-3, 1e3)
    fig.tight_layout()
    _salva(fig, "ad5933_dft")


# ---------------------------------------------------------------------------
def tempo_acomodacao() -> None:
    """Duração do settling e da varredura conforme a frequência."""
    f = np.logspace(3, 5, 400)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.8, 3.6))

    for ciclos, cor in ((10, "#2f7a3f"), (100, "#1f5fa8"), (511, "#b03030")):
        ax1.loglog(f, 1000.0 * ciclos / f, lw=1.8, color=cor,
                   label=f"{ciclos} ciclos")
    ax1.set_xlabel("frequência (Hz)")
    ax1.set_ylabel("tempo de acomodação (ms)")
    ax1.set_title("Acomodação = N/f", fontsize=9.5)
    ax1.grid(True, which="both", alpha=0.25)
    ax1.legend(fontsize=7.5, frameon=False)

    # Duração total de uma varredura de 100 pontos de f0 até 100 kHz.
    f0 = np.logspace(1, 4.9, 400)
    t_dft = AMOSTRAS_DFT * DIVISOR_ADC / MCLK_HZ
    for ciclos, cor in ((10, "#2f7a3f"), (100, "#1f5fa8"), (511, "#b03030")):
        pontos = np.linspace(f0, 100000.0, 100)
        total = np.sum(ciclos / pontos + t_dft, axis=0)
        ax2.loglog(f0, total, lw=1.8, color=cor, label=f"{ciclos} ciclos")
    ax2.set_xlabel("frequência inicial da varredura (Hz)")
    ax2.set_ylabel("duração total (s)")
    ax2.set_title("Varredura de 100 pontos até 100 kHz", fontsize=9.5)
    ax2.grid(True, which="both", alpha=0.25)
    ax2.legend(fontsize=7.5, frameon=False)

    fig.tight_layout()
    _salva(fig, "ad5933_acomodacao")


# ---------------------------------------------------------------------------
def faixa_impedancia() -> None:
    """Faixa mensurável em função do resistor de realimentação."""
    fig, ax = plt.subplots(figsize=(7.8, 3.6))

    faixas = [
        ("100 Ω", 100.0, 1e3),
        ("1 kΩ", 1e3, 1e4),
        ("10 kΩ", 1e4, 1e5),
        ("100 kΩ", 1e5, 1e6),
        ("1 MΩ", 1e6, 2e6),
    ]
    for i, (rotulo, zmin, zmax) in enumerate(faixas):
        ax.plot([zmin, zmax], [i, i], lw=7, color="#9fb8d4",
                solid_capstyle="butt")
        ax.text(zmax * 1.35, i, f"$R_{{FB}}$ = {rotulo}",
                va="center", fontsize=7.5, color="#33506e")

    # A placa deste projeto, antes e depois da modificação.
    ax.plot([1e5, 1e7], [5.4, 5.4], lw=7, color="#d0a0a0",
            solid_capstyle="butt")
    ax.text(1.3e7, 5.4, "placa de fábrica: $R_{FB}$ = 200 kΩ",
            va="center", fontsize=7.5, color="#8a2020")
    ax.plot([150.0, 1.5e4], [6.4, 6.4], lw=7, color="#8fbf8f",
            solid_capstyle="butt")
    ax.text(2.0e4, 6.4, "após a modificação: $R_{FB}$ ≈ 330 Ω",
            va="center", fontsize=7.5, color="#2f7a3f")

    ax.set_xscale("log")
    ax.set_xlim(50, 5e8)
    ax.set_ylim(-0.8, 7.2)
    ax.set_yticks([])
    ax.set_xlabel("impedância mensurável (Ω)")
    ax.set_title(
        "A faixa é escolhida pelo resistor de realimentação, "
        "uma década por vez", fontsize=10)
    ax.grid(True, axis="x", which="both", alpha=0.25)
    fig.tight_layout()
    _salva(fig, "ad5933_faixa")


# ---------------------------------------------------------------------------
def ganho_pga() -> None:
    """Nível de sinal no conversor conforme |Z|, para PGA ×1 e ×5."""
    z = np.logspace(1.7, 5.2, 500)
    # Modelo medido nesta placa: mag = K/(ROUT+|Z|), com o R9 modificado.
    k1 = 4.635e6
    mag1 = k1 / (ROUT_OHM + z)
    mag5 = mag1 * 4.858          # ganho efetivo medido do PGA

    fig, ax = plt.subplots(figsize=(7.8, 4.0))
    ax.loglog(z, mag1, lw=2, color="#1f5fa8", label="PGA ×1")
    ax.loglog(z, mag5, lw=2, color="#2f7a3f", label="PGA ×5")
    ax.axhline(TETO_CONTAGENS, color="#b03030", ls="--", lw=1.3)
    ax.axhline(300.0, color="#a07a20", ls="--", lw=1.3)
    ax.fill_between(z, TETO_CONTAGENS, 1e6, color="#b03030", alpha=0.08)
    ax.fill_between(z, 1e0, 300.0, color="#a07a20", alpha=0.08)

    ax.text(2e3, TETO_CONTAGENS * 1.7, "ceifamento — sinal perdido",
            fontsize=8, color="#8a2020")
    ax.text(2e3, 120, "ruído domina — resolução pobre",
            fontsize=8, color="#7a5000")
    ax.set_xlabel("impedância da amostra (Ω)")
    ax.set_ylabel("magnitude bruta (contagens da DFT)")
    ax.set_title(
        "O PGA desloca a janela útil: ×1 para impedância baixa, "
        "×5 para alta", fontsize=10)
    ax.set_ylim(50, 3e5)
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout()
    _salva(fig, "ad5933_pga")


# ---------------------------------------------------------------------------
def clock_externo() -> None:
    """Banda útil em função do clock fornecido ao AD5933."""
    mclk = np.logspace(4, 7.3, 500)
    f_min = mclk / (AMOSTRAS_DFT * DIVISOR_ADC)   # 1 ciclo na janela
    f_max = mclk / 168.0                          # limite prático do DDS

    fig, ax = plt.subplots(figsize=(7.8, 4.0))
    ax.fill_between(mclk, f_min, f_max, color="#9fb8d4", alpha=0.35,
                    label="banda utilizável")
    ax.loglog(mclk, f_min, lw=1.8, color="#b03030",
              label="piso (1 ciclo na janela da DFT)")
    ax.loglog(mclk, f_max, lw=1.8, color="#1f5fa8", label="teto prático")

    ax.plot([MCLK_HZ], [MCLK_HZ / (AMOSTRAS_DFT * DIVISOR_ADC)], "o",
            color="#12233a", ms=6)
    ax.annotate(
        "clock interno 16,776 MHz\n→ piso de ~1 kHz",
        xy=(MCLK_HZ, MCLK_HZ / (AMOSTRAS_DFT * DIVISOR_ADC)),
        xytext=(2.5e5, 4e3), fontsize=8, color="#12233a",
        arrowprops=dict(arrowstyle="->", color="#12233a", lw=1),
    )
    alvo = 10.0 * AMOSTRAS_DFT * DIVISOR_ADC
    ax.plot([alvo], [10.0], "o", color="#2f7a3f", ms=6)
    ax.annotate(
        "para medir 10 Hz:\nMCLK ≈ 164 kHz no SMA P5",
        xy=(alvo, 10.0), xytext=(2.4e5, 0.75), fontsize=8, color="#2f7a3f",
        arrowprops=dict(arrowstyle="->", color="#2f7a3f", lw=1),
    )

    ax.set_xlabel("clock fornecido ao AD5933, MCLK (Hz)")
    ax.set_ylabel("frequência de excitação (Hz)")
    ax.set_title("Baixar o clock desloca a banda inteira para baixo",
                 fontsize=10)
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    _salva(fig, "ad5933_clock")


if __name__ == "__main__":
    print("Gerando figuras do tópico AD5933 em", DESTINO)
    diagrama_blocos()
    janela_dft()
    tempo_acomodacao()
    faixa_impedancia()
    ganho_pga()
    clock_externo()
    print("Concluído.")
