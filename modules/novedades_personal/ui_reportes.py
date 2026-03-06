"""
modules/novedades_personal/ui_reportes.py
==========================================
Pantallas de reportes, prelistado mensual y confirmación.
"""

import streamlit as st
from datetime import date
import pandas as pd
from . import queries, services
from .utils import (
    lista_a_opciones_selectbox,
    novedades_a_dataframe,
    resumen_a_dataframe,
    nombre_mes,
    fecha_a_periodo,
)
import auth


# ══════════════════════════════════════════════════════════════
# NOVEDADES POR SUCURSAL
# ══════════════════════════════════════════════════════════════

def pantalla_novedades_sucursal():
    st.header("🏢 Novedades por Sucursal")

    todas = queries.get_sucursales_activas()
    sucursales = auth.filtrar_sucursales_disponibles(todas)
    if not sucursales:
        return

    opciones_suc = lista_a_opciones_selectbox(sucursales, "id", "nombre")

    col1, col2, col3 = st.columns(3)
    with col1:
        sucursal_nombre = st.selectbox("Sucursal", list(opciones_suc.keys()))
        sucursal_id = opciones_suc[sucursal_nombre]
    with col2:
        fecha_desde = st.date_input("Desde", value=date.today().replace(day=1))
    with col3:
        fecha_hasta = st.date_input("Hasta", value=date.today())

    if st.button("📊 Ver Novedades", type="primary"):
        datos = services.obtener_novedades_por_sucursal(sucursal_id, fecha_desde, fecha_hasta)

        if not datos:
            st.info("No hay novedades en el período seleccionado.")
            return

        df = novedades_a_dataframe(datos)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        df_raw = pd.DataFrame(datos)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total registros", len(df))
        if "cantidad" in df_raw.columns:
            col_b.metric("Total horas extras", f"{df_raw['cantidad'].sum():.1f} hs")
        if "importe" in df_raw.columns:
            col_c.metric("Total adicionales", f"${df_raw['importe'].sum():,.2f}")


# ══════════════════════════════════════════════════════════════
# PRELISTADO MENSUAL
# ══════════════════════════════════════════════════════════════

def pantalla_prelistado_mensual():
    st.header("📑 Prelistado Mensual")

    todas = queries.get_sucursales_activas()
    sucursales = auth.filtrar_sucursales_disponibles(todas)
    if not sucursales:
        return

    opciones_suc = lista_a_opciones_selectbox(sucursales, "id", "nombre")

    col1, col2 = st.columns(2)
    with col1:
        sucursal_nombre = st.selectbox("Sucursal", list(opciones_suc.keys()))
        sucursal_id = opciones_suc[sucursal_nombre]
    with col2:
        hoy = date.today()
        periodos = []
        for i in range(12):
            anio, mes = hoy.year, hoy.month - i
            while mes <= 0:
                mes += 12
                anio -= 1
            periodos.append(f"{anio}-{mes:02d}")
        periodo = st.selectbox("Período", periodos, format_func=nombre_mes)

    if st.button("📋 Generar Prelistado", type="primary"):
        datos = services.generar_prelistado_mensual(sucursal_id, periodo)

        if not datos:
            st.info(f"No hay novedades para {nombre_mes(periodo)} en {sucursal_nombre}.")
            return

        df = resumen_a_dataframe(datos)
        st.subheader(f"Prelistado — {sucursal_nombre} — {nombre_mes(periodo)}")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Resumen por tipo
        st.divider()
        st.subheader("Resumen por tipo de novedad")
        df_raw = pd.DataFrame(datos)
        resumen = (
            df_raw.groupby(["categoria", "tipo_novedad"])
            .agg(
                Registros=("cantidad_registros", "sum"),
                Total_Cantidad=("total_cantidad", "sum"),
                Total_Importe=("total_importe", "sum"),
            )
            .reset_index()
            .rename(columns={"categoria": "Categoría", "tipo_novedad": "Novedad"})
        )
        st.dataframe(resumen, use_container_width=True, hide_index=True)

        # ── Confirmación (solo admin/gerente) ────────────────
        if auth.is_admin() or auth.is_gerente():
            st.divider()
            st.subheader("✅ Confirmación Mensual")

            confirmados = df_raw["todo_confirmado"].all() if "todo_confirmado" in df_raw.columns else False

            if confirmados:
                st.success(f"✅ Las novedades de {nombre_mes(periodo)} ya están CONFIRMADAS.")
            else:
                st.warning(
                    "⚠️ Al confirmar, las novedades quedan bloqueadas y no podrán modificarse. "
                    "Asegurate de haber revisado el prelistado."
                )
                if st.button("🔒 CONFIRMAR NOVEDADES DEL MES", type="primary"):
                    _confirmar_mes(sucursal_id, periodo,
                                   st.session_state.user.get("nombre", "sistema"))
        else:
            st.info("La confirmación mensual es realizada por el administrador o gerente.")


def _confirmar_mes(sucursal_id, periodo, usuario):
    try:
        resultado = services.confirmar_novedades_mes(sucursal_id, periodo, usuario)
        if resultado["confirmadas"] == 0:
            st.info(resultado.get("mensaje", "No había novedades pendientes."))
        else:
            st.success(
                f"✅ {resultado['confirmadas']} novedades confirmadas "
                f"para {nombre_mes(periodo)}."
            )
            st.rerun()
    except Exception as e:
        st.error(f"❌ Error al confirmar: {e}")


