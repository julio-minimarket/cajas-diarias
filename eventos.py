# eventos.py - Módulo de Gestión de Eventos con Artistas
#
# 🎭 FUNCIONALIDADES:
# - Carga de eventos (solo admins)
# - Listado y edición de eventos
# - Análisis de impacto en ventas con 3 comparaciones:
#   1. Día del evento vs promedio del mes (excluyendo eventos)
#   2. Día del evento vs mismo día de semana del mes
#   3. Día del evento vs mismo "número de día de semana" del mes anterior
#      (ej: primer viernes de diciembre vs primer viernes de noviembre)
#

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from supabase import create_client, Client
import os
from functools import wraps
import calendar

# ==================== CONFIGURACIÓN ====================

@st.cache_resource
def init_supabase():
    """Inicializa conexión a Supabase"""
    if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        st.error("⚠️ Falta configurar credenciales de Supabase")
        st.stop()
    
    return create_client(url, key)

supabase: Client = init_supabase()

# ==================== FUNCIONES AUXILIARES ====================

def obtener_numero_dia_semana_mes(fecha):
    """
    Calcula qué número de día de semana es dentro del mes.
    
    Ejemplos:
    - 6 de diciembre (viernes) → 1 (primer viernes)
    - 13 de diciembre (viernes) → 2 (segundo viernes)
    - 20 de diciembre (viernes) → 3 (tercer viernes)
    
    Args:
        fecha: date object
    
    Returns:
        int: Número del día de semana (1-5)
    """
    dia_del_mes = fecha.day
    return (dia_del_mes - 1) // 7 + 1

def obtener_mismo_dia_semana_mes_anterior(fecha):
    """
    Encuentra el mismo "número de día de semana" del mes anterior.
    
    Ejemplo:
    - Input: 6 de diciembre 2024 (primer viernes)
    - Output: 1 de noviembre 2024 (primer viernes)
    
    Args:
        fecha: date object
    
    Returns:
        date: Fecha correspondiente del mes anterior, o None si no existe
    """
    # Obtener el día de la semana (0=lunes, 6=domingo)
    dia_semana = fecha.weekday()
    
    # Número del día de semana en el mes (1=primero, 2=segundo, etc.)
    numero_dia = obtener_numero_dia_semana_mes(fecha)
    
    # Calcular mes anterior
    if fecha.month == 1:
        mes_anterior = 12
        anio_anterior = fecha.year - 1
    else:
        mes_anterior = fecha.month - 1
        anio_anterior = fecha.year
    
    # Encontrar el mismo día de semana del mes anterior
    # Primer día del mes anterior
    primer_dia = date(anio_anterior, mes_anterior, 1)
    
    # Encontrar el primer día de la semana objetivo
    dias_hasta_dia_semana = (dia_semana - primer_dia.weekday()) % 7
    primer_ocurrencia = primer_dia + timedelta(days=dias_hasta_dia_semana)
    
    # Calcular la fecha objetivo (agregar semanas según el número)
    fecha_objetivo = primer_ocurrencia + timedelta(weeks=numero_dia - 1)
    
    # Verificar que la fecha esté dentro del mes
    if fecha_objetivo.month == mes_anterior:
        return fecha_objetivo
    else:
        return None

def formatear_moneda(valor):
    """Formatea un valor numérico como moneda argentina"""
    if valor is None:
        return "$0"
    return f"${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatear_porcentaje(valor):
    """Formatea un valor como porcentaje con signo"""
    if valor is None:
        return "0%"
    signo = "+" if valor > 0 else ""
    return f"{signo}{valor:.1f}%"

# ==================== FUNCIONES DE DATOS ====================

@st.cache_data(ttl=30)
def obtener_sucursales():
    """Obtiene sucursales activas"""
    result = supabase.table("sucursales")\
        .select("id, nombre, codigo")\
        .eq("activa", True)\
        .order("nombre")\
        .execute()
    return result.data

