# auth.py
# ============================================================
# CHANGELOG v2.1 - Optimizacion de tokens (Feb 2025)
# ------------------------------------------------------------
# 1. login(): Cambiado flujo - primero login, despues sign_out("others")
#    Antes: sign_out("global") ANTES del login - mataba la sesion actual
#    Ahora: login primero, despues sign_out("others") - mata las viejas, conserva la nueva
#
# 2. cambiar_password(): Agregado sign_out("others") despues de verificar
#    Antes: sign_in para verificar creaba un token extra sin limpiar
#    Ahora: limpia tokens sobrantes despues de verificar
#
# 3. Nuevo: Control de expiracion de sesion (SESSION_TIMEOUT_HOURS)
#    Si la sesion tiene mas de 12 horas, fuerza re-login
#    Esto evita sesiones "zombi" que acumulan tokens indefinidamente
#
# 4. init_supabase(): Agregado cache con st.cache_resource
#    Evita crear multiples clientes Supabase por recarga de pagina
# ============================================================

import streamlit as st
from supabase import create_client, Client
from datetime import date, datetime, timedelta
import os
import pytz

ARGENTINA_TZ = pytz.timezone('America/Argentina/Buenos_Aires')

# Tiempo maximo de sesion antes de forzar re-login (en horas)
SESSION_TIMEOUT_HOURS = 12


def obtener_fecha_argentina():
    """Obtiene la fecha actual en zona horaria de Argentina"""
    return datetime.now(ARGENTINA_TZ).date()


@st.cache_resource
def init_supabase() -> Client:
    """
    Inicializa cliente de Supabase (cacheado para no recrear en cada rerun).
    MEJORA: @st.cache_resource evita crear multiples conexiones por recarga.
    """
    if hasattr(st, "secrets") and "supabase" in st.secrets:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    else:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    return create_client(url, key)


def login(email: str, password: str):
    """
    Inicia sesion con proteccion anti-duplicados MEJORADA.
    
    CAMBIO CLAVE: Antes haciamos sign_out("global") ANTES del login,
    lo que no servia porque no habia sesion activa en ese cliente.
    Ahora: primero login (crea 1 token), despues sign_out("others")
    que invalida TODOS los tokens anteriores de ese usuario,
    conservando solo el token de la sesion actual.
    """
    try:
        supabase = init_supabase()
        
        # 1. Crear nueva sesion (genera 1 token nuevo)
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        # 2. ANTI-DUPLICADO: Invalidar todas las sesiones ANTERIORES
        #    "others" = mata todos los tokens EXCEPTO el actual
        try:
            supabase.auth.sign_out({"scope": "others"})
        except:
            pass  # Si falla, el cron de limpieza se encarga
        
        # 3. Obtener perfil del usuario
        user_id = response.user.id
        profile = supabase.table('user_profiles').select('*').eq('id', user_id).single().execute()
        
        # 4. Guardar en session_state (incluye timestamp para control de expiracion)
        st.session_state.user = {
            'id': user_id,
            'email': response.user.email,
            'rol': profile.data['rol'],
            'nombre': profile.data.get('nombre_completo', email),
            'sucursal_asignada': profile.data.get('sucursal_asignada'),
            'access_token': response.session.access_token
        }
        
        st.session_state.authenticated = True
        st.session_state.login_timestamp = datetime.now(ARGENTINA_TZ).isoformat()
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
    """
    Verifica si hay usuario autenticado Y si la sesion no expiro.
    
    NUEVO: Si la sesion tiene mas de SESSION_TIMEOUT_HOURS horas,
    se considera expirada y fuerza re-login. Esto evita que usuarios
    que dejan la pestana abierta acumulen tokens indefinidamente.
    """
    if not st.session_state.get('authenticated', False):
        return False
    
    # Verificar expiracion de sesion
    login_time = st.session_state.get('login_timestamp')
    if login_time:
        try:
            login_dt = datetime.fromisoformat(login_time)
            ahora = datetime.now(ARGENTINA_TZ)
            horas_transcurridas = (ahora - login_dt).total_seconds() / 3600
            
            if horas_transcurridas > SESSION_TIMEOUT_HOURS:
                # Sesion expirada - forzar re-login
                logout()
                return False
        except:
            pass  # Si falla el parseo, dejamos pasar
    
    return True


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
    """
    Permite al usuario cambiar su contrasena.
    
    MEJORA: Agregado sign_out("others") despues de verificar password.
    Antes, el sign_in de verificacion creaba un token extra sin limpiarlo.
    """
    try:
        supabase = init_supabase()
        user = st.session_state.user
        
        # Verificar password actual (esto crea un token temporal)
        try:
            supabase.auth.sign_in_with_password({
                "email": user['email'],
                "password": password_actual
            })
        except:
            return False, "La contrasena actual es incorrecta"
        
        # Cambiar la contrasena
        supabase.auth.update_user({"password": password_nueva})
        
        # Limpiar el token extra que creo el sign_in de verificacion
        try:
            supabase.auth.sign_out({"scope": "others"})
        except:
            pass
        
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
