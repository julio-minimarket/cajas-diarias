# cajas_diarias.py
import streamlit as st
import pandas as pd
from datetime import date, datetime
import os

# Intentar cargar dotenv solo si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import create_client, Client
import auth  # Asegúrate de que auth.py esté en la misma carpeta

# ==================== CONFIGURACIÓN DE PÁGINA ====================
# DEBE ir estrictamente al principio
st.set_page_config(
    page_title="Cajas Diarias",
    page_icon="💰",
    layout="wide"
)

# ==================== VERIFICAR AUTENTICACIÓN ====================
if not auth.is_authenticated():
    auth.show_login_form()
    st.stop()

# ==================== OPTIMIZACIÓN 1: CONEXIÓN CACHEADA ====================
# Usamos cache_resource para conectar solo una vez por sesión del servidor, no por cada clic.
@st.cache_resource
def init_supabase() -> Client:
    """Inicializa y cachea la conexión a Supabase"""
    # Prioridad: st.secrets > variables de entorno
    if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        st.error("⚠️ Falta configurar las credenciales de Supabase (SUPABASE_URL y SUPABASE_KEY).")
        st.stop()

    try:
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Error crítico conectando a Supabase: {str(e)}")
        st.stop()

supabase = init_supabase()

# ==================== FUNCIONES DE DATOS (CACHEADA) ====================

@st.cache_data(ttl=3600)
def obtener_sucursales():
    try:
        result = supabase.table("sucursales").select("*").eq("activa", True).order("nombre").execute()
        return result.data if result.data else []
    except Exception as e:
        st.error(f"Error obteniendo sucursales: {e}")
        return []

@st.cache_data(ttl=3600)
def obtener_categorias(tipo):
    try:
        result = supabase.table("categorias")\
            .select("*")\
            .eq("tipo", tipo)\
            .eq("activa", True)\
            .execute()
        return result.data
    except Exception as e:
        st.error(f"Error obteniendo categorías: {e}")
        return []

@st.cache_data(ttl=3600)
def obtener_medios_pago(tipo):
    """tipo: 'venta', 'gasto', o 'ambos'"""
    try:
        result = supabase.table("medios_pago")\
            .select("*")\
            .eq("activo", True)\
            .or_(f"tipo_aplicable.eq.{tipo},tipo_aplicable.eq.ambos")\
            .order("orden")\
            .execute()
        return result.data
    except Exception as e:
        st.error(f"Error obteniendo medios de pago: {e}")
        return []

def limpiar_cache():
    """Limpia el cache de datos y recarga"""
    st.cache_data.clear()
    st.rerun()

# ==================== INTERFAZ PRINCIPAL ====================

st.title("💰 Sistema de Cajas Diarias")
st.markdown("---")

# --- CARGA INICIAL DE DATOS ---
sucursales = obtener_sucursales()

if not sucursales:
    st.warning("⚠️ No hay sucursales configuradas o activas.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.header("🏪 Configuración")

# Filtrar sucursales según el usuario (Lógica de auth.py)
sucursales_disponibles = auth.filtrar_sucursales_disponibles(sucursales)

if not sucursales_disponibles:
    st.error("⚠️ No tienes sucursales asignadas. Contacta al administrador.")
    st.stop()

# Selector de sucursal
sucursal_seleccionada = st.sidebar.selectbox(
    "Sucursal",
    options=sucursales_disponibles,
    format_func=lambda x: x['nombre'],
    key="selector_sucursal"
)

# Selector de fecha
fecha_mov = auth.obtener_selector_fecha()

# Info usuario y botón refrescar
auth.mostrar_info_usuario_sidebar()
if st.sidebar.button("🔄 Refrescar Datos"):
    limpiar_cache()

# Debug en expander para no ensuciar la interfaz
with st.sidebar.expander("🔍 Debug Info"):
    st.write(f"ID Sucursal: {sucursal_seleccionada['id']}")
    st.write(f"Registros: {len(sucursales)} sucursales")

# Lógica de cambio de password
if st.session_state.get('mostrar_cambio_pwd', False):
    auth.mostrar_cambio_password()
    st.stop()

# ================== TABS ==================
# Definición de pestañas según rol
es_admin = auth.is_admin()

if es_admin:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📝 Carga", "📊 Resumen", "📈 Reportes", "💼 CRM", "🔄 Conciliación", "🔧 Mantenimiento"
    ])