@st.cache_data(ttl=30)
def obtener_eventos(sucursal_id=None, fecha_desde=None, fecha_hasta=None):
    """
    Obtiene eventos con filtros opcionales
    
    Args:
        sucursal_id: Filtrar por sucursal
        fecha_desde: Fecha inicio
        fecha_hasta: Fecha fin
    """
    query = supabase.table("eventos")\
        .select("*, sucursales(nombre, codigo)")
    
    if sucursal_id:
        query = query.eq("sucursal_id", sucursal_id)
    if fecha_desde:
        query = query.gte("fecha_evento", str(fecha_desde))
    if fecha_hasta:
        query = query.lte("fecha_evento", str(fecha_hasta))
    
    result = query.order("fecha_evento", desc=True).execute()
    return result.data

@st.cache_data(ttl=30)
def obtener_ventas_dia(sucursal_id, fecha):
    """
    Obtiene el total de ventas de una sucursal en una fecha específica
    
    Returns:
        dict con total_ventas y cantidad_tickets
    """
    # Obtener movimientos del día
    movimientos = supabase.table("movimientos_diarios")\
        .select("monto, categoria_id, categorias(tipo)")\
        .eq("sucursal_id", sucursal_id)\
        .eq("fecha", str(fecha))\
        .execute()
    
    # Calcular total de ventas (solo categorías de tipo 'venta')
    total_ventas = sum(
        m['monto'] for m in movimientos.data 
        if m.get('categorias') and m['categorias'].get('tipo') == 'venta'
    )
    
    # Obtener tickets del CRM
    crm = supabase.table("crm_datos_diarios")\
        .select("cantidad_tickets")\
        .eq("sucursal_id", sucursal_id)\
        .eq("fecha", str(fecha))\
        .execute()
    
    cantidad_tickets = crm.data[0]['cantidad_tickets'] if crm.data else 0
    
    return {
        'total_ventas': total_ventas,
        'cantidad_tickets': cantidad_tickets,
        'ticket_promedio': total_ventas / cantidad_tickets if cantidad_tickets > 0 else 0
    }

@st.cache_data(ttl=60)
def obtener_fechas_con_eventos(sucursal_id, fecha_desde, fecha_hasta):
    """
    Obtiene lista de fechas que tienen eventos en una sucursal
    
    Returns:
        list de fechas
    """
    eventos = supabase.table("eventos")\
        .select("fecha_evento")\
        .eq("sucursal_id", sucursal_id)\
        .gte("fecha_evento", str(fecha_desde))\
        .lte("fecha_evento", str(fecha_hasta))\
        .execute()
    
    return [datetime.strptime(e['fecha_evento'], '%Y-%m-%d').date() for e in eventos.data]

