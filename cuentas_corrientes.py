# cuentas_corrientes.py - MÓDULO DE CUENTAS CORRIENTES DE CLIENTES v1.0
#
# 📋 DESCRIPCIÓN:
# Sistema completo de gestión de cuentas corrientes para clientes
# Exclusivo para Sucursal 1 - Minimarket
# Solo accesible por rol Administrador
#
# 🔧 FUNCIONALIDADES:
# - ABM de Clientes con numeración secuencial de 4 dígitos
# - Carga de Compras (Débitos)
# - Carga de Pagos (Créditos) con selección de facturas a cancelar
# - Estado de cuenta por cliente
# - Dashboard de alertas (saldos altos, clientes morosos)
# - Importación inicial desde Excel
# - Exportación de estados de cuenta
#
# 📅 Fecha: Diciembre 2025
# 👨‍💻 Desarrollado para: Sistema Cajas Diarias

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
SUCURSAL_MINIMARKET_ID = 1  # ID de Sucursal 1 - Minimarket
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

@st.cache_data(ttl=30)
@manejar_error_db("Error al cargar clientes")
def obtener_clientes(incluir_inactivos=False):
    """Obtiene lista de clientes."""
    supabase = get_supabase_client()
    query = supabase.table("cc_clientes").select("*").order("nro_cliente")
    
    if not incluir_inactivos:
        query = query.eq("estado", "activo")
    
    result = query.execute()
    return result.data if result.data else []

@st.cache_data(ttl=30)
@manejar_error_db("Error al buscar cliente")
def buscar_cliente_por_numero(nro_cliente):
    """Busca un cliente por su número."""
    supabase = get_supabase_client()
    result = supabase.table("cc_clientes")\
        .select("*")\
        .eq("nro_cliente", nro_cliente)\
        .execute()
    return result.data[0] if result.data else None

@st.cache_data(ttl=30)
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

@st.cache_data(ttl=30)
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

@st.cache_data(ttl=30)
@manejar_error_db("Error al cargar comprobantes pendientes")
def obtener_comprobantes_pendientes(cliente_id):
    """
    Obtiene comprobantes (facturas) pendientes de cancelación.
    Un comprobante está pendiente si saldo_pendiente > 0
    """
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

@manejar_error_db("Error al calcular saldo")
def calcular_saldo_cliente(cliente_id):
    """
    Calcula el saldo actual de un cliente.
    Saldo = Sum(Débitos) - Sum(Créditos)
    Positivo = Cliente debe | Negativo = Saldo a favor del cliente
    """
    supabase = get_supabase_client()
    
    # Obtener todas las operaciones
    result = supabase.table("cc_operaciones")\
        .select("tipo_movimiento, importe")\
        .eq("cliente_id", cliente_id)\
        .execute()
    
    if not result.data:
        return Decimal('0.00')
    
    saldo = Decimal('0.00')
    for op in result.data:
        importe = Decimal(str(op['importe']))
        if op['tipo_movimiento'] == TIPO_DEBITO:
            saldo += importe
        else:  # CREDITO
            saldo -= importe
    
    return saldo

