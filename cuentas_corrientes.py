# cuentas_corrientes.py - MÓDULO DE CUENTAS CORRIENTES v2.0 OPTIMIZADO
#
# 🚀 OPTIMIZACIONES IMPLEMENTADAS:
# ✅ Usa vista SQL vw_cc_saldos_clientes (evita problema N+1)
# ✅ Caché selectivo con limpiar_cache_cc() (no borra caché de otros módulos)
# ✅ Consultas batch para pagos múltiples
# ✅ Sin st.rerun() innecesarios después de guardar
# ✅ TTL de caché optimizado (60 segundos)
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

ESTADOS_CLIENTE = {
    'activo': '🟢 Activo',
    'inactivo': '🟡 Inactivo',
    'suspendido': '🔴 Suspendido'
}

TIPO_DEBITO = 'debito'
TIPO_CREDITO = 'credito'

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

# ==================== FUNCIÓN PARA LIMPIAR CACHÉ (SOLO CC) ====================
def limpiar_cache_cc():
    """
    Limpia SOLO las funciones cacheadas de Cuentas Corrientes.
    NO afecta el caché de cajas_diarias ni otros módulos.
    """
    try:
        obtener_clientes.clear()
        buscar_cliente_por_numero.clear()
        buscar_clientes_por_nombre.clear()
        obtener_operaciones_cliente.clear()
        obtener_comprobantes_pendientes.clear()
        obtener_resumen_saldos.clear()
        obtener_saldo_cliente.clear()
    except Exception:
        pass

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
    """Busca clientes por nombre/razón social."""
    supabase = get_supabase_client()
    result = supabase.table("cc_clientes")\
        .select("*")\
        .ilike("denominacion", f"%{texto_busqueda}%")\
        .eq("estado", "activo")\
        .order("denominacion")\
        .limit(20)\
        .execute()
    return result.data if result.data else []

@manejar_error_db("Error al obtener siguiente número")
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
    return 1

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
        limpiar_cache_cc()
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
        limpiar_cache_cc()
        return result.data[0]
    return None

# ==================== FUNCIONES OPTIMIZADAS CON VISTA SQL ====================

@st.cache_data(ttl=60)
@manejar_error_db("Error al obtener saldo")
def obtener_saldo_cliente(cliente_id):
    """
    Obtiene el saldo de UN cliente usando la vista optimizada.
    Para consultas individuales (Tab Compra/Pago).
    """
    supabase = get_supabase_client()
    result = supabase.table("vw_cc_saldos_clientes")\
        .select("saldo_actual")\
        .eq("cliente_id", cliente_id)\
        .execute()
    
    if result.data:
        return Decimal(str(result.data[0]['saldo_actual']))
    return Decimal('0.00')

@st.cache_data(ttl=60)
@manejar_error_db("Error al obtener resumen de saldos")
def obtener_resumen_saldos():
    """
    🚀 OPTIMIZADO: Obtiene TODOS los saldos en UNA sola consulta.
    Usa la vista SQL vw_cc_saldos_clientes que calcula todo en la BD.
    Esto elimina el problema N+1 (de 179 consultas a 1).
    """
    supabase = get_supabase_client()
    
    # UNA sola consulta que trae todo calculado
    result = supabase.table("vw_cc_saldos_clientes")\
        .select("*")\
        .eq("estado", "activo")\
        .order("denominacion")\
        .execute()
    
    if not result.data:
        return []
    
    resumen = []
    for row in result.data:
        saldo = Decimal(str(row['saldo_actual']))
        
        # Determinar estado visual
        if saldo > 0:
            estado_saldo = "🔴 Deudor"
        elif saldo < 0:
            estado_saldo = "🟢 A favor"
        else:
            estado_saldo = "⚪ Sin saldo"
        
        # Verificar límite
        excede_limite = False
        if row.get('limite_credito') and saldo > Decimal(str(row['limite_credito'])):
            excede_limite = True
        
        resumen.append({
            'nro_cliente': row['nro_cliente'],
            'denominacion': row['denominacion'],
            'saldo': float(saldo),
            'estado_saldo': estado_saldo,
            'limite_credito': row.get('limite_credito'),
            'excede_limite': excede_limite,
            'cliente_id': row['cliente_id'],
            'facturas_pendientes': row.get('facturas_pendientes', 0),
            'ultima_operacion': row.get('ultima_operacion')
        })
    
    return resumen

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
    """Obtiene facturas pendientes de cancelación."""
    supabase = get_supabase_client()
    result = supabase.table("cc_operaciones")\
        .select("*")\
        .eq("cliente_id", cliente_id)\
        .eq("tipo_movimiento", TIPO_DEBITO)\
        .gt("saldo_pendiente", 0)\
        .order("fecha")\
        .execute()
    return result.data if result.data else []

