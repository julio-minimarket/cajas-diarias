"""
modules/novedades_personal/ui_carga.py
========================================
Pantallas de carga diaria de novedades de personal.
"""

import streamlit as st
from datetime import date
from . import queries, services
from .utils import lista_a_opciones_selectbox, novedades_a_dataframe
import auth

_PLACEHOLDER_EMP = "— Seleccionar empleado —"


# ══════════════════════════════════════════════════════════════
# PANTALLA PRINCIPAL DE CARGA
# ══════════════════════════════════════════════════════════════

def pantalla_carga_diaria():
    st.header("📋 Carga Diaria de Novedades")

    # ── Usuario actual (desde auth.py) ───────────────────────
    usuario_nombre = st.session_state.user.get("nombre", "sistema")

    # ── Filtros principales ──────────────────────────────────
    col1, col2 = st.columns([2, 2])

    with col1:
        # Filtra sucursales según rol: encargado ve solo la suya
        todas = queries.get_sucursales_activas()
        sucursales = auth.filtrar_sucursales_disponibles(todas)
        if not sucursales:
            return  # filtrar_sucursales_disponibles ya muestra el error

        opciones_suc = lista_a_opciones_selectbox(sucursales, "id", "nombre")
        sucursal_nombre = st.selectbox("Sucursal", list(opciones_suc.keys()))
        sucursal_id = opciones_suc[sucursal_nombre]

    with col2:
        fecha = st.date_input("Fecha", value=date.today())

    # ── Validar acceso a la sucursal seleccionada ────────────
    if not auth.validar_acceso_sucursal(sucursal_id):
        st.error("No tenés permiso para cargar novedades en esta sucursal.")
        return

    st.caption(f"Usuario: **{usuario_nombre}**")
    st.divider()

    # ── Empleados de la sucursal ─────────────────────────────
    empleados = queries.get_empleados_por_sucursal(sucursal_id)
    if not empleados:
        st.warning("No hay empleados activos en esta sucursal.")
        return

    tipos = queries.get_tipos_novedad()
    opciones_tipo = {t["descripcion"]: t for t in tipos}

    # Novedades ya cargadas hoy — UNA sola query con JOIN (sin N+1)
    novedades_hoy = queries.get_novedades_del_dia(sucursal_id, fecha)
    empleados_con_novedad = {n["empleado_id"] for n in novedades_hoy}

    # Guardar snapshot al cargar la página (no se actualiza al guardar)
    # Así el aviso solo aparece si el empleado YA tenía novedades antes de esta sesión
    key_snapshot = f"snapshot_novedades_{sucursal_id}_{fecha}"
    if key_snapshot not in st.session_state:
        st.session_state[key_snapshot] = set(empleados_con_novedad)
    snapshot_previo = st.session_state[key_snapshot]

    st.subheader(f"Empleados — {sucursal_nombre} — {fecha.strftime('%d/%m/%Y')}")

    # ── Tabla resumen del día ────────────────────────────────
    if novedades_hoy:
        df = novedades_a_dataframe(novedades_hoy)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay novedades cargadas para esta fecha.")

    st.divider()

    # ── Formulario para cargar/editar novedad ────────────────
    st.subheader("➕ Cargar / Editar Novedad")

    opciones_emp = {_PLACEHOLDER_EMP: None} | {
        f"{e['apellido']}, {e['nombre']}": e for e in empleados
    }
    empleado_label = st.selectbox("Empleado", list(opciones_emp.keys()),
                                  key="sel_empleado_carga")

    if empleado_label == _PLACEHOLDER_EMP:
        st.info("Seleccioná un empleado del listado para cargar sus novedades.")
        return

    empleado = opciones_emp[empleado_label]
    ya_tiene = empleado["id"] in empleados_con_novedad

    # Aviso solo si el empleado YA tenía novedades antes de esta sesión
    if empleado["id"] in snapshot_previo:
        st.info("ℹ️ Este empleado ya tiene novedades cargadas hoy. Al guardar se reemplazarán.")

    # ── Filas dinámicas de novedad (una fila + botón agregar) ──
    st.markdown("**Novedades a cargar:**")

    # Inicializar contador de filas en session_state
    key_filas = f"num_filas_novedad_{empleado['id']}"
    if key_filas not in st.session_state:
        st.session_state[key_filas] = 1

    detalles_form = []

    for i in range(st.session_state[key_filas]):
        cols = st.columns([3, 1.5, 1.5, 3])
        tipo_sel = cols[0].selectbox(
            f"Tipo novedad {i+1}" if st.session_state[key_filas] > 1 else "Tipo novedad",
            ["— ninguna —"] + list(opciones_tipo.keys()),
            key=f"tipo_{empleado['id']}_{i}"
        )
        if tipo_sel == "— ninguna —":
            cols[1].empty()
            cols[2].empty()
            cols[3].empty()
            continue

        tipo_data = opciones_tipo[tipo_sel]
        cantidad = None
        importe  = None

        if tipo_data["requiere_cantidad"]:
            cantidad = cols[1].number_input("Cantidad (hs)", min_value=0.0, step=0.5,
                                            key=f"cant_{empleado['id']}_{i}")
        else:
            cols[1].empty()

        if tipo_data["requiere_importe"]:
            importe = cols[2].number_input("Importe $", min_value=0.0, step=100.0,
                                           key=f"imp_{empleado['id']}_{i}")
        else:
            cols[2].empty()

        observaciones = cols[3].text_input("Observaciones", key=f"obs_{empleado['id']}_{i}")

        detalles_form.append({
            "tipo_novedad_id": tipo_data["id"],
            "cantidad":        cantidad,
            "importe":         importe,
            "observaciones":   observaciones,
        })

    # Botón para agregar más filas (máximo 5)
    if st.session_state[key_filas] < 5:
        if st.button("➕ Agregar otra novedad", key=f"add_fila_{empleado['id']}"):
            st.session_state[key_filas] += 1
            st.rerun()

    # ── Botones de acción ────────────────────────────────────
    col_guardar, col_eliminar, _ = st.columns([2, 2, 4])

    with col_guardar:
        if st.button("💾 Guardar Novedades", type="primary", use_container_width=True):
            _guardar(empleado, sucursal_id, fecha, usuario_nombre, detalles_form)

    with col_eliminar:
        if ya_tiene:
            if st.button("🗑️ Eliminar Novedades del Día", use_container_width=True):
                _eliminar(empleado, fecha)


