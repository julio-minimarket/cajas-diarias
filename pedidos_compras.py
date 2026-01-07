"""
pedidos_compras.py - Módulo de Pedidos y Compras
Integrado con cajas_diarias.py
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import os
from supabase import create_client, Client
import auth  # Reutilizar autenticación existente

# ==================== INICIALIZACIÓN ====================

@st.cache_resource
def init_supabase():
    """Inicializa cliente de Supabase (reutilizado de cajas_diarias)"""
    if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        st.error("⚠️ Falta configurar las credenciales de Supabase")
        st.stop()
    
    return create_client(url, key)

supabase: Client = init_supabase()

# ==================== FUNCIONES DE DATOS ====================

@st.cache_data(ttl=60)
def obtener_productos_sucursal(sucursal_id):
    """
    Obtiene productos disponibles para una sucursal específica
    Agrupados por categoría
    """
    try:
        result = supabase.table('productos_sucursales')\
            .select('*, productos(*, proveedores(razon_social))')\
            .eq('sucursal_id', sucursal_id)\
            .execute()
        
        if not result.data:
            return {}
        
        # Agrupar por categoría
        productos_por_categoria = {}
        for item in result.data:
            prod = item['productos']
            if prod['activo']:  # Solo productos activos
                categoria = prod['categoria'] or 'Sin categoría'
                if categoria not in productos_por_categoria:
                    productos_por_categoria[categoria] = []
                
                productos_por_categoria[categoria].append({
                    'id': prod['id'],
                    'codigo': prod['codigo_producto'],
                    'nombre': prod['nombre_producto'],
                    'unidad': prod['unidad_medida'],
                    'precio_ref': prod['precio_referencia'],
                    'proveedor': prod['proveedores']['razon_social'] if prod['proveedores'] else 'N/A',
                    'orden': item.get('orden', 0)
                })
        
        # Ordenar productos dentro de cada categoría
        for categoria in productos_por_categoria:
            productos_por_categoria[categoria].sort(key=lambda x: (x['orden'], x['nombre']))
        
        return productos_por_categoria
        
    except Exception as e:
        st.error(f"❌ Error al cargar productos: {str(e)}")
        return {}

@st.cache_data(ttl=60)
def obtener_pedidos_sucursal(sucursal_id):
    """Obtiene pedidos de una sucursal con su detalle"""
    try:
        result = supabase.table('pedidos')\
            .select('*, pedidos_detalle(*, productos(nombre_producto, unidad_medida))')\
            .eq('sucursal_id', sucursal_id)\
            .order('fecha_pedido', desc=True)\
            .limit(20)\
            .execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        st.error(f"❌ Error al cargar pedidos: {str(e)}")
        return []

@st.cache_data(ttl=30)
def obtener_pedidos_pendientes():
    """Obtiene todos los pedidos pendientes de revisión (Admin)"""
    try:
        result = supabase.table('pedidos')\
            .select('*, sucursales(nombre, codigo)')\
            .eq('estado', 'PENDIENTE_REVISION')\
            .order('fecha_pedido', desc=False)\
            .execute()
        
        return result.data if result.data else []
        
    except Exception as e:
        st.error(f"❌ Error al cargar pedidos pendientes: {str(e)}")
        return []

def crear_pedido(usuario_id, sucursal_id, items, fecha_necesaria, observaciones):
    """
    Crea un nuevo pedido con sus líneas de detalle
    
    Args:
        usuario_id: UUID del usuario
        sucursal_id: ID de la sucursal
        items: Lista de dicts {'producto_id': int, 'cantidad': int}
        fecha_necesaria: date o None
        observaciones: str
    
    Returns:
        bool: True si fue exitoso
    """
    try:
        # 1. Crear cabecera del pedido
        pedido_data = {
            'sucursal_id': sucursal_id,
            'usuario_id': str(usuario_id),
            'fecha_necesaria': str(fecha_necesaria) if fecha_necesaria else None,
            'estado': 'PENDIENTE_REVISION',
            'observaciones': observaciones
        }
        
        result_pedido = supabase.table('pedidos').insert(pedido_data).execute()
        pedido_id = result_pedido.data[0]['id']
        
        # 2. Insertar líneas de detalle
        for item in items:
            detalle_data = {
                'pedido_id': pedido_id,
                'producto_id': item['producto_id'],
                'cantidad_solicitada': item['cantidad']
            }
            supabase.table('pedidos_detalle').insert(detalle_data).execute()
        
        # Limpiar caché
        st.cache_data.clear()
        return True
        
    except Exception as e:
        st.error(f"❌ Error al crear pedido: {str(e)}")
        return False

def obtener_pedido_detalle_admin(pedido_id):
    """Obtiene el detalle completo de un pedido para revisión (Admin)"""
    try:
        # Pedido
        pedido = supabase.table('pedidos')\
            .select('*, sucursales(nombre, codigo, direccion)')\
            .eq('id', pedido_id)\
            .single()\
            .execute()
        
        # Detalle
        detalle = supabase.table('pedidos_detalle')\
            .select('*, productos(codigo_producto, nombre_producto, unidad_medida)')\
            .eq('pedido_id', pedido_id)\
            .execute()
        
        return {
            'pedido': pedido.data,
            'items': detalle.data
        }
        
    except Exception as e:
        st.error(f"❌ Error al cargar detalle: {str(e)}")
        return None

# ==================== PANTALLAS ====================

def pantalla_nuevo_pedido():
    """Pantalla para que encargados creen pedidos"""
    st.subheader("📝 Nuevo Pedido")
    
    user = st.session_state.user
    sucursal_id = user.get('sucursal_asignada')
    
    if not sucursal_id:
        st.error("⚠️ Tu usuario no tiene una sucursal asignada. Contacta al administrador.")
        return
    
    # Obtener productos disponibles
    productos = obtener_productos_sucursal(sucursal_id)
    
    if not productos:
        st.warning("⚠️ No hay productos configurados para tu sucursal")
        return
    
    # Formulario de pedido
    with st.form("form_nuevo_pedido"):
        st.write("**Selecciona los productos y cantidades:**")
        st.markdown("---")
        
        pedido_items = []
        
        # Mostrar productos por categoría
        for categoria, prods in productos.items():
            st.markdown(f"### {categoria}")
            
            # Headers
            cols = st.columns([4, 2, 3])
            cols[0].write("**Producto**")
            cols[1].write("**Unidad**")
            cols[2].write("**Cantidad**")
            
            for prod in prods:
                cols = st.columns([4, 2, 3])
                cols[0].write(prod['nombre'])
                cols[1].write(prod['unidad'])
                cantidad = cols[2].number_input(
                    "cant",
                    min_value=0,
                    value=0,
                    step=1,
                    key=f"prod_{prod['id']}",
                    label_visibility="collapsed"
                )
                
                if cantidad > 0:
                    pedido_items.append({
                        'producto_id': prod['id'],
                        'cantidad': cantidad
                    })
            
            st.markdown("---")
        
        # Campos adicionales
        fecha_necesaria = st.date_input(
            "📅 Fecha necesaria (opcional)",
            value=None,
            help="¿Para cuándo necesitas estos productos?"
        )
        
        observaciones = st.text_area(
            "📝 Observaciones",
            placeholder="Ej: Urgente para el fin de semana, Pedido para evento especial, etc.",
            height=100
        )
        
        # Botones
        col1, col2 = st.columns([2, 1])
        with col1:
            submitted = st.form_submit_button(
                "✅ Enviar Pedido",
                use_container_width=True,
                type="primary"
            )
        with col2:
            cancel = st.form_submit_button(
                "❌ Cancelar",
                use_container_width=True
            )
        
        if cancel:
            st.rerun()
        
        if submitted:
            if len(pedido_items) == 0:
                st.error("❌ Debes agregar al menos un producto")
            else:
                with st.spinner("Creando pedido..."):
                    exito = crear_pedido(
                        usuario_id=user['id'],
                        sucursal_id=sucursal_id,
                        items=pedido_items,
                        fecha_necesaria=fecha_necesaria,
                        observaciones=observaciones
                    )
                    
                    if exito:
                        st.success("✅ Pedido creado correctamente")
                        st.info("El pedido será revisado por el área de administración")
                        st.rerun()

def pantalla_mis_pedidos():
    """Pantalla para que encargados vean sus pedidos"""
    st.subheader("📋 Mis Pedidos")
    
    user = st.session_state.user
    sucursal_id = user.get('sucursal_asignada')
    
    if not sucursal_id:
        st.error("⚠️ Tu usuario no tiene una sucursal asignada.")
        return
    
    pedidos = obtener_pedidos_sucursal(sucursal_id)
    
    if not pedidos:
        st.info("No hay pedidos registrados")
        return
    
    # Mostrar pedidos
    for pedido in pedidos:
        with st.expander(
            f"🛒 Pedido #{pedido['id']} - {pedido['fecha_pedido'][:10]} - **{pedido['estado']}**"
        ):
            col1, col2, col3 = st.columns(3)
            col1.metric("Estado", pedido['estado'])
            col2.metric("Fecha pedido", pedido['fecha_pedido'][:10])
            if pedido.get('fecha_necesaria'):
                col3.metric("Fecha necesaria", pedido['fecha_necesaria'])
            
            if pedido.get('observaciones'):
                st.info(f"📝 {pedido['observaciones']}")
            
            # Detalle
            st.markdown("**Productos solicitados:**")
            
            items_data = []
            for item in pedido.get('pedidos_detalle', []):
                items_data.append({
                    'Producto': item['productos']['nombre_producto'],
                    'Cantidad': item['cantidad_solicitada'],
                    'Unidad': item['productos']['unidad_medida'],
                    'CC': item.get('cantidad_entrega_cc', 0),
                    'OC': item.get('cantidad_oc', 0)
                })
            
            if items_data:
                df = pd.DataFrame(items_data)
                st.dataframe(df, hide_index=True, use_container_width=True)

def pantalla_revisar_pedidos():
    """Pantalla para que admin revise y procese pedidos"""
    st.subheader("🔍 Revisar Pedidos Pendientes")
    
    pedidos = obtener_pedidos_pendientes()
    
    if not pedidos:
        st.success("✅ No hay pedidos pendientes de revisión")
        return
    
    # Selector de pedido
    opciones = [
        f"Pedido #{p['id']} - {p['sucursales']['nombre']} - {p['fecha_pedido'][:10]}"
        for p in pedidos
    ]
    
    seleccion = st.selectbox("📦 Seleccionar pedido a revisar:", opciones)
    pedido_id = int(seleccion.split("#")[1].split(" ")[0])
    
    # Obtener detalle completo
    detalle = obtener_pedido_detalle_admin(pedido_id)
    
    if not detalle:
        return
    
    pedido = detalle['pedido']
    items = detalle['items']
    
    st.markdown("---")
    
    # Información del pedido
    col1, col2, col3 = st.columns(3)
    col1.metric("🏪 Sucursal", pedido['sucursales']['nombre'])
    col2.metric("📅 Fecha", pedido['fecha_pedido'][:10])
    if pedido.get('fecha_necesaria'):
        col3.metric("🎯 Fecha necesaria", pedido['fecha_necesaria'])
    
    if pedido.get('observaciones'):
        st.info(f"📝 **Observaciones del encargado:** {pedido['observaciones']}")
    
    st.markdown("---")
    
    # FORMULARIO DE REVISIÓN
    with st.form(f"form_revision_{pedido_id}"):
        st.write("**Revisar línea por línea:**")
        st.caption("Marca en 'Entrego CC' la cantidad que entregarás desde Casa Central. Lo demás irá automáticamente a Orden de Compra.")
        
        # Headers
        cols = st.columns([4, 2, 2, 3, 2])
        cols[0].write("**Producto**")
        cols[1].write("**Pedido**")
        cols[2].write("**Unidad**")
        cols[3].write("**✅ Entrego CC**")
        cols[4].write("**📋 Va a OC**")
        
        cantidades_cc = {}
        
        for item in items:
            cols = st.columns([4, 2, 2, 3, 2])
            cols[0].write(item['productos']['nombre_producto'])
            cols[1].write(item['cantidad_solicitada'])
            cols[2].write(item['productos']['unidad_medida'])
            
            # Input cantidad a entregar desde CC
            cant_cc = cols[3].number_input(
                "cc",
                min_value=0,
                max_value=item['cantidad_solicitada'],
                value=0,
                step=1,
                key=f"cc_{item['id']}",
                label_visibility="collapsed"
            )
            
            # Calcular automático lo que va a OC
            cant_oc = item['cantidad_solicitada'] - cant_cc
            cols[4].write(f"**{cant_oc}**")
            
            cantidades_cc[item['id']] = cant_cc
        
        st.markdown("---")
        
        # Resumen
        total_cc = sum([c for c in cantidades_cc.values() if c > 0])
        total_oc_items = sum([1 for item in items if item['cantidad_solicitada'] - cantidades_cc.get(item['id'], 0) > 0])
        
        col1, col2 = st.columns(2)
        col1.metric("🏪 Productos para Remito CC", f"{len([c for c in cantidades_cc.values() if c > 0])}")
        col2.metric("📋 Productos para OC", total_oc_items)
        
        obs_admin = st.text_area(
            "Observaciones administrativas",
            placeholder="Notas internas sobre este pedido..."
        )
        
        # Botones
        col1, col2 = st.columns([2, 1])
        with col1:
            submitted = st.form_submit_button(
                "✅ Confirmar y Generar Documentos",
                use_container_width=True,
                type="primary"
            )
        with col2:
            cancel = st.form_submit_button("❌ Cancelar", use_container_width=True)
        
        if cancel:
            st.rerun()
        
        if submitted:
            with st.spinner("Procesando pedido..."):
                try:
                    # Actualizar cantidades en pedidos_detalle
                    for item_id, cant_cc in cantidades_cc.items():
                        supabase.table('pedidos_detalle')\
                            .update({
                                'cantidad_entrega_cc': cant_cc,
                                'observaciones_admin': obs_admin
                            })\
                            .eq('id', item_id)\
                            .execute()
                    
                    # Actualizar estado del pedido
                    supabase.table('pedidos')\
                        .update({
                            'estado': 'EN_PROCESO',
                            'revisado_por': st.session_state.user['id'],
                            'fecha_revision': datetime.now().isoformat()
                        })\
                        .eq('id', pedido_id)\
                        .execute()
                    
                    st.success("✅ Pedido procesado correctamente")
                    st.info("💡 En la siguiente fase podrás generar el Remito CC y la OC en PDF")
                    st.cache_data.clear()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al procesar: {str(e)}")

# ==================== FUNCIÓN PRINCIPAL ====================

def main():
    """Función principal del módulo de Pedidos y Compras"""
    
    # Verificar autenticación
    if not auth.is_authenticated():
        st.warning("⚠️ Debes iniciar sesión para acceder")
        st.stop()
    
    user = st.session_state.user
    rol = user['rol'].lower()
    
    st.title("🛒 Módulo de Pedidos y Compras")
    st.markdown("---")
    
    # Menú según rol
    if rol == 'encargado':
        # TAB para encargados
        tab1, tab2 = st.tabs(["📝 Nuevo Pedido", "📋 Mis Pedidos"])
        
        with tab1:
            pantalla_nuevo_pedido()
        
        with tab2:
            pantalla_mis_pedidos()
    
    elif rol in ['admin', 'administrador']:
        # TAB para administradores
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🔍 Revisar Pedidos",
            "📄 Remitos CC",
            "📋 Órdenes de Compra",
            "⚙️ Administración",
            "📊 Auditoría"
        ])
        
        with tab1:
            pantalla_revisar_pedidos()
        
        with tab2:
            st.info("🚧 En desarrollo - Fase 2")
            st.write("Aquí verás los remitos generados desde Casa Central")
        
        with tab3:
            st.info("🚧 En desarrollo - Fase 2")
            st.write("Aquí verás las órdenes de compra generadas")
        
        with tab4:
            st.info("⚙️ **Módulo de Administración**")
            st.markdown("""
            Para gestionar productos, proveedores y pedidos, usá el módulo dedicado:
            
            ```python
            import admin_pedidos
            admin_pedidos.main()
            ```
            
            O ejecutá directamente:
            ```bash
            streamlit run admin_pedidos.py
            ```
            
            **Funcionalidades disponibles:**
            - 📦 ABM Productos (Alta/Baja/Modificación)
            - 🏢 ABM Proveedores
            - 📋 Gestión de Pedidos (ver, editar, cancelar)
            - 📊 Auditoría de cambios
            """)
        
        with tab5:
            st.info("📊 **Auditoría de Cambios**")
            
            try:
                result = supabase.table('auditoria_pedidos')\
                    .select('*')\
                    .order('created_at', desc=True)\
                    .limit(50)\
                    .execute()
                
                if result.data:
                    df = pd.DataFrame([{
                        'Fecha': item['created_at'][:19],
                        'Tabla': item['tabla'],
                        'Registro': item['registro_id'],
                        'Acción': item['accion'],
                        'Motivo': item.get('motivo', '-')
                    } for item in result.data])
                    
                    st.dataframe(df, hide_index=True, use_container_width=True)
                    st.caption("Mostrando últimos 50 registros")
                else:
                    st.info("No hay registros de auditoría aún")
            except Exception as e:
                st.warning("⚠️ La tabla de auditoría aún no está creada. Ejecutá mejoras_seguridad_rls.sql")
    
    else:
        st.warning("⚠️ No tienes permisos para acceder a este módulo")

if __name__ == '__main__':
    main()
