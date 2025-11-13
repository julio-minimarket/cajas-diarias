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

# Configuración de Supabase
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

# Configuración de página
st.set_page_config(
    page_title="Cajas Diarias",
    page_icon="💰",
    layout="wide"
)

st.title("💰 Sistema de Cajas Diarias")
st.markdown("---")

# Función para obtener sucursales
@st.cache_data(ttl=3600)
def obtener_sucursales():
    try:
        result = supabase.table("sucursales").select("*").eq("activa", True).execute()
        return result.data
    except Exception as e:
        st.error(f"Error obteniendo sucursales: {e}")
        return []

# Función para obtener categorías
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

# Cargar sucursales
sucursales = obtener_sucursales()

if not sucursales:
    st.warning("⚠️ No hay sucursales configuradas.")
    st.stop()

# ================== SIDEBAR ==================
st.sidebar.header("🏪 Configuración")

sucursal_seleccionada = st.sidebar.selectbox(
    "Sucursal",
    options=sucursales,
    format_func=lambda x: x['nombre']
)

fecha_mov = st.sidebar.date_input("📅 Fecha", date.today())

st.sidebar.markdown("---")
usuario = st.sidebar.text_input("👤 Usuario", value="admin")

# ================== TABS PRINCIPALES ==================
tab1, tab2, tab3 = st.tabs(["📝 Carga", "📊 Resumen del Día", "📈 Reportes"])

