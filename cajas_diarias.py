# cajas_diarias.py
import streamlit as st
import pandas as pd
from datetime import date, datetime
import os

# Intentar cargar dotenv solo si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from supabase import create_client, Client
import auth  # Importar módulo de autenticación

# Configuración de página (DEBE ir primero)
st.set_page_config(
    page_title="Cajas Diarias",
    page_icon="💰",
    layout="wide"
)

# ==================== VERIFICAR AUTENTICACIÓN ====================
if not auth.is_authenticated():
    auth.show_login_form()
    st.stop()

# ==================== CONFIGURACIÓN DE SUPABASE ====================
if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
else:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("⚠️ Falta configurar las credenciales de Supabase")
    st.stop()

# Conectar a Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Error conectando a Supabase: {str(e)}")
    st.stop()

# ==================== TÍTULO ====================
st.title("💰 Sistema de Cajas Diarias")
st.markdown("---")

# ==================== FUNCIONES ====================

@st.cache_data(ttl=3600)
def obtener_sucursales():
    try:
        result = supabase.table("sucursales").select("*").eq("activa", True).order("nombre").execute()
        if not result.data:
            st.warning("⚠️ No se encontraron sucursales activas en la base de datos")
        return result.data
    except Exception as e:
        st.error(f"Error obteniendo sucursales: {e}")
        return []

def limpiar_cache():
    """Limpia el cache de datos"""
    st.cache_data.clear()
    st.rerun()

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
    """
    Obtiene medios de pago según el tipo de movimiento
    tipo: 'venta', 'gasto', o 'ambos'
    """
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

# ==================== CARGAR DATOS ====================

sucursales = obtener_sucursales()

if not sucursales:
    st.warning("⚠️ No hay sucursales configuradas.")
    st.stop()

# DEBUG: Mostrar cuántas sucursales se cargaron
st.sidebar.info(f"✅ {len(sucursales)} sucursales cargadas")

# Expander con información de debug
with st.sidebar.expander("🔍 Debug - Sucursales"):
    st.write("**Sucursales en base de datos:**")
    for suc in sucursales:
        st.write(f"- {suc['nombre']} (ID: {suc['id']})")

# Botón para refrescar datos
if st.sidebar.button("🔄 Refrescar Datos", help="Limpia el caché y recarga las sucursales"):
    limpiar_cache()

# Filtrar sucursales según el usuario
sucursales_disponibles = auth.filtrar_sucursales_disponibles(sucursales)

if not sucursales_disponibles:
    st.error("⚠️ No tienes sucursales asignadas. Contacta al administrador.")
    st.stop()

# ================== SIDEBAR ==================
st.sidebar.header("🏪 Configuración")

# Selector de sucursal (filtrado según usuario)
sucursal_seleccionada = st.sidebar.selectbox(
    "Sucursal",
    options=sucursales_disponibles,
    format_func=lambda x: x['nombre'],
    key="selector_sucursal"
)

# Selector de fecha (con validación según rol)
fecha_mov = auth.obtener_selector_fecha()

# Mostrar información del usuario
auth.mostrar_info_usuario_sidebar()

# ==================== CAMBIO DE CONTRASEÑA ====================
# Si el usuario solicitó cambiar contraseña, mostrar formulario
if st.session_state.get('mostrar_cambio_pwd', False):
    auth.mostrar_cambio_password()
    st.stop()

# ================== TABS PRINCIPALES ==================
# Mostrar diferentes tabs según el rol del usuario
if auth.is_admin():
    # Admin ve todas las tabs incluyendo CRM
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Carga", "📊 Resumen del Día", "📈 Reportes", "💼 CRM"])
else:
    # Encargados solo ven Carga y Resumen
    tab1, tab2 = st.tabs(["📝 Carga", "📊 Resumen del Día"])
    tab3 = None  # No hay tab de reportes para encargados
    tab4 = None  # No hay tab de CRM para encargados

