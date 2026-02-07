# auth.py
import streamlit as st
from supabase import create_client, Client
from datetime import date, datetime, timedelta
import os
import pytz

ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')


def obtener_fecha_argentina():
    """Obtiene la fecha actual en zona horaria de Argentina"""
    return datetime.now(ARGENTINA_TZ).date()


def init_supabase() -> Client:
    """Inicializa cliente de Supabase"""
    if hasattr(st, "secrets") and "supabase" in st.secrets:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    return create_client(url, key)


def login(email: str, password: str):
    """
    Inicia sesion con proteccion anti-duplicados
    """
    try:
        supabase = init_supabase()
        
        # ANTI-DUPLICADO: Invalidar sesiones previas antes de crear nueva
        try:
            supabase.auth.sign_out({"scope": "global"})
        except:
            pass
        
        # Crear nueva sesion
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        # Obtener perfil del usuario
        user_id = response.user.id
        profile = supabase.table('user_profiles').select('*').eq('id', user_id).single().execute()
        
        # Guardar en session_state
        st.session_state.user = {
            'id': user_id,
            'email': response.user.email,
            'rol': profile.data['rol'],
            'nombre': profile.data.get('nombre_completo', email),
            'sucursal_asignada': profile.data.get('sucursal_asignada'),
            'access_token': response.session.access_token
        }
        
        st.session_state.authenticated = True
        return True, "Sesion iniciada correctamente"
        
    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return False, "Email o contrasena incorrectos"
        return False, f"Error de autenticacion: {error_msg}"


def logout():
    """Cierra sesion limpiando todo"""
    try:
        supabase = init_supabase()
        supabase.auth.sign_out({"scope": "global"})
    except:
        pass
    
    # Limpiar session_state
    keys_to_delete = list(st.session_state.keys())
    for key in keys_to_delete:
        del st.session_state[key]


def is_authenticated():
    """Verifica si hay usuario autenticado"""
    return st.session_state.get('authenticated', False)


def get_user_role():
    """Obtiene el rol del usuario actual"""
    if is_authenticated():
        return st.session_state.user.get('rol', 'encargado')
    return None


def is_admin():
    return get_user_role() == 'admin'


def is_gerente():
    return get_user_role() == 'gerente'


def get_user_sucursal():
    """Obtiene la sucursal asignada al usuario"""
    if is_authenticated():
        return st.session_state.user.get('sucursal_asignada')
    return None


def require_auth():
    """Protege paginas que requieren autenticacion"""
    if not is_authenticated():
        st.warning("Debes iniciar sesion para acceder")
        show_login_form()
        st.stop()


def show_login_form():
    """Muestra formulario de login"""
    st.title("Sistema de Cajas Diarias")
    st.subheader("Iniciar Sesion")
    
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="usuario@cajas.local")
        password = st.text_input("Contrasena", type="password")
        submit = st.form_submit_button("Iniciar Sesion")
        
        if submit:
            if not email or not password:
                st.error("Por favor completa todos los campos")
            else:
                with st.spinner("Verificando credenciales..."):
                    success, message = login(email, password)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
    
    with st.expander("Informacion de acceso"):
        st.markdown("""
        **Usuarios de Sucursales:**
        - Email: `Suc01@cajas.local` hasta `Suc11@cajas.local`
        - Contrasena inicial: igual al usuario (ej: `Suc01`)
        """)


def puede_cargar_fecha(fecha_seleccionada, rol_usuario):
    """Valida si el usuario puede cargar una fecha especifica"""
    hoy = obtener_fecha_argentina()
    ayer = hoy - timedelta(days=1)
    
    if rol_usuario in ['admin', 'gerente']:
        return True, ""
    
    if fecha_seleccionada in [hoy, ayer]:
        return True, ""
    else:
        return False, f"Solo puedes cargar movimientos de HOY ({hoy.strftime('%d/%m/%Y')}) o AYER ({ayer.strftime('%d/%m/%Y')})"


