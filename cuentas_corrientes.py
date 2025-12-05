# cuentas_corrientes.py - MÓDULO DE CUENTAS CORRIENTES DE CLIENTES v1.1 (OPTIMIZADO)
#
# 📋 DESCRIPCIÓN:
# Sistema completo de gestión de cuentas corrientes para clientes
# Exclusivo para Sucursal 1 - Minimarket
# Versión optimizada para alto rendimiento usando Vistas SQL
#
# 🛠️ REQUISITO SQL (Ejecutar en Supabase):
# CREATE OR REPLACE VIEW view_saldos_clientes AS
# SELECT c.id as cliente_id, c.nro_cliente, c.denominacion, c.limite_credito, c.estado,
# COALESCE(SUM(CASE WHEN o.tipo_movimiento = 'debito' THEN o.importe WHEN o.tipo_movimiento = 'credito' THEN -o.importe ELSE 0 END), 0) as saldo_actual
# FROM cc_clientes c LEFT JOIN cc_operaciones o ON c.id = o.cliente_id
# GROUP BY c.id, c.nro_cliente, c.denominacion, c.limite_credito, c.estado;
#
# 📅 Fecha: Diciembre 2025

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from supabase import create_client, Client
import pytz
import io

# Timezone Argentina
ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# ==================== CONSTANTES ====================
SUCURSAL_MINIMARKET_ID = 1
SUCURSAL_MINIMARKET_NOMBRE = "Sucursal 1 - Minimarket"

# Estados de cliente
ESTADOS_CLIENTE = {
    'activo': '🟢 Activo',
    'inactivo': '🟡 Inactivo',
    'suspendido': '🔴 Suspendido'
}

# Tipos de movimiento
TIPO_DEBITO = 'debito'   # Compras - Aumenta saldo
TIPO_CREDITO = 'credito'  # Pagos - Disminuye saldo

# ==================== DECORADOR DE ERRORES ====================
def manejar_error_db(mensaje_personalizado=None):
    """Decorador para manejar errores de base de datos."""
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = mensaje_personalizado or f"Error en {func.__name__}"
                st.error(f"❌ {error_msg}: {str(e)}")
                print(f"[ERROR CC] {func.__name__}: {str(e)}")
                return None
        return wrapper
    return decorador

# ==================== CONEXIÓN SUPABASE ====================
@st.cache_resource
def get_supabase_client():
    """Obtiene cliente de Supabase (singleton)."""
    if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        st.error("⚠️ Falta configurar las credenciales de Supabase")
        return None
    
    return create_client(url, key)

# ==================== FUNCIONES DE CLIENTES ====================

@st.cache_data(ttl=60)
@manejar_error_db("Error al cargar clientes")
def obtener_clientes(incluir_inactivos=False):
    """Obtiene lista de clientes."""
    supabase = get_supabase_client()
    query = supabase.table("cc_clientes").select("*").order("nro_cliente")
    
    if not incluir_inactivos:
        query = query.eq("estado", "activo")
    
    result = query.execute()
    return result.data if result.data else []

@st.cache_data(ttl=60)
@manejar_error_db("Error al buscar cliente")
def buscar_cliente_por_numero(nro_cliente):
    """Busca un cliente por su número."""
    supabase = get_supabase_client()
    result = supabase.table("cc_clientes")\
        .select("*")\
        .eq("nro_cliente", nro_cliente)\
        .execute()
    return result.data[0] if result.data else None

@st.cache_data(ttl=60)
@manejar_error_db("Error al buscar clientes")
def buscar_clientes_por_nombre(texto_busqueda):
    """Busca clientes por nombre/razón social (búsqueda parcial)."""
    supabase = get_supabase_client()
    result = supabase.table("cc_clientes")\
        .select("*")\
        .ilike("denominacion", f"%{texto_busqueda}%")\
        .eq("estado", "activo")\
        .order("denominacion")\
        .limit(20)\
        .execute()
    return result.data if result.data else []

@manejar_error_db("Error al obtener siguiente número de cliente")
def obtener_siguiente_nro_cliente():
    """Obtiene el siguiente número de cliente disponible."""
    supabase = get_supabase_client()
    result = supabase.table("cc_clientes")\
        .select("nro_cliente")\
        .order("nro_cliente", desc=True)\
        .limit(1)\
        .execute()
    
    if result.data:
        return result.data[0]['nro_cliente'] + 1
    return 1  # Primer cliente

@manejar_error_db("Error al crear cliente")
def crear_cliente(denominacion, telefono=None, email=None, limite_credito=None, observaciones=None):
    """Crea un nuevo cliente con número secuencial."""
    supabase = get_supabase_client()
    
    nro_cliente = obtener_siguiente_nro_cliente()
    
    data = {
        'nro_cliente': nro_cliente,
        'denominacion': denominacion.strip().upper(),
        'telefono': telefono.strip() if telefono else None,
        'email': email.strip().lower() if email else None,
        'limite_credito': limite_credito,
        'observaciones': observaciones,
        'estado': 'activo',
        'fecha_alta': datetime.now(ARGENTINA_TZ).isoformat()
    }
    
    result = supabase.table("cc_clientes").insert(data).execute()
    
    if result.data:
        st.cache_data.clear()
        return result.data[0]
    return None

