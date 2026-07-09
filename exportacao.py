"""Exportação de dados, imagens e relatórios (AMOSTRAS FRA 2.0).

Recursos:

* Exportação de figuras para PNG, PDF e SVG.
* Exportação de medições para Excel (uma planilha por medição, com
  resumo, parâmetros de ajuste e métricas de Kramers-Kronig) e CSV.
* Geração de relatório PDF completo (resumo, tabela de parâmetros,
  Nyquist, Bode, Kramers-Kronig, circuito equivalente e observações)
  usando ``matplotlib.backends.backend_pdf.PdfPages`` com tema claro,
  adequado para impressão.
"""

from __future__ import annotations

import datetime
import logging
import re
import textwrap
from pathlib import Path
from typing import Optional, Sequence

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from circuitos import FitResult
from correcao import InstrumentCorrection
from kk import KKResult, METRIC_LABELS
from plots import (
    LIGHT_RC,
    PlotStyle,
    plot_bode_magnitude,
    plot_bode_phase,
    plot_circuit_fit,
    plot_kk,
    plot_nyquist,
)
from util import (
    APP_NAME,
    APP_VERSION,
    IV_METRIC_LABELS,
    IVCurve,
    Measurement,
)

logger = logging.getLogger(__name__)

#: Tamanho de página A4 paisagem, em polegadas.
_A4_LANDSCAPE: tuple[float, float] = (11.69, 8.27)

#: Extensões de imagem suportadas pela exportação de figuras.
IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".pdf", ".svg")


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------
def export_figure(figure: Figure, path: str | Path, dpi: int = 300) -> None:
    """Salva uma figura em PNG, PDF ou SVG.

    Args:
        figure: Figura do Matplotlib a salvar.
        path: Caminho de destino; a extensão define o formato.
        dpi: Resolução para formatos rasterizados.

    Raises:
        ValueError: Se a extensão não for suportada.
    """
    file_path = Path(path)
    if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(
            f"Extensão '{file_path.suffix}' não suportada. "
            f"Use: {', '.join(IMAGE_EXTENSIONS)}."
        )
    figure.savefig(file_path, dpi=dpi, bbox_inches="tight")
    logger.info("Figura exportada: %s", file_path)


# ---------------------------------------------------------------------------
# Dados tabulares
# ---------------------------------------------------------------------------
def _sanitize_sheet_name(name: str, used: set[str]) -> str:
    """Sanitiza um nome de planilha do Excel (31 caracteres, único)."""
    clean = re.sub(r"[\[\]:*?/\\]", "_", name).strip() or "Medicao"
    clean = clean[:31]
    candidate = clean
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = clean[: 31 - len(suffix)] + suffix
        index += 1
    used.add(candidate)
    return candidate


