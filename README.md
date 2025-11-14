# 💰 Sistema de Cajas Diarias

Sistema integral de gestión de cajas diarias para 11 sucursales con autenticación y control de acceso.

## 🚀 Instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/julio-minimarket/cajas-diarias.git
cd cajas-diarias
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar Supabase

#### A. Obtener credenciales
1. Ve a tu proyecto en [Supabase](https://supabase.com)
2. **Settings** > **API**
3. Copia:
   - **Project URL**
   - **anon/public key** (NO la service_role)

#### B. Crear archivo de configuración
Crea el archivo `.streamlit/secrets.toml`:

```toml
[supabase]
url = "https://tu-proyecto.supabase.co"
key = "tu-anon-public-key-aqui"

SUPABASE_URL = "https://tu-proyecto.supabase.co"
SUPABASE_KEY = "tu-anon-public-key-aqui"
```

⚠️ **IMPORTANTE**: Nunca subas este archivo a GitHub

### 4. Ejecutar la aplicación
```bash
streamlit run cajas_diarias_con_auth.py
```

## 👥 Usuarios del Sistema

### Administradores
- Acceso a todas las sucursales
- Pueden cargar movimientos de cualquier fecha
- Pueden generar reportes consolidados

### Encargados de Sucursal
- Acceso solo a su sucursal asignada
- Pueden cargar movimientos solo de HOY o AYER
- Reportes limitados a su sucursal

## 🔐 Credenciales por Defecto

### Sucursales (Suc01 - Suc11)
```
Email: Suc01@cajas.local hasta Suc11@cajas.local
Password: igual al usuario (Suc01, Suc02, etc.)
```

### Administradores
Contacta al administrador del sistema para credenciales.

⚠️ **Se recomienda cambiar las contraseñas en el primer acceso**

## 📋 Funcionalidades

### ✅ Carga de Movimientos
- **Ventas**: Múltiples métodos de pago
- **Gastos**: Solo efectivo, categorías personalizables
- **Sueldos**: Registro especial con nombre de empleado

### 📊 Resumen Diario
- Total de ventas por método de pago
- Total de gastos por categoría
- Cálculo automático de efectivo a entregar
- Gráficos interactivos

### 📈 Reportes
- Filtrado por rango de fechas
- Consolidado por sucursal (solo admin)
- Exportación a CSV
- Visualización detallada

## 🔧 Configuración Avanzada

### Estructura de Base de Datos

**Tablas principales:**
- `sucursales`: Registro de tiendas
- `movimientos_diarios`: Transacciones diarias
- `categorias`: Categorías de gastos/ventas
- `medios_pago`: Formas de pago
- `user_profiles`: Perfiles de usuarios

### Agregar Nueva Sucursal

```sql
-- En Supabase SQL Editor
INSERT INTO sucursales (id, nombre, activa)
VALUES (12, 'Nueva Sucursal', TRUE);

-- Crear usuario en Authentication > Users
-- Email: Suc12@cajas.local
-- Password: Suc12
-- ✅ Auto Confirm User

-- Asignar sucursal al usuario
UPDATE public.user_profiles
SET sucursal_asignada = 12,
    nombre_completo = 'Nueva Sucursal'
WHERE id = (
  SELECT id FROM auth.users 
  WHERE email = 'Suc12@cajas.local'
);
```

## 🛡️ Seguridad

- ✅ Autenticación mediante Supabase Auth
- ✅ Row Level Security (RLS) habilitado
- ✅ Validación de fechas según rol de usuario
- ✅ Restricción de acceso por sucursal
- ✅ Contraseñas encriptadas

## 📝 Cambiar Contraseña

1. Iniciar sesión
2. Click en **"🔑 Cambiar Contraseña"** en el sidebar
3. Ingresar contraseña actual y nueva
4. Confirmar cambio

## 🐛 Solución de Problemas

### Error: "Invalid login credentials"
- Verifica que el email y contraseña sean correctos
- Los usuarios de sucursal usan formato: `Suc01@cajas.local`

### Error: "No se encontró la categoría 'Sueldos'"
```sql
-- Ejecutar en Supabase SQL Editor
UPDATE categorias SET activa = TRUE WHERE nombre = 'Sueldos';
```

### No aparecen sucursales
- Verifica que tu usuario tenga sucursales asignadas
- Contacta al administrador

## 📞 Soporte

Para problemas o consultas, contacta al administrador del sistema.

## 📄 Licencia

Uso interno - Todos los derechos reservados