@manejar_error_db("Error al registrar compra")
def registrar_compra(cliente_id, importe, nro_comprobante=None, observaciones=None, usuario=None):
    """Registra una compra (débito) en la cuenta corriente."""
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
        limpiar_cache_cc()
        return result.data[0]
    return None

@manejar_error_db("Error al registrar pago")
def registrar_pago(cliente_id, importe_total, comprobantes_a_cancelar, nro_recibo=None, observaciones=None, usuario=None):
    """
    🚀 OPTIMIZADO: Registra pago con menos consultas.
    - 1 consulta para insertar pago
    - 1 consulta para obtener saldos actuales
    - N actualizaciones (inevitable por limitación de Supabase)
    - 1 insert batch para detalles
    """
    supabase = get_supabase_client()
    
    # 1. Crear registro de pago
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
    
    # 2. Obtener saldos actuales en UNA consulta
    ids_comprobantes = [comp['id'] for comp in comprobantes_a_cancelar]
    
    if ids_comprobantes:
        saldos_result = supabase.table("cc_operaciones")\
            .select("id, saldo_pendiente")\
            .in_("id", ids_comprobantes)\
            .execute()
        
        saldos_dict = {op['id']: Decimal(str(op['saldo_pendiente'])) 
                       for op in (saldos_result.data or [])}
        
        # 3. Preparar batch de detalles
        detalles_batch = []
        
        for comp in comprobantes_a_cancelar:
            op_id = comp['id']
            monto = Decimal(str(comp['monto_aplicar']))
            saldo_actual = saldos_dict.get(op_id, Decimal('0'))
            nuevo_saldo = max(Decimal('0'), saldo_actual - monto)
            
            # Actualizar saldo (individual por limitación de Supabase)
            supabase.table("cc_operaciones")\
                .update({'saldo_pendiente': float(nuevo_saldo)})\
                .eq("id", op_id)\
                .execute()
            
            detalles_batch.append({
                'pago_id': pago_id,
                'comprobante_id': op_id,
                'monto_aplicado': float(monto)
            })
        
        # 4. Insert batch de detalles
        if detalles_batch:
            supabase.table("cc_aplicaciones_pago").insert(detalles_batch).execute()
    
    limpiar_cache_cc()
    return result_pago.data[0]

# ==================== FUNCIONES DE REPORTES ====================

@manejar_error_db("Error al generar estado de cuenta")
def generar_estado_cuenta(cliente_id, fecha_desde=None, fecha_hasta=None):
    """Genera estado de cuenta detallado de un cliente."""
    supabase = get_supabase_client()
    
    # Datos del cliente
    cliente = supabase.table("cc_clientes")\
        .select("*")\
        .eq("id", cliente_id)\
        .execute()
    
    if not cliente.data:
        return None
    
    cliente_data = cliente.data[0]
    
    # Operaciones
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
    
    # Calcular saldo corrido
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

# ==================== FUNCIONES DE IMPORTACIÓN ====================

@manejar_error_db("Error en importación")
def importar_clientes_excel(df, fecha_saldo_anterior, usuario):
    """Importa clientes desde Excel."""
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
                        'observaciones': f'Saldo anterior importado',
                        'usuario': usuario,
                        'es_saldo_inicial': True,
                        'created_at': datetime.now(ARGENTINA_TZ).isoformat()
                    }
                    supabase.table("cc_operaciones").insert(data_saldo).execute()
                
                resultados['exitosos'] += 1
        except Exception as e:
            resultados['errores'].append(f"Fila {idx+2}: {str(e)}")
    
    limpiar_cache_cc()
    return resultados