def export_measurements_excel(
    measurements: Sequence[Measurement],
    path: str | Path,
    fit_results: Optional[Sequence[FitResult]] = None,
    kk_results: Optional[Sequence[KKResult]] = None,
) -> None:
    """Exporta medições (e resultados de análise) para um arquivo XLSX.

    Estrutura: planilha ``Resumo`` com a visão geral, uma planilha por
    medição com as 5 colunas canônicas, planilha ``Ajustes`` com os
    parâmetros dos circuitos equivalentes e planilha
    ``Kramers-Kronig`` com as métricas de validação.

    Args:
        measurements: Medições a exportar (ao menos uma).
        path: Caminho do arquivo ``.xlsx``.
        fit_results: Resultados de ajuste a incluir (opcional).
        kk_results: Resultados de KK a incluir (opcional).

    Raises:
        ValueError: Se nenhuma medição for fornecida.
    """
    if not measurements:
        raise ValueError("Nenhuma medição para exportar.")
    file_path = Path(path)

    summary = pd.DataFrame(
        {
            "Medição": [m.name for m in measurements],
            "Pontos": [m.n_points for m in measurements],
            "f mínima (Hz)": [float(np.min(m.frequency)) for m in measurements],
            "f máxima (Hz)": [float(np.max(m.frequency)) for m in measurements],
            "Corrigida": ["Sim" if m.corrected else "Não" for m in measurements],
        }
    )

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Resumo", index=False)
        used_names: set[str] = {"Resumo", "Ajustes", "Kramers-Kronig"}
        for m in measurements:
            sheet = _sanitize_sheet_name(m.name, used_names)
            m.to_dataframe().to_excel(writer, sheet_name=sheet, index=False)

        if fit_results:
            rows: list[dict[str, object]] = []
            for fit in fit_results:
                for name, unit, value, error in zip(
                    fit.param_names,
                    fit.param_units,
                    fit.param_values,
                    fit.param_errors,
                ):
                    rows.append(
                        {
                            "Medição": fit.measurement_name,
                            "Modelo": fit.model_name,
                            "Circuito": fit.circuit_string,
                            "Parâmetro": name,
                            "Valor": value,
                            "Incerteza (1σ)": error,
                            "Unidade": unit,
                        }
                    )
                rows.append(
                    {
                        "Medição": fit.measurement_name,
                        "Modelo": fit.model_name,
                        "Circuito": fit.circuit_string,
                        "Parâmetro": "χ²",
                        "Valor": fit.chi_squared,
                        "Incerteza (1σ)": np.nan,
                        "Unidade": "",
                    }
                )
                rows.append(
                    {
                        "Medição": fit.measurement_name,
                        "Modelo": fit.model_name,
                        "Circuito": fit.circuit_string,
                        "Parâmetro": "RMSE",
                        "Valor": fit.rmse,
                        "Incerteza (1σ)": np.nan,
                        "Unidade": "Ω",
                    }
                )
                rows.append(
                    {
                        "Medição": fit.measurement_name,
                        "Modelo": fit.model_name,
                        "Circuito": fit.circuit_string,
                        "Parâmetro": "R²",
                        "Valor": fit.r_squared,
                        "Incerteza (1σ)": np.nan,
                        "Unidade": "",
                    }
                )
            pd.DataFrame(rows).to_excel(
                writer, sheet_name="Ajustes", index=False
            )

        if kk_results:
            kk_rows: list[dict[str, object]] = []
            for kk in kk_results:
                for key, label in METRIC_LABELS.items():
                    kk_rows.append(
                        {
                            "Medição": kk.measurement_name,
                            "Métrica": label,
                            "Valor": kk.metrics.get(key, np.nan),
                        }
                    )
            pd.DataFrame(kk_rows).to_excel(
                writer, sheet_name="Kramers-Kronig", index=False
            )

    logger.info(
        "Excel exportado: %s (%d medição(ões)).",
        file_path,
        len(measurements),
    )


def export_measurements_csv(
    measurements: Sequence[Measurement],
    path: str | Path,
    sep: str = ";",
    decimal: str = ",",
    iv_curves: Sequence[IVCurve] = (),
) -> None:
    """Exporta medições e curvas I-V para CSV (formato pt-BR).

    Gera um CSV **autocontido** e reimportável: cada linha traz a
    coluna ``Medição`` (nome da amostra) e a coluna ``Tipo`` (``EIS``
    para os pontos de impedância, ``I-V`` para os pontos da curva I-V).
    Assim a exportação preserva o FRA **e** a curva I-V de cada amostra
    num único arquivo, e a importação restaura ambos.  O padrão ``;`` +
    vírgula decimal abre corretamente no Excel pt-BR.

    Args:
        measurements: Medições (EIS/FRA) a exportar.
        path: Caminho do arquivo ``.csv``.
        sep: Separador de campos.
        decimal: Separador decimal.
        iv_curves: Curvas I-V a exportar junto (opcional).

    Raises:
        ValueError: Se não houver nem medição nem curva I-V.
    """
    if not measurements and not iv_curves:
        raise ValueError("Nenhuma medição ou curva I-V para exportar.")
    frames: list[pd.DataFrame] = []
    for m in measurements:
        df = m.to_dataframe()
        df.insert(0, "Tipo", "EIS")
        df.insert(0, "Medição", m.name)
        frames.append(df)
    for curve in iv_curves:
        df = curve.to_dataframe()
        df.insert(0, "Tipo", "I-V")
        df.insert(0, "Medição", curve.name)
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(
        path, sep=sep, decimal=decimal, index=False, encoding="utf-8-sig"
    )
    logger.info(
        "CSV exportado: %s (%d medição(ões), %d curva(s) I-V).",
        path,
        len(measurements),
        len(iv_curves),
    )