@manejar_error_db("Error al registrar compra")
def registrar_compra(cliente_id, importe, nro_comprobante=None, observaciones=None, usuario=None):
    """
    Registra una compra (débito) en la cuenta corriente.
    """
    supabase = get_supabase_client()
    
    data = {
        'sucursal_id': SUCURSAL_MINIMARKET_ID,
        'cliente_id': cliente_id,
        'tipo_movimiento': TIPO_DEBITO,
        'nro_comprobante': nro_comprobante.strip().upper() if nro_comprobante else None,
        'importe': float(importe),
        'saldo_pendiente': float(importe),  # Inicialmente todo pendiente
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
    """
    Registra un pago (crédito) y cancela/reduce los comprobantes seleccionados.
    
    Args:
        cliente_id: ID del cliente
        importe_total: Monto total del pago
        comprobantes_a_cancelar: Lista de dicts con {'id': id_operacion, 'monto_aplicar': monto}
        nro_recibo: Número de recibo opcional
        observaciones: Observaciones del pago
        usuario: Usuario que registra
    
    Returns:
        Operación de pago creada o None si error
    """
    supabase = get_supabase_client()
    
    # 1. Crear el registro de pago
    data_pago = {
        'sucursal_id': SUCURSAL_MINIMARKET_ID,
        'cliente_id': cliente_id,
        'tipo_movimiento': TIPO_CREDITO,
        'nro_comprobante': nro_recibo.strip().upper() if nro_recibo else None,
        'importe': float(importe_total),
        'saldo_pendiente': 0,  # Los pagos no tienen saldo pendiente
        'fecha': datetime.now(ARGENTINA_TZ).date().isoformat(),
        'observaciones': observaciones,
        'usuario': usuario,
        'created_at': datetime.now(ARGENTINA_TZ).isoformat()
    }
    
    result_pago = supabase.table("cc_operaciones").insert(data_pago).execute()
    
    if not result_pago.data:
        return None
    
    pago_id = result_pago.data[0]['id']
    
    # 2. Actualizar saldos pendientes de los comprobantes cancelados
    for comp in comprobantes_a_cancelar:
        operacion_id = comp['id']
        monto_aplicar = Decimal(str(comp['monto_aplicar']))
        
        # Obtener saldo actual del comprobante
        op_actual = supabase.table("cc_operaciones")\
            .select("saldo_pendiente")\
            .eq("id", operacion_id)\
            .execute()
        
        if op_actual.data:
            saldo_actual = Decimal(str(op_actual.data[0]['saldo_pendiente']))
            nuevo_saldo = max(Decimal('0'), saldo_actual - monto_aplicar)
            
            # Actualizar saldo pendiente
            supabase.table("cc_operaciones")\
                .update({'saldo_pendiente': float(nuevo_saldo)})\
                .eq("id", operacion_id)\
                .execute()
            
            # Registrar la aplicación en tabla de detalle
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
    """
    Importa clientes y saldos iniciales desde DataFrame de Excel.
    
    Columnas esperadas:
    - nro_cliente (opcional, si no existe se genera)
    - denominacion (obligatorio)
    - telefono (opcional)
    - email (opcional)
    - saldo_anterior (opcional, default 0)
    """
    supabase = get_supabase_client()
    
    resultados = {
        'exitosos': 0,
        'errores': [],
        'clientes_creados': []
    }
    
    # Normalizar nombres de columnas
    df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]
    
    for idx, row in df.iterrows():
        try:
            denominacion = str(row.get('denominacion', '')).strip()
            if not denominacion:
                resultados['errores'].append(f"Fila {idx+2}: Denominación vacía")
                continue
            
            # Obtener o generar número de cliente
            nro_cliente = row.get('nro_cliente')
            if pd.isna(nro_cliente) or nro_cliente == '':
                nro_cliente = obtener_siguiente_nro_cliente()
            else:
                nro_cliente = int(nro_cliente)
            
            # Crear cliente
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
                
                # Si hay saldo anterior, crear operación inicial
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

# ==================== FUNCIONES DE REPORTES ====================

@st.cache_data(ttl=30)
@manejar_error_db("Error al obtener resumen de saldos")
def obtener_resumen_saldos():
    """Obtiene resumen de saldos de todos los clientes activos."""
    supabase = get_supabase_client()
    
    # Obtener clientes activos
    clientes = supabase.table("cc_clientes")\
        .select("id, nro_cliente, denominacion, limite_credito")\
        .eq("estado", "activo")\
        .order("denominacion")\
        .execute()
    
    if not clientes.data:
        return []
    
    resumen = []
    for cliente in clientes.data:
        saldo = calcular_saldo_cliente(cliente['id'])
        
        # Determinar estado del saldo
        if saldo > 0:
            estado_saldo = "🔴 Deudor"
        elif saldo < 0:
            estado_saldo = "🟢 A favor"
        else:
            estado_saldo = "⚪ Sin saldo"
        
        # Verificar límite de crédito
        excede_limite = False
        if cliente.get('limite_credito') and saldo > Decimal(str(cliente['limite_credito'])):
            excede_limite = True
        
        resumen.append({
            'nro_cliente': cliente['nro_cliente'],
            'denominacion': cliente['denominacion'],
            'saldo': float(saldo),
            'estado_saldo': estado_saldo,
            'limite_credito': cliente.get('limite_credito'),
            'excede_limite': excede_limite,
            'cliente_id': cliente['id']
        })
    
    return resumen

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

# ==================== INTERFAZ PRINCIPAL ====================

