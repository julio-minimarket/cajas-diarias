"""
modules/novedades_personal/pdf_reporte.py
==========================================
Generación del Reporte Mensual PDF de Novedades de Personal.
Usa fpdf2 (pip install fpdf2).

Estructura del documento:
  1. Encabezado (título, sucursal, período, fecha, usuario)
  2. Métricas resumen (empleados, ausencias, horas extras, adicionales $)
  3. Tabla AUSENCIAS  (agrupada por empleado)
  4. Tabla ADICIONALES (agrupada por empleado)
  5. Detalle día a día (todas las novedades con fecha exacta)
  Footer: número de página en cada hoja
"""

from __future__ import annotations
from datetime import date
from fpdf import FPDF

# ── Paleta de colores ─────────────────────────────────────────
COLOR_HEADER_BG   = (31, 73, 125)   # azul oscuro — encabezado de tabla
COLOR_HEADER_TEXT = (255, 255, 255) # blanco
COLOR_FILA_PAR    = (240, 245, 255) # azul muy claro — filas pares
COLOR_FILA_IMPAR  = (255, 255, 255) # blanco — filas impares
COLOR_SECCION_BG  = (220, 230, 241) # azul claro — título de sección
COLOR_SECCION_TXT = (31, 73, 125)   # azul oscuro
COLOR_METRICA_BG  = (245, 245, 245) # gris claro — bloque métricas
COLOR_BORDE       = (180, 190, 200) # gris para bordes


# ══════════════════════════════════════════════════════════════
# CLASE PDF
# ══════════════════════════════════════════════════════════════

class _ReportePDF(FPDF):
    """FPDF con header/footer personalizados."""

    def __init__(self, titulo_sucursal: str, periodo_label: str,
                 usuario: str, fecha_gen: str):
        super().__init__(orientation="L", unit="mm", format="A4")
        self._titulo_sucursal = titulo_sucursal
        self._periodo_label   = periodo_label
        self._usuario         = usuario
        self._fecha_gen       = fecha_gen
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(left=12, top=10, right=12)

    def header(self):
        # Franja azul superior
        self.set_fill_color(*COLOR_HEADER_BG)
        self.rect(0, 0, self.w, 22, style="F")

        self.set_y(3)
        self.set_text_color(*COLOR_HEADER_TEXT)

        # Título izquierda
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 7, "REPORTE MENSUAL DE NOVEDADES DE PERSONAL", ln=True)

        # Subtítulo: sucursal y período
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5,
                  f"Sucursal: {self._titulo_sucursal}    |    Período: {self._periodo_label}    |    "
                  f"Generado: {self._fecha_gen}    |    Por: {self._usuario}",
                  ln=True)

        # Línea separadora
        self.set_draw_color(*COLOR_BORDE)
        self.line(12, 23, self.w - 12, 23)
        self.set_y(26)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 5, f"Página {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


# ══════════════════════════════════════════════════════════════
# HELPERS DE RENDER
# ══════════════════════════════════════════════════════════════

def _titulo_seccion(pdf: _ReportePDF, texto: str):
    """Renderiza un bloque de título de sección."""
    pdf.set_fill_color(*COLOR_SECCION_BG)
    pdf.set_text_color(*COLOR_SECCION_TXT)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, f"  {texto}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _encabezado_tabla(pdf: _ReportePDF, columnas: list[tuple[str, float, str]]):
    """
    Dibuja la fila de encabezado de una tabla.
    columnas = [(label, ancho_mm, alineacion), ...]
    """
    pdf.set_fill_color(*COLOR_HEADER_BG)
    pdf.set_text_color(*COLOR_HEADER_TEXT)
    pdf.set_font("Helvetica", "B", 8)
    for label, ancho, align in columnas:
        pdf.cell(ancho, 7, label, border=1, align=align, fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)


def _fila_tabla(pdf: _ReportePDF, valores: list[tuple[str, float, str]], num_fila: int):
    """
    Dibuja una fila de datos con color alternado.
    valores = [(texto, ancho_mm, alineacion), ...]
    """
    color = COLOR_FILA_PAR if num_fila % 2 == 0 else COLOR_FILA_IMPAR
    pdf.set_fill_color(*color)
    pdf.set_font("Helvetica", "", 8)
    for texto, ancho, align in valores:
        pdf.cell(ancho, 6, str(texto) if texto is not None else "", border=1, align=align, fill=True)
    pdf.ln()