@manejar_error_db("Error al actualizar cliente")
def actualizar_cliente(cliente_id, datos):
    """Actualiza datos de un cliente."""
    supabase = get_supabase_client()
    
    result = supabase.table("cc_clientes")\
        .update(datos)\
        .eq("id", cliente_id)\
        .execute()
    
    if result.data:
        st.cache_data.clear()
        return result.data[0]
    return None

# ==================== FUNCIONES DE OPERACIONES ====================

@st.cache_data(ttl=60)
@manejar_error_db("Error al cargar operaciones")
def obtener_operaciones_cliente(cliente_id, limite=100):
    """Obtiene historial de operaciones de un cliente."""
    supabase = get_supabase_client()
    result = supabase.table("cc_operaciones")\
        .select("*")\
        .eq("cliente_id", cliente_id)\
        .order("fecha", desc=True)\
        .order("created_at", desc=True)\
        .limit(limite)\
        .execute()
    return result.data if result.data else []

@st.cache_data(ttl=60)
@manejar_error_db("Error al cargar comprobantes pendientes")
def obtener_comprobantes_pendientes(cliente_id):
    """Obtiene comprobantes (facturas) pendientes de cancelación."""
    supabase = get_supabase_client()
    result = supabase.table("cc_operaciones")\
        .select("*")\
        .eq("cliente_id", cliente_id)\
        .eq("tipo_movimiento", TIPO_DEBITO)\
        .gt("saldo_pendiente", 0)\
        .order("fecha")\
        .order("nro_comprobante")\
        .execute()
    return result.data if result.data else []

@manejar_error_db("Error al calcular saldo individual")
def calcular_saldo_cliente(cliente_id):
    """
    Calcula el saldo actual de UN solo cliente.
    Usado para verificaciones rápidas (Compras/Pagos).
    """
    supabase = get_supabase_client()
    
    # Opción A: Usar la vista (filtrada por ID) - Más rápido si hay muchas operaciones
    try:
        result = supabase.table("view_saldos_clientes")\
            .select("saldo_actual")\
            .eq("cliente_id", cliente_id)\
            .execute()
        if result.data:
            return Decimal(str(result.data[0]['saldo_actual']))
        return Decimal('0.00')
    except:
        # Fallback a cálculo manual si la vista falla
        return Decimal('0.00')

@manejar_error_db("Error al registrar compra")
def registrar_compra(cliente_id, importe, nro_comprobante=None, observaciones=None, usuario=None):
    """Registra una compra (débito)."""
    supabase = get_supabase_client()
    
    data = {
        'sucursal_id': SUCURSAL_MINIMARKET_ID,
        'cliente_id': cliente_id,
        'tipo_movimiento': TIPO_DEBITO,
        'nro_comprobante': nro_comprobante.strip().upper() if nro_comprobante else None,
        'importe': float(importe),
        'saldo_pendiente': float(importe),
        'fecha': datetime.now(ARGENTINA_TZ).date().isoformat(),
        'observaciones': observaciones,
        'usuario': usuario,
        'created_at': datetime.now(ARGENTINA_TZ).isoformat()
    }
    
    result = supabase.table("cc_operaciones").insert(data).execute()
    
    if result.data:
        st.cache_data.clear()
        return result.data[0]
    return None

@manejar_error_db("Error al registrar pago")
def registrar_pago(cliente_id, importe_total, comprobantes_a_cancelar, nro_recibo=None, observaciones=None, usuario=None):
    """Registra un pago (crédito) y cancela comprobantes."""
    supabase = get_supabase_client()
    
    # 1. Crear el registro de pago
    data_pago = {
        'sucursal_id': SUCURSAL_MINIMARKET_ID,
        'cliente_id': cliente_id,
        'tipo_movimiento': TIPO_CREDITO,
        'nro_comprobante': nro_recibo.strip().upper() if nro_recibo else None,
        'importe': float(importe_total),
        'saldo_pendiente': 0,
        'fecha': datetime.now(ARGENTINA_TZ).date().isoformat(),
        'observaciones': observaciones,
        'usuario': usuario,
        'created_at': datetime.now(ARGENTINA_TZ).isoformat()
    }
    
    result_pago = supabase.table("cc_operaciones").insert(data_pago).execute()
    
    if not result_pago.data:
        return None
    
    pago_id = result_pago.data[0]['id']
    
    # 2. Actualizar saldos pendientes
    for comp in comprobantes_a_cancelar:
        operacion_id = comp['id']
        monto_aplicar = Decimal(str(comp['monto_aplicar']))
        
        op_actual = supabase.table("cc_operaciones")\
            .select("saldo_pendiente")\
            .eq("id", operacion_id)\
            .execute()
        
        if op_actual.data:
            saldo_actual = Decimal(str(op_actual.data[0]['saldo_pendiente']))
            nuevo_saldo = max(Decimal('0'), saldo_actual - monto_aplicar)
            
            supabase.table("cc_operaciones")\
                .update({'saldo_pendiente': float(nuevo_saldo)})\
                .eq("id", operacion_id)\
                .execute()
            
            detalle = {
                'pago_id': pago_id,
                'comprobante_id': operacion_id,
                'monto_aplicado': float(monto_aplicar)
            }
            supabase.table("cc_aplicaciones_pago").insert(detalle).execute()
    
    st.cache_data.clear()
    return result_pago.data[0]