def _guardar(empleado, sucursal_id, fecha, usuario, detalles):
    try:
        resultado = services.guardar_novedades_empleado(
            empleado_id=empleado["id"],
            sucursal_id=sucursal_id,
            fecha=fecha,
            usuario_carga=usuario,
            detalles=detalles,
        )
        st.success(f"✅ Novedades guardadas correctamente (ID: {resultado['novedad_id']})")
        # Resetear contador de filas y snapshot
        for k in list(st.session_state.keys()):
            if k.startswith("num_filas_novedad_") or k.startswith("snapshot_novedades_"):
                del st.session_state[k]
        st.session_state["sel_empleado_carga"] = _PLACEHOLDER_EMP
        st.rerun()
    except services.NovedadError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ Error inesperado: {e}")


def _eliminar(empleado, fecha):
    try:
        services.eliminar_novedad_empleado_fecha(empleado["id"], fecha)
        st.success("🗑️ Novedades eliminadas.")
        for k in list(st.session_state.keys()):
            if k.startswith("num_filas_novedad_") or k.startswith("snapshot_novedades_"):
                del st.session_state[k]
        st.session_state["sel_empleado_carga"] = _PLACEHOLDER_EMP
        st.rerun()
    except services.NovedadError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ Error inesperado: {e}")


# ══════════════════════════════════════════════════════════════
# HISTORIAL POR EMPLEADO
# ══════════════════════════════════════════════════════════════

def pantalla_historial_empleado():
    st.header("🔍 Historial por Empleado")

    col1, col2, col3 = st.columns(3)

    todas = queries.get_sucursales_activas()
    sucursales = auth.filtrar_sucursales_disponibles(todas)
    if not sucursales:
        return

    opciones_suc = lista_a_opciones_selectbox(sucursales, "id", "nombre")

    with col1:
        sucursal_nombre = st.selectbox("Sucursal", list(opciones_suc.keys()))
        sucursal_id = opciones_suc[sucursal_nombre]

    with col2:
        fecha_desde = st.date_input("Desde", value=date.today().replace(day=1))

    with col3:
        fecha_hasta = st.date_input("Hasta", value=date.today())

    empleados = queries.get_empleados_por_sucursal(sucursal_id)
    if not empleados:
        st.warning("No hay empleados activos en esta sucursal.")
        return

    opciones_emp = {f"{e['apellido']}, {e['nombre']}": e["id"] for e in empleados}
    empleado_label = st.selectbox("Empleado", list(opciones_emp.keys()))
    empleado_id = opciones_emp[empleado_label]

    if st.button("🔎 Buscar", type="primary"):
        datos = services.obtener_novedades_por_empleado(empleado_id, fecha_desde, fecha_hasta)
        if datos:
            df = novedades_a_dataframe(datos)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Total de registros: {len(df)}")
        else:
            st.info("No hay novedades en el período seleccionado.")
