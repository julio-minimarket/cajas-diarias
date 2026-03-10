"""
modules/novedades_personal/main.py
====================================
Punto de entrada del módulo de Novedades de Personal.
Se llama desde el app.py principal del sistema Cajas Diarias.

─────────────────────────────────────────────────────────
CÓMO INTEGRARLO AL SISTEMA EXISTENTE:
─────────────────────────────────────────────────────────

En tu app.py principal, agregá en el menú:

    from modules.novedades_personal.main import render_modulo_novedades

    # En el sidebar donde tenés las opciones del menú:
    opciones = [
        "Cajas Diarias",
        "Novedades de Personal",   # ← agregar esta línea
        # ... otras opciones
    ]
    modulo = st.sidebar.radio("Módulo", opciones)

    if modulo == "Novedades de Personal":
        render_modulo_novedades()
─────────────────────────────────────────────────────────
"""

import streamlit as st
from .ui_carga import (
    pantalla_carga_diaria,
    pantalla_historial_empleado,
)
from .ui_reportes import (
    pantalla_novedades_sucursal,
    pantalla_prelistado_mensual,
    pantalla_informe_mensual,
    pantalla_administracion,
    pantalla_reporte_pdf,
)


def render_modulo_novedades():
    """
    Función principal del módulo.
    Renderiza el submenú y la pantalla correspondiente.
    Llamar desde el app.py del sistema principal.
    """

    # ── Submenú lateral del módulo ───────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 👥 Novedades de Personal")

    opciones = {
        "📋 Carga Diaria":          pantalla_carga_diaria,
        "🔍 Historial por Empleado": pantalla_historial_empleado,
        "🏢 Por Sucursal":           pantalla_novedades_sucursal,
        "📑 Prelistado Mensual":     pantalla_prelistado_mensual,
        "📊 Informe Mensual":        pantalla_informe_mensual,
        "📄 Reporte PDF":            pantalla_reporte_pdf,
        "⚙️ Administración":         pantalla_administracion,
    }

    pantalla_seleccionada = st.sidebar.radio(
        "Pantalla",
        list(opciones.keys()),
        label_visibility="collapsed",
    )

    # ── Renderizar pantalla elegida ──────────────────────────
    opciones[pantalla_seleccionada]()