# ==================== FUNCIONES DE IMPORTACIÓN ====================

@manejar_error_db("Error en importación")
def importar_clientes_excel(df, fecha_saldo_anterior, usuario):
    """Importa clientes y saldos iniciales."""
    supabase = get_supabase_client()
    
    resultados = {'exitosos': 0, 'errores': [], 'clientes_creados': []}
    df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]
    
    for idx, row in df.iterrows():
        try:
            denominacion = str(row.get('denominacion', '')).strip()
            if not denominacion:
                resultados['errores'].append(f"Fila {idx+2}: Denominación vacía")
                continue
            
            nro_cliente = row.get('nro_cliente')
            if pd.isna(nro_cliente) or nro_cliente == '':
                nro_cliente = obtener_siguiente_nro_cliente()
            else:
                nro_cliente = int(nro_cliente)
            
            data_cliente = {
                'nro_cliente': nro_cliente,
                'denominacion': denominacion.upper(),
                'telefono': str(row.get('telefono', '')).strip() if pd.notna(row.get('telefono')) else None,
                'email': str(row.get('email', '')).strip().lower() if pd.notna(row.get('email')) else None,
                'estado': 'activo',
                'fecha_alta': datetime.now(ARGENTINA_TZ).isoformat()
            }
            
            result_cliente = supabase.table("cc_clientes").insert(data_cliente).execute()
            
            if result_cliente.data:
                cliente_id = result_cliente.data[0]['id']
                resultados['clientes_creados'].append(nro_cliente)
                
                saldo_anterior = row.get('saldo_anterior', 0)
                if pd.notna(saldo_anterior) and float(saldo_anterior) > 0:
                    data_saldo = {
                        'sucursal_id': SUCURSAL_MINIMARKET_ID,
                        'cliente_id': cliente_id,
                        'tipo_movimiento': TIPO_DEBITO,
                        'nro_comprobante': 'SALDO_INICIAL',
                        'importe': float(saldo_anterior),
                        'saldo_pendiente': float(saldo_anterior),
                        'fecha': fecha_saldo_anterior.isoformat(),
                        'observaciones': f'Saldo anterior importado - {fecha_saldo_anterior}',
                        'usuario': usuario,
                        'es_saldo_inicial': True,
                        'created_at': datetime.now(ARGENTINA_TZ).isoformat()
                    }
                    supabase.table("cc_operaciones").insert(data_saldo).execute()
                
                resultados['exitosos'] += 1
            else:
                resultados['errores'].append(f"Fila {idx+2}: Error al crear cliente {denominacion}")
        
        except Exception as e:
            resultados['errores'].append(f"Fila {idx+2}: {str(e)}")
    
    st.cache_data.clear()
    return resultados

# ==================== FUNCIONES DE REPORTES (OPTIMIZADAS) ====================

@st.cache_data(ttl=60)
@manejar_error_db("Error al obtener resumen de saldos")
def obtener_resumen_saldos(incluir_inactivos=False):
    """
    Obtiene resumen de saldos utilizando la VISTA optimizada de base de datos.
    Reduce de N+1 consultas a 1 sola consulta.
    """
    supabase = get_supabase_client()
    
    # Consulta directa a la vista view_saldos_clientes
    query = supabase.table("view_saldos_clientes").select("*").order("denominacion")
    
    if not incluir_inactivos:
        query = query.eq("estado", "activo")
        
    result = query.execute()
    
    if not result.data:
        return []
    
    resumen = []
    for row in result.data:
        saldo = Decimal(str(row.get('saldo_actual', 0)))
        
        # Determinar estado del saldo para visualización
        if saldo > 0:
            estado_saldo = "🔴 Deudor"
        elif saldo < 0:
            estado_saldo = "🟢 A favor"
        else:
            estado_saldo = "⚪ Sin saldo"
        
        excede_limite = False
        limite = row.get('limite_credito')
        if limite and saldo > Decimal(str(limite)):
            excede_limite = True
        
        resumen.append({
            'nro_cliente': row['nro_cliente'],
            'denominacion': row['denominacion'],
            'saldo': float(saldo),
            'estado_saldo': estado_saldo,
            'limite_credito': limite,
            'excede_limite': excede_limite,
            'cliente_id': row['cliente_id'],
            'estado': row.get('estado', 'activo') # Para filtros internos
        })
    
    return resumen