# ==================== TAB 1: CARGA ====================
with tab1:
    st.subheader(f"Cargar movimiento - {sucursal_seleccionada['nombre']}")
    
    tipo = st.radio("Tipo de movimiento", ["Venta", "Gasto"], horizontal=True)
    
    with st.form("form_movimiento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            categorias_data = obtener_categorias(tipo.lower())
            
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
            
            if tipo == "Venta":
                medios = ["Efectivo", "Débito", "Crédito", "Transferencia", "Mercado Pago", "QR"]
            else:
                medios = ["Efectivo", "Transferencia", "Cheque", "Tarjeta"]
            
            medio_pago = st.selectbox("Medio de pago", medios)
        
        submitted = st.form_submit_button("💾 Guardar", use_container_width=True, type="primary")
        
        if submitted:
            if monto <= 0 or not categoria_seleccionada:
                st.error("⚠️ Completá la categoría y el monto correctamente")
            else:
                try:
                    data = {
                        "sucursal_id": sucursal_seleccionada['id'],
                        "fecha": str(fecha_mov),
                        "tipo": tipo.lower(),
                        "categoria_id": categoria_seleccionada['id'],
                        "concepto": concepto if concepto else None,
                        "monto": float(monto),
                        "medio_pago": medio_pago,
                        "usuario": usuario,
                        "fecha_carga": datetime.now().isoformat()
                    }
                    
                    result = supabase.table("movimientos_diarios").insert(data).execute()
                    st.success(f"✅ {tipo} guardada correctamente: ${monto:,.2f}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al guardar: {str(e)}")

# ==================== TAB 2: RESUMEN ====================
with tab2:
    st.subheader(f"Movimientos del {fecha_mov.strftime('%d/%m/%Y')} - {sucursal_seleccionada['nombre']}")
    
    try:
        movimientos = supabase.table("movimientos_diarios")\
            .select("*, categorias(nombre)")\
            .eq("fecha", str(fecha_mov))\
            .eq("sucursal_id", sucursal_seleccionada['id'])\
            .order("fecha_carga", desc=True)\
            .execute()
        
        if movimientos.data:
            df = pd.DataFrame(movimientos.data)
            df['categoria_nombre'] = df['categorias'].apply(lambda x: x['nombre'] if x else 'Sin categoría')
            
            # CÁLCULO DE MÉTRICAS
            df_ventas = df[df['tipo'] == 'venta'].copy()
            df_gastos = df[df['tipo'] == 'gasto'].copy()
            
            # Totales generales
            ventas_total = df_ventas['monto'].sum() if len(df_ventas) > 0 else 0.0
            gastos_total = df_gastos['monto'].sum() if len(df_gastos) > 0 else 0.0
            neto = ventas_total - gastos_total
            
            # Ventas en efectivo específicamente
            ventas_efectivo = df_ventas[df_ventas['medio_pago'] == 'Efectivo']['monto'].sum() if len(df_ventas) > 0 else 0.0
            
            # EFECTIVO ENTREGADO = Ventas en Efectivo - Total de Gastos
            efectivo_entregado = ventas_efectivo - gastos_total
            
            # Métricas principales (5 columnas)
            col1, col2, col3, col4, col5 = st.columns(5)
            
            col1.metric("💰 Ventas", f"${ventas_total:,.2f}")
            col2.metric("💸 Gastos", f"${gastos_total:,.2f}")
            col3.metric("📊 Neto", f"${neto:,.2f}")
            col4.metric("💵 Ventas Efectivo", f"${ventas_efectivo:,.2f}")
            
            delta_color = "normal" if efectivo_entregado >= 0 else "inverse"
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
                    medios_resumen = df_ventas.groupby('medio_pago')['monto'].sum().reset_index()
                    medios_resumen.columns = ['Medio de Pago', 'Monto']
                    medios_resumen['Monto'] = medios_resumen['Monto'].apply(lambda x: f"${x:,.2f}")
                    st.dataframe(medios_resumen, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Tabla de movimientos
            df_display = df[['tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago', 'usuario']].copy()
            df_display['concepto'] = df_display['concepto'].fillna('Sin detalle')
            df_display['monto'] = df_display['monto'].apply(lambda x: f"${x:,.2f}")
            df_display.columns = ['Tipo', 'Categoría', 'Concepto', 'Monto', 'Medio Pago', 'Usuario']
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Gráficos
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Ventas por Medio de Pago")
                if len(df_ventas) > 0:
                    ventas_medio = df_ventas.groupby('medio_pago')['monto'].sum()
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
with tab3:
    st.subheader("📈 Generar Reportes")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        fecha_desde = st.date_input("Desde", value=date.today().replace(day=1))
    
    with col2:
        fecha_hasta = st.date_input("Hasta", value=date.today())
    
    with col3:
        st.write("")
        todas_sucursales = st.checkbox("Todas las sucursales", value=False)
    
    if st.button("📊 Generar Reporte", type="primary"):
        with st.spinner("Generando reporte..."):
            try:
                query = supabase.table("movimientos_diarios")\
                    .select("*, sucursales(nombre), categorias(nombre)")\
                    .gte("fecha", str(fecha_desde))\
                    .lte("fecha", str(fecha_hasta))
                
                if not todas_sucursales:
                    query = query.eq("sucursal_id", sucursal_seleccionada['id'])
                
                result = query.execute()
                
                if result.data:
                    df = pd.DataFrame(result.data)
                    
                    df['sucursal_nombre'] = df['sucursales'].apply(lambda x: x['nombre'] if x else 'N/A')
                    df['categoria_nombre'] = df['categorias'].apply(lambda x: x['nombre'] if x else 'Sin categoría')
                    
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
                    
                    # Detalle completo
                    st.markdown("### 📋 Detalle de Movimientos")
                    
                    df_detalle = df[['fecha', 'sucursal_nombre', 'tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago']].copy()
                    df_detalle['concepto'] = df_detalle['concepto'].fillna('Sin detalle')
                    df_detalle['monto'] = df_detalle['monto'].apply(lambda x: f"${x:,.2f}")
                    df_detalle.columns = ['Fecha', 'Sucursal', 'Tipo', 'Categoría', 'Concepto', 'Monto', 'Medio Pago']
                    
                    st.dataframe(df_detalle, use_container_width=True, hide_index=True)
                    
                    # Botón para descargar CSV
                    csv = df[['fecha', 'sucursal_nombre', 'tipo', 'categoria_nombre', 'concepto', 'monto', 'medio_pago']].to_csv(index=False)
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