def export_correction(
    correction: InstrumentCorrection,
    path: str | Path,
    sep: str = ";",
    decimal: str = ",",
) -> None:
    """Exporta a tabela de uma correção do instrumento.

    Grava frequência, magnitude e fase do resistor padrão e a função
    de transferência ``H(f)`` calculada (Re, Im, |H| e fase de H).  O
    arquivo é reimportável pela janela de Correção do Instrumento (as
    colunas de frequência, magnitude e fase são reconhecidas).

    Args:
        correction: Correção a exportar.
        path: Caminho do arquivo (``.csv``, ``.txt``, ``.xlsx`` ou
            ``.xlsm``).
        sep: Separador de campos (apenas para CSV/TXT).
        decimal: Separador decimal (apenas para CSV/TXT).

    Raises:
        ValueError: Se a extensão não for suportada.
    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    df = correction.to_dataframe()
    if suffix in {".xlsx", ".xlsm"}:
        sheet = _sanitize_sheet_name(correction.name, set())
        df.to_excel(file_path, sheet_name=sheet, index=False)
    elif suffix in {".csv", ".txt", ".dat"}:
        df.to_csv(
            file_path, sep=sep, decimal=decimal, index=False,
            encoding="utf-8-sig",
        )
    else:
        raise ValueError(
            f"Extensão '{suffix}' não suportada. Use CSV, TXT ou XLSX."
        )
    logger.info(
        "Correção '%s' exportada: %s.", correction.name, file_path
    )


def export_iv_excel(
    curves: Sequence[IVCurve],
    path: str | Path,
) -> None:
    """Exporta curvas I-V para um arquivo XLSX.

    Estrutura: planilha ``Resumo`` com os parâmetros característicos
    (Isc, Voc, Pmáx, Vmp, Imp, FF) e uma planilha por curva com
    tensão, corrente e potência.

    Args:
        curves: Curvas I-V a exportar (ao menos uma).
        path: Caminho do arquivo ``.xlsx``.

    Raises:
        ValueError: Se nenhuma curva for fornecida.
    """
    if not curves:
        raise ValueError("Nenhuma curva I-V para exportar.")
    file_path = Path(path)

    summary_rows: list[dict[str, object]] = []
    for curve in curves:
        row: dict[str, object] = {
            "Curva": curve.name,
            "Pontos": curve.n_points,
        }
        metrics = curve.metrics()
        for key, label in IV_METRIC_LABELS.items():
            row[label] = metrics[key]
        summary_rows.append(row)

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(
            writer, sheet_name="Resumo", index=False
        )
        used_names: set[str] = {"Resumo"}
        for curve in curves:
            sheet = _sanitize_sheet_name(curve.name, used_names)
            curve.to_dataframe().to_excel(
                writer, sheet_name=sheet, index=False
            )

    logger.info(
        "Excel de curvas I-V exportado: %s (%d curva(s)).",
        file_path,
        len(curves),
    )


# ---------------------------------------------------------------------------
# Relatório PDF
# ---------------------------------------------------------------------------
def _new_page(figsize: tuple[float, float] = _A4_LANDSCAPE) -> Figure:
    """Cria uma nova página (figura) para o relatório."""
    return Figure(figsize=figsize, constrained_layout=True)


def _paginate(items: Sequence, per_page: int) -> list[Sequence]:
    """Divide uma sequência em blocos de até ``per_page`` itens."""
    return [
        items[i: i + per_page] for i in range(0, len(items), per_page)
    ]


#: Linhas de tabela por página do relatório (evita transbordar a página).
_SUMMARY_ROWS_FIRST_PAGE: int = 12
_TABLE_ROWS_PER_PAGE: int = 20
_OBSERVATION_LINES_PER_PAGE: int = 38


def _summary_pages(
    measurements: Sequence[Measurement],
    corrections: Sequence[InstrumentCorrection],
) -> list[Figure]:
    """Monta a(s) página(s) de resumo do relatório (paginadas)."""
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    header = (
        f"Gerado em: {now}\n"
        f"Software: {APP_NAME} (versão {APP_VERSION})\n"
        f"Medições analisadas: {len(measurements)}\n"
        "Técnica: Espectroscopia de Impedância (EIS/FRA)"
    )
    if corrections:
        descriptions = "; ".join(
            f"{c.name} (resistor {c.r_nominal:.6g} Ω, {c.n_points} pts)"
            for c in corrections
        )
        header += (
            f"\nCorreções do instrumento ({len(corrections)}): "
            f"{descriptions}"
        )
    else:
        header += "\nCorreção do instrumento: não configurada"

    table_data = [
        [
            m.name,
            str(m.n_points),
            f"{float(np.min(m.frequency)):.6g}",
            f"{float(np.max(m.frequency)):.6g}",
            "Sim" if m.corrected else "Não",
        ]
        for m in measurements
    ]
    col_labels = [
        "Medição", "Pontos", "f mín (Hz)", "f máx (Hz)", "Corrigida",
    ]

    first = table_data[:_SUMMARY_ROWS_FIRST_PAGE]
    remaining = table_data[_SUMMARY_ROWS_FIRST_PAGE:]
    chunks: list[Sequence] = [first] + _paginate(
        remaining, _TABLE_ROWS_PER_PAGE
    )

    pages: list[Figure] = []
    for page_index, chunk in enumerate(chunks):
        if not chunk and page_index > 0:
            continue
        fig = _new_page()
        ax = fig.add_subplot(111)
        ax.axis("off")
        if page_index == 0:
            fig.suptitle(
                f"{APP_NAME} — Relatório de Análise de Impedância",
                fontsize=16,
                fontweight="bold",
            )
            ax.text(
                0.0, 0.98, header, transform=ax.transAxes,
                va="top", ha="left", fontsize=11,
            )
        else:
            ax.set_title(
                "Resumo das medições (continuação)", fontsize=13, pad=20
            )
        if chunk:
            table = ax.table(
                cellText=list(chunk),
                colLabels=col_labels,
                loc="center" if page_index > 0 else "lower center",
                cellLoc="center",
            )
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1.0, 1.4)
        pages.append(fig)
    return pages


def _fit_table_pages(fit_results: Sequence[FitResult]) -> list[Figure]:
    """Monta a(s) página(s) da tabela de parâmetros (paginadas)."""
    rows: list[list[str]] = []
    for fit in fit_results:
        for name, unit, value, error in zip(
            fit.param_names,
            fit.param_units,
            fit.param_values,
            fit.param_errors,
        ):
            error_text = f"{error:.3g}" if np.isfinite(error) else "—"
            rows.append(
                [
                    fit.measurement_name,
                    fit.circuit_string,
                    name,
                    f"{value:.6g}",
                    error_text,
                    unit,
                ]
            )
        rows.append(
            [fit.measurement_name, fit.circuit_string, "χ²",
             f"{fit.chi_squared:.4g}", "—", ""]
        )
        rows.append(
            [fit.measurement_name, fit.circuit_string, "RMSE",
             f"{fit.rmse:.4g}", "—", "Ω"]
        )
        rows.append(
            [fit.measurement_name, fit.circuit_string, "R²",
             f"{fit.r_squared:.6f}", "—", ""]
        )

    pages: list[Figure] = []
    for page_index, chunk in enumerate(
        _paginate(rows, _TABLE_ROWS_PER_PAGE)
    ):
        fig = _new_page()
        ax = fig.add_subplot(111)
        ax.axis("off")
        title = "Parâmetros dos circuitos equivalentes ajustados"
        if page_index > 0:
            title += " (continuação)"
        ax.set_title(title, fontsize=13, pad=20)
        table = ax.table(
            cellText=list(chunk),
            colLabels=[
                "Medição", "Circuito", "Parâmetro", "Valor",
                "Incerteza (1σ)", "Unidade",
            ],
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.0, 1.25)
        pages.append(fig)
    return pages


def _kk_page(result: KKResult) -> Figure:
    """Monta a página de Kramers-Kronig de uma medição."""
    fig = _new_page()
    plot_kk(fig, result, PlotStyle(marker="o", marker_size=3.5))
    metrics_text = " | ".join(
        (
            f"RMSE Z'={result.metrics['rmse_real']:.4g} Ω",
            f"RMSE Z''={result.metrics['rmse_imag']:.4g} Ω",
            f"Erro máx. Z'={result.metrics['max_error_real']:.4g} Ω",
            f"Erro máx. Z''={result.metrics['max_error_imag']:.4g} Ω",
            f"Erro % médio={result.metrics['pct_error_mean']:.3g} %",
        )
    )
    fig.text(0.5, 0.005, metrics_text, ha="center", fontsize=8)
    return fig


def _observations_pages(observations: str) -> list[Figure]:
    """Monta a(s) página(s) de observações do relatório (paginadas)."""
    wrapped_lines: list[str] = []
    for paragraph in observations.splitlines():
        if paragraph.strip():
            wrapped_lines.extend(
                textwrap.fill(paragraph, width=110).splitlines()
            )
        else:
            wrapped_lines.append("")
    if not wrapped_lines:
        wrapped_lines = ["(sem observações)"]

    pages: list[Figure] = []
    for page_index, chunk in enumerate(
        _paginate(wrapped_lines, _OBSERVATION_LINES_PER_PAGE)
    ):
        fig = _new_page()
        ax = fig.add_subplot(111)
        ax.axis("off")
        title = "Observações"
        if page_index > 0:
            title += " (continuação)"
        ax.set_title(title, fontsize=13, pad=20)
        ax.text(
            0.0, 0.97, "\n".join(chunk),
            transform=ax.transAxes, va="top", ha="left", fontsize=10,
        )
        pages.append(fig)
    return pages


def generate_pdf_report(
    path: str | Path,
    measurements: Sequence[Measurement],
    kk_results: Optional[Sequence[KKResult]] = None,
    fit_results: Optional[Sequence[FitResult]] = None,
    corrections: Optional[Sequence[InstrumentCorrection]] = None,
    observations: str = "",
) -> None:
    """Gera o relatório PDF completo da análise.

    Conteúdo: página de resumo, tabela de parâmetros dos ajustes,
    diagrama de Nyquist, diagramas de Bode, validação de
    Kramers-Kronig (uma página por medição validada), ajuste de
    circuito (uma página por ajuste) e observações.

    Args:
        path: Caminho do arquivo ``.pdf`` de saída.
        measurements: Medições incluídas no relatório (ao menos uma).
        kk_results: Resultados de Kramers-Kronig (opcional).
        fit_results: Resultados de ajuste de circuito (opcional).
        corrections: Correções do instrumento da biblioteca (opcional).
        observations: Texto livre de observações.

    Raises:
        ValueError: Se nenhuma medição for fornecida.
    """
    if not measurements:
        raise ValueError("Nenhuma medição para incluir no relatório.")
    file_path = Path(path)
    kk_results = list(kk_results or [])
    fit_results = list(fit_results or [])
    corrections = list(corrections or [])
    style = PlotStyle(marker="o", marker_size=4.0, line_width=1.2)

    logger.info(
        "Gerando relatório PDF: %s (%d medições, %d KK, %d ajustes).",
        file_path,
        len(measurements),
        len(kk_results),
        len(fit_results),
    )

    with matplotlib.rc_context(LIGHT_RC):
        with PdfPages(file_path) as pdf:
            for fig in _summary_pages(measurements, corrections):
                pdf.savefig(fig)

            if fit_results:
                for fig in _fit_table_pages(fit_results):
                    pdf.savefig(fig)

            fig = _new_page()
            ax = fig.add_subplot(111)
            plot_nyquist(ax, measurements, style)
            pdf.savefig(fig)

            fig = _new_page()
            ax_mag, ax_ph = fig.subplots(1, 2)
            plot_bode_magnitude(ax_mag, measurements, style)
            plot_bode_phase(ax_ph, measurements, style)
            pdf.savefig(fig)

            for kk_result in kk_results:
                pdf.savefig(_kk_page(kk_result))

            for fit in fit_results:
                fig = _new_page()
                plot_circuit_fit(fig, fit, style)
                pdf.savefig(fig)

            for fig in _observations_pages(observations):
                pdf.savefig(fig)

            info = pdf.infodict()
            info["Title"] = f"{APP_NAME} — Relatório de Análise"
            info["Author"] = (
                f"Eng. Leones Moura dos Santos ({APP_NAME})"
            )
            info["Subject"] = (
                "Espectroscopia de Impedância — detecção de falhas em "
                "módulos fotovoltaicos"
            )
            info["CreationDate"] = datetime.datetime.now()

    logger.info("Relatório PDF gerado com sucesso: %s", file_path)