@manejar_error_db("Error al generar estado de cuenta")
def generar_estado_cuenta(cliente_id, fecha_desde=None, fecha_hasta=None):
    """Genera estado de cuenta detallado de un cliente."""
    supabase = get_supabase_client()
    
    cliente = supabase.table("cc_clientes").select("*").eq("id", cliente_id).execute()
    if not cliente.data:
        return None
    
    cliente_data = cliente.data[0]
    
    query = supabase.table("cc_operaciones")\
        .select("*")\
        .eq("cliente_id", cliente_id)\
        .order("fecha")\
        .order("created_at")
    
    if fecha_desde:
        query = query.gte("fecha", fecha_desde.isoformat())
    if fecha_hasta:
        query = query.lte("fecha", fecha_hasta.isoformat())
    
    operaciones = query.execute()
    
    movimientos = []
    saldo_corrido = Decimal('0.00')
    
    for op in operaciones.data or []:
        importe = Decimal(str(op['importe']))
        
        if op['tipo_movimiento'] == TIPO_DEBITO:
            saldo_corrido += importe
            tipo_display = "COMPRA"
        else:
            saldo_corrido -= importe
            tipo_display = "PAGO"
        
        movimientos.append({
            'fecha': op['fecha'],
            'tipo': tipo_display,
            'comprobante': op.get('nro_comprobante', '-'),
            'debe': float(importe) if op['tipo_movimiento'] == TIPO_DEBITO else 0,
            'haber': float(importe) if op['tipo_movimiento'] == TIPO_CREDITO else 0,
            'saldo': float(saldo_corrido),
            'observaciones': op.get('observaciones', '')
        })
    
    return {
        'cliente': cliente_data,
        'movimientos': movimientos,
        'saldo_actual': float(saldo_corrido)
    }

# ==================== INTERFAZ PRINCIPAL ====================