# ==================== INTERFAZ PRINCIPAL ====================

def main():
    """Función principal del módulo de Cuentas Corrientes."""
    
    st.header("💳 Cuentas Corrientes de Clientes")
    st.caption(f"📍 {SUCURSAL_MINIMARKET_NOMBRE}")
    
    # Tabs
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
            metodo_busqueda = st.radio(
                "Buscar cliente por:",
                ["Número", "Nombre"],
                horizontal=True,
                key="metodo_busq_compra"
            )
        
        cliente_seleccionado = None
        
        with col_busq2:
            if metodo_busqueda == "Número":
                nro_cliente_input = st.number_input(
                    "Nro. Cliente",
                    min_value=1,
                    max_value=9999,
                    step=1,
                    key="nro_cliente_compra"
                )
                if nro_cliente_input:
                    cliente_seleccionado = buscar_cliente_por_numero(nro_cliente_input)
                    if not cliente_seleccionado:
                        st.warning(f"⚠️ No existe cliente con número {nro_cliente_input}")
            else:
                texto_busqueda = st.text_input(
                    "Buscar por nombre",
                    placeholder="Escriba al menos 3 caracteres...",
                    key="texto_busq_compra"
                )
                if texto_busqueda and len(texto_busqueda) >= 3:
                    clientes_encontrados = buscar_clientes_por_nombre(texto_busqueda)
                    if clientes_encontrados:
                        opciones = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_encontrados}
                        seleccion = st.selectbox("Seleccionar cliente", list(opciones.keys()), key="select_cliente_compra")
                        if seleccion:
                            cliente_seleccionado = opciones[seleccion]
                    else:
                        st.warning("No se encontraron clientes")
        
        if cliente_seleccionado:
            saldo_actual = obtener_saldo_cliente(cliente_seleccionado['id'])
            
            st.markdown("---")
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                st.metric("Cliente", f"{cliente_seleccionado['nro_cliente']:04d}")
            with col_info2:
                st.metric("Denominación", cliente_seleccionado['denominacion'])
            with col_info3:
                color = "🔴" if saldo_actual > 0 else "🟢" if saldo_actual < 0 else "⚪"
                st.metric("Saldo Actual", f"{color} ${saldo_actual:,.2f}")
            
            st.markdown("---")
            
            with st.form("form_compra", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    nro_comprobante = st.text_input(
                        "Nro. Comprobante (opcional)",
                        placeholder="Ej: FC-A-0001-00001234"
                    )
                
                with col2:
                    importe = st.number_input(
                        "Importe ($) *",
                        min_value=0.01,
                        step=0.01,
                        format="%.2f"
                    )
                
                observaciones = st.text_area("Observaciones (opcional)", height=80)
                
                submitted = st.form_submit_button("💾 Registrar Compra", use_container_width=True, type="primary")
                
                if submitted and importe > 0:
                    nuevo_saldo = saldo_actual + Decimal(str(importe))
                    limite = cliente_seleccionado.get('limite_credito')
                    
                    if limite and nuevo_saldo > Decimal(str(limite)):
                        st.warning(f"⚠️ Excede límite de crédito (${limite:,.2f})")
                    
                    usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                    resultado = registrar_compra(
                        cliente_id=cliente_seleccionado['id'],
                        importe=importe,
                        nro_comprobante=nro_comprobante,
                        observaciones=observaciones,
                        usuario=usuario
                    )
                    
                    if resultado:
                        st.success(f"✅ Compra registrada. Nuevo saldo: ${nuevo_saldo:,.2f}")
                        st.balloons()
    
    # ==================== TAB 2: REGISTRAR PAGO ====================
    with tab2:
        st.subheader("💰 Registrar Pago (Crédito)")
        
        col_busq1, col_busq2 = st.columns([1, 2])
        
        with col_busq1:
            metodo_busqueda_pago = st.radio(
                "Buscar cliente por:",
                ["Número", "Nombre"],
                horizontal=True,
                key="metodo_busq_pago"
            )
        
        cliente_pago = None
        
        with col_busq2:
            if metodo_busqueda_pago == "Número":
                nro_cliente_pago = st.number_input(
                    "Nro. Cliente",
                    min_value=1,
                    max_value=9999,
                    step=1,
                    key="nro_cliente_pago"
                )
                if nro_cliente_pago:
                    cliente_pago = buscar_cliente_por_numero(nro_cliente_pago)
                    if not cliente_pago:
                        st.warning(f"⚠️ No existe cliente con número {nro_cliente_pago}")
            else:
                texto_busqueda_pago = st.text_input(
                    "Buscar por nombre",
                    placeholder="Escriba al menos 3 caracteres...",
                    key="texto_busq_pago"
                )
                if texto_busqueda_pago and len(texto_busqueda_pago) >= 3:
                    clientes_encontrados_pago = buscar_clientes_por_nombre(texto_busqueda_pago)
                    if clientes_encontrados_pago:
                        opciones_pago = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_encontrados_pago}
                        seleccion_pago = st.selectbox("Seleccionar cliente", list(opciones_pago.keys()), key="select_cliente_pago")
                        if seleccion_pago:
                            cliente_pago = opciones_pago[seleccion_pago]
        
        if cliente_pago:
            saldo_cliente = obtener_saldo_cliente(cliente_pago['id'])
            
            st.markdown("---")
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                st.metric("Cliente", f"{cliente_pago['nro_cliente']:04d}")
            with col_info2:
                st.metric("Denominación", cliente_pago['denominacion'])
            with col_info3:
                color = "🔴" if saldo_cliente > 0 else "🟢" if saldo_cliente < 0 else "⚪"
                st.metric("Saldo a Pagar", f"{color} ${saldo_cliente:,.2f}")
            
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
                                        'id': comp['id'],
                                        'fecha': comp['fecha'],
                                        'nro_comprobante': comp.get('nro_comprobante', 'S/N'),
                                        'saldo_pendiente': comp['saldo_pendiente'],
                                        'monto_aplicar': comp['saldo_pendiente']
                                    }
                            else:
                                if comp['id'] in st.session_state.comprobantes_seleccionados:
                                    del st.session_state.comprobantes_seleccionados[comp['id']]
                        
                        total_pendiente = sum(c['saldo_pendiente'] for c in comprobantes_pendientes)
                        st.markdown("---")
                        st.markdown(f"**TOTAL PENDIENTE: ${total_pendiente:,.2f}**")
                    else:
                        st.info("No hay comprobantes pendientes")
                
                with col_cancel:
                    st.markdown("### ✅ Comprobantes a Cancelar")
                    
                    if st.session_state.comprobantes_seleccionados:
                        total_a_cancelar = Decimal('0')
                        
                        for comp_id, comp_data in st.session_state.comprobantes_seleccionados.items():
                            st.markdown(f"📄 **{comp_data['fecha']}** | {comp_data['nro_comprobante']} | ${comp_data['saldo_pendiente']:,.2f}")
                            
                            monto_aplicar = st.number_input(
                                f"Monto a aplicar",
                                min_value=0.01,
                                max_value=float(comp_data['saldo_pendiente']),
                                value=float(comp_data['saldo_pendiente']),
                                step=0.01,
                                key=f"monto_{comp_id}"
                            )
                            st.session_state.comprobantes_seleccionados[comp_id]['monto_aplicar'] = monto_aplicar
                            total_a_cancelar += Decimal(str(monto_aplicar))
                            st.markdown("---")
                        
                        st.markdown(f"### TOTAL: ${total_a_cancelar:,.2f}")
                        
                        nro_recibo = st.text_input("Nro. Recibo (opcional)", key="nro_recibo_pago")
                        obs_pago = st.text_area("Observaciones", height=60, key="obs_pago")
                        
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("🗑️ Limpiar", use_container_width=True):
                                st.session_state.comprobantes_seleccionados = {}
                                st.rerun()
                        
                        with col_btn2:
                            if st.button("💾 Confirmar Pago", type="primary", use_container_width=True):
                                usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                                
                                comps_cancelar = [
                                    {'id': cid, 'monto_aplicar': cd['monto_aplicar']}
                                    for cid, cd in st.session_state.comprobantes_seleccionados.items()
                                ]
                                
                                resultado = registrar_pago(
                                    cliente_id=cliente_pago['id'],
                                    importe_total=float(total_a_cancelar),
                                    comprobantes_a_cancelar=comps_cancelar,
                                    nro_recibo=nro_recibo,
                                    observaciones=obs_pago,
                                    usuario=usuario
                                )
                                
                                if resultado:
                                    nuevo_saldo = saldo_cliente - total_a_cancelar
                                    st.success(f"✅ Pago registrado. Nuevo saldo: ${nuevo_saldo:,.2f}")
                                    st.session_state.comprobantes_seleccionados = {}
                                    st.balloons()
                    else:
                        st.info("👈 Seleccione comprobantes")
    
    # ==================== TAB 3: CLIENTES ====================
    with tab3:
        st.subheader("👥 Gestión de Clientes")
        
        subtab1, subtab2, subtab3 = st.tabs(["📋 Lista", "➕ Nuevo", "✏️ Editar"])
        
        with subtab1:
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                buscar_lista = st.text_input("🔍 Buscar", key="buscar_lista")
            with col_f2:
                incluir_inactivos = st.checkbox("Incluir inactivos")
            
            # 🚀 OPTIMIZADO: Usa la vista para obtener clientes con saldos
            resumen = obtener_resumen_saldos()
            
            if buscar_lista:
                busq = buscar_lista.lower()
                resumen = [c for c in resumen if busq in c['denominacion'].lower() or busq in str(c['nro_cliente'])]
            
            if resumen:
                df = pd.DataFrame(resumen)
                df['nro_cliente'] = df['nro_cliente'].apply(lambda x: f"{x:04d}")
                
                st.dataframe(
                    df[['nro_cliente', 'denominacion', 'saldo', 'estado_saldo']],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "nro_cliente": "Nro.",
                        "denominacion": "Cliente",
                        "saldo": st.column_config.NumberColumn("Saldo", format="$ %.2f"),
                        "estado_saldo": "Estado"
                    }
                )
                st.caption(f"Total: {len(resumen)} clientes")
            else:
                st.info("No hay clientes")
        
        with subtab2:
            st.markdown("#### ➕ Nuevo Cliente")
            
            with st.form("form_nuevo_cliente", clear_on_submit=True):
                siguiente_nro = obtener_siguiente_nro_cliente()
                st.info(f"📌 Número asignado: **{siguiente_nro:04d}**")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    denominacion_nueva = st.text_input("Nombre/Razón Social *")
                    telefono_nuevo = st.text_input("Teléfono")
                
                with col2:
                    email_nuevo = st.text_input("Email")
                    limite_nuevo = st.number_input("Límite de Crédito ($)", min_value=0.0, step=1000.0)
                
                obs_cliente = st.text_area("Observaciones", height=80)
                
                if st.form_submit_button("💾 Crear Cliente", use_container_width=True, type="primary"):
                    if denominacion_nueva:
                        resultado = crear_cliente(
                            denominacion=denominacion_nueva,
                            telefono=telefono_nuevo,
                            email=email_nuevo,
                            limite_credito=limite_nuevo if limite_nuevo > 0 else None,
                            observaciones=obs_cliente
                        )
                        if resultado:
                            st.success(f"✅ Cliente creado: {resultado['nro_cliente']:04d}")
                            st.balloons()
                    else:
                        st.error("⚠️ Denominación obligatoria")
        
        with subtab3:
            st.markdown("#### ✏️ Editar Cliente")
            
            nro_editar = st.number_input("Nro. Cliente", min_value=1, max_value=9999, step=1, key="nro_editar")
            
            if nro_editar:
                cliente_editar = buscar_cliente_por_numero(nro_editar)
                
                if cliente_editar:
                    with st.form("form_editar"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            denom_edit = st.text_input("Nombre *", value=cliente_editar['denominacion'])
                            tel_edit = st.text_input("Teléfono", value=cliente_editar.get('telefono') or '')
                            estado_edit = st.selectbox("Estado", ['activo', 'inactivo', 'suspendido'], 
                                                       index=['activo', 'inactivo', 'suspendido'].index(cliente_editar.get('estado', 'activo')))
                        
                        with col2:
                            email_edit = st.text_input("Email", value=cliente_editar.get('email') or '')
                            limite_edit = st.number_input("Límite Crédito", value=float(cliente_editar.get('limite_credito') or 0))
                        
                        obs_edit = st.text_area("Observaciones", value=cliente_editar.get('observaciones') or '')
                        
                        if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
                            datos = {
                                'denominacion': denom_edit.strip().upper(),
                                'telefono': tel_edit.strip() if tel_edit else None,
                                'email': email_edit.strip().lower() if email_edit else None,
                                'limite_credito': limite_edit if limite_edit > 0 else None,
                                'estado': estado_edit,
                                'observaciones': obs_edit
                            }
                            if actualizar_cliente(cliente_editar['id'], datos):
                                st.success("✅ Cliente actualizado")
                else:
                    st.warning(f"⚠️ No existe cliente {nro_editar}")
    
    # ==================== TAB 4: ESTADO DE CUENTA ====================
    with tab4:
        st.subheader("📊 Estados de Cuenta")
        
        subtab_ind, subtab_gral = st.tabs(["👤 Individual", "📋 Todos los Saldos"])
        
        with subtab_ind:
            clientes_lista = obtener_clientes()
            opciones_ec = {}
            cliente_ec_sel = ""
            
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                if clientes_lista:
                    opciones_ec = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_lista}
                    cliente_ec_sel = st.selectbox("Cliente", [""] + list(opciones_ec.keys()), key="cliente_ec")
            
            with col2:
                fecha_desde = st.date_input("Desde", value=date.today().replace(day=1), key="fecha_desde_ec")
            
            with col3:
                fecha_hasta = st.date_input("Hasta", value=date.today(), key="fecha_hasta_ec")
            
            if cliente_ec_sel and cliente_ec_sel in opciones_ec:
                cliente_ec = opciones_ec[cliente_ec_sel]
                estado = generar_estado_cuenta(cliente_ec['id'], fecha_desde, fecha_hasta)
                
                if estado:
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Cliente:** {estado['cliente']['nro_cliente']:04d}")
                    c2.markdown(f"**{estado['cliente']['denominacion']}**")
                    saldo = estado['saldo_actual']
                    color = "🔴" if saldo > 0 else "🟢" if saldo < 0 else "⚪"
                    c3.markdown(f"**Saldo: {color} ${saldo:,.2f}**")
                    
                    if estado['movimientos']:
                        df = pd.DataFrame(estado['movimientos'])
                        st.dataframe(df, use_container_width=True, hide_index=True,
                                     column_config={
                                         "debe": st.column_config.NumberColumn("Debe", format="$ %.2f"),
                                         "haber": st.column_config.NumberColumn("Haber", format="$ %.2f"),
                                         "saldo": st.column_config.NumberColumn("Saldo", format="$ %.2f")
                                     })
                        
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as w:
                            df.to_excel(w, index=False)
                        st.download_button("📥 Excel", output.getvalue(), 
                                           f"estado_{cliente_ec['nro_cliente']:04d}_{date.today()}.xlsx")
        
        with subtab_gral:
            st.markdown("#### 📋 Saldos de Todos los Clientes")
            
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                filtro = st.selectbox("Filtrar", ["Todos", "Deudores", "A favor", "Sin saldo"], key="filtro_saldos")
            
            with col2:
                orden = st.selectbox("Ordenar", ["Nro.", "Nombre", "Saldo ↓", "Saldo ↑"], key="orden_saldos")
            
            with col3:
                if st.button("🔄 Actualizar", key="btn_actualizar"):
                    limpiar_cache_cc()
                    st.rerun()
            
            # 🚀 OPTIMIZADO: Una sola consulta a la vista
            resumen = obtener_resumen_saldos()
            
            if resumen:
                df = pd.DataFrame(resumen)
                
                # Filtros
                if filtro == "Deudores":
                    df = df[df['saldo'] > 0]
                elif filtro == "A favor":
                    df = df[df['saldo'] < 0]
                elif filtro == "Sin saldo":
                    df = df[df['saldo'] == 0]
                
                # Ordenamiento
                if orden == "Nro.":
                    df = df.sort_values('nro_cliente')
                elif orden == "Nombre":
                    df = df.sort_values('denominacion')
                elif orden == "Saldo ↓":
                    df = df.sort_values('saldo', ascending=False)
                elif orden == "Saldo ↑":
                    df = df.sort_values('saldo')
                
                # Métricas
                st.markdown("---")
                m1, m2, m3, m4 = st.columns(4)
                total_deudores = df[df['saldo'] > 0]['saldo'].sum()
                total_favor = abs(df[df['saldo'] < 0]['saldo'].sum())
                m1.metric("Total a Cobrar", f"${total_deudores:,.2f}")
                m2.metric("Total a Favor", f"${total_favor:,.2f}")
                m3.metric("Deudores", len(df[df['saldo'] > 0]))
                m4.metric("Total Clientes", len(df))
                
                st.markdown("---")
                
                df_show = df.copy()
                df_show['nro_cliente'] = df_show['nro_cliente'].apply(lambda x: f"{x:04d}")
                
                st.dataframe(
                    df_show[['nro_cliente', 'denominacion', 'saldo', 'estado_saldo']],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "nro_cliente": "Nro.",
                        "denominacion": "Cliente",
                        "saldo": st.column_config.NumberColumn("Saldo", format="$ %.2f"),
                        "estado_saldo": "Estado"
                    }
                )
                
                # Exportar
                df_excel = df[['nro_cliente', 'denominacion', 'saldo']].copy()
                df_excel.columns = ['Nro', 'Cliente', 'Saldo']
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as w:
                    df_excel.to_excel(w, index=False)
                st.download_button("📥 Exportar Excel", output.getvalue(), f"saldos_cc_{date.today()}.xlsx", type="primary")
    
    # ==================== TAB 5: IMPORTAR/EXPORTAR ====================
    with tab5:
        st.subheader("📥 Importar / 📤 Exportar")
        
        subtab_imp, subtab_exp = st.tabs(["📥 Importar", "📤 Exportar"])
        
        with subtab_imp:
            st.info("""
            **Columnas del Excel:**
            - `denominacion` (obligatorio)
            - `nro_cliente` (opcional)
            - `telefono`, `email` (opcionales)
            - `saldo_anterior` (opcional)
            """)
            
            archivo = st.file_uploader("Excel", type=['xlsx', 'xls'])
            fecha_saldo = st.date_input("Fecha saldo anterior", value=date.today())
            
            if archivo:
                try:
                    df_imp = pd.read_excel(archivo)
                    st.dataframe(df_imp.head(10))
                    st.warning(f"⚠️ {len(df_imp)} registros")
                    
                    if st.checkbox("Confirmar importación"):
                        if st.button("🚀 Importar", type="primary"):
                            usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                            res = importar_clientes_excel(df_imp, fecha_saldo, usuario)
                            st.success(f"✅ {res['exitosos']} clientes importados")
                            if res['errores']:
                                for e in res['errores'][:5]:
                                    st.error(e)
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        
        with subtab_exp:
            if st.button("📥 Generar Excel de Saldos", type="primary"):
                resumen = obtener_resumen_saldos()
                if resumen:
                    df = pd.DataFrame(resumen)[['nro_cliente', 'denominacion', 'saldo']]
                    df.columns = ['Nro', 'Cliente', 'Saldo']
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as w:
                        df.to_excel(w, index=False)
                    st.download_button("📥 Descargar", output.getvalue(), f"clientes_saldos_{date.today()}.xlsx")

# ==================== PUNTO DE ENTRADA ====================
if __name__ == "__main__":
    main()
