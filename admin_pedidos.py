"""
admin_pedidos.py - Módulo de Administración y ABM
Gestión completa de productos, proveedores, pedidos, remitos y OC
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import os
from supabase import create_client, Client
import auth

# ==================== INICIALIZACIÓN ====================

@st.cache_resource
def init_supabase():
    """Inicializa cliente de Supabase"""
    if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    return create_client(url, key)

supabase: Client = init_supabase()

# ==================== ABM PRODUCTOS ====================

def abm_productos():
    """Gestión completa de productos"""
    st.subheader("📦 Gestión de Productos")
    
    tab1, tab2, tab3 = st.tabs(["📋 Listar", "➕ Nuevo", "✏️ Editar/Eliminar"])
    
    with tab1:
        # LISTAR PRODUCTOS
        st.markdown("### Lista de Productos")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            filtro_categoria = st.text_input("🔍 Filtrar por categoría", key="filtro_cat")
        with col2:
            filtro_proveedor = st.text_input("🔍 Filtrar por proveedor", key="filtro_prov")
        with col3:
            mostrar_inactivos = st.checkbox("Mostrar inactivos", key="mostrar_inact")
        
        # Consultar productos
        try:
            query = supabase.table('productos')\
                .select('*, proveedores(razon_social)')
            
            if not mostrar_inactivos:
                query = query.eq('activo', True)
            
            result = query.execute()
            
            if result.data:
                df = pd.DataFrame(result.data)
                
                # Agregar columna de proveedor
                df['proveedor'] = df['proveedores'].apply(
                    lambda x: x['razon_social'] if x else 'Sin proveedor'
                )
                
                # Aplicar filtros
                if filtro_categoria:
                    df = df[df['categoria'].str.contains(filtro_categoria, case=False, na=False)]
                
                if filtro_proveedor:
                    df = df[df['proveedor'].str.contains(filtro_proveedor, case=False, na=False)]
                
                # Mostrar tabla
                cols_mostrar = ['id', 'codigo_producto', 'nombre_producto', 'categoria', 
                               'unidad_medida', 'proveedor', 'precio_referencia', 'activo']
                
                st.dataframe(
                    df[cols_mostrar],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        'precio_referencia': st.column_config.NumberColumn(
                            'Precio Ref.',
                            format="$ %.2f"
                        )
                    }
                )
                
                st.metric("Total productos", len(df))
                
                # Exportar a Excel
                if st.button("📥 Exportar a Excel"):
                    df_export = df[cols_mostrar]
                    df_export.to_excel('/tmp/productos.xlsx', index=False)
                    with open('/tmp/productos.xlsx', 'rb') as f:
                        st.download_button(
                            "⬇️ Descargar",
                            f,
                            "productos.xlsx",
                            "application/vnd.ms-excel"
                        )
            else:
                st.info("No hay productos registrados")
                
        except Exception as e:
            st.error(f"❌ Error al cargar productos: {str(e)}")
    
    with tab2:
        # NUEVO PRODUCTO
        st.markdown("### ➕ Agregar Nuevo Producto")
        
        with st.form("form_nuevo_producto"):
            col1, col2 = st.columns(2)
            
            with col1:
                codigo = st.text_input("* Código producto", placeholder="COCA-225")
                nombre = st.text_input("* Nombre producto", placeholder="Coca Cola 2.25L")
                categoria = st.text_input("Categoría", placeholder="Bebidas")
                unidad = st.text_input("Unidad de medida", placeholder="Unidad")
            
            with col2:
                # Obtener proveedores
                proveedores = supabase.table('proveedores')\
                    .select('id, razon_social')\
                    .eq('activo', True)\
                    .execute()
                
                prov_options = {p['razon_social']: p['id'] for p in proveedores.data}
                prov_seleccionado = st.selectbox(
                    "Proveedor principal",
                    options=['Ninguno'] + list(prov_options.keys())
                )
                
                precio = st.number_input("Precio referencia", min_value=0.0, step=100.0)
                activo = st.checkbox("Activo", value=True)
            
            # Sucursales
            st.markdown("**Sucursales que pueden pedir este producto:**")
            sucursales = supabase.table('sucursales')\
                .select('id, nombre, codigo')\
                .eq('activa', True)\
                .execute()
            
            todas_suc = st.checkbox("Todas las sucursales", value=True)
            
            if not todas_suc:
                suc_seleccionadas = st.multiselect(
                    "Seleccionar sucursales",
                    options=[(s['id'], s['nombre']) for s in sucursales.data],
                    format_func=lambda x: x[1]
                )
            
            observaciones = st.text_area("Observaciones", height=100)
            
            submitted = st.form_submit_button("✅ Guardar Producto", use_container_width=True)
            
            if submitted:
                if not codigo or not nombre:
                    st.error("❌ Código y nombre son obligatorios")
                else:
                    try:
                        # Insertar producto
                        producto_data = {
                            'codigo_producto': codigo.strip(),
                            'nombre_producto': nombre.strip(),
                            'categoria': categoria.strip() if categoria else None,
                            'unidad_medida': unidad.strip() if unidad else None,
                            'proveedor_principal_id': prov_options.get(prov_seleccionado) if prov_seleccionado != 'Ninguno' else None,
                            'precio_referencia': precio,
                            'activo': activo,
                            'observaciones': observaciones.strip() if observaciones else None
                        }
                        
                        result = supabase.table('productos').insert(producto_data).execute()
                        producto_id = result.data[0]['id']
                        
                        # Insertar relaciones con sucursales
                        if todas_suc:
                            suc_ids = [s['id'] for s in sucursales.data]
                        else:
                            suc_ids = [s[0] for s in suc_seleccionadas]
                        
                        for suc_id in suc_ids:
                            supabase.table('productos_sucursales').insert({
                                'producto_id': producto_id,
                                'sucursal_id': suc_id
                            }).execute()
                        
                        st.success("✅ Producto creado correctamente")
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error al crear producto: {str(e)}")
    
    with tab3:
        # EDITAR/ELIMINAR PRODUCTO
        st.markdown("### ✏️ Editar o Eliminar Producto")
        
        # Selector de producto
        productos = supabase.table('productos')\
            .select('id, codigo_producto, nombre_producto, activo')\
            .execute()
        
        if not productos.data:
            st.info("No hay productos para editar")
            return
        
        prod_options = {
            f"{p['codigo_producto']} - {p['nombre_producto']} {'[INACTIVO]' if not p['activo'] else ''}": p['id']
            for p in productos.data
        }
        
        prod_seleccionado = st.selectbox(
            "Seleccionar producto a editar",
            options=list(prod_options.keys())
        )
        
        producto_id = prod_options[prod_seleccionado]
        
        # Cargar datos del producto
        producto = supabase.table('productos')\
            .select('*, proveedores(razon_social)')\
            .eq('id', producto_id)\
            .single()\
            .execute()
        
        prod_data = producto.data
        
        # Formulario de edición
        with st.form("form_editar_producto"):
            st.warning("⚠️ Los cambios afectarán a todos los pedidos futuros")
            
            col1, col2 = st.columns(2)
            
            with col1:
                codigo_edit = st.text_input("Código", value=prod_data['codigo_producto'])
                nombre_edit = st.text_input("Nombre", value=prod_data['nombre_producto'])
                categoria_edit = st.text_input("Categoría", value=prod_data.get('categoria', ''))
                unidad_edit = st.text_input("Unidad", value=prod_data.get('unidad_medida', ''))
            
            with col2:
                proveedores = supabase.table('proveedores')\
                    .select('id, razon_social')\
                    .eq('activo', True)\
                    .execute()
                
                prov_options_edit = {p['razon_social']: p['id'] for p in proveedores.data}
                
                prov_actual = prod_data['proveedores']['razon_social'] if prod_data.get('proveedores') else 'Ninguno'
                prov_edit = st.selectbox(
                    "Proveedor",
                    options=['Ninguno'] + list(prov_options_edit.keys()),
                    index=list(['Ninguno'] + list(prov_options_edit.keys())).index(prov_actual) 
                          if prov_actual in ['Ninguno'] + list(prov_options_edit.keys()) else 0
                )
                
                precio_edit = st.number_input("Precio", value=float(prod_data.get('precio_referencia', 0)))
                activo_edit = st.checkbox("Activo", value=prod_data.get('activo', True))
            
            obs_edit = st.text_area("Observaciones", value=prod_data.get('observaciones', ''))
            
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                guardar = st.form_submit_button("💾 Guardar Cambios", use_container_width=True)
            with col_btn2:
                desactivar = st.form_submit_button("🔒 Desactivar", use_container_width=True)
            with col_btn3:
                eliminar = st.form_submit_button("🗑️ Eliminar", use_container_width=True, type="secondary")
            
            if guardar:
                try:
                    update_data = {
                        'codigo_producto': codigo_edit.strip(),
                        'nombre_producto': nombre_edit.strip(),
                        'categoria': categoria_edit.strip() if categoria_edit else None,
                        'unidad_medida': unidad_edit.strip() if unidad_edit else None,
                        'proveedor_principal_id': prov_options_edit.get(prov_edit) if prov_edit != 'Ninguno' else None,
                        'precio_referencia': precio_edit,
                        'activo': activo_edit,
                        'observaciones': obs_edit.strip() if obs_edit else None
                    }
                    
                    supabase.table('productos').update(update_data).eq('id', producto_id).execute()
                    
                    st.success("✅ Producto actualizado correctamente")
                    st.cache_data.clear()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error al actualizar: {str(e)}")
            
            if desactivar:
                try:
                    supabase.table('productos').update({'activo': False}).eq('id', producto_id).execute()
                    st.success("✅ Producto desactivado")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            
            if eliminar:
                st.warning("⚠️ Confirmar eliminación en el checkbox de abajo")
                confirmar = st.checkbox("Confirmo que quiero ELIMINAR permanentemente este producto")
                
                if confirmar:
                    try:
                        # Verificar si tiene pedidos asociados
                        pedidos_asociados = supabase.table('pedidos_detalle')\
                            .select('id')\
                            .eq('producto_id', producto_id)\
                            .limit(1)\
                            .execute()
                        
                        if pedidos_asociados.data:
                            st.error("❌ No se puede eliminar: tiene pedidos asociados. Mejor desactívalo.")
                        else:
                            supabase.table('productos').delete().eq('id', producto_id).execute()
                            st.success("✅ Producto eliminado")
                            st.cache_data.clear()
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"❌ Error al eliminar: {str(e)}")

# ==================== ABM PROVEEDORES ====================

def abm_proveedores():
    """Gestión completa de proveedores"""
    st.subheader("🏢 Gestión de Proveedores")
    
    tab1, tab2, tab3 = st.tabs(["📋 Listar", "➕ Nuevo", "✏️ Editar/Eliminar"])
    
    with tab1:
        # LISTAR PROVEEDORES
        try:
            result = supabase.table('proveedores').select('*').execute()
            
            if result.data:
                df = pd.DataFrame(result.data)
                
                cols_mostrar = ['id', 'codigo_proveedor', 'razon_social', 'telefono', 
                               'email', 'cuit', 'forma_pago', 'activo']
                
                st.dataframe(df[cols_mostrar], hide_index=True, use_container_width=True)
                st.metric("Total proveedores", len(df))
            else:
                st.info("No hay proveedores registrados")
                
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
    
    with tab2:
        # NUEVO PROVEEDOR
        with st.form("form_nuevo_proveedor"):
            col1, col2 = st.columns(2)
            
            with col1:
                codigo = st.text_input("* Código", placeholder="PROV-001")
                razon_social = st.text_input("* Razón Social", placeholder="Distribuidora Sur SA")
                contacto = st.text_input("Nombre contacto", placeholder="Carlos Pérez")
                telefono = st.text_input("Teléfono", placeholder="2966-123456")
            
            with col2:
                email = st.text_input("Email", placeholder="ventas@proveedor.com")
                cuit = st.text_input("CUIT", placeholder="30-12345678-9")
                forma_pago = st.text_input("Forma de pago", placeholder="Cta Cte 30 días")
                activo = st.checkbox("Activo", value=True)
            
            direccion = st.text_input("Dirección", placeholder="Av. Roca 1250")
            observaciones = st.text_area("Observaciones", height=100)
            
            submitted = st.form_submit_button("✅ Guardar Proveedor", use_container_width=True)
            
            if submitted:
                if not codigo or not razon_social:
                    st.error("❌ Código y razón social son obligatorios")
                else:
                    try:
                        data = {
                            'codigo_proveedor': codigo.strip(),
                            'razon_social': razon_social.strip(),
                            'nombre_contacto': contacto.strip() if contacto else None,
                            'telefono': telefono.strip() if telefono else None,
                            'email': email.strip() if email else None,
                            'cuit': cuit.strip() if cuit else None,
                            'direccion': direccion.strip() if direccion else None,
                            'forma_pago': forma_pago.strip() if forma_pago else None,
                            'observaciones': observaciones.strip() if observaciones else None,
                            'activo': activo
                        }
                        
                        supabase.table('proveedores').insert(data).execute()
                        st.success("✅ Proveedor creado correctamente")
                        st.cache_data.clear()
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
    
    with tab3:
        # EDITAR/ELIMINAR (similar a productos, lo dejo resumido)
        st.info("🚧 Funcionalidad similar a productos - implementar según necesidad")

# ==================== GESTIÓN DE PEDIDOS ====================

def gestion_pedidos():
    """Gestión completa de pedidos (ver, editar, cancelar)"""
    st.subheader("📋 Gestión de Pedidos")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        filtro_estado = st.selectbox(
            "Estado",
            ['TODOS', 'PENDIENTE_REVISION', 'EN_PROCESO', 'COMPLETADO', 'CANCELADO']
        )
    with col2:
        sucursales = supabase.table('sucursales').select('id, nombre').execute()
        suc_options = {s['nombre']: s['id'] for s in sucursales.data}
        filtro_suc = st.selectbox("Sucursal", ['TODAS'] + list(suc_options.keys()))
    with col3:
        fecha_desde = st.date_input("Desde", value=None)
    
    # Consultar pedidos
    try:
        query = supabase.table('pedidos')\
            .select('*, sucursales(nombre), user_profiles(nombre_completo)')
        
        if filtro_estado != 'TODOS':
            query = query.eq('estado', filtro_estado)
        
        if filtro_suc != 'TODAS':
            query = query.eq('sucursal_id', suc_options[filtro_suc])
        
        if fecha_desde:
            query = query.gte('fecha_pedido', str(fecha_desde))
        
        result = query.order('fecha_pedido', desc=True).limit(50).execute()
        
        if result.data:
            for pedido in result.data:
                with st.expander(
                    f"🛒 Pedido #{pedido['id']} - {pedido['sucursales']['nombre']} - {pedido['estado']}"
                ):
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Estado", pedido['estado'])
                    col2.metric("Fecha", pedido['fecha_pedido'][:10])
                    col3.metric("Usuario", pedido['user_profiles']['nombre_completo'])
                    if pedido.get('fecha_necesaria'):
                        col4.metric("Fecha necesaria", pedido['fecha_necesaria'])
                    
                    if pedido.get('observaciones'):
                        st.info(f"📝 {pedido['observaciones']}")
                    
                    # Acciones
                    col_acc1, col_acc2, col_acc3 = st.columns(3)
                    
                    with col_acc1:
                        if st.button("📄 Ver Detalle", key=f"ver_{pedido['id']}"):
                            st.session_state[f'ver_detalle_{pedido["id"]}'] = True
                    
                    with col_acc2:
                        if pedido['estado'] == 'PENDIENTE_REVISION':
                            if st.button("❌ Cancelar", key=f"cancel_{pedido['id']}"):
                                st.session_state[f'cancelar_{pedido["id"]}'] = True
                    
                    with col_acc3:
                        if pedido['estado'] != 'COMPLETADO':
                            if st.button("✅ Marcar Completado", key=f"complete_{pedido['id']}"):
                                try:
                                    supabase.table('pedidos')\
                                        .update({'estado': 'COMPLETADO'})\
                                        .eq('id', pedido['id'])\
                                        .execute()
                                    st.success("✅ Pedido completado")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")
                    
                    # Mostrar detalle si se solicitó
                    if st.session_state.get(f'ver_detalle_{pedido["id"]}'):
                        detalle = supabase.table('pedidos_detalle')\
                            .select('*, productos(nombre_producto, unidad_medida)')\
                            .eq('pedido_id', pedido['id'])\
                            .execute()
                        
                        if detalle.data:
                            df_detalle = pd.DataFrame([{
                                'Producto': item['productos']['nombre_producto'],
                                'Solicitado': item['cantidad_solicitada'],
                                'Entrega CC': item.get('cantidad_entrega_cc', 0),
                                'En OC': item.get('cantidad_oc', 0)
                            } for item in detalle.data])
                            
                            st.dataframe(df_detalle, hide_index=True)
                    
                    # Cancelar pedido
                    if st.session_state.get(f'cancelar_{pedido["id"]}'):
                        motivo = st.text_input("Motivo de cancelación", key=f"motivo_{pedido['id']}")
                        if st.button("Confirmar Cancelación", key=f"confirm_cancel_{pedido['id']}"):
                            try:
                                # Usar función de cancelación
                                supabase.rpc('cancelar_pedido', {
                                    'pedido_id': pedido['id'],
                                    'motivo': motivo
                                }).execute()
                                
                                st.success("✅ Pedido cancelado")
                                del st.session_state[f'cancelar_{pedido["id"]}']
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
        else:
            st.info("No hay pedidos con esos filtros")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

# ==================== AUDITORÍA ====================

def ver_auditoria():
    """Visualizar auditoría de cambios"""
    st.subheader("📊 Auditoría de Cambios")
    
    try:
        result = supabase.table('auditoria_pedidos')\
            .select('*, user_profiles(nombre_completo)')\
            .order('created_at', desc=True)\
            .limit(100)\
            .execute()
        
        if result.data:
            df = pd.DataFrame([{
                'Fecha': item['created_at'][:19],
                'Usuario': item['user_profiles']['nombre_completo'] if item.get('user_profiles') else 'Sistema',
                'Tabla': item['tabla'],
                'Registro ID': item['registro_id'],
                'Acción': item['accion'],
                'Motivo': item.get('motivo', '-')
            } for item in result.data])
            
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.info("No hay registros de auditoría")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

# ==================== FUNCIÓN PRINCIPAL ====================

def main():
    """Función principal del módulo de administración"""
    
    # Verificar que sea admin
    if not auth.is_admin():
        st.error("⚠️ Solo administradores pueden acceder a esta sección")
        st.stop()
    
    st.title("⚙️ Administración del Sistema de Pedidos")
    st.markdown("---")
    
    # Menú de administración
    opcion = st.selectbox(
        "Seleccionar módulo",
        [
            "📦 Gestión de Productos",
            "🏢 Gestión de Proveedores",
            "📋 Gestión de Pedidos",
            "📊 Auditoría"
        ]
    )
    
    if opcion == "📦 Gestión de Productos":
        abm_productos()
    elif opcion == "🏢 Gestión de Proveedores":
        abm_proveedores()
    elif opcion == "📋 Gestión de Pedidos":
        gestion_pedidos()
    elif opcion == "📊 Auditoría":
        ver_auditoria()

if __name__ == '__main__':
    main()