@st.cache_data(ttl=60)
def calcular_promedio_mes_sin_eventos(sucursal_id, fecha_referencia):
    """
    Calcula el promedio de ventas del mes excluyendo días con eventos
    
    Args:
        sucursal_id: ID de la sucursal
        fecha_referencia: Fecha del evento a analizar
    
    Returns:
        dict con promedio_ventas, promedio_tickets, promedio_ticket_promedio
    """
    # Primer y último día del mes
    primer_dia = fecha_referencia.replace(day=1)
    if fecha_referencia.month == 12:
        ultimo_dia = date(fecha_referencia.year + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo_dia = date(fecha_referencia.year, fecha_referencia.month + 1, 1) - timedelta(days=1)
    
    # Obtener fechas con eventos en el mes
    fechas_eventos = obtener_fechas_con_eventos(sucursal_id, primer_dia, ultimo_dia)
    
    # Obtener todos los movimientos del mes
    movimientos = supabase.table("movimientos_diarios")\
        .select("fecha, monto, categoria_id, categorias(tipo)")\
        .eq("sucursal_id", sucursal_id)\
        .gte("fecha", str(primer_dia))\
        .lte("fecha", str(ultimo_dia))\
        .execute()
    
    # Obtener datos CRM del mes
    crm_datos = supabase.table("crm_datos_diarios")\
        .select("fecha, cantidad_tickets")\
        .eq("sucursal_id", sucursal_id)\
        .gte("fecha", str(primer_dia))\
        .lte("fecha", str(ultimo_dia))\
        .execute()
    
    # Agrupar ventas por día (excluyendo días con eventos)
    ventas_por_dia = {}
    for m in movimientos.data:
        fecha_mov = datetime.strptime(m['fecha'], '%Y-%m-%d').date()
        if fecha_mov not in fechas_eventos:  # Excluir días con eventos
            if m.get('categorias') and m['categorias'].get('tipo') == 'venta':
                if fecha_mov not in ventas_por_dia:
                    ventas_por_dia[fecha_mov] = 0
                ventas_por_dia[fecha_mov] += m['monto']
    
    # Agrupar tickets por día
    tickets_por_dia = {}
    for crm in crm_datos.data:
        fecha_crm = datetime.strptime(crm['fecha'], '%Y-%m-%d').date()
        if fecha_crm not in fechas_eventos:  # Excluir días con eventos
            tickets_por_dia[fecha_crm] = crm['cantidad_tickets']
    
    # Calcular promedios
    if ventas_por_dia:
        promedio_ventas = sum(ventas_por_dia.values()) / len(ventas_por_dia)
    else:
        promedio_ventas = 0
    
    if tickets_por_dia:
        promedio_tickets = sum(tickets_por_dia.values()) / len(tickets_por_dia)
    else:
        promedio_tickets = 0
    
    promedio_ticket_promedio = promedio_ventas / promedio_tickets if promedio_tickets > 0 else 0
    
    return {
        'promedio_ventas': promedio_ventas,
        'promedio_tickets': promedio_tickets,
        'promedio_ticket_promedio': promedio_ticket_promedio,
        'dias_considerados': len(ventas_por_dia)
    }

@st.cache_data(ttl=60)
def calcular_promedio_mismo_dia_semana_mes(sucursal_id, fecha_referencia):
    """
    Calcula el promedio de ventas del mismo día de semana en el mes
    (ej: todos los viernes del mes)
    
    Args:
        sucursal_id: ID de la sucursal
        fecha_referencia: Fecha del evento
    
    Returns:
        dict con promedios
    """
    dia_semana = fecha_referencia.weekday()  # 0=lunes, 6=domingo
    
    # Primer y último día del mes
    primer_dia = fecha_referencia.replace(day=1)
    if fecha_referencia.month == 12:
        ultimo_dia = date(fecha_referencia.year + 1, 1, 1) - timedelta(days=1)
    else:
        ultimo_dia = date(fecha_referencia.year, fecha_referencia.month + 1, 1) - timedelta(days=1)
    
    # Encontrar todos los días de la misma semana en el mes (excluyendo la fecha del evento)
    fechas_mismo_dia = []
    fecha_actual = primer_dia
    while fecha_actual <= ultimo_dia:
        if fecha_actual.weekday() == dia_semana and fecha_actual != fecha_referencia:
            fechas_mismo_dia.append(fecha_actual)
        fecha_actual += timedelta(days=1)
    
    if not fechas_mismo_dia:
        return {
            'promedio_ventas': 0,
            'promedio_tickets': 0,
            'promedio_ticket_promedio': 0,
            'dias_considerados': 0
        }
    
    # Obtener ventas de esos días
    ventas_totales = 0
    tickets_totales = 0
    
    for fecha in fechas_mismo_dia:
        datos = obtener_ventas_dia(sucursal_id, fecha)
        ventas_totales += datos['total_ventas']
        tickets_totales += datos['cantidad_tickets']
    
    dias_considerados = len(fechas_mismo_dia)
    promedio_ventas = ventas_totales / dias_considerados
    promedio_tickets = tickets_totales / dias_considerados
    promedio_ticket_promedio = promedio_ventas / promedio_tickets if promedio_tickets > 0 else 0
    
    return {
        'promedio_ventas': promedio_ventas,
        'promedio_tickets': promedio_tickets,
        'promedio_ticket_promedio': promedio_ticket_promedio,
        'dias_considerados': dias_considerados,
        'fechas_consideradas': fechas_mismo_dia
    }

# ==================== INTERFAZ DE USUARIO ====================

def mostrar_formulario_carga():
    """Muestra formulario para cargar un nuevo evento"""
    st.subheader("📝 Cargar Nuevo Evento")
    
    sucursales = obtener_sucursales()
    if not sucursales:
        st.error("⚠️ No hay sucursales disponibles")
        return
    
    with st.form("form_nuevo_evento"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Selector de sucursal
            sucursal_opciones = {f"{s['nombre']} ({s['codigo']})": s['id'] for s in sucursales}
            sucursal_seleccionada = st.selectbox(
                "🏪 Sucursal del Evento *",
                options=list(sucursal_opciones.keys())
            )
            sucursal_id = sucursal_opciones[sucursal_seleccionada]
            
            # Fecha del evento
            fecha_evento = st.date_input(
                "📅 Fecha del Evento *",
                value=date.today(),
                min_value=date(2020, 1, 1)
            )
            
            # Artista
            artista = st.text_input(
                "🎤 Artista / Banda *",
                max_chars=200,
                placeholder="Ej: Los Palmeras"
            )
        
        with col2:
            # Cachet del artista
            cachet = st.number_input(
                "💰 Cachet del Artista *",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                format="%.2f",
                help="Monto pagado al artista"
            )
            
            # Contratación de sonido
            sonido = st.number_input(
                "🔊 Contratación de Sonido",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                format="%.2f",
                help="Monto pagado por sonido (opcional)"
            )
            
            # Costo total calculado
            costo_total = cachet + sonido
            st.info(f"**Costo Total:** {formatear_moneda(costo_total)}")
        
        # Botón de submit
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
        with col_btn1:
            submitted = st.form_submit_button("💾 Guardar Evento", width="stretch")
        with col_btn2:
            cancelar = st.form_submit_button("❌ Cancelar", width="stretch")
        
        if cancelar:
            st.rerun()
        
        if submitted:
            # Validaciones
            if not artista or artista.strip() == "":
                st.error("⚠️ El nombre del artista es obligatorio")
                return
            
            if cachet <= 0:
                st.error("⚠️ El cachet debe ser mayor a cero")
                return
            
            try:
                # Insertar en la base de datos
                nuevo_evento = {
                    'sucursal_id': sucursal_id,
                    'fecha_evento': str(fecha_evento),
                    'artista': artista.strip(),
                    'cachet_artista': cachet,
                    'contratacion_sonido': sonido,
                    'created_by': st.session_state.user['id']
                }
                
                result = supabase.table("eventos").insert(nuevo_evento).execute()
                
                if result.data:
                    st.success(f"✅ Evento '{artista}' guardado exitosamente")
                    st.cache_data.clear()  # Limpiar caché
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ Error al guardar el evento")
            
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

def mostrar_listado_eventos():
    """Muestra listado de eventos con filtros"""
    st.subheader("📋 Listado de Eventos")
    
    # Filtros
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        sucursales = obtener_sucursales()
        sucursal_filter = st.selectbox(
            "Filtrar por Sucursal",
            options=["Todas"] + [f"{s['nombre']}" for s in sucursales],
            key="filter_sucursal_listado"
        )
    
    with col2:
        fecha_desde = st.date_input(
            "Desde",
            value=date.today().replace(day=1),
            key="filter_desde_listado"
        )
    
    with col3:
        fecha_hasta = st.date_input(
            "Hasta",
            value=date.today(),
            key="filter_hasta_listado"
        )
    
    with col4:
        st.write("")  # Espaciador
        if st.button("🔄 Actualizar", key="btn_actualizar_listado"):
            st.cache_data.clear()
            st.rerun()
    
    # Obtener eventos
    sucursal_id = None
    if sucursal_filter != "Todas":
        sucursal_id = next(s['id'] for s in sucursales if s['nombre'] == sucursal_filter)
    
    eventos = obtener_eventos(sucursal_id, fecha_desde, fecha_hasta)
    
    if not eventos:
        st.info("ℹ️ No hay eventos registrados en el período seleccionado")
        return
    
    # Mostrar en tabla
    df_eventos = pd.DataFrame(eventos)
    
    # Formatear datos
    df_display = pd.DataFrame({
        'Fecha': pd.to_datetime(df_eventos['fecha_evento']).dt.strftime('%d/%m/%Y'),
        'Sucursal': df_eventos['sucursales'].apply(lambda x: x['nombre']),
        'Artista': df_eventos['artista'],
        'Cachet': df_eventos['cachet_artista'].apply(formatear_moneda),
        'Sonido': df_eventos['contratacion_sonido'].apply(formatear_moneda),
        'Costo Total': (df_eventos['cachet_artista'] + df_eventos['contratacion_sonido']).apply(formatear_moneda)
    })
    
    st.dataframe(df_display, width="stretch", hide_index=True)
    
    # Totales
    total_cachets = df_eventos['cachet_artista'].sum()
    total_sonido = df_eventos['contratacion_sonido'].sum()
    total_general = total_cachets + total_sonido
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cantidad de Eventos", len(eventos))
    col2.metric("Total Cachets", formatear_moneda(total_cachets))
    col3.metric("Total Sonido", formatear_moneda(total_sonido))
    col4.metric("Costo Total", formatear_moneda(total_general))

def mostrar_analisis_impacto():
    """Muestra análisis de impacto de eventos en ventas"""
    st.subheader("📊 Análisis de Impacto en Ventas")
    
    st.info("""
    **Este análisis compara las ventas del día del evento con:**
    
    1. **Promedio del mes sin eventos** - Para ver el impacto real excluyendo otros eventos
    2. **Promedio del mismo día de semana** - Comparar viernes con viernes del mismo mes
    3. **Mismo día de semana del mes anterior** - Primer viernes vs primer viernes del mes anterior
    """)
    
    # Obtener eventos recientes
    eventos_recientes = obtener_eventos(
        fecha_desde=date.today() - timedelta(days=90),
        fecha_hasta=date.today()
    )
    
    if not eventos_recientes:
        st.warning("⚠️ No hay eventos recientes para analizar")
        return
    
    # Crear opciones para selectbox
    opciones_eventos = {}
    for e in eventos_recientes:
        fecha = datetime.strptime(e['fecha_evento'], '%Y-%m-%d').date()
        label = f"{fecha.strftime('%d/%m/%Y')} - {e['artista']} ({e['sucursales']['nombre']})"
        opciones_eventos[label] = e
    
    # Selector y botón en columnas
    col1, col2 = st.columns([3, 1])
    
    with col1:
        evento_seleccionado_label = st.selectbox(
            "Seleccionar Evento a Analizar",
            options=list(opciones_eventos.keys())
        )
    
    with col2:
        st.write("")  # Espaciador
        analizar_button = st.button("📈 Generar Análisis", type="primary", width="stretch")
    
    # Mostrar análisis FUERA de las columnas (usa todo el ancho)
    if analizar_button:
        evento = opciones_eventos[evento_seleccionado_label]
        generar_analisis_detallado(evento)

def generar_analisis_detallado(evento):
    """
    Genera el análisis detallado de impacto de un evento
    
    Args:
        evento: dict con datos del evento
    """
    fecha_evento = datetime.strptime(evento['fecha_evento'], '%Y-%m-%d').date()
    sucursal_id = evento['sucursal_id']
    sucursal_nombre = evento['sucursales']['nombre']
    artista = evento['artista']
    costo_total = evento['cachet_artista'] + evento['contratacion_sonido']
    
    # Título del análisis
    st.markdown("---")
    st.markdown(f"### 🎭 Análisis: {artista}")
    st.markdown(f"**📍 Sucursal:** {sucursal_nombre}")
    st.markdown(f"**📅 Fecha:** {fecha_evento.strftime('%d/%m/%Y')} ({['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][fecha_evento.weekday()]})")
    st.markdown(f"**💰 Costo Total:** {formatear_moneda(costo_total)}")
    st.markdown("---")
    
    # Obtener datos del día del evento
    with st.spinner("Obteniendo datos del día del evento..."):
        datos_evento = obtener_ventas_dia(sucursal_id, fecha_evento)
    
    # COMPARACIÓN 1: Promedio del mes sin eventos
    st.markdown("#### 1️⃣ Comparación vs Promedio del Mes (sin eventos)")
    with st.spinner("Calculando promedio del mes..."):
        promedio_mes = calcular_promedio_mes_sin_eventos(sucursal_id, fecha_evento)
    
    col1, col2, col3 = st.columns(3)
    
    # Ventas
    diff_ventas_pct = ((datos_evento['total_ventas'] - promedio_mes['promedio_ventas']) / promedio_mes['promedio_ventas'] * 100) if promedio_mes['promedio_ventas'] > 0 else 0
    col1.metric(
        "Ventas del Evento",
        formatear_moneda(datos_evento['total_ventas']),
        delta=formatear_porcentaje(diff_ventas_pct),
        delta_color="normal"
    )
    col1.caption(f"Promedio mes: {formatear_moneda(promedio_mes['promedio_ventas'])}")
    col1.caption(f"(Basado en {promedio_mes['dias_considerados']} días)")
    
    # Tickets
    diff_tickets_pct = ((datos_evento['cantidad_tickets'] - promedio_mes['promedio_tickets']) / promedio_mes['promedio_tickets'] * 100) if promedio_mes['promedio_tickets'] > 0 else 0
    col2.metric(
        "Tickets del Evento",
        f"{datos_evento['cantidad_tickets']:.0f}",
        delta=formatear_porcentaje(diff_tickets_pct),
        delta_color="normal"
    )
    col2.caption(f"Promedio mes: {promedio_mes['promedio_tickets']:.0f}")
    
    # Ticket Promedio
    diff_tp_pct = ((datos_evento['ticket_promedio'] - promedio_mes['promedio_ticket_promedio']) / promedio_mes['promedio_ticket_promedio'] * 100) if promedio_mes['promedio_ticket_promedio'] > 0 else 0
    col3.metric(
        "Ticket Promedio",
        formatear_moneda(datos_evento['ticket_promedio']),
        delta=formatear_porcentaje(diff_tp_pct),
        delta_color="normal"
    )
    col3.caption(f"Promedio mes: {formatear_moneda(promedio_mes['promedio_ticket_promedio'])}")
    
    # ROI
    ventas_extra = datos_evento['total_ventas'] - promedio_mes['promedio_ventas']
    roi = ((ventas_extra - costo_total) / costo_total * 100) if costo_total > 0 else 0
    
    if ventas_extra > costo_total:
        st.success(f"✅ **ROI Positivo:** {formatear_porcentaje(roi)} - El evento generó {formatear_moneda(ventas_extra - costo_total)} por encima del costo")
    elif ventas_extra > 0:
        st.warning(f"⚠️ **ROI Negativo:** {formatear_porcentaje(roi)} - El evento generó {formatear_moneda(ventas_extra)} extra, pero no cubrió el costo de {formatear_moneda(costo_total)}")
    else:
        st.error(f"❌ **Sin impacto positivo** - Las ventas fueron menores al promedio")
    
    st.markdown("---")
    
    # COMPARACIÓN 2: Mismo día de semana del mes
    st.markdown("#### 2️⃣ Comparación vs Mismo Día de Semana del Mes")
    with st.spinner("Calculando promedio del mismo día de semana..."):
        promedio_dia_semana = calcular_promedio_mismo_dia_semana_mes(sucursal_id, fecha_evento)
    
    if promedio_dia_semana['dias_considerados'] > 0:
        col1, col2, col3 = st.columns(3)
        
        diff_ventas_ds_pct = ((datos_evento['total_ventas'] - promedio_dia_semana['promedio_ventas']) / promedio_dia_semana['promedio_ventas'] * 100) if promedio_dia_semana['promedio_ventas'] > 0 else 0
        col1.metric(
            "Ventas del Evento",
            formatear_moneda(datos_evento['total_ventas']),
            delta=formatear_porcentaje(diff_ventas_ds_pct),
            delta_color="normal"
        )
        col1.caption(f"Promedio {['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][fecha_evento.weekday()]}: {formatear_moneda(promedio_dia_semana['promedio_ventas'])}")
        col1.caption(f"(Basado en {promedio_dia_semana['dias_considerados']} {['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábados', 'domingos'][fecha_evento.weekday()]})")
        
        diff_tickets_ds_pct = ((datos_evento['cantidad_tickets'] - promedio_dia_semana['promedio_tickets']) / promedio_dia_semana['promedio_tickets'] * 100) if promedio_dia_semana['promedio_tickets'] > 0 else 0
        col2.metric(
            "Tickets del Evento",
            f"{datos_evento['cantidad_tickets']:.0f}",
            delta=formatear_porcentaje(diff_tickets_ds_pct),
            delta_color="normal"
        )
        col2.caption(f"Promedio: {promedio_dia_semana['promedio_tickets']:.0f}")
        
        diff_tp_ds_pct = ((datos_evento['ticket_promedio'] - promedio_dia_semana['promedio_ticket_promedio']) / promedio_dia_semana['promedio_ticket_promedio'] * 100) if promedio_dia_semana['promedio_ticket_promedio'] > 0 else 0
        col3.metric(
            "Ticket Promedio",
            formatear_moneda(datos_evento['ticket_promedio']),
            delta=formatear_porcentaje(diff_tp_ds_pct),
            delta_color="normal"
        )
        col3.caption(f"Promedio: {formatear_moneda(promedio_dia_semana['promedio_ticket_promedio'])}")
    else:
        st.info("ℹ️ No hay otros días de la misma semana en el mes para comparar")
    
    st.markdown("---")
    
    # COMPARACIÓN 3: Mismo día de semana del mes anterior
    st.markdown("#### 3️⃣ Comparación vs Mismo Día de Semana del Mes Anterior")
    
    numero_dia = obtener_numero_dia_semana_mes(fecha_evento)
    dia_nombre = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][fecha_evento.weekday()]
    numeros_texto = ['primer', 'segundo', 'tercer', 'cuarto', 'quinto']
    
    st.caption(f"Comparando con el {numeros_texto[numero_dia-1] if numero_dia <= 5 else str(numero_dia)+'º'} {dia_nombre} del mes anterior")
    
    fecha_mes_anterior = obtener_mismo_dia_semana_mes_anterior(fecha_evento)
    
    if fecha_mes_anterior:
        with st.spinner("Obteniendo datos del mes anterior..."):
            datos_mes_anterior = obtener_ventas_dia(sucursal_id, fecha_mes_anterior)
        
        col1, col2, col3 = st.columns(3)
        
        diff_ventas_ma_pct = ((datos_evento['total_ventas'] - datos_mes_anterior['total_ventas']) / datos_mes_anterior['total_ventas'] * 100) if datos_mes_anterior['total_ventas'] > 0 else 0
        col1.metric(
            "Ventas del Evento",
            formatear_moneda(datos_evento['total_ventas']),
            delta=formatear_porcentaje(diff_ventas_ma_pct),
            delta_color="normal"
        )
        col1.caption(f"{fecha_mes_anterior.strftime('%d/%m/%Y')}: {formatear_moneda(datos_mes_anterior['total_ventas'])}")
        
        diff_tickets_ma_pct = ((datos_evento['cantidad_tickets'] - datos_mes_anterior['cantidad_tickets']) / datos_mes_anterior['cantidad_tickets'] * 100) if datos_mes_anterior['cantidad_tickets'] > 0 else 0
        col2.metric(
            "Tickets del Evento",
            f"{datos_evento['cantidad_tickets']:.0f}",
            delta=formatear_porcentaje(diff_tickets_ma_pct),
            delta_color="normal"
        )
        col2.caption(f"{fecha_mes_anterior.strftime('%d/%m/%Y')}: {datos_mes_anterior['cantidad_tickets']:.0f}")
        
        diff_tp_ma_pct = ((datos_evento['ticket_promedio'] - datos_mes_anterior['ticket_promedio']) / datos_mes_anterior['ticket_promedio'] * 100) if datos_mes_anterior['ticket_promedio'] > 0 else 0
        col3.metric(
            "Ticket Promedio",
            formatear_moneda(datos_evento['ticket_promedio']),
            delta=formatear_porcentaje(diff_tp_ma_pct),
            delta_color="normal"
        )
        col3.caption(f"{fecha_mes_anterior.strftime('%d/%m/%Y')}: {formatear_moneda(datos_mes_anterior['ticket_promedio'])}")
    else:
        st.info(f"ℹ️ No existe el {numeros_texto[numero_dia-1] if numero_dia <= 5 else str(numero_dia)+'º'} {dia_nombre} del mes anterior")
    
    st.markdown("---")
    
    # CONCLUSIÓN
    st.markdown("### 🎯 Conclusión del Análisis")
    
    conclusiones = []
    
    # Análisis de ventas
    if diff_ventas_pct > 20:
        conclusiones.append(f"✅ **Excelente impacto en ventas:** +{diff_ventas_pct:.1f}% vs promedio del mes")
    elif diff_ventas_pct > 0:
        conclusiones.append(f"✓ **Impacto positivo moderado:** +{diff_ventas_pct:.1f}% vs promedio del mes")
    else:
        conclusiones.append(f"⚠️ **Sin impacto positivo en ventas:** {diff_ventas_pct:.1f}% vs promedio del mes")
    
    # Análisis de ROI
    if roi > 100:
        conclusiones.append(f"💰 **ROI excepcional:** {roi:.1f}% - El evento duplicó la inversión")
    elif roi > 0:
        conclusiones.append(f"💵 **ROI positivo:** {roi:.1f}% - El evento fue rentable")
    else:
        conclusiones.append(f"📉 **ROI negativo:** {roi:.1f}% - El evento no cubrió su costo")
    
    # Análisis de ticket promedio
    if diff_tp_pct > 10:
        conclusiones.append(f"📈 **Aumento en ticket promedio:** +{diff_tp_pct:.1f}%")
    elif diff_tp_pct > 0:
        conclusiones.append(f"➡️ **Ticket promedio estable:** +{diff_tp_pct:.1f}%")
    else:
        conclusiones.append(f"📉 **Disminución en ticket promedio:** {diff_tp_pct:.1f}%")
    
    # Mostrar conclusiones
    for conclusion in conclusiones:
        st.markdown(f"- {conclusion}")
    
    # Recomendación
    st.markdown("---")
    if roi > 50 and diff_ventas_pct > 15:
        st.success("🌟 **RECOMENDACIÓN: Repetir este tipo de evento** - Demostró excelente rentabilidad")
    elif roi > 0 and diff_ventas_pct > 0:
        st.info("✓ **RECOMENDACIÓN: Considerar repetir** - El evento fue rentable")
    else:
        st.warning("⚠️ **RECOMENDACIÓN: Analizar alternativas** - El evento no justificó su costo")

# ==================== FUNCIÓN PRINCIPAL ====================

def main():
    """Función principal del módulo de eventos"""
    
    # Verificar que el usuario sea admin
    if not hasattr(st.session_state, 'user'):
        st.error("⚠️ Debes iniciar sesión")
        st.stop()
    
    if st.session_state.user.get('rol') != 'admin':
        st.error("🔒 Solo los administradores pueden acceder a este módulo")
        st.stop()
    
    # Título del módulo
    st.title("🎭 Gestión de Eventos")
    st.markdown("---")
    
    # Tabs principales
    tab1, tab2, tab3 = st.tabs(["📝 Cargar Evento", "📋 Listado", "📊 Análisis de Impacto"])
    
    with tab1:
        mostrar_formulario_carga()
    
    with tab2:
        mostrar_listado_eventos()
    
    with tab3:
        mostrar_analisis_impacto()

if __name__ == "__main__":
    main()