def main():
    """Función principal del módulo de Cuentas Corrientes."""
    
    st.header("💳 Cuentas Corrientes de Clientes")
    st.caption(f"📍 {SUCURSAL_MINIMARKET_NOMBRE}")
    
    # Submenú con tabs
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
        
        # Buscador de cliente
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
                    "Buscar por nombre/razón social",
                    placeholder="Escriba al menos 3 caracteres...",
                    key="texto_busq_compra"
                )
                if texto_busqueda and len(texto_busqueda) >= 3:
                    clientes_encontrados = buscar_clientes_por_nombre(texto_busqueda)
                    if clientes_encontrados:
                        opciones = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_encontrados}
                        seleccion = st.selectbox(
                            "Seleccionar cliente",
                            options=list(opciones.keys()),
                            key="select_cliente_compra"
                        )
                        if seleccion:
                            cliente_seleccionado = opciones[seleccion]
                    else:
                        st.warning("No se encontraron clientes con ese nombre")
        
        # Mostrar info del cliente seleccionado
        if cliente_seleccionado:
            saldo_actual = calcular_saldo_cliente(cliente_seleccionado['id'])
            
            st.markdown("---")
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                st.metric("Cliente", f"{cliente_seleccionado['nro_cliente']:04d}")
            with col_info2:
                st.metric("Denominación", cliente_seleccionado['denominacion'])
            with col_info3:
                color_saldo = "🔴" if saldo_actual > 0 else "🟢" if saldo_actual < 0 else "⚪"
                st.metric("Saldo Actual", f"{color_saldo} ${saldo_actual:,.2f}")
            
            st.markdown("---")
            
            # Formulario de carga de compra
            with st.form("form_compra", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    nro_comprobante = st.text_input(
                        "Nro. Comprobante (opcional)",
                        placeholder="Ej: FC-A-0001-00001234",
                        help="Número de factura o ticket"
                    )
                
                with col2:
                    importe = st.number_input(
                        "Importe ($) *",
                        min_value=0.01,
                        step=0.01,
                        format="%.2f"
                    )
                
                observaciones = st.text_area(
                    "Observaciones (opcional)",
                    placeholder="Detalle de la compra...",
                    height=80
                )
                
                submitted = st.form_submit_button("💾 Registrar Compra", use_container_width=True, type="primary")
                
                if submitted:
                    if importe > 0:
                        # Verificar límite de crédito
                        nuevo_saldo = saldo_actual + Decimal(str(importe))
                        limite = cliente_seleccionado.get('limite_credito')
                        
                        if limite and nuevo_saldo > Decimal(str(limite)):
                            st.warning(f"⚠️ Esta compra excede el límite de crédito (${limite:,.2f}). Saldo resultante: ${nuevo_saldo:,.2f}")
                        
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
                            #st.balloons()
                        else:
                            st.error("❌ Error al registrar la compra")
                    else:
                        st.error("⚠️ El importe debe ser mayor a cero")
    
    # ==================== TAB 2: REGISTRAR PAGO ====================
    with tab2:
        st.subheader("💰 Registrar Pago (Crédito)")
        
        # Buscador de cliente (similar a Tab 1)
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
                    "Buscar por nombre/razón social",
                    placeholder="Escriba al menos 3 caracteres...",
                    key="texto_busq_pago"
                )
                if texto_busqueda_pago and len(texto_busqueda_pago) >= 3:
                    clientes_encontrados_pago = buscar_clientes_por_nombre(texto_busqueda_pago)
                    if clientes_encontrados_pago:
                        opciones_pago = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_encontrados_pago}
                        seleccion_pago = st.selectbox(
                            "Seleccionar cliente",
                            options=list(opciones_pago.keys()),
                            key="select_cliente_pago"
                        )
                        if seleccion_pago:
                            cliente_pago = opciones_pago[seleccion_pago]
                    else:
                        st.warning("No se encontraron clientes con ese nombre")
        
        # Interfaz de pago con dos paneles
        if cliente_pago:
            saldo_cliente = calcular_saldo_cliente(cliente_pago['id'])
            
            st.markdown("---")
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                st.metric("Cliente", f"{cliente_pago['nro_cliente']:04d}")
            with col_info2:
                st.metric("Denominación", cliente_pago['denominacion'])
            with col_info3:
                color_saldo = "🔴" if saldo_cliente > 0 else "🟢" if saldo_cliente < 0 else "⚪"
                st.metric("Saldo a Pagar", f"{color_saldo} ${saldo_cliente:,.2f}")
            
            if saldo_cliente <= 0:
                st.info("ℹ️ Este cliente no tiene saldo pendiente")
            else:
                st.markdown("---")
                
                # Obtener comprobantes pendientes
                comprobantes_pendientes = obtener_comprobantes_pendientes(cliente_pago['id'])
                
                # Inicializar session_state para comprobantes seleccionados
                if 'comprobantes_seleccionados' not in st.session_state:
                    st.session_state.comprobantes_seleccionados = {}
                
                # Dos columnas: Pendientes | A Cancelar
                col_pend, col_cancel = st.columns(2)
                
                with col_pend:
                    st.markdown("### 📋 Comprobantes Pendientes")
                    st.caption("Seleccione los comprobantes a cancelar")
                    
                    if comprobantes_pendientes:
                        for comp in comprobantes_pendientes:
                            comp_key = f"comp_{comp['id']}"
                            
                            col_check, col_data = st.columns([0.15, 0.85])
                            
                            with col_check:
                                seleccionado = st.checkbox(
                                    "",
                                    key=comp_key,
                                    value=comp['id'] in st.session_state.comprobantes_seleccionados
                                )
                            
                            with col_data:
                                fecha_comp = comp['fecha']
                                nro_comp = comp.get('nro_comprobante', 'S/N')
                                saldo_pend = comp['saldo_pendiente']
                                
                                st.markdown(
                                    f"**{fecha_comp}** | {nro_comp} | "
                                    f"**${saldo_pend:,.2f}**"
                                )
                            
                            # Actualizar selección
                            if seleccionado:
                                if comp['id'] not in st.session_state.comprobantes_seleccionados:
                                    st.session_state.comprobantes_seleccionados[comp['id']] = {
                                        'id': comp['id'],
                                        'fecha': comp['fecha'],
                                        'nro_comprobante': comp.get('nro_comprobante', 'S/N'),
                                        'saldo_pendiente': comp['saldo_pendiente'],
                                        'monto_aplicar': comp['saldo_pendiente']  # Por defecto cancela todo
                                    }
                            else:
                                if comp['id'] in st.session_state.comprobantes_seleccionados:
                                    del st.session_state.comprobantes_seleccionados[comp['id']]
                        
                        # Total pendiente
                        total_pendiente = sum(c['saldo_pendiente'] for c in comprobantes_pendientes)
                        st.markdown("---")
                        st.markdown(f"**TOTAL PENDIENTE: ${total_pendiente:,.2f}**")
                    else:
                        st.info("No hay comprobantes pendientes")
                
                with col_cancel:
                    st.markdown("### ✅ Comprobantes a Cancelar")
                    st.caption("Comprobantes seleccionados para este pago")
                    
                    if st.session_state.comprobantes_seleccionados:
                        total_a_cancelar = Decimal('0')
                        
                        for comp_id, comp_data in st.session_state.comprobantes_seleccionados.items():
                            st.markdown(
                                f"📄 **{comp_data['fecha']}** | {comp_data['nro_comprobante']} | "
                                f"${comp_data['saldo_pendiente']:,.2f}"
                            )
                            
                            # Permitir cancelación parcial
                            monto_aplicar = st.number_input(
                                f"Monto a aplicar",
                                min_value=0.01,
                                max_value=float(comp_data['saldo_pendiente']),
                                value=float(comp_data['saldo_pendiente']),
                                step=0.01,
                                key=f"monto_aplicar_{comp_id}"
                            )
                            st.session_state.comprobantes_seleccionados[comp_id]['monto_aplicar'] = monto_aplicar
                            total_a_cancelar += Decimal(str(monto_aplicar))
                            
                            st.markdown("---")
                        
                        st.markdown(f"### TOTAL A CANCELAR: ${total_a_cancelar:,.2f}")
                        
                        # Formulario de pago
                        st.markdown("---")
                        nro_recibo = st.text_input(
                            "Nro. Recibo (opcional)",
                            placeholder="Ej: REC-0001",
                            key="nro_recibo_pago"
                        )
                        
                        obs_pago = st.text_area(
                            "Observaciones",
                            placeholder="Forma de pago, detalles...",
                            height=60,
                            key="obs_pago"
                        )
                        
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("🗑️ Limpiar Selección", use_container_width=True):
                                st.session_state.comprobantes_seleccionados = {}
                                st.rerun()
                        
                        with col_btn2:
                            if st.button("💾 Confirmar Pago", type="primary", use_container_width=True):
                                usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                                
                                # Preparar lista de comprobantes a cancelar
                                comps_cancelar = [
                                    {'id': comp_id, 'monto_aplicar': comp_data['monto_aplicar']}
                                    for comp_id, comp_data in st.session_state.comprobantes_seleccionados.items()
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
                                    #st.balloons()
                                    st.rerun()
                                else:
                                    st.error("❌ Error al registrar el pago")
                    else:
                        st.info("👈 Seleccione comprobantes de la izquierda")
    
    # ==================== TAB 3: CLIENTES ====================
    with tab3:
        st.subheader("👥 Gestión de Clientes")
        
        subtab1, subtab2, subtab3 = st.tabs(["📋 Lista", "➕ Nuevo Cliente", "✏️ Editar"])
        
        with subtab1:
            # Filtros
            col_f1, col_f2 = st.columns([3, 1])
            with col_f1:
                buscar_cliente_lista = st.text_input(
                    "🔍 Buscar cliente",
                    placeholder="Nombre o número...",
                    key="buscar_cliente_lista"
                )
            with col_f2:
                incluir_inactivos = st.checkbox("Incluir inactivos", key="incluir_inactivos")
            
            # Obtener y mostrar clientes
            clientes = obtener_clientes(incluir_inactivos=incluir_inactivos)
            
            if buscar_cliente_lista:
                busq_lower = buscar_cliente_lista.lower()
                clientes = [
                    c for c in clientes 
                    if busq_lower in c['denominacion'].lower() or 
                       busq_lower in str(c['nro_cliente'])
                ]
            
            if clientes:
                # Crear DataFrame para mostrar
                df_clientes = pd.DataFrame(clientes)
                df_clientes['nro_cliente'] = df_clientes['nro_cliente'].apply(lambda x: f"{x:04d}")
                df_clientes['estado_display'] = df_clientes['estado'].map(ESTADOS_CLIENTE)
                
                # Calcular saldos
                saldos = []
                for cliente in clientes:
                    saldo = calcular_saldo_cliente(cliente['id'])
                    saldos.append(float(saldo))
                df_clientes['saldo'] = saldos
                
                # Seleccionar columnas a mostrar
                cols_mostrar = ['nro_cliente', 'denominacion', 'telefono', 'email', 'saldo', 'estado_display']
                cols_disponibles = [c for c in cols_mostrar if c in df_clientes.columns]
                
                df_display = df_clientes[cols_disponibles].copy()
                df_display.columns = ['Nro.', 'Denominación', 'Teléfono', 'Email', 'Saldo', 'Estado']
                
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Saldo": st.column_config.NumberColumn(format="$ %.2f")
                    }
                )
                
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
                    denominacion_nueva = st.text_input(
                        "Nombre/Razón Social *",
                        placeholder="Ej: GARCÍA JUAN CARLOS"
                    )
                    telefono_nuevo = st.text_input(
                        "Teléfono",
                        placeholder="Ej: 2966-123456"
                    )
                
                with col2:
                    email_nuevo = st.text_input(
                        "Email",
                        placeholder="Ej: cliente@email.com"
                    )
                    limite_credito_nuevo = st.number_input(
                        "Límite de Crédito ($)",
                        min_value=0.0,
                        step=1000.0,
                        format="%.2f",
                        help="Dejar en 0 para sin límite"
                    )
                
                obs_cliente = st.text_area(
                    "Observaciones",
                    placeholder="Notas adicionales...",
                    height=80
                )
                
                submitted_cliente = st.form_submit_button("💾 Crear Cliente", use_container_width=True, type="primary")
                
                if submitted_cliente:
                    if denominacion_nueva:
                        resultado = crear_cliente(
                            denominacion=denominacion_nueva,
                            telefono=telefono_nuevo,
                            email=email_nuevo,
                            limite_credito=limite_credito_nuevo if limite_credito_nuevo > 0 else None,
                            observaciones=obs_cliente
                        )
                        
                        if resultado:
                            st.success(f"✅ Cliente creado: {resultado['nro_cliente']:04d} - {resultado['denominacion']}")
                            #st.balloons()
                        else:
                            st.error("❌ Error al crear cliente")
                    else:
                        st.error("⚠️ La denominación es obligatoria")
        
        with subtab3:
            st.markdown("#### ✏️ Editar Cliente")
            
            # Buscador para edición
            nro_editar = st.number_input(
                "Nro. Cliente a editar",
                min_value=1,
                max_value=9999,
                step=1,
                key="nro_editar"
            )
            
            if nro_editar:
                cliente_editar = buscar_cliente_por_numero(nro_editar)
                
                if cliente_editar:
                    with st.form("form_editar_cliente"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            denominacion_edit = st.text_input(
                                "Nombre/Razón Social *",
                                value=cliente_editar['denominacion']
                            )
                            telefono_edit = st.text_input(
                                "Teléfono",
                                value=cliente_editar.get('telefono', '') or ''
                            )
                            estado_edit = st.selectbox(
                                "Estado",
                                options=['activo', 'inactivo', 'suspendido'],
                                index=['activo', 'inactivo', 'suspendido'].index(cliente_editar.get('estado', 'activo'))
                            )
                        
                        with col2:
                            email_edit = st.text_input(
                                "Email",
                                value=cliente_editar.get('email', '') or ''
                            )
                            limite_edit = st.number_input(
                                "Límite de Crédito ($)",
                                min_value=0.0,
                                value=float(cliente_editar.get('limite_credito', 0) or 0),
                                step=1000.0,
                                format="%.2f"
                            )
                        
                        obs_edit = st.text_area(
                            "Observaciones",
                            value=cliente_editar.get('observaciones', '') or '',
                            height=80
                        )
                        
                        submitted_edit = st.form_submit_button("💾 Guardar Cambios", use_container_width=True, type="primary")
                        
                        if submitted_edit:
                            datos_update = {
                                'denominacion': denominacion_edit.strip().upper(),
                                'telefono': telefono_edit.strip() if telefono_edit else None,
                                'email': email_edit.strip().lower() if email_edit else None,
                                'limite_credito': limite_edit if limite_edit > 0 else None,
                                'estado': estado_edit,
                                'observaciones': obs_edit
                            }
                            
                            resultado = actualizar_cliente(cliente_editar['id'], datos_update)
                            
                            if resultado:
                                st.success("✅ Cliente actualizado correctamente")
                            else:
                                st.error("❌ Error al actualizar cliente")
                else:
                    st.warning(f"⚠️ No existe cliente con número {nro_editar}")
    
    # ==================== TAB 4: ESTADO DE CUENTA ====================
    with tab4:
        st.subheader("📊 Estados de Cuenta")
        
        # Subtabs para diferentes vistas
        subtab_individual, subtab_general = st.tabs([
            "👤 Estado Individual",
            "📋 Saldos de Todos los Clientes"
        ])
        
        # -------------------- SUBTAB: ESTADO INDIVIDUAL --------------------
        with subtab_individual:
            st.markdown("#### 👤 Estado de Cuenta Individual")
            
            # Selector de cliente
            col1, col2, col3 = st.columns([2, 1, 1])
            
            # Inicializar variables
            clientes_lista = obtener_clientes()
            opciones_ec = {}
            cliente_ec_seleccion = ""
            
            with col1:
                if clientes_lista:
                    opciones_ec = {f"{c['nro_cliente']:04d} - {c['denominacion']}": c for c in clientes_lista}
                    cliente_ec_seleccion = st.selectbox(
                        "Seleccionar cliente",
                        options=[""] + list(opciones_ec.keys()),
                        key="cliente_estado_cuenta"
                    )
                else:
                    st.info("No hay clientes registrados")
            
            with col2:
                fecha_desde_ec = st.date_input(
                    "Desde",
                    value=date.today().replace(day=1),
                    key="fecha_desde_ec"
                )
            
            with col3:
                fecha_hasta_ec = st.date_input(
                    "Hasta",
                    value=date.today(),
                    key="fecha_hasta_ec"
                )
            
            if cliente_ec_seleccion and cliente_ec_seleccion in opciones_ec:
                cliente_ec = opciones_ec[cliente_ec_seleccion]
                
                estado_cuenta = generar_estado_cuenta(
                    cliente_ec['id'],
                    fecha_desde=fecha_desde_ec,
                    fecha_hasta=fecha_hasta_ec
                )
                
                if estado_cuenta:
                    # Encabezado
                    st.markdown("---")
                    col_ec1, col_ec2, col_ec3 = st.columns(3)
                    
                    with col_ec1:
                        st.markdown(f"**Cliente:** {estado_cuenta['cliente']['nro_cliente']:04d}")
                    with col_ec2:
                        st.markdown(f"**{estado_cuenta['cliente']['denominacion']}**")
                    with col_ec3:
                        saldo = estado_cuenta['saldo_actual']
                        color = "🔴" if saldo > 0 else "🟢" if saldo < 0 else "⚪"
                        st.markdown(f"**Saldo: {color} ${saldo:,.2f}**")
                    
                    st.markdown("---")
                    
                    # Tabla de movimientos
                    if estado_cuenta['movimientos']:
                        df_mov = pd.DataFrame(estado_cuenta['movimientos'])
                        
                        st.dataframe(
                            df_mov,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "fecha": st.column_config.TextColumn("Fecha"),
                                "tipo": st.column_config.TextColumn("Tipo"),
                                "comprobante": st.column_config.TextColumn("Comprobante"),
                                "debe": st.column_config.NumberColumn("Debe", format="$ %.2f"),
                                "haber": st.column_config.NumberColumn("Haber", format="$ %.2f"),
                                "saldo": st.column_config.NumberColumn("Saldo", format="$ %.2f"),
                                "observaciones": st.column_config.TextColumn("Obs.")
                            }
                        )
                        
                        # Botón de exportación
                        st.markdown("---")
                        
                        # Crear Excel para descarga
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_mov.to_excel(writer, sheet_name='Estado de Cuenta', index=False)
                        
                        st.download_button(
                            label="📥 Descargar Excel",
                            data=output.getvalue(),
                            file_name=f"estado_cuenta_{cliente_ec['nro_cliente']:04d}_{date.today()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.info("No hay movimientos en el período seleccionado")
        
        # -------------------- SUBTAB: SALDOS GENERALES --------------------
        with subtab_general:
            st.markdown("#### 📋 Saldos de Cuenta Corriente - Todos los Clientes")
            
            # Filtros
            col_filtro1, col_filtro2, col_filtro3 = st.columns([1, 1, 2])
            
            with col_filtro1:
                filtro_saldo = st.selectbox(
                    "Filtrar por saldo",
                    ["Todos", "Solo deudores (saldo > 0)", "Solo con saldo a favor", "Solo con saldo cero"],
                    key="filtro_saldo_general"
                )
            
            with col_filtro2:
                ordenar_por = st.selectbox(
                    "Ordenar por",
                    ["Nro. Cliente", "Denominación", "Saldo (mayor a menor)", "Saldo (menor a mayor)"],
                    key="ordenar_saldos"
                )
            
            with col_filtro3:
                if st.button("🔄 Actualizar Saldos", key="btn_actualizar_saldos"):
                    st.cache_data.clear()
                    st.rerun()
            
            # Obtener resumen de saldos
            resumen_saldos = obtener_resumen_saldos()
            
            if resumen_saldos:
                df_saldos = pd.DataFrame(resumen_saldos)
                
                # Aplicar filtros
                if filtro_saldo == "Solo deudores (saldo > 0)":
                    df_saldos = df_saldos[df_saldos['saldo'] > 0]
                elif filtro_saldo == "Solo con saldo a favor":
                    df_saldos = df_saldos[df_saldos['saldo'] < 0]
                elif filtro_saldo == "Solo con saldo cero":
                    df_saldos = df_saldos[df_saldos['saldo'] == 0]
                
                # Aplicar ordenamiento
                if ordenar_por == "Nro. Cliente":
                    df_saldos = df_saldos.sort_values('nro_cliente')
                elif ordenar_por == "Denominación":
                    df_saldos = df_saldos.sort_values('denominacion')
                elif ordenar_por == "Saldo (mayor a menor)":
                    df_saldos = df_saldos.sort_values('saldo', ascending=False)
                elif ordenar_por == "Saldo (menor a mayor)":
                    df_saldos = df_saldos.sort_values('saldo', ascending=True)
                
                # Métricas resumen
                st.markdown("---")
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                
                total_deudores = df_saldos[df_saldos['saldo'] > 0]['saldo'].sum()
                total_favor = abs(df_saldos[df_saldos['saldo'] < 0]['saldo'].sum())
                cant_deudores = len(df_saldos[df_saldos['saldo'] > 0])
                cant_total = len(df_saldos)
                
                with col_m1:
                    st.metric("Total a Cobrar", f"${total_deudores:,.2f}")
                with col_m2:
                    st.metric("Total a Favor Clientes", f"${total_favor:,.2f}")
                with col_m3:
                    st.metric("Clientes Deudores", f"{cant_deudores}")
                with col_m4:
                    st.metric("Total Clientes", f"{cant_total}")
                
                st.markdown("---")
                
                # Preparar DataFrame para mostrar
                df_display = df_saldos.copy()
                df_display['nro_cliente'] = df_display['nro_cliente'].apply(lambda x: f"{x:04d}")
                
                # Seleccionar y renombrar columnas
                columnas_mostrar = ['nro_cliente', 'denominacion', 'saldo', 'estado_saldo']
                if 'limite_credito' in df_display.columns:
                    columnas_mostrar.append('limite_credito')
                if 'excede_limite' in df_display.columns:
                    columnas_mostrar.append('excede_limite')
                
                df_display = df_display[columnas_mostrar]
                
                # Mostrar tabla
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "nro_cliente": st.column_config.TextColumn("Nro."),
                        "denominacion": st.column_config.TextColumn("Cliente"),
                        "saldo": st.column_config.NumberColumn("Saldo", format="$ %.2f"),
                        "estado_saldo": st.column_config.TextColumn("Estado"),
                        "limite_credito": st.column_config.NumberColumn("Límite", format="$ %.2f"),
                        "excede_limite": st.column_config.CheckboxColumn("Excede Límite")
                    }
                )
                
                st.caption(f"Mostrando {len(df_display)} clientes")
                
                # Exportar a Excel
                st.markdown("---")
                
                # Preparar datos para Excel (sin emojis)
                df_excel = df_saldos.copy()
                df_excel['nro_cliente'] = df_excel['nro_cliente'].apply(lambda x: f"{x:04d}")
                df_excel['estado'] = df_excel['saldo'].apply(
                    lambda x: 'Deudor' if x > 0 else ('A Favor' if x < 0 else 'Sin Saldo')
                )
                
                cols_excel = ['nro_cliente', 'denominacion', 'saldo', 'estado']
                if 'limite_credito' in df_excel.columns:
                    cols_excel.append('limite_credito')
                
                df_excel = df_excel[cols_excel]
                df_excel.columns = ['Nro. Cliente', 'Denominación', 'Saldo', 'Estado', 'Límite Crédito'] if 'limite_credito' in cols_excel else ['Nro. Cliente', 'Denominación', 'Saldo', 'Estado']
                
                output_general = io.BytesIO()
                with pd.ExcelWriter(output_general, engine='openpyxl') as writer:
                    df_excel.to_excel(writer, sheet_name='Saldos CC', index=False)
                    
                    # Agregar hoja de resumen
                    resumen_data = {
                        'Concepto': ['Total a Cobrar', 'Total a Favor Clientes', 'Saldo Neto', 'Cantidad Deudores', 'Total Clientes'],
                        'Valor': [total_deudores, total_favor, total_deudores - total_favor, cant_deudores, cant_total]
                    }
                    df_resumen = pd.DataFrame(resumen_data)
                    df_resumen.to_excel(writer, sheet_name='Resumen', index=False)
                
                col_exp1, col_exp2 = st.columns([1, 3])
                with col_exp1:
                    st.download_button(
                        label="📥 Exportar a Excel",
                        data=output_general.getvalue(),
                        file_name=f"saldos_cuenta_corriente_{date.today()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
            else:
                st.info("No hay clientes con operaciones registradas")
    
    # ==================== TAB 5: IMPORTAR/EXPORTAR ====================
    with tab5:
        st.subheader("📥 Importar / 📤 Exportar")
        
        subtab_imp, subtab_exp = st.tabs(["📥 Importar Clientes", "📤 Exportar Datos"])
        
        with subtab_imp:
            st.markdown("#### 📥 Importación Inicial de Clientes")
            st.info("""
            **Formato del archivo Excel:**
            - **denominacion** (obligatorio): Nombre/Razón Social
            - **nro_cliente** (opcional): Número de cliente (si no se indica, se genera automáticamente)
            - **telefono** (opcional): Teléfono de contacto
            - **email** (opcional): Email de contacto
            - **saldo_anterior** (opcional): Saldo a importar
            """)
            
            archivo_excel = st.file_uploader(
                "Seleccionar archivo Excel",
                type=['xlsx', 'xls'],
                key="archivo_importar"
            )
            
            fecha_saldo = st.date_input(
                "Fecha del saldo anterior",
                value=date.today(),
                key="fecha_saldo_importar"
            )
            
            if archivo_excel:
                try:
                    df_import = pd.read_excel(archivo_excel)
                    st.markdown("**Vista previa:**")
                    st.dataframe(df_import.head(10), use_container_width=True)
                    
                    st.warning(f"⚠️ Se importarán **{len(df_import)}** registros")
                    
                    confirmar_import = st.checkbox("Confirmo que quiero importar estos datos", key="confirmar_import")
                    
                    if confirmar_import and st.button("🚀 Iniciar Importación", type="primary"):
                        with st.spinner("Importando..."):
                            usuario = st.session_state.get('user', {}).get('nombre', 'Sistema')
                            resultados = importar_clientes_excel(df_import, fecha_saldo, usuario)
                            
                            if resultados:
                                st.success(f"✅ Importación completada: {resultados['exitosos']} clientes creados")
                                
                                if resultados['errores']:
                                    st.warning(f"⚠️ {len(resultados['errores'])} errores:")
                                    for error in resultados['errores'][:10]:
                                        st.error(error)
                
                except Exception as e:
                    st.error(f"❌ Error al leer el archivo: {str(e)}")
        
        with subtab_exp:
            st.markdown("#### 📤 Exportar Datos")
            
            tipo_export = st.selectbox(
                "¿Qué desea exportar?",
                ["Lista de Clientes con Saldos", "Todas las Operaciones"],
                key="tipo_exportar"
            )
            
            if st.button("📥 Generar Exportación", type="primary"):
                with st.spinner("Generando archivo..."):
                    if tipo_export == "Lista de Clientes con Saldos":
                        resumen = obtener_resumen_saldos()
                        if resumen:
                            df_export = pd.DataFrame(resumen)
                            
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df_export.to_excel(writer, sheet_name='Clientes', index=False)
                            
                            st.download_button(
                                label="📥 Descargar Excel",
                                data=output.getvalue(),
                                file_name=f"clientes_saldos_{date.today()}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        # Exportar todas las operaciones
                        supabase = get_supabase_client()
                        result = supabase.table("cc_operaciones")\
                            .select("*, cc_clientes(nro_cliente, denominacion)")\
                            .order("fecha", desc=True)\
                            .execute()
                        
                        if result.data:
                            df_ops = pd.DataFrame(result.data)
                            df_ops['cliente'] = df_ops['cc_clientes'].apply(
                                lambda x: f"{x['nro_cliente']:04d} - {x['denominacion']}" if x else ''
                            )
                            
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df_ops.to_excel(writer, sheet_name='Operaciones', index=False)
                            
                            st.download_button(
                                label="📥 Descargar Excel",
                                data=output.getvalue(),
                                file_name=f"operaciones_cc_{date.today()}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        else:
                            st.warning("No hay operaciones para exportar")

# ==================== PUNTO DE ENTRADA ====================
if __name__ == "__main__":
    main()