# ══════════════════════════════════════════════════════════════
# INFORME MENSUAL FINAL
# ══════════════════════════════════════════════════════════════

def pantalla_informe_mensual():
    st.header("📊 Informe Mensual Final")

    todas = queries.get_sucursales_activas()
    sucursales = auth.filtrar_sucursales_disponibles(todas)
    if not sucursales:
        return

    # Admin/gerente puede ver todas las sucursales juntas
    if auth.is_admin() or auth.is_gerente():
        opciones_suc = {"TODAS LAS SUCURSALES": None,
                        **{s["nombre"]: s["id"] for s in sucursales}}
    else:
        opciones_suc = {s["nombre"]: s["id"] for s in sucursales}

    col1, col2 = st.columns(2)
    with col1:
        sucursal_nombre = st.selectbox("Sucursal", list(opciones_suc.keys()))
        sucursal_id = opciones_suc[sucursal_nombre]
    with col2:
        hoy = date.today()
        periodos = []
        for i in range(12):
            anio, mes = hoy.year, hoy.month - i
            while mes <= 0:
                mes += 12
                anio -= 1
            periodos.append(f"{anio}-{mes:02d}")
        periodo = st.selectbox("Período", periodos, format_func=nombre_mes)

    if st.button("📈 Generar Informe", type="primary"):
        _generar_informe(sucursal_id, sucursal_nombre, periodo, todas)


def _generar_informe(sucursal_id, sucursal_nombre, periodo, todas_sucursales):
    if sucursal_id is not None:
        datos = services.generar_prelistado_mensual(sucursal_id, periodo)
    else:
        datos = []
        for suc in todas_sucursales:
            datos.extend(services.generar_prelistado_mensual(suc["id"], periodo))

    if not datos:
        st.info("No hay datos para el período seleccionado.")
        return

    df = pd.DataFrame(datos)
    st.subheader(f"Informe — {sucursal_nombre} — {nombre_mes(periodo)}")

    ausencias   = df[df["categoria"] == "AUSENCIA"]   if "categoria" in df.columns else pd.DataFrame()
    adicionales = df[df["categoria"] == "ADICIONAL"]  if "categoria" in df.columns else pd.DataFrame()

    st.markdown("#### 🔴 Ausencias")
    if not ausencias.empty:
        tabla = (
            ausencias.groupby(["sucursal_nombre", "empleado_nombre_completo", "tipo_novedad"])
            .agg(Días=("cantidad_registros", "sum"))
            .reset_index()
            .rename(columns={"sucursal_nombre": "Sucursal",
                             "empleado_nombre_completo": "Empleado",
                             "tipo_novedad": "Tipo"})
        )
        st.dataframe(tabla, use_container_width=True, hide_index=True)
    else:
        st.info("Sin ausencias.")

    st.markdown("#### 🟢 Adicionales")
    if not adicionales.empty:
        tabla = (
            adicionales.groupby(["sucursal_nombre", "empleado_nombre_completo", "tipo_novedad"])
            .agg(Cantidad=("total_cantidad", "sum"), Importe=("total_importe", "sum"))
            .reset_index()
            .rename(columns={"sucursal_nombre": "Sucursal",
                             "empleado_nombre_completo": "Empleado",
                             "tipo_novedad": "Tipo"})
        )
        tabla["Importe"] = tabla["Importe"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(tabla, use_container_width=True, hide_index=True)
    else:
        st.info("Sin adicionales.")

    st.divider()
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Empleados con novedades",
                 df["empleado_id"].nunique() if "empleado_id" in df.columns else 0)
    col_b.metric("Total ausencias",
                 int(ausencias["cantidad_registros"].sum()) if not ausencias.empty else 0)
    col_c.metric("Total horas extras",
                 f"{adicionales['total_cantidad'].sum():.1f} hs" if not adicionales.empty else "0 hs")
    col_d.metric("Total adicionales $",
                 f"${adicionales['total_importe'].sum():,.2f}" if not adicionales.empty else "$0")


# ══════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE CIERRE MENSUAL (solo admin)
# ══════════════════════════════════════════════════════════════

def pantalla_administracion():
    st.header("⚙️ Administración de Período")

    if not auth.is_admin():
        st.error("Esta sección es solo para administradores.")
        return

    cierre_actual = queries.get_configuracion("fecha_cierre_novedades")

    if cierre_actual:
        st.warning(f"🔒 Período cerrado: **{nombre_mes(cierre_actual)}**. "
                   "No se pueden cargar novedades para ese período o anteriores.")
    else:
        st.success("✅ No hay cierre activo. Todos los períodos están abiertos.")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cerrar período")
        periodo_cierre = st.text_input(
            "Período a cerrar (YYYY-MM)",
            value=fecha_a_periodo(date.today().replace(day=1)),
        )
        if st.button("🔒 Cerrar Período", type="primary"):
            services.cerrar_periodo(periodo_cierre)
            st.success(f"✅ Período {nombre_mes(periodo_cierre)} cerrado.")
            st.rerun()

    with col2:
        st.subheader("Reabrir período")
        st.info("Elimina el cierre activo, permitiendo cargar novedades en todos los períodos.")
        if st.button("🔓 Reabrir", type="secondary"):
            services.reabrir_periodo()
            st.success("✅ Cierre eliminado.")
            st.rerun()