def main():
    """Función principal del módulo de Cuentas Corrientes."""
    
    st.header("💳 Cuentas Corrientes de Clientes")
    st.caption(f"📍 {SUCURSAL_MINIMARKET_NOMBRE}")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📝 Cargar Compra",
        "💰 Registrar Pago",
        "👥 Clientes",
        "📊 Estado de Cuenta",
        "📥 Importar/Exportar"
    ])
    
    # ==================== TAB 1: CARGAR COMPRA ====================
    with tab1:
        st.subheader("📝 Cargar Compra (Débito)")
        
        col_busq1, col_busq2 = st.columns([1, 2])
        with col_busq1:
            metodo_busqueda = st.radio("Buscar cliente por:", ["Número", "Nombre"], horizontal=True, key="metodo_busq_compra")
        
        cliente_seleccionado = None
        with col_busq2:
            if metodo_busqueda == "Número":
                nro_cliente_input = st.number_input("Nro. Cliente", min_value=1, max_value=9999, step=1, key="nro_cliente_compra")
                if nro_cliente_input:
                    cliente_seleccionado = buscar_cliente_por_numero(nro_cliente_input)
                    if not cliente_seleccionado:
                        st.warning(f"⚠️ No existe cliente con número {nro_cliente_input}")
            else:
                texto_busqueda = st.text_input("Buscar por nombre/razón social", placeholder="Escriba al menos 3 caracteres...", key="texto_busq_compra")
                if texto_busqueda and len(texto_busqueda) >= 3:
                    clientes_encontrados = buscar_clientes_por_nombre(texto_busqueda)
                    if clientes_encontrados:
                        opciones = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_encontrados}
                        seleccion = st.selectbox("Seleccionar cliente", options=list(opciones.keys()), key="select_cliente_compra")
                        if seleccion:
                            cliente_seleccionado = opciones[seleccion]
                    else:
                        st.warning("No se encontraron clientes")
        
        if cliente_seleccionado:
            # Uso de la función optimizada o individual
            saldo_actual = calcular_saldo_cliente(cliente_seleccionado['id'])
            
            st.markdown("---")
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1: st.metric("Cliente", f"{cliente_seleccionado['nro_cliente']:04d}")
            with col_info2: st.metric("Denominación", cliente_seleccionado['denominacion'])
            with col_info3:
                color_saldo = "🔴" if saldo_actual > 0 else "🟢" if saldo_actual < 0 else "⚪"
                st.metric("Saldo Actual", f"{color_saldo} ${saldo_actual:,.2f}")
            st.markdown("---")
            
            with st.form("form_compra", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    nro_comprobante = st.text_input("Nro. Comprobante (opcional)", placeholder="Ej: FC-A-0001-00001234")
                with col2:
                    importe = st.number_input("Importe ($) *", min_value=0.01, step=0.01, format="%.2f")
                
                observaciones = st.text_area("Observaciones (opcional)", height=80)
                submitted = st.form_submit_button("💾 Registrar Compra", use_container_width=True, type="primary")
                
                if submitted:
                    if importe > 0:
                        nuevo_saldo = saldo_actual + Decimal(str(importe))
                        limite = cliente_seleccionado.get('limite_credito')
                        if limite and nuevo_saldo > Decimal(str(limite)):
                            st.warning(f"⚠️ Excede límite de crédito (${limite:,.2f}). Saldo resultante: ${nuevo_saldo:,.2f}")
                        
                        usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                        resultado = registrar_compra(cliente_seleccionado['id'], importe, nro_comprobante, observaciones, usuario)
                        
                        if resultado:
                            st.success(f"✅ Compra registrada. Nuevo saldo: ${nuevo_saldo:,.2f}")
                            st.balloons()
                        else:
                            st.error("❌ Error al registrar la compra")
    
    # ==================== TAB 2: REGISTRAR PAGO ====================
    with tab2:
        st.subheader("💰 Registrar Pago (Crédito)")
        
        col_busq1, col_busq2 = st.columns([1, 2])
        with col_busq1:
            metodo_busqueda_pago = st.radio("Buscar cliente por:", ["Número", "Nombre"], horizontal=True, key="metodo_busq_pago")
        
        cliente_pago = None
        with col_busq2:
            if metodo_busqueda_pago == "Número":
                nro_cliente_pago = st.number_input("Nro. Cliente", min_value=1, max_value=9999, step=1, key="nro_cliente_pago")
                if nro_cliente_pago:
                    cliente_pago = buscar_cliente_por_numero(nro_cliente_pago)
                    if not cliente_pago:
                        st.warning(f"⚠️ No existe cliente con número {nro_cliente_pago}")
            else:
                texto_busqueda_pago = st.text_input("Buscar por nombre/razón social", placeholder="Escriba al menos 3 caracteres...", key="texto_busq_pago")
                if texto_busqueda_pago and len(texto_busqueda_pago) >= 3:
                    clientes_encontrados_pago = buscar_clientes_por_nombre(texto_busqueda_pago)
                    if clientes_encontrados_pago:
                        opciones_pago = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_encontrados_pago}
                        seleccion_pago = st.selectbox("Seleccionar cliente", options=list(opciones_pago.keys()), key="select_cliente_pago")
                        if seleccion_pago:
                            cliente_pago = opciones_pago[seleccion_pago]
        
        if cliente_pago:
            saldo_cliente = calcular_saldo_cliente(cliente_pago['id'])
            
            st.markdown("---")
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1: st.metric("Cliente", f"{cliente_pago['nro_cliente']:04d}")
            with col_info2: st.metric("Denominación", cliente_pago['denominacion'])
            with col_info3:
                color_saldo = "🔴" if saldo_cliente > 0 else "🟢" if saldo_cliente < 0 else "⚪"
                st.metric("Saldo a Pagar", f"{color_saldo} ${saldo_cliente:,.2f}")
            
            if saldo_cliente <= 0:
                st.info("ℹ️ Este cliente no tiene saldo pendiente")
            else:
                st.markdown("---")
                comprobantes_pendientes = obtener_comprobantes_pendientes(cliente_pago['id'])
                
                if 'comprobantes_seleccionados' not in st.session_state:
                    st.session_state.comprobantes_seleccionados = {}
                
                col_pend, col_cancel = st.columns(2)
                
                with col_pend:
                    st.markdown("### 📋 Comprobantes Pendientes")
                    if comprobantes_pendientes:
                        for comp in comprobantes_pendientes:
                            comp_key = f"comp_{comp['id']}"
                            col_check, col_data = st.columns([0.15, 0.85])
                            with col_check:
                                seleccionado = st.checkbox("", key=comp_key, value=comp['id'] in st.session_state.comprobantes_seleccionados)
                            with col_data:
                                st.markdown(f"**{comp['fecha']}** | {comp.get('nro_comprobante', 'S/N')} | **${comp['saldo_pendiente']:,.2f}**")
                            
                            if seleccionado:
                                if comp['id'] not in st.session_state.comprobantes_seleccionados:
                                    st.session_state.comprobantes_seleccionados[comp['id']] = {
                                        'id': comp['id'], 'fecha': comp['fecha'],
                                        'nro_comprobante': comp.get('nro_comprobante', 'S/N'),
                                        'saldo_pendiente': comp['saldo_pendiente'],
                                        'monto_aplicar': comp['saldo_pendiente']
                                    }
                            else:
                                if comp['id'] in st.session_state.comprobantes_seleccionados:
                                    del st.session_state.comprobantes_seleccionados[comp['id']]
                        
                        total_pendiente = sum(c['saldo_pendiente'] for c in comprobantes_pendientes)
                        st.markdown(f"**TOTAL PENDIENTE: ${total_pendiente:,.2f}**")
                    else:
                        st.info("No hay comprobantes pendientes")
                
                with col_cancel:
                    st.markdown("### ✅ Comprobantes a Cancelar")
                    if st.session_state.comprobantes_seleccionados:
                        total_a_cancelar = Decimal('0')
                        for comp_id, comp_data in st.session_state.comprobantes_seleccionados.items():
                            st.markdown(f"📄 **{comp_data['fecha']}** | {comp_data['nro_comprobante']} | ${comp_data['saldo_pendiente']:,.2f}")
                            monto_aplicar = st.number_input("Monto a aplicar", min_value=0.01, max_value=float(comp_data['saldo_pendiente']), value=float(comp_data['saldo_pendiente']), step=0.01, key=f"monto_aplicar_{comp_id}")
                            st.session_state.comprobantes_seleccionados[comp_id]['monto_aplicar'] = monto_aplicar
                            total_a_cancelar += Decimal(str(monto_aplicar))
                            st.markdown("---")
                        
                        st.markdown(f"### TOTAL A CANCELAR: ${total_a_cancelar:,.2f}")
                        
                        st.markdown("---")
                        nro_recibo = st.text_input("Nro. Recibo (opcional)", placeholder="Ej: REC-0001", key="nro_recibo_pago")
                        obs_pago = st.text_area("Observaciones", height=60, key="obs_pago")
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("🗑️ Limpiar", use_container_width=True):
                                st.session_state.comprobantes_seleccionados = {}
                                st.rerun()
                        with col_btn2:
                            if st.button("💾 Confirmar Pago", type="primary", use_container_width=True):
                                usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                                comps_cancelar = [{'id': k, 'monto_aplicar': v['monto_aplicar']} for k, v in st.session_state.comprobantes_seleccionados.items()]
                                
                                resultado = registrar_pago(cliente_pago['id'], float(total_a_cancelar), comps_cancelar, nro_recibo, obs_pago, usuario)
                                if resultado:
                                    nuevo_saldo = saldo_cliente - total_a_cancelar
                                    st.success(f"✅ Pago registrado. Nuevo saldo: ${nuevo_saldo:,.2f}")
                                    st.session_state.comprobantes_seleccionados = {}
                                    st.balloons()
                                    st.rerun()
                                else:
                                    st.error("❌ Error al registrar el pago")
    
    # ==================== TAB 3: CLIENTES (OPTIMIZADO) ====================
    with tab3:
        st.subheader("👥 Gestión de Clientes")
        subtab1, subtab2, subtab3 = st.tabs(["📋 Lista", "➕ Nuevo Cliente", "✏️ Editar"])
        
        with subtab1:
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                buscar_cliente_lista = st.text_input("🔍 Buscar cliente", placeholder="Nombre o número...", key="buscar_cliente_lista")
            with col_f2:
                incluir_inactivos = st.checkbox("Incluir inactivos", key="incluir_inactivos")
            
            # --- OPTIMIZACIÓN AQUÍ ---
            # 1. Obtenemos clientes
            clientes = obtener_clientes(incluir_inactivos=incluir_inactivos)
            
            # 2. Obtenemos saldos en lote desde la VISTA (mucho más rápido que el bucle)
            resumen_saldos = obtener_resumen_saldos(incluir_inactivos=incluir_inactivos)
            # Creamos un mapa {cliente_id: saldo}
            mapa_saldos = {item['cliente_id']: item['saldo'] for item in resumen_saldos}
            
            if buscar_cliente_lista:
                busq_lower = buscar_cliente_lista.lower()
                clientes = [c for c in clientes if busq_lower in c['denominacion'].lower() or busq_lower in str(c['nro_cliente'])]
            
            if clientes:
                df_clientes = pd.DataFrame(clientes)
                df_clientes['nro_cliente'] = df_clientes['nro_cliente'].apply(lambda x: f"{x:04d}")
                df_clientes['estado_display'] = df_clientes['estado'].map(ESTADOS_CLIENTE)
                
                # 3. Asignar saldo usando el mapa (instantáneo)
                df_clientes['saldo'] = df_clientes['id'].apply(lambda x: mapa_saldos.get(x, 0.0))
                
                cols_mostrar = ['nro_cliente', 'denominacion', 'telefono', 'email', 'saldo', 'estado_display']
                df_display = df_clientes[cols_mostrar].copy()
                df_display.columns = ['Nro.', 'Denominación', 'Teléfono', 'Email', 'Saldo', 'Estado']
                
                st.dataframe(df_display, use_container_width=True, hide_index=True, column_config={"Saldo": st.column_config.NumberColumn(format="$ %.2f")})
                st.caption(f"Total: {len(clientes)} clientes")
            else:
                st.info("No se encontraron clientes")
        
        with subtab2:
            st.markdown("#### ➕ Nuevo Cliente")
            with st.form("form_nuevo_cliente", clear_on_submit=True):
                siguiente_nro = obtener_siguiente_nro_cliente()
                st.info(f"📌 Número de cliente asignado: **{siguiente_nro:04d}**")
                
                col1, col2 = st.columns(2)
                with col1:
                    denominacion_nueva = st.text_input("Nombre/Razón Social *")
                    telefono_nuevo = st.text_input("Teléfono")
                with col2:
                    email_nuevo = st.text_input("Email")
                    limite_credito_nuevo = st.number_input("Límite de Crédito ($)", min_value=0.0, step=1000.0)
                
                obs_cliente = st.text_area("Observaciones", height=80)
                submitted_cliente = st.form_submit_button("💾 Crear Cliente", use_container_width=True, type="primary")
                
                if submitted_cliente:
                    if denominacion_nueva:
                        resultado = crear_cliente(denominacion_nueva, telefono_nuevo, email_nuevo, limite_credito_nuevo, obs_cliente)
                        if resultado:
                            st.success(f"✅ Cliente creado: {resultado['nro_cliente']:04d}")
                            st.balloons()
                        else:
                            st.error("❌ Error al crear cliente")
                    else:
                        st.error("⚠️ Denominación obligatoria")
        
        with subtab3:
            st.markdown("#### ✏️ Editar Cliente")
            nro_editar = st.number_input("Nro. Cliente a editar", min_value=1, step=1, key="nro_editar")
            if nro_editar:
                cliente_editar = buscar_cliente_por_numero(nro_editar)
                if cliente_editar:
                    with st.form("form_editar_cliente"):
                        col1, col2 = st.columns(2)
                        with col1:
                            denominacion_edit = st.text_input("Nombre/Razón Social *", value=cliente_editar['denominacion'])
                            telefono_edit = st.text_input("Teléfono", value=cliente_editar.get('telefono', '') or '')
                            estado_edit = st.selectbox("Estado", options=['activo', 'inactivo', 'suspendido'], index=['activo', 'inactivo', 'suspendido'].index(cliente_editar.get('estado', 'activo')))
                        with col2:
                            email_edit = st.text_input("Email", value=cliente_editar.get('email', '') or '')
                            limite_edit = st.number_input("Límite de Crédito ($)", min_value=0.0, value=float(cliente_editar.get('limite_credito', 0) or 0), step=1000.0)
                        
                        obs_edit = st.text_area("Observaciones", value=cliente_editar.get('observaciones', '') or '', height=80)
                        submitted_edit = st.form_submit_button("💾 Guardar Cambios", use_container_width=True, type="primary")
                        
                        if submitted_edit:
                            datos_update = {'denominacion': denominacion_edit.strip().upper(), 'telefono': telefono_edit, 'email': email_edit, 'limite_credito': limite_edit, 'estado': estado_edit, 'observaciones': obs_edit}
                            if actualizar_cliente(cliente_editar['id'], datos_update):
                                st.success("✅ Cliente actualizado")
                            else:
                                st.error("❌ Error al actualizar")
                else:
                    st.warning("⚠️ No existe cliente")

    # ==================== TAB 4: ESTADO DE CUENTA ====================
    with tab4:
        st.subheader("📊 Estados de Cuenta")
        subtab_individual, subtab_general = st.tabs(["👤 Estado Individual", "📋 Saldos de Todos los Clientes"])
        
        with subtab_individual:
            col1, col2, col3 = st.columns([2, 1, 1])
            clientes_lista = obtener_clientes()
            opciones_ec = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_lista}
            
            with col1:
                cliente_ec_seleccion = st.selectbox("Seleccionar cliente", options=[""] + list(opciones_ec.keys()), key="cliente_estado_cuenta")
            with col2:
                fecha_desde_ec = st.date_input("Desde", value=date.today().replace(day=1))
            with col3:
                fecha_hasta_ec = st.date_input("Hasta", value=date.today())
            
            if cliente_ec_seleccion and cliente_ec_seleccion in opciones_ec:
                cliente_ec = opciones_ec[cliente_ec_seleccion]
                estado_cuenta = generar_estado_cuenta(cliente_ec['id'], fecha_desde_ec, fecha_hasta_ec)
                
                if estado_cuenta:
                    st.markdown("---")
                    col_ec1, col_ec2, col_ec3 = st.columns(3)
                    with col_ec1: st.markdown(f"**Cliente:** {estado_cuenta['cliente']['nro_cliente']:04d}")
                    with col_ec2: st.markdown(f"**{estado_cuenta['cliente']['denominacion']}**")
                    with col_ec3:
                        saldo = estado_cuenta['saldo_actual']
                        color = "🔴" if saldo > 0 else "🟢" if saldo < 0 else "⚪"
                        st.markdown(f"**Saldo: {color} ${saldo:,.2f}**")
                    
                    st.markdown("---")
                    if estado_cuenta['movimientos']:
                        df_mov = pd.DataFrame(estado_cuenta['movimientos'])
                        st.dataframe(df_mov, use_container_width=True, hide_index=True, column_config={"debe": st.column_config.NumberColumn(format="$ %.2f"), "haber": st.column_config.NumberColumn(format="$ %.2f"), "saldo": st.column_config.NumberColumn(format="$ %.2f")})
                        
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_mov.to_excel(writer, sheet_name='Estado de Cuenta', index=False)
                        st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name=f"estado_cuenta_{cliente_ec['nro_cliente']:04d}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    else:
                        st.info("No hay movimientos")
        
        with subtab_general:
            st.markdown("#### 📋 Saldos de Cuenta Corriente - Todos los Clientes")
            col_filtro1, col_filtro2, col_filtro3 = st.columns([1, 1, 2])
            with col_filtro1:
                filtro_saldo = st.selectbox("Filtrar por saldo", ["Todos", "Solo deudores (saldo > 0)", "Solo con saldo a favor", "Solo con saldo cero"])
            with col_filtro2:
                ordenar_por = st.selectbox("Ordenar por", ["Nro. Cliente", "Denominación", "Saldo (mayor a menor)", "Saldo (menor a mayor)"])
            with col_filtro3:
                if st.button("🔄 Actualizar Saldos"):
                    st.cache_data.clear()
                    st.rerun()
            
            # --- OPTIMIZACIÓN: Usa la función basada en Vistas ---
            resumen_saldos = obtener_resumen_saldos(incluir_inactivos=True)
            
            if resumen_saldos:
                df_saldos = pd.DataFrame(resumen_saldos)
                
                if filtro_saldo == "Solo deudores (saldo > 0)":
                    df_saldos = df_saldos[df_saldos['saldo'] > 0]
                elif filtro_saldo == "Solo con saldo a favor":
                    df_saldos = df_saldos[df_saldos['saldo'] < 0]
                elif filtro_saldo == "Solo con saldo cero":
                    df_saldos = df_saldos[df_saldos['saldo'] == 0]
                
                if ordenar_por == "Nro. Cliente":
                    df_saldos = df_saldos.sort_values('nro_cliente')
                elif ordenar_por == "Denominación":
                    df_saldos = df_saldos.sort_values('denominacion')
                elif ordenar_por == "Saldo (mayor a menor)":
                    df_saldos = df_saldos.sort_values('saldo', ascending=False)
                elif ordenar_por == "Saldo (menor a mayor)":
                    df_saldos = df_saldos.sort_values('saldo', ascending=True)
                
                st.markdown("---")
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1: st.metric("Total a Cobrar", f"${df_saldos[df_saldos['saldo'] > 0]['saldo'].sum():,.2f}")
                with col_m2: st.metric("Total a Favor", f"${abs(df_saldos[df_saldos['saldo'] < 0]['saldo'].sum()):,.2f}")
                with col_m3: st.metric("Deudores", f"{len(df_saldos[df_saldos['saldo'] > 0])}")
                with col_m4: st.metric("Total", f"{len(df_saldos)}")
                st.markdown("---")
                
                df_display = df_saldos[['nro_cliente', 'denominacion', 'saldo', 'estado_saldo', 'limite_credito', 'excede_limite']].copy()
                df_display['nro_cliente'] = df_display['nro_cliente'].apply(lambda x: f"{x:04d}")
                
                st.dataframe(df_display, use_container_width=True, hide_index=True, column_config={"saldo": st.column_config.NumberColumn(format="$ %.2f"), "limite_credito": st.column_config.NumberColumn(format="$ %.2f")})
                
                output_general = io.BytesIO()
                with pd.ExcelWriter(output_general, engine='openpyxl') as writer:
                    df_saldos.to_excel(writer, sheet_name='Saldos', index=False)
                st.download_button("📥 Exportar a Excel", data=output_general.getvalue(), file_name=f"saldos_cc_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.info("No hay datos")

    # ==================== TAB 5: IMPORTAR/EXPORTAR ====================
    with tab5:
        st.subheader("📥 Importar / 📤 Exportar")
        subtab_imp, subtab_exp = st.tabs(["📥 Importar", "📤 Exportar"])
        
        with subtab_imp:
            archivo_excel = st.file_uploader("Excel (denominacion, nro_cliente, telefono, saldo_anterior)", type=['xlsx'])
            fecha_saldo = st.date_input("Fecha saldo anterior", value=date.today())
            
            if archivo_excel and st.button("🚀 Iniciar Importación"):
                try:
                    df_import = pd.read_excel(archivo_excel)
                    usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                    resultados = importar_clientes_excel(df_import, fecha_saldo, usuario)
                    st.success(f"✅ Completado: {resultados['exitosos']} creados")
                    if resultados['errores']:
                        st.error(f"⚠️ Errores: {len(resultados['errores'])}")
                        st.write(resultados['errores'])
                except Exception as e:
                    st.error(f"Error: {e}")

        with subtab_exp:
            if st.button("📥 Exportar Todo (Operaciones)"):
                supabase = get_supabase_client()
                result = supabase.table("cc_operaciones").select("*, cc_clientes(nro_cliente, denominacion)").order("fecha", desc=True).execute()
                if result.data:
                    df_ops = pd.DataFrame(result.data)
                    df_ops['cliente'] = df_ops['cc_clientes'].apply(lambda x: f"{x['nro_cliente']:04d} - {x['denominacion']}" if x else '')
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_ops.to_excel(writer, sheet_name='Operaciones', index=False)
                    st.download_button("📥 Descargar", data=output.getvalue(), file_name=f"operaciones_cc_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    main()