def obtener_selector_fecha():
    """Retorna el widget de fecha apropiado segun el rol"""
    hoy = obtener_fecha_argentina()
    ayer = hoy - timedelta(days=1)
    
    if is_admin() or is_gerente():
        st.info("Modo Administrador/Gerente: Puedes cargar cualquier fecha")
        return st.date_input("Fecha", value=hoy, key="fecha_admin")
    else:
        st.warning(f"Solo puedes cargar HOY ({hoy.strftime('%d/%m/%Y')}) o AYER ({ayer.strftime('%d/%m/%Y')})")
        
        opciones = {
            f"HOY - {hoy.strftime('%d/%m/%Y')}": hoy,
            f"AYER - {ayer.strftime('%d/%m/%Y')}": ayer
        }
        
        seleccion = st.selectbox("Selecciona la fecha:", list(opciones.keys()), key="fecha_encargado")
        return opciones[seleccion]


def cambiar_password(password_actual: str, password_nueva: str):
    """Permite al usuario cambiar su contrasena"""
    try:
        supabase = init_supabase()
        user = st.session_state.user
        
        try:
            supabase.auth.sign_in_with_password({
                "email": user['email'],
                "password": password_actual
            })
        except:
            return False, "La contrasena actual es incorrecta"
        
        supabase.auth.update_user({"password": password_nueva})
        return True, "Contrasena actualizada exitosamente"
        
    except Exception as e:
        return False, f"Error al cambiar contrasena: {str(e)}"


def mostrar_cambio_password():
    """Widget para cambiar contrasena"""
    st.subheader("Cambiar Contrasena")
    
    with st.form("cambiar_password_form"):
        password_actual = st.text_input("Contrasena actual", type="password")
        password_nueva = st.text_input("Nueva contrasena", type="password")
        password_confirmar = st.text_input("Confirmar nueva contrasena", type="password")
        
        col1, col2 = st.columns(2)
        with col1:
            submit = st.form_submit_button("Cambiar")
        with col2:
            cancel = st.form_submit_button("Cancelar")
        
        if cancel:
            st.session_state.mostrar_cambio_pwd = False
            st.rerun()
        
        if submit:
            if not all([password_actual, password_nueva, password_confirmar]):
                st.error("Completa todos los campos")
            elif password_nueva != password_confirmar:
                st.error("Las contrasenas nuevas no coinciden")
            elif len(password_nueva) < 6:
                st.error("La contrasena debe tener al menos 6 caracteres")
            else:
                success, message = cambiar_password(password_actual, password_nueva)
                if success:
                    st.success(message)
                    st.session_state.mostrar_cambio_pwd = False
                    st.rerun()
                else:
                    st.error(message)


def mostrar_info_usuario_sidebar():
    """Muestra informacion del usuario en el sidebar"""
    with st.sidebar:
        st.markdown("---")
        st.subheader("Usuario")
        user = st.session_state.user
        
        st.write(f"**{user['nombre']}**")
        st.caption(f"{user['email']}")
        
        rol = user['rol'].lower()
        if rol == 'admin':
            st.success("ADMINISTRADOR")
        elif rol == 'gerente':
            st.info("GERENTE")
        else:
            st.info("ENCARGADO")
        
        sucursal_asignada = user.get('sucursal_asignada')
        if sucursal_asignada:
            st.write(f"Sucursal ID: **{sucursal_asignada}**")
        else:
            if rol == 'encargado':
                st.warning("Sin sucursal asignada")
        
        st.markdown("---")
        
        if st.button("Cambiar Contrasena", key="btn_cambiar_pwd"):
            st.session_state.mostrar_cambio_pwd = True
            st.rerun()
        
        if st.button("Cerrar Sesion", key="btn_logout"):
            logout()
            st.rerun()


def validar_acceso_sucursal(sucursal_id: int) -> bool:
    """Valida si el usuario puede acceder a una sucursal especifica"""
    if is_admin() or is_gerente():
        return True
    
    sucursal_usuario = get_user_sucursal()
    if sucursal_usuario is None:
        return False
    
    return sucursal_id == sucursal_usuario


def filtrar_sucursales_disponibles(todas_sucursales: list) -> list:
    """Filtra las sucursales disponibles segun el rol"""
    if is_admin() or is_gerente():
        return todas_sucursales
    
    sucursal_usuario = get_user_sucursal()
    
    if sucursal_usuario is None:
        st.error("Tu usuario no tiene una sucursal asignada. Contacta al administrador.")
        return []
    
    sucursales_filtradas = [s for s in todas_sucursales if s['id'] == sucursal_usuario]
    
    if len(sucursales_filtradas) == 0:
        st.error(f"Tu sucursal asignada (ID: {sucursal_usuario}) no existe.")
    
    return sucursales_filtradas
