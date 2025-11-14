# 🚀 Guía de Implementación: Sistema con Autenticación

## 📋 Checklist de Implementación

### ✅ PASO 1: Archivos necesarios

Descarga estos archivos desde `/mnt/user-data/outputs/`:

1. ✅ `auth.py` - Módulo de autenticación
2. ✅ `cajas_diarias_con_auth.py` - Aplicación con autenticación
3. ✅ `secrets.toml` - Configuración (debes editarlo)
4. ✅ `.gitignore` - Protección de credenciales
5. ✅ `requirements.txt` - Dependencias
6. ✅ `README.md` - Documentación

---

### ✅ PASO 2: Estructura de carpetas

```
cajas-diarias/
│
├── .streamlit/
│   └── secrets.toml          # ← Editar con tus credenciales
│
├── auth.py                   # ← Nuevo archivo
├── cajas_diarias_con_auth.py # ← Reemplaza cajas_diarias.py
├── requirements.txt          # ← Actualizar
├── .gitignore               # ← Verificar
└── README.md                # ← Nuevo archivo
```

---

### ✅ PASO 3: Configurar Supabase

#### A. Obtener ANON key

1. Ve a Supabase Dashboard
2. **Settings** > **API**
3. Copia la **anon public** key (NO la service_role)

#### B. Editar secrets.toml

```toml
[supabase]
url = "https://wzfcxjoyybjonvitlynze.supabase.co"
key = "TU_ANON_KEY_AQUI"  # ← PEGAR AQUÍ

SUPABASE_URL = "https://wzfcxjoyybjonvitlynze.supabase.co"
SUPABASE_KEY = "TU_ANON_KEY_AQUI"  # ← PEGAR AQUÍ
```

---

### ✅ PASO 4: Instalar dependencias

```bash
pip install -r requirements.txt
```

---

### ✅ PASO 5: Probar localmente

```bash
streamlit run cajas_diarias_con_auth.py
```

Deberías ver la pantalla de login.

---

### ✅ PASO 6: Probar credenciales

**Como Admin:**
```
Email: tu_email_admin@ejemplo.com
Password: tu_password
```

**Como Encargado:**
```
Email: Suc01@cajas.local
Password: Suc01
```

---

### ✅ PASO 7: Verificar funcionalidades

#### Como Admin:
- ✅ Puedes ver todas las sucursales
- ✅ Puedes seleccionar cualquier fecha
- ✅ Puedes generar reportes consolidados

#### Como Encargado:
- ✅ Solo ves tu sucursal asignada
- ✅ Solo puedes cargar HOY o AYER
- ✅ Reportes limitados a tu sucursal

---

### ✅ PASO 8: Cambiar contraseñas por defecto

1. Inicia sesión con cada usuario
2. Click en "🔑 Cambiar Contraseña"
3. Ingresa nueva contraseña segura
4. Guarda las nuevas credenciales

---

### ✅ PASO 9: Desplegar en Streamlit Cloud

#### A. Actualizar GitHub

```bash
git add auth.py cajas_diarias_con_auth.py requirements.txt .gitignore README.md
git commit -m "✨ Agregar sistema de autenticación"
git push origin main
```

⚠️ **NUNCA subas secrets.toml**

#### B. Configurar Secrets en Streamlit Cloud

1. Ve a tu app en [share.streamlit.io](https://share.streamlit.io)
2. **Settings** > **Secrets**
3. Pega el contenido de `secrets.toml`
4. Save

#### C. Actualizar nombre del archivo

En Streamlit Cloud:
- Cambia el **Main file path** a: `cajas_diarias_con_auth.py`

---

## 🎯 Diferencias Clave: Sin Auth vs Con Auth

### SIN AUTENTICACIÓN (anterior):
```python
# Cualquiera puede acceder
# Selector de sucursal manual
# Fecha manual sin validación
# Campo de usuario manual
```

### CON AUTENTICACIÓN (nuevo):
```python
# Requiere login
# Sucursales filtradas por usuario
# Fecha validada según rol
# Usuario automático desde sesión
```

---

## 🔧 Troubleshooting

### Error: "ModuleNotFoundError: No module named 'auth'"
```bash
# Asegúrate de que auth.py está en la misma carpeta
ls -la auth.py
```

### Error: "Invalid login credentials"
```
# Verifica formato de email:
✅ Correcto: Suc01@cajas.local
❌ Incorrecto: suc01@cajas.local
```

### No aparece la pantalla de login
```python
# Verifica línea 22 en cajas_diarias_con_auth.py:
if not auth.is_authenticated():
    auth.show_login_form()
    st.stop()
```

### Usuario no puede ver su sucursal
```sql
-- Verificar en Supabase SQL Editor:
SELECT 
  u.email,
  up.sucursal_asignada
FROM auth.users u
JOIN user_profiles up ON u.id = up.id
WHERE u.email = 'Suc01@cajas.local';

-- Si sucursal_asignada es NULL, actualizar:
UPDATE user_profiles
SET sucursal_asignada = 1
WHERE id = (SELECT id FROM auth.users WHERE email = 'Suc01@cajas.local');
```

---

## 🎉 ¡Listo!

Tu sistema ahora tiene:
- ✅ Autenticación segura
- ✅ Control de acceso por rol
- ✅ Restricción de fechas
- ✅ Usuarios por sucursal
- ✅ Cambio de contraseña

---

## 📞 Próximos Pasos

1. Cambiar todas las contraseñas por defecto
2. Crear usuarios admin adicionales
3. Probar todas las funcionalidades
4. Capacitar a los usuarios
5. Monitorear logs de acceso

---

## 💡 Tips de Seguridad

- 🔒 Usa contraseñas fuertes (mínimo 8 caracteres)
- 🔄 Cambia contraseñas periódicamente
- 📝 Mantén registro de usuarios activos
- 🚫 Desactiva usuarios que ya no trabajen
- 📊 Revisa logs de acceso regularmente