else:
    tab1, tab2 = st.tabs(["📝 Carga", "📊 Resumen"])
    tab3 = tab4 = tab5 = tab6 = None

# ==================== TAB 1: CARGA ====================
with tab1:
    st.subheader(f"Cargar movimiento - {sucursal_seleccionada['nombre']}")
    
    tipo = st.radio("Tipo de movimiento", ["Venta", "Gasto", "Sueldos"], horizontal=True)
    
    with st.form("form_movimiento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        # Lógica de campos según tipo
        categoria_seleccionada = None
        medio_pago_seleccionado = None
        concepto = ""
        
        with col1:
            if tipo == "Sueldos":
                cats = obtener_categorias("gasto")
                cat_sueldos = next((c for c in cats if c['nombre'] == 'Sueldos'), None)
                
                if cat_sueldos:
                    categoria_seleccionada = cat_sueldos
                    st.info(f"📂 Categoría: **{categoria_seleccionada['nombre']}**")
                else:
                    st.error("❌ No existe la categoría 'Sueldos'. Créala en Mantenimiento.")
                
                concepto = st.text_input("👤 Nombre del Empleado *")
            
            else:
                cats = obtener_categorias(tipo.lower())
                # Filtrar "Sueldos" si es Gasto manual
                if tipo == "Gasto":
                    cats = [c for c in cats if c['nombre'] != 'Sueldos']
                
                if cats:
                    categoria_seleccionada = st.selectbox("Categoría", options=cats, format_func=lambda x: x['nombre'])
                else:
                    st.error(f"No hay categorías de {tipo} disponibles.")
                
                concepto = st.text_input("Concepto/Detalle (opcional)")
        
        with col2:
            monto = st.number_input("Monto ($)", min_value=0.0, step=0.01, format="%.2f")
            
            # Medio de pago automático para Sueldos/Gastos
            if tipo in ["Sueldos", "Gasto"]:
                medios = obtener_medios_pago("gasto")
                medio_efectivo = next((m for m in medios if m['nombre'] == 'Efectivo'), None)
                
                if medio_efectivo:
                    medio_pago_seleccionado = medio_efectivo
                    st.info("💵 Medio de pago: **Efectivo** (automático)")
                else:
                    st.error("Falta medio de pago 'Efectivo'.")
            else:
                medios = obtener_medios_pago("venta")
                if medios:
                    medio_pago_seleccionado = st.selectbox("Medio de pago", options=medios, format_func=lambda x: x['nombre'])
        
        submitted = st.form_submit_button("💾 Guardar Movimiento", use_container_width=True, type="primary")
        
        if submitted:
            # 1. Validaciones
            puede_cargar, msg_error = auth.puede_cargar_fecha(fecha_mov, auth.get_user_role())
            if not puede_cargar:
                st.error(msg_error)
            elif monto <= 0:
                st.error("⚠️ El monto debe ser mayor a 0.")
            elif not categoria_seleccionada or not medio_pago_seleccionado:
                st.error("⚠️ Faltan configuraciones (categoría o medio de pago).")
            elif tipo == "Sueldos" and not concepto:
                st.error("⚠️ Debes ingresar el nombre del empleado.")
            else:
                # 2. Guardado
                try:
                    usuario = st.session_state.user['nombre']
                    datos = {
                        "sucursal_id": sucursal_seleccionada['id'],
                        "fecha": str(fecha_mov),
                        "tipo": "gasto" if tipo == "Sueldos" else tipo.lower(),
                        "categoria_id": categoria_seleccionada['id'],
                        "concepto": concepto,
                        "monto": monto,
                        "medio_pago_id": medio_pago_seleccionado['id'],
                        "usuario": usuario
                    }
                    
                    res = supabase.table("movimientos_diarios").insert(datos).execute()
                    
                    if res.data:
                        # OPTIMIZACIÓN 2: Uso de Toast en lugar de success estático
                        st.toast(f"✅ {tipo} de ${monto:,.2f} guardado!", icon="✅")
                        st.cache_data.clear() # Limpiar cache para actualizar reportes
                    else:
                        st.error("No se recibieron datos de confirmación.")
                        
                except Exception as e:
                    st.error(f"❌ Error al guardar: {str(e)}")

# ==================== TAB 2: RESUMEN (FRAGMENTADO) ====================
with tab2:
    # OPTIMIZACIÓN 3: @st.fragment
    # Esta función se renderiza de forma independiente. Si cambias algo visual aquí dentro 
    # en el futuro (ej. un filtro interno), no recargará toda la página.
    @st.fragment
    def mostrar_resumen_dia():
        st.subheader(f"📊 Resumen del {fecha_mov.strftime('%d/%m/%Y')} - {sucursal_seleccionada['nombre']}")
        
        try:
            query = supabase.table("movimientos_diarios")\
                .select("*, categorias(nombre), medios_pago(nombre)")\
                .eq("sucursal_id", sucursal_seleccionada['id'])\
                .eq("fecha", str(fecha_mov))
            
            result = query.execute()
            
            if not result.data:
                st.info("📭 No hay movimientos cargados para esta fecha.")
                return

            df = pd.DataFrame(result.data)
            
            # Procesamiento de columnas seguras
            df['categoria_nombre'] = df['categorias'].apply(lambda x: x['nombre'] if x else 'N/A')
            df['medio_pago_nombre'] = df['medios_pago'].apply(lambda x: x['nombre'] if x else 'N/A')
            
            # Cálculos
            df_ventas = df[df['tipo'] == 'venta']
            df_gastos = df[df['tipo'] == 'gasto']
            
            ventas_total = df_ventas['monto'].sum()
            gastos_total = df_gastos['monto'].sum()
            neto = ventas_total - gastos_total
            
            # Ventas Efectivo
            ventas_efectivo = df_ventas[df_ventas['medio_pago_nombre'] == 'Efectivo']['monto'].sum()
            efectivo_entregado = ventas_efectivo - gastos_total
            
            # Métricas
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("💰 Ventas", f"${ventas_total:,.2f}")
            c2.metric("💸 Gastos", f"${gastos_total:,.2f}")
            c3.metric("📊 Neto", f"${neto:,.2f}", delta_color="normal")
            c4.metric("💵 Ventas Efectivo", f"${ventas_efectivo:,.2f}")
            c5.metric("🏦 A Rendir", f"${efectivo_entregado:,.2f}", help="Ventas Efete. - Gastos")
            
            st.markdown("---")
            
            # Tablas y Gráficos
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                if not df_ventas.empty:
                    st.caption("Ventas por Medio de Pago")
                    st.bar_chart(df_ventas.groupby('medio_pago_nombre')['monto'].sum())
            
            with col_chart2:
                if not df_gastos.empty:
                    st.caption("Gastos por Categoría")
                    st.bar_chart(df_gastos.groupby('categoria_nombre')['monto'].sum())

            # Tabla detallada
            st.subheader("📋 Detalle de Movimientos")
            df_show = df[['tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago_nombre', 'usuario']].copy()
            df_show['monto'] = df_show['monto'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            
        except Exception as e:
            st.error(f"Error cargando resumen: {str(e)}")

    # Ejecutar la función fragmentada
    mostrar_resumen_dia()


# ==================== TAB 3: REPORTES (SOLO ADMIN) ====================
if tab3:
    with tab3:
        st.subheader("📈 Generar Reportes")
        
        c1, c2, c3 = st.columns(3)
        f_desde = c1.date_input("Desde", value=date.today().replace(day=1), key="rep_desde")
        f_hasta = c2.date_input("Hasta", value=date.today(), key="rep_hasta")
        todas = c3.checkbox("Incluir todas las sucursales") if auth.is_admin() else False
        
        if st.button("📊 Generar", type="primary"):
            with st.spinner("Consultando base de datos..."):
                try:
                    q = supabase.table("movimientos_diarios")\
                        .select("*, sucursales(nombre), categorias(nombre), medios_pago(nombre)")\
                        .gte("fecha", str(f_desde))\
                        .lte("fecha", str(f_hasta))
                    
                    if not todas:
                        q = q.eq("sucursal_id", sucursal_seleccionada['id'])
                    
                    res = q.execute()
                    
                    if res.data:
                        df = pd.DataFrame(res.data)
                        # Aplanar JSON
                        df['sucursal'] = df['sucursales'].apply(lambda x: x['nombre'] if x else '')
                        df['categoria'] = df['categorias'].apply(lambda x: x['nombre'] if x else '')
                        df['medio'] = df['medios_pago'].apply(lambda x: x['nombre'] if x else '')
                        
                        # KPIs
                        ventas = df[df['tipo']=='venta']['monto'].sum()
                        gastos = df[df['tipo']=='gasto']['monto'].sum()
                        
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Total Ventas", f"${ventas:,.2f}")
                        k2.metric("Total Gastos", f"${gastos:,.2f}")
                        k3.metric("Resultado", f"${(ventas-gastos):,.2f}")
                        
                        # Tablas
                        st.markdown("### Detalle")
                        st.dataframe(df[['fecha', 'sucursal', 'tipo', 'categoria', 'concepto', 'monto', 'medio']], use_container_width=True)
                        
                        # Download
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button("⬇️ Descargar CSV", csv, "reporte.csv", "text/csv")
                    else:
                        st.warning("No se encontraron datos en ese período.")
                except Exception as e:
                    st.error(f"Error: {e}")

# ==================== TAB 4: CRM ====================
if tab4:
    with tab4:
        st.subheader("💼 Carga Datos CRM (Comparativa)")
        
        with st.form("frm_crm"):
            c1, c2 = st.columns(2)
            with c1:
                # Obtener lista de sistemas CRM
                sucs_crm_data = supabase.table("sucursales_crm").select("*").execute().data
                map_crm = {s['sucursal_id']: s['sistema_crm'] for s in sucs_crm_data}
                
                opciones = sucursales_disponibles
                sel_suc = st.selectbox("Sucursal", opciones, format_func=lambda x: f"{x['nombre']} ({map_crm.get(x['id'], 'Sin CRM')})")
                
                fecha_crm = st.date_input("Fecha", value=date.today())
            
            with c2:
                vta_crm = st.number_input("Ventas CRM ($)", min_value=0.0, format="%.2f")
                tkts = st.number_input("Cantidad Tickets", min_value=0)
                
            if st.form_submit_button("💾 Guardar Datos CRM", type="primary"):
                try:
                    datos = {
                        "sucursal_id": sel_suc['id'],
                        "fecha": str(fecha_crm),
                        "total_ventas_crm": vta_crm,
                        "cantidad_tickets": tkts,
                        "usuario": st.session_state.user['nombre'],
                        "updated_at": datetime.now().isoformat()
                    }
                    
                    # Upsert (insertar o actualizar si existe)
                    # Nota: Para que upsert funcione, debe haber una constraint unique en (sucursal_id, fecha) en Supabase
                    # Si no existe, hacemos check manual:
                    
                    existe = supabase.table("crm_datos_diarios").select("id")\
                        .eq("sucursal_id", sel_suc['id']).eq("fecha", str(fecha_crm)).execute()
                    
                    if existe.data:
                        supabase.table("crm_datos_diarios").update(datos).eq("id", existe.data[0]['id']).execute()
                        st.toast("🔄 Datos actualizados correctamente", icon="🔄")
                    else:
                        supabase.table("crm_datos_diarios").insert(datos).execute()
                        st.toast("✅ Datos guardados correctamente", icon="✅")
                        
                except Exception as e:
                    st.error(f"Error guardando CRM: {e}")

# ==================== TAB 5: CONCILIACIÓN (MODIFICADO) ====================
if tab5:
    with tab5:
        st.subheader("📊 Informe de Conciliación por Rango")
        st.info("Compara el total de ventas registradas en Cajas vs CRM en un período específico.")
        
        # --- 1. Filtros de Búsqueda ---
        with st.form("form_conciliacion"):
            col_filt1, col_filt2, col_filt3 = st.columns(3)
            
            with col_filt1:
                fecha_desde_concil = st.date_input(
                    "📅 Desde", 
                    value=date.today().replace(day=1), # Por defecto primer día del mes
                    key="concil_desde"
                )
                
            with col_filt2:
                fecha_hasta_concil = st.date_input(
                    "📅 Hasta", 
                    value=date.today(),
                    key="concil_hasta"
                )
                
            with col_filt3:
                # Usamos la lista de sucursales cargada al inicio
                sucursal_concil = st.selectbox(
                    "🏪 Sucursal", 
                    options=sucursales, 
                    format_func=lambda x: x['nombre'],
                    key="concil_sucursal"
                )
            
            # Botón para generar
            submitted_concil = st.form_submit_button("🔍 Generar Informe", type="primary")

        # --- 2. Lógica de Procesamiento ---
        if submitted_concil:
            with st.spinner(f"Analizando datos de {sucursal_concil['nombre']}..."):
                try:
                    # A) Consultar SISTEMA DE CAJAS (Solo ventas)
                    query_cajas = supabase.table("movimientos_diarios")\
                        .select("monto, fecha")\
                        .eq("sucursal_id", sucursal_concil['id'])\
                        .eq("tipo", "venta")\
                        .gte("fecha", str(fecha_desde_concil))\
                        .lte("fecha", str(fecha_hasta_concil))\
                        .execute()
                    
                    # B) Consultar CRM
                    query_crm = supabase.table("crm_datos_diarios")\
                        .select("total_ventas_crm, fecha")\
                        .eq("sucursal_id", sucursal_concil['id'])\
                        .gte("fecha", str(fecha_desde_concil))\
                        .lte("fecha", str(fecha_hasta_concil))\
                        .execute()
                    
                    # --- 3. Cálculos ---
                    total_cajas = 0.0
                    total_crm = 0.0
                    dias_con_datos = 0
                    
                    # Sumar Cajas
                    if query_cajas.data:
                        df_cajas = pd.DataFrame(query_cajas.data)
                        total_cajas = df_cajas['monto'].sum()
                    
                    # Sumar CRM
                    if query_crm.data:
                        df_crm = pd.DataFrame(query_crm.data)
                        total_crm = df_crm['total_ventas_crm'].sum()
                        dias_con_datos = len(df_crm)
                    
                    diferencia = total_cajas - total_crm
                    
                    # Evitar división por cero para el porcentaje
                    porcentaje = (diferencia / total_crm * 100) if total_crm > 0 else 0.0

                    # --- 4. Mostrar Resultados ---
                    st.markdown("---")
                    st.markdown(f"### Resultados: **{sucursal_concil['nombre']}**")
                    st.caption(f"Período: {fecha_desde_concil.strftime('%d/%m/%Y')} al {fecha_hasta_concil.strftime('%d/%m/%Y')}")

                    # Métricas Grandes
                    col_met1, col_met2, col_met3, col_met4 = st.columns(4)
                    
                    col_met1.metric("💼 Total Cajas", f"${total_cajas:,.2f}")
                    col_met2.metric("💻 Total CRM", f"${total_crm:,.2f}")
                    
                    # Color dinámico para la diferencia
                    color_diff = "normal"
                    if abs(diferencia) > 1000: color_diff = "inverse" # Rojo si es mucha diferencia
                    
                    col_met3.metric("📊 Diferencia ($)", f"${diferencia:,.2f}", delta_color=color_diff)
                    col_met4.metric("📉 Diferencia (%)", f"{porcentaje:.2f}%")

                    # Análisis de Estado
                    st.markdown("#### 📝 Diagnóstico")
                    if total_crm == 0:
                        st.warning("⚠️ No hay datos cargados en el CRM para este período.")
                    elif abs(diferencia) < 100: # Tolerancia de $100
                        st.success("✅ **Conciliación Exitosa:** Los valores coinciden correctamente.")
                    elif abs(diferencia) < (total_crm * 0.01): # Menos del 1% de error
                        st.info("ℹ️ **Diferencia Menor:** Existe una pequeña variación (menos del 1%).")
                    else:
                        st.error("❌ **Diferencia Significativa:** Revisar tickets y cargas manuales.")

                    # (Opcional) Tabla comparativa día a día si hay datos
                    if query_cajas.data or query_crm.data:
                        with st.expander("ver detalle día por día"):
                            # Unificar datos para mostrar tabla diaria
                            df_base_c = pd.DataFrame(query_cajas.data) if query_cajas.data else pd.DataFrame(columns=['fecha', 'monto'])
                            df_base_crm = pd.DataFrame(query_crm.data) if query_crm.data else pd.DataFrame(columns=['fecha', 'total_ventas_crm'])
                            
                            if not df_base_c.empty:
                                df_base_c = df_base_c.groupby('fecha')['monto'].sum().reset_index()
                            
                            # Merge de datos
                            df_merge = pd.merge(df_base_c, df_base_crm, on='fecha', how='outer').fillna(0)
                            df_merge = df_merge.sort_values('fecha', ascending=False)
                            df_merge['diferencia'] = df_merge['monto'] - df_merge['total_ventas_crm']
                            
                            # Formato visual
                            df_show = df_merge.rename(columns={
                                'fecha': 'Fecha',
                                'monto': 'Cajas ($)',
                                'total_ventas_crm': 'CRM ($)',
                                'diferencia': 'Diferencia'
                            })
                            
                            st.dataframe(
                                df_show.style.format({
                                    'Cajas ($)': "${:,.2f}", 
                                    'CRM ($)': "${:,.2f}", 
                                    'Diferencia': "${:,.2f}"
                                }), 
                                use_container_width=True
                            )

                except Exception as e:
                    st.error(f"❌ Error al generar el reporte: {str(e)}")

# ==================== TAB 6: MANTENIMIENTO ====================
if tab6:
    with tab6:
        st.subheader("🔧 Edición Directa de Tablas")
        st.warning("⚠️ Los cambios aquí son directos a la base de datos.")
        
        tablas = {
            "sucursales": "Sucursales",
            "categorias": "Categorías",
            "medios_pago": "Medios de Pago",
            "movimientos_diarios": "Movimientos (Admin)",
            "crm_datos_diarios": "Datos CRM"
        }
        
        tabla_sel = st.selectbox("Tabla", options=list(tablas.keys()), format_func=lambda x: tablas[x])
        
        # Carga de datos con filtros básicos si es tabla grande
        query = supabase.table(tabla_sel).select("*").order("id", desc=True)
        if tabla_sel == "movimientos_diarios":
            query = query.limit(200) # Limitar para no explotar la memoria en edición
            st.caption("Mostrando los últimos 200 registros por seguridad.")
            
        res = query.execute()
        
        if res.data:
            df_orig = pd.DataFrame(res.data)
            
            # Editor
            df_edit = st.data_editor(
                df_orig, 
                num_rows="dynamic", 
                use_container_width=True,
                key=f"editor_{tabla_sel}"
            )
            
            if st.button("💾 Guardar Cambios Masivos", type="primary"):
                # Detección de cambios
                # Nota: st.data_editor no devuelve fácilmente el 'delta', comparamos dataframes
                # Esta es una implementación simple. Para producción masiva, optimizar lógica.
                
                cambios = 0
                errores = 0
                
                # 1. Detectar registros nuevos (IDs vacíos o nulos en lógica local, 
                # pero data_editor suele manejar esto diferente. Asumimos edición de existentes por simplicidad
                # o nuevos si se agregaron filas).
                
                # Estrategia simple: Iterar filas modificadas
                # Comparamos iterando índices. 
                # (En una app real, usaríamos session_state para trackear edits específicos es más eficiente)
                
                with st.status("Procesando cambios...", expanded=True) as status:
                    # Barrido simplificado: Upsert de todo el DF editado si son pocos datos, 
                    # o iterar comparando. Dado que limitamos a 200 filas, upsert es viable.
                    
                    datos_a_subir = df_edit.to_dict(orient="records")
                    
                    # Limpiar columnas que no deben ir al update si son generadas
                    # En este caso enviamos todo. Supabase ignora columnas extra si no existen, 
                    # pero cuidado con foreign keys rotas.
                    
                    try:
                        # Upsert en lotes
                        res_up = supabase.table(tabla_sel).upsert(datos_a_subir).execute()
                        status.update(label="✅ ¡Datos sincronizados!", state="complete")
                        st.toast("Base de datos actualizada", icon="💾")
                        # Recargar para asegurar IDs correctos
                        st.cache_data.clear() 
                        
                    except Exception as e:
                        status.update(label="❌ Error al guardar", state="error")
                        st.error(f"Detalle del error: {e}")
        else:
            st.info("Tabla vacía.")