def _bloque_metricas(pdf: _ReportePDF, metricas: list[tuple[str, str]]):
    """
    Renderiza una fila de métricas (label + valor en recuadro).
    metricas = [(label, valor), ...]
    """
    pdf.set_fill_color(*COLOR_METRICA_BG)
    ancho = (pdf.w - 24) / len(metricas)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(80, 80, 80)
    for label, _ in metricas:
        pdf.cell(ancho, 6, label, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(31, 73, 125)
    for _, valor in metricas:
        pdf.cell(ancho, 9, valor, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)


# ══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════

def generar_pdf_mensual(
    datos_resumen: list[dict],
    datos_detalle: list[dict],
    sucursal_nombre: str,
    periodo: str,
    usuario: str,
    consolidado: bool = False,
) -> bytes:
    """
    Genera el PDF del reporte mensual de novedades.

    Parámetros:
      datos_resumen  — resultado de v_resumen_mensual
      datos_detalle  — resultado de v_novedades_completas
      sucursal_nombre — nombre a mostrar en encabezado
      periodo        — 'YYYY-MM'
      usuario        — nombre del usuario que genera
      consolidado    — True si incluye todas las sucursales

    Devuelve bytes del PDF listo para st.download_button.
    """
    from .utils import nombre_mes as _nombre_mes

    periodo_label = _nombre_mes(periodo)
    fecha_gen = date.today().strftime("%d/%m/%Y")

    pdf = _ReportePDF(sucursal_nombre, periodo_label, usuario, fecha_gen)
    pdf.add_page()

    # ── 1. MÉTRICAS RESUMEN ───────────────────────────────────
    empleados_ids = {r.get("empleado_id") for r in datos_resumen if r.get("empleado_id")}
    ausencias     = [r for r in datos_resumen if r.get("categoria") == "AUSENCIA"]
    adicionales   = [r for r in datos_resumen if r.get("categoria") == "ADICIONAL"]

    total_ausencias   = sum(r.get("cantidad_registros", 0) or 0 for r in ausencias)
    total_hs_extras   = sum(r.get("total_cantidad", 0) or 0 for r in adicionales)
    total_adicionales = sum(r.get("total_importe", 0) or 0 for r in adicionales)

    _titulo_seccion(pdf, "RESUMEN DEL PERÍODO")
    _bloque_metricas(pdf, [
        ("Empleados con novedades", str(len(empleados_ids))),
        ("Total ausencias (días/veces)", str(int(total_ausencias))),
        ("Total horas extras", f"{total_hs_extras:.1f} hs"),
        ("Total adicionales $", f"${total_adicionales:,.2f}"),
    ])

    # ── 2. TABLA AUSENCIAS ────────────────────────────────────
    _titulo_seccion(pdf, "AUSENCIAS")

    if ausencias:
        if consolidado:
            cols_aus = [
                ("Sucursal",     55, "L"),
                ("Empleado",     75, "L"),
                ("Tipo",         80, "L"),
                ("Días/Veces",   25, "C"),
            ]
        else:
            cols_aus = [
                ("Empleado",     100, "L"),
                ("Tipo",          100, "L"),
                ("Días/Veces",    35, "C"),
            ]
        _encabezado_tabla(pdf, cols_aus)
        for i, r in enumerate(ausencias):
            if consolidado:
                vals = [
                    (r.get("sucursal_nombre", ""),         55, "L"),
                    (r.get("empleado_nombre_completo", ""), 75, "L"),
                    (r.get("tipo_novedad", ""),             80, "L"),
                    (r.get("cantidad_registros", 0),        25, "C"),
                ]
            else:
                vals = [
                    (r.get("empleado_nombre_completo", ""), 100, "L"),
                    (r.get("tipo_novedad", ""),             100, "L"),
                    (r.get("cantidad_registros", 0),         35, "C"),
                ]
            _fila_tabla(pdf, vals, i)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 7, "  Sin ausencias en el período.", ln=True)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(5)

    # ── 3. TABLA ADICIONALES ──────────────────────────────────
    _titulo_seccion(pdf, "ADICIONALES")

    if adicionales:
        if consolidado:
            cols_adic = [
                ("Sucursal",    55, "L"),
                ("Empleado",    70, "L"),
                ("Tipo",        75, "L"),
                ("Total Hs.",   25, "C"),
                ("Total $",     30, "R"),
            ]
        else:
            cols_adic = [
                ("Empleado",    95, "L"),
                ("Tipo",        95, "L"),
                ("Total Hs.",   30, "C"),
                ("Total $",     35, "R"),
            ]
        _encabezado_tabla(pdf, cols_adic)
        for i, r in enumerate(adicionales):
            hs  = r.get("total_cantidad") or 0
            imp = r.get("total_importe") or 0
            if consolidado:
                vals = [
                    (r.get("sucursal_nombre", ""),         55, "L"),
                    (r.get("empleado_nombre_completo", ""), 70, "L"),
                    (r.get("tipo_novedad", ""),             75, "L"),
                    (f"{hs:.1f}" if hs else "",            25, "C"),
                    (f"${imp:,.2f}" if imp else "",        30, "R"),
                ]
            else:
                vals = [
                    (r.get("empleado_nombre_completo", ""), 95, "L"),
                    (r.get("tipo_novedad", ""),             95, "L"),
                    (f"{hs:.1f}" if hs else "",            30, "C"),
                    (f"${imp:,.2f}" if imp else "",        35, "R"),
                ]
            _fila_tabla(pdf, vals, i)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 7, "  Sin adicionales en el período.", ln=True)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(5)

    # ── 4. DETALLE DÍA A DÍA ─────────────────────────────────
    pdf.add_page()
    _titulo_seccion(pdf, "DETALLE DÍA A DÍA")

    if datos_detalle:
        if consolidado:
            cols_det = [
                ("Fecha",       22, "C"),
                ("Sucursal",    50, "L"),
                ("Empleado",    60, "L"),
                ("Novedad",     60, "L"),
                ("Cant.",       18, "C"),
                ("Importe $",   28, "R"),
                ("Observaciones", 32, "L"),
            ]
        else:
            cols_det = [
                ("Fecha",        22, "C"),
                ("Empleado",     75, "L"),
                ("Novedad",      75, "L"),
                ("Cant.",        20, "C"),
                ("Importe $",    30, "R"),
                ("Observaciones", 43, "L"),
            ]
        _encabezado_tabla(pdf, cols_det)
        for i, r in enumerate(datos_detalle):
            fecha_raw = r.get("fecha", "")
            # Formatear fecha de YYYY-MM-DD a DD/MM/YYYY
            try:
                fecha_fmt = date.fromisoformat(str(fecha_raw)).strftime("%d/%m/%Y")
            except Exception:
                fecha_fmt = str(fecha_raw)

            cant = r.get("cantidad")
            imp  = r.get("importe")
            obs  = r.get("observaciones") or ""

            if consolidado:
                vals = [
                    (fecha_fmt,                            22, "C"),
                    (r.get("sucursal_nombre", ""),         50, "L"),
                    (r.get("empleado_nombre_completo", ""),60, "L"),
                    (r.get("tipo_descripcion", ""),        60, "L"),
                    (f"{cant:.1f}" if cant else "",        18, "C"),
                    (f"${imp:,.2f}" if imp else "",        28, "R"),
                    (obs[:28],                             32, "L"),
                ]
            else:
                vals = [
                    (fecha_fmt,                            22, "C"),
                    (r.get("empleado_nombre_completo", ""),75, "L"),
                    (r.get("tipo_descripcion", ""),        75, "L"),
                    (f"{cant:.1f}" if cant else "",        20, "C"),
                    (f"${imp:,.2f}" if imp else "",        30, "R"),
                    (obs[:38],                             43, "L"),
                ]
            _fila_tabla(pdf, vals, i)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 7, "  Sin registros de detalle.", ln=True)
        pdf.set_text_color(0, 0, 0)

    return bytes(pdf.output())