# ==================== TAB 1: CARGA ====================
with tab1:
    st.subheader(f"Cargar movimiento - {sucursal_seleccionada['nombre']}")
    
    tipo = st.radio("Tipo de movimiento", ["Venta", "Gasto", "Sueldos"], horizontal=True)
    
    with st.form("form_movimiento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Si es "Sueldos", buscar automáticamente la categoría "Sueldos"
            if tipo == "Sueldos":
                categorias_data = obtener_categorias("gasto")
                categoria_sueldos = [cat for cat in categorias_data if cat['nombre'] == 'Sueldos']
                
                if categoria_sueldos:
                    categoria_seleccionada = categoria_sueldos[0]
                    st.info(f"📂 Categoría: **{categoria_seleccionada['nombre']}**")
                else:
                    st.error("No se encontró la categoría 'Sueldos'")
                    categoria_seleccionada = None
                
                concepto = st.text_input("👤 Nombre del Empleado *")
                
            else:
                categorias_data = obtener_categorias(tipo.lower())
                
                # FILTRAR "Sueldos" si es tipo "Gasto"
                if tipo == "Gasto":
                    categorias_data = [cat for cat in categorias_data if cat['nombre'] != 'Sueldos']
                
                if categorias_data:
                    categoria_seleccionada = st.selectbox(
                        "Categoría",
                        options=categorias_data,
                        format_func=lambda x: x['nombre']
                    )
                else:
                    st.error("No hay categorías disponibles")
                    categoria_seleccionada = None
                
                concepto = st.text_input("Concepto/Detalle (opcional)")
        
        with col2:
            monto = st.number_input("Monto ($)", min_value=0.0, step=0.01, format="%.2f")
            
            # Medio de pago
            if tipo in ["Sueldos", "Gasto"]:
                # Para Sueldos y Gastos, buscar el medio "Efectivo"
                medios_data = obtener_medios_pago("gasto")
                medio_efectivo = [m for m in medios_data if m['nombre'] == 'Efectivo']
                
                if medio_efectivo:
                    medio_pago_seleccionado = medio_efectivo[0]
                    st.info("💵 Medio de pago: **Efectivo** (automático)")
                else:
                    st.error("No se encontró el medio de pago 'Efectivo'")
                    medio_pago_seleccionado = None
            else:
                # Solo para Ventas, mostrar selector desde BD
                medios_data = obtener_medios_pago(tipo.lower())
                
                if medios_data:
                    medio_pago_seleccionado = st.selectbox(
                        "Medio de pago",
                        options=medios_data,
                        format_func=lambda x: x['nombre']
                    )
                else:
                    st.error("No hay medios de pago disponibles")
                    medio_pago_seleccionado = None
        
        submitted = st.form_submit_button("💾 Guardar", use_container_width=True, type="primary")
        
        if submitted:
            # VALIDAR FECHA antes de guardar
            puede_cargar, mensaje_error = auth.puede_cargar_fecha(fecha_mov, auth.get_user_role())
            
            if not puede_cargar:
                st.error(mensaje_error)
            else:
                # Obtener nombre del usuario autenticado
                usuario = st.session_state.user['nombre']
                
                # Validación según tipo
                if tipo == "Sueldos":
                    if not concepto or monto <= 0 or not categoria_seleccionada or not medio_pago_seleccionado:
                        st.error("⚠️ Completa todos los campos. El nombre del empleado y el monto son obligatorios.")
                    else:
                        # Guardar sueldo
                        try:
                            data = {
                                "sucursal_id": sucursal_seleccionada['id'],
                                "fecha": str(fecha_mov),
                                "tipo": "gasto",  # Sueldos se guardan como gastos
                                "categoria_id": categoria_seleccionada['id'],
                                "concepto": concepto,
                                "monto": monto,
                                "medio_pago_id": medio_pago_seleccionado['id'],
                                "usuario": usuario
                            }
                            
                            result = supabase.table("movimientos_diarios").insert(data).execute()
                            
                            if result.data:
                                st.success(f"✅ Sueldo de {concepto} guardado exitosamente: ${monto:,.2f}")
                                st.cache_data.clear()
                            else:
                                st.error("Error al guardar el movimiento")
                                
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                else:
                    # Validación para Venta y Gasto
                    if monto <= 0 or not categoria_seleccionada or not medio_pago_seleccionado:
                        st.error("⚠️ Completa todos los campos obligatorios")
                    else:
                        try:
                            data = {
                                "sucursal_id": sucursal_seleccionada['id'],
                                "fecha": str(fecha_mov),
                                "tipo": tipo.lower(),
                                "categoria_id": categoria_seleccionada['id'],
                                "concepto": concepto if concepto else None,
                                "monto": monto,
                                "medio_pago_id": medio_pago_seleccionado['id'],
                                "usuario": usuario
                            }
                            
                            result = supabase.table("movimientos_diarios").insert(data).execute()
                            
                            if result.data:
                                st.success(f"✅ {tipo} guardado exitosamente: ${monto:,.2f}")
                                st.cache_data.clear()
                            else:
                                st.error("Error al guardar el movimiento")
                                
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")

# ==================== TAB 2: RESUMEN ====================
with tab2:
    st.subheader(f"📊 Resumen del {fecha_mov.strftime('%d/%m/%Y')} - {sucursal_seleccionada['nombre']}")
    
    try:
        # Obtener movimientos del día
        result = supabase.table("movimientos_diarios")\
            .select("*, categorias(nombre), medios_pago(nombre)")\
            .eq("sucursal_id", sucursal_seleccionada['id'])\
            .eq("fecha", str(fecha_mov))\
            .execute()
        
        if result.data:
            df = pd.DataFrame(result.data)
            
            df['categoria_nombre'] = df['categorias'].apply(lambda x: x['nombre'] if x else 'Sin categoría')
            df['medio_pago_nombre'] = df['medios_pago'].apply(lambda x: x['nombre'] if x else 'Sin medio')
            
            # Separar ventas y gastos
            df_ventas = df[df['tipo'] == 'venta']
            df_gastos = df[df['tipo'] == 'gasto']
            
            # Totales
            ventas_total = df_ventas['monto'].sum() if len(df_ventas) > 0 else 0.0
            gastos_total = df_gastos['monto'].sum() if len(df_gastos) > 0 else 0.0
            neto = ventas_total - gastos_total
            
            # Ventas en efectivo específicamente
            ventas_efectivo = df_ventas[df_ventas['medio_pago_nombre'] == 'Efectivo']['monto'].sum() if len(df_ventas) > 0 else 0.0
            
            # EFECTIVO ENTREGADO = Ventas en Efectivo - Total de Gastos
            efectivo_entregado = ventas_efectivo - gastos_total
            
            # Métricas principales (5 columnas)
            col1, col2, col3, col4, col5 = st.columns(5)
            
            col1.metric("💰 Ventas", f"${ventas_total:,.2f}")
            col2.metric("💸 Gastos", f"${gastos_total:,.2f}")
            col3.metric("📊 Neto", f"${neto:,.2f}")
            col4.metric("💵 Ventas Efectivo", f"${ventas_efectivo:,.2f}")
            col5.metric("🏦 Efectivo Entregado", f"${efectivo_entregado:,.2f}")
            
            # Detalle del cálculo de efectivo
            with st.expander("💵 Detalle del Efectivo"):
                st.write("**Cálculo: Ventas en Efectivo - Total de Gastos**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Ventas Efectivo", f"${ventas_efectivo:,.2f}")
                with col2:
                    st.metric("(-) Gastos", f"${gastos_total:,.2f}")
                with col3:
                    st.metric("(=) Efectivo Entregado", f"${efectivo_entregado:,.2f}")
                
                st.markdown("---")
                st.write("**Resumen por Medio de Pago:**")
                if len(df_ventas) > 0:
                    medios_resumen = df_ventas.groupby('medio_pago_nombre')['monto'].sum().reset_index()
                    medios_resumen.columns = ['Medio de Pago', 'Monto']
                    medios_resumen['Monto'] = medios_resumen['Monto'].apply(lambda x: f"${x:,.2f}")
                    st.dataframe(medios_resumen, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Tabla de movimientos
            df_display = df[['tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago_nombre', 'usuario']].copy()
            df_display['concepto'] = df_display['concepto'].fillna('Sin detalle')
            df_display['monto'] = df_display['monto'].apply(lambda x: f"${x:,.2f}")
            df_display.columns = ['Tipo', 'Categoría', 'Concepto', 'Monto', 'Medio Pago', 'Usuario']
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Gráficos
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Ventas por Medio de Pago")
                if len(df_ventas) > 0:
                    ventas_medio = df_ventas.groupby('medio_pago_nombre')['monto'].sum()
                    if not ventas_medio.empty:
                        st.bar_chart(ventas_medio)
                else:
                    st.info("No hay ventas para mostrar")
            
            with col2:
                st.subheader("Gastos por Categoría")
                if len(df_gastos) > 0:
                    gastos_cat = df_gastos.groupby('categoria_nombre')['monto'].sum()
                    if not gastos_cat.empty:
                        st.bar_chart(gastos_cat)
                else:
                    st.info("No hay gastos para mostrar")
        else:
            st.info("📭 No hay movimientos cargados para esta fecha")
            
    except Exception as e:
        st.error(f"❌ Error al cargar movimientos: {str(e)}")

# ==================== TAB 3: REPORTES ====================
# Solo mostrar reportes si el usuario es admin
if tab3 is not None:
    with tab3:
        st.subheader("📈 Generar Reportes")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            fecha_desde = st.date_input("Desde", value=date.today().replace(day=1), key="reporte_desde")
        
        with col2:
            fecha_hasta = st.date_input("Hasta", value=date.today(), key="reporte_hasta")
        
        with col3:
            st.write("")
            # Solo admin puede ver todas las sucursales
            if auth.is_admin():
                todas_sucursales = st.checkbox("Todas las sucursales", value=False)
            else:
                todas_sucursales = False
        
        if st.button("📊 Generar Reporte", type="primary"):
            with st.spinner("Generando reporte..."):
                try:
                    query = supabase.table("movimientos_diarios")\
                        .select("*, sucursales(nombre), categorias(nombre), medios_pago(nombre)")\
                        .gte("fecha", str(fecha_desde))\
                        .lte("fecha", str(fecha_hasta))
                    
                    if not todas_sucursales:
                        query = query.eq("sucursal_id", sucursal_seleccionada['id'])
                    
                    result = query.execute()
                    
                    if result.data:
                        df = pd.DataFrame(result.data)
                        
                        df['sucursal_nombre'] = df['sucursales'].apply(lambda x: x['nombre'] if x else 'N/A')
                        df['categoria_nombre'] = df['categorias'].apply(lambda x: x['nombre'] if x else 'Sin categoría')
                        df['medio_pago_nombre'] = df['medios_pago'].apply(lambda x: x['nombre'] if x else 'Sin medio')
                        
                        # Resumen general
                        st.markdown("### 📊 Resumen del Período")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        ventas = df[df['tipo']=='venta']['monto'].sum()
                        gastos = df[df['tipo']=='gasto']['monto'].sum()
                        neto = ventas - gastos
                        
                        col1.metric("💰 Total Ventas", f"${ventas:,.2f}")
                        col2.metric("💸 Total Gastos", f"${gastos:,.2f}")
                        col3.metric("📊 Neto", f"${neto:,.2f}")
                        
                        st.markdown("---")
                        
                        # Tabla resumen por sucursal
                        if todas_sucursales:
                            st.markdown("### 🏪 Resumen por Sucursal")
                            
                            resumen = df.groupby(['sucursal_nombre', 'tipo'])['monto'].sum().unstack(fill_value=0)
                            if 'venta' in resumen.columns and 'gasto' in resumen.columns:
                                resumen['neto'] = resumen['venta'] - resumen['gasto']
                            
                            resumen_display = resumen.copy()
                            for col in resumen_display.columns:
                                resumen_display[col] = resumen_display[col].apply(lambda x: f"${x:,.2f}")
                            
                            st.dataframe(resumen_display, use_container_width=True)
                            
                            st.markdown("---")
                        
                        # Resumen por categoría
                        st.markdown("### 📂 Resumen por Categoría")
                        
                        resumen_cat = df.groupby(['tipo', 'categoria_nombre'])['monto'].sum().unstack(fill_value=0)
                        st.dataframe(resumen_cat.style.format("${:,.2f}"), use_container_width=True)
                        
                        st.markdown("---")
                        
                        # Resumen por medio de pago
                        st.markdown("### 💳 Resumen por Medio de Pago")
                        
                        resumen_medios = df[df['tipo']=='venta'].groupby('medio_pago_nombre')['monto'].sum().reset_index()
                        resumen_medios.columns = ['Medio de Pago', 'Monto Total']
                        resumen_medios = resumen_medios.sort_values('Monto Total', ascending=False)
                        resumen_medios['Monto Total'] = resumen_medios['Monto Total'].apply(lambda x: f"${x:,.2f}")
                        st.dataframe(resumen_medios, use_container_width=True, hide_index=True)
                        
                        st.markdown("---")
                        
                        # Detalle completo
                        st.markdown("### 📋 Detalle de Movimientos")
                        
                        df_detalle = df[['fecha', 'sucursal_nombre', 'tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago_nombre']].copy()
                        df_detalle['concepto'] = df_detalle['concepto'].fillna('Sin detalle')
                        df_detalle['monto'] = df_detalle['monto'].apply(lambda x: f"${x:,.2f}")
                        df_detalle.columns = ['Fecha', 'Sucursal', 'Tipo', 'Categoría', 'Concepto', 'Monto', 'Medio Pago']
                        
                        st.dataframe(df_detalle, use_container_width=True, hide_index=True)
                        
                        # Botón para descargar CSV
                        csv = df[['fecha', 'sucursal_nombre', 'tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago_nombre']].to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar CSV",
                            data=csv,
                            file_name=f"reporte_{fecha_desde}_{fecha_hasta}.csv",
                            mime="text/csv"
                        )
                        
                    else:
                        st.warning("⚠️ No hay datos para el período seleccionado")
                        
                except Exception as e:
                    st.error(f"❌ Error generando reporte: {str(e)}")

# ==================== TAB 4: CRM ====================
# Solo mostrar CRM si el usuario es admin
if tab4 is not None:
    with tab4:
        st.subheader("💼 Datos de CRM por Sucursal")
        
        st.info("📊 Esta sección permite cargar los datos de ventas y tickets desde los sistemas CRM de cada sucursal para comparación y control.")
        
        # ==================== FORMULARIO DE CARGA ====================
        st.markdown("### 📝 Cargar Datos del CRM")
        
        with st.form("form_crm", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                # Selector de sucursal
                sucursal_crm = st.selectbox(
                    "🏪 Sucursal",
                    options=sucursales,
                    format_func=lambda x: x['nombre'],
                    key="sucursal_crm"
                )
                
                # Obtener sistema CRM de la sucursal
                try:
                    crm_info = supabase.table("sucursales_crm")\
                        .select("sistema_crm")\
                        .eq("sucursal_id", sucursal_crm['id'])\
                        .single()\
                        .execute()
                    
                    if crm_info.data:
                        sistema_crm = crm_info.data['sistema_crm']
                        st.info(f"💻 Sistema CRM: **{sistema_crm}**")
                    else:
                        sistema_crm = "No asignado"
                        st.warning("⚠️ Esta sucursal no tiene sistema CRM asignado")
                except Exception as e:
                    sistema_crm = "Error"
                    st.error(f"❌ Error obteniendo sistema CRM: {str(e)}")
                    st.info("💡 Verifica que las tablas 'sucursales_crm' existan en Supabase")
                
                # Fecha
                fecha_crm = st.date_input(
                    "📅 Fecha",
                    value=date.today(),
                    key="fecha_crm"
                )
            
            with col2:
                # Total de ventas del CRM
                total_ventas_crm = st.number_input(
                    "💰 Total Ventas CRM ($)",
                    min_value=0.0,
                    step=0.01,
                    format="%.2f",
                    help="Total de ventas según el sistema CRM",
                    key="total_ventas_crm"
                )
                
                # Cantidad de tickets
                cantidad_tickets = st.number_input(
                    "🎫 Cantidad de Tickets",
                    min_value=0,
                    step=1,
                    help="Número total de tickets/facturas emitidas",
                    key="cantidad_tickets"
                )
            
            # Botón de guardar
            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn2:
                submitted_crm = st.form_submit_button("💾 Guardar", use_container_width=True, type="primary")
            
            if submitted_crm:
                if total_ventas_crm <= 0 or cantidad_tickets <= 0:
                    st.error("⚠️ Completa todos los campos con valores válidos")
                else:
                    try:
                        # Verificar si ya existe un registro para esta fecha y sucursal
                        existing = supabase.table("crm_datos_diarios")\
                            .select("id")\
                            .eq("sucursal_id", sucursal_crm['id'])\
                            .eq("fecha", str(fecha_crm))\
                            .execute()
                        
                        if existing.data:
                            # Actualizar registro existente
                            result = supabase.table("crm_datos_diarios")\
                                .update({
                                    "total_ventas_crm": total_ventas_crm,
                                    "cantidad_tickets": cantidad_tickets,
                                    "usuario": st.session_state.user['nombre'],
                                    "updated_at": datetime.now().isoformat()
                                })\
                                .eq("sucursal_id", sucursal_crm['id'])\
                                .eq("fecha", str(fecha_crm))\
                                .execute()
                            
                            st.success(f"✅ Datos de CRM actualizados: ${total_ventas_crm:,.2f} - {cantidad_tickets} tickets")
                        else:
                            # Insertar nuevo registro
                            data_crm = {
                                "sucursal_id": sucursal_crm['id'],
                                "fecha": str(fecha_crm),
                                "total_ventas_crm": total_ventas_crm,
                                "cantidad_tickets": cantidad_tickets,
                                "usuario": st.session_state.user['nombre']
                            }
                            
                            result = supabase.table("crm_datos_diarios").insert(data_crm).execute()
                            
                            if result.data:
                                st.success(f"✅ Datos de CRM guardados: ${total_ventas_crm:,.2f} - {cantidad_tickets} tickets")
                            else:
                                st.error("❌ Error al guardar los datos")
                        
                        st.cache_data.clear()
                        
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        st.markdown("---")
        
        # ==================== COMPARACIÓN Y VISUALIZACIÓN ====================
        st.markdown("### 📊 Comparación: Sistema de Cajas vs CRM")
        
        col_comp1, col_comp2, col_comp3 = st.columns(3)
        
        with col_comp1:
            fecha_comparacion = st.date_input(
                "Fecha a comparar",
                value=date.today(),
                key="fecha_comparacion"
            )
        
        with col_comp2:
            sucursal_comparacion = st.selectbox(
                "Sucursal",
                options=sucursales_disponibles,
                format_func=lambda x: x['nombre'],
                key="sucursal_comparacion"
            )
        
        with col_comp3:
            st.write("")
            if st.button("🔍 Comparar", type="primary", use_container_width=True):
                try:
                    # Obtener datos del sistema de cajas
                    movimientos = supabase.table("movimientos_diarios")\
                        .select("*")\
                        .eq("sucursal_id", sucursal_comparacion['id'])\
                        .eq("fecha", str(fecha_comparacion))\
                        .eq("tipo", "venta")\
                        .execute()
                    
                    total_cajas = sum([m['monto'] for m in movimientos.data]) if movimientos.data else 0.0
                    
                    # Obtener datos del CRM
                    crm_data = supabase.table("crm_datos_diarios")\
                        .select("*")\
                        .eq("sucursal_id", sucursal_comparacion['id'])\
                        .eq("fecha", str(fecha_comparacion))\
                        .execute()
                    
                    if crm_data.data:
                        total_crm = crm_data.data[0]['total_ventas_crm']
                        tickets = crm_data.data[0]['cantidad_tickets']
                        
                        st.markdown("#### 📈 Resultados de la Comparación")
                        
                        col_res1, col_res2, col_res3 = st.columns(3)
                        
                        with col_res1:
                            st.metric(
                                "💼 Sistema de Cajas",
                                f"${total_cajas:,.2f}",
                                help="Total de ventas registradas en el sistema de cajas"
                            )
                        
                        with col_res2:
                            st.metric(
                                "💻 Sistema CRM",
                                f"${total_crm:,.2f}",
                                help="Total de ventas según el CRM"
                            )
                        
                        with col_res3:
                            diferencia = total_cajas - total_crm
                            porcentaje = (diferencia / total_crm * 100) if total_crm > 0 else 0
                            
                            st.metric(
                                "📊 Diferencia",
                                f"${abs(diferencia):,.2f}",
                                f"{porcentaje:.2f}%",
                                delta_color="inverse" if diferencia < 0 else "normal"
                            )
                        
                        # Análisis
                        st.markdown("---")
                        
                        if abs(diferencia) < 100:
                            st.success("✅ Los valores coinciden correctamente (diferencia < $100)")
                        elif abs(diferencia) < 500:
                            st.warning(f"⚠️ Diferencia moderada de ${abs(diferencia):,.2f} - Revisar")
                        else:
                            st.error(f"❌ Diferencia significativa de ${abs(diferencia):,.2f} - Requiere auditoría")
                        
                        # Información adicional
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.info(f"🎫 **Tickets emitidos:** {tickets}")
                            if total_cajas > 0 and tickets > 0:
                                ticket_promedio = total_cajas / tickets
                                st.info(f"💵 **Ticket promedio:** ${ticket_promedio:,.2f}")
                        
                        with col_info2:
                            # Obtener sistema CRM
                            crm_sistema = supabase.table("sucursales_crm")\
                                .select("sistema_crm")\
                                .eq("sucursal_id", sucursal_comparacion['id'])\
                                .single()\
                                .execute()
                            
                            if crm_sistema.data:
                                st.info(f"💻 **Sistema CRM:** {crm_sistema.data['sistema_crm']}")
                    else:
                        st.warning(f"⚠️ No hay datos de CRM cargados para {sucursal_comparacion['nombre']} en la fecha {fecha_comparacion.strftime('%d/%m/%Y')}")
                        st.info(f"💼 Sistema de Cajas registró: ${total_cajas:,.2f}")
                
                except Exception as e:
                    st.error(f"❌ Error en la comparación: {str(e)}")
        
        st.markdown("---")
        
        # ==================== HISTORIAL ====================
        st.markdown("### 📋 Historial de Datos CRM")
        
        col_hist1, col_hist2 = st.columns(2)
        
        with col_hist1:
            fecha_desde_crm = st.date_input("Desde", value=date.today().replace(day=1), key="fecha_desde_crm")
        
        with col_hist2:
            fecha_hasta_crm = st.date_input("Hasta", value=date.today(), key="fecha_hasta_crm")
        
        if st.button("📊 Ver Historial", type="secondary"):
            try:
                historial = supabase.table("crm_datos_diarios")\
                    .select("*, sucursales(nombre)")\
                    .gte("fecha", str(fecha_desde_crm))\
                    .lte("fecha", str(fecha_hasta_crm))\
                    .order("fecha", desc=True)\
                    .execute()
                
                if historial.data:
                    df_hist = pd.DataFrame(historial.data)
                    df_hist['sucursal_nombre'] = df_hist['sucursales'].apply(lambda x: x['nombre'] if x else 'N/A')
                    
                    df_display = df_hist[['fecha', 'sucursal_nombre', 'total_ventas_crm', 'cantidad_tickets', 'usuario']].copy()
                    df_display['total_ventas_crm'] = df_display['total_ventas_crm'].apply(lambda x: f"${x:,.2f}")
                    df_display.columns = ['Fecha', 'Sucursal', 'Total Ventas CRM', 'Tickets', 'Usuario']
                    
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    
                    # Estadísticas del período
                    st.markdown("#### 📈 Estadísticas del Período")
                    col_stats1, col_stats2, col_stats3 = st.columns(3)
                    
                    with col_stats1:
                        total_ventas_periodo = df_hist['total_ventas_crm'].sum()
                        st.metric("💰 Total Ventas CRM", f"${total_ventas_periodo:,.2f}")
                    
                    with col_stats2:
                        total_tickets_periodo = df_hist['cantidad_tickets'].sum()
                        st.metric("🎫 Total Tickets", f"{total_tickets_periodo:,}")
                    
                    with col_stats3:
                        ticket_promedio_periodo = total_ventas_periodo / total_tickets_periodo if total_tickets_periodo > 0 else 0
                        st.metric("💵 Ticket Promedio", f"${ticket_promedio_periodo:,.2f}")
                else:
                    st.info("📭 No hay datos de CRM para el período seleccionado")
            
            except Exception as e:
                st.error(f"❌ Error al cargar historial: {str(e)}")
