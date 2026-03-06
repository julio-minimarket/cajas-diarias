"""
modules/novedades_personal/queries.py
======================================
Todas las consultas a la base de datos.

PRINCIPIO: NUNCA hacer queries dentro de un loop (problema N+1).
Siempre traer todo de una sola vez usando JOINs o fetch masivo.
"""

from datetime import date
from .db import get_supabase


# ══════════════════════════════════════════════════════════════
# SUCURSALES
# ══════════════════════════════════════════════════════════════

def get_sucursales_activas() -> list[dict]:
    """Devuelve todas las sucursales activas ordenadas por nombre."""
    resp = (
        get_supabase()
        .table("sucursales")
        .select("id, codigo, nombre")
        .eq("activa", True)
        .order("nombre")
        .execute()
    )
    return resp.data or []


# ══════════════════════════════════════════════════════════════
# EMPLEADOS
# ══════════════════════════════════════════════════════════════

def get_empleados_por_sucursal(sucursal_id: int) -> list[dict]:
    """
    Devuelve todos los empleados activos de una sucursal.
    UNA sola query — sin loop posterior.
    """
    resp = (
        get_supabase()
        .table("empleados")
        .select("id, legajo, apellido, nombre, cuit")
        .eq("sucursal_id", sucursal_id)
        .eq("activo", True)
        .order("apellido")
        .execute()
    )
    return resp.data or []


def get_todos_los_empleados() -> list[dict]:
    """Devuelve todos los empleados activos con su sucursal (JOIN)."""
    resp = (
        get_supabase()
        .table("empleados")
        .select("id, legajo, apellido, nombre, cuit, sucursal_id, sucursales(nombre)")
        .eq("activo", True)
        .order("apellido")
        .execute()
    )
    return resp.data or []


# ══════════════════════════════════════════════════════════════
# TIPOS DE NOVEDAD
# ══════════════════════════════════════════════════════════════

def get_tipos_novedad(categoria: str | None = None) -> list[dict]:
    """
    Devuelve todos los tipos de novedad activos.
    Si se pasa categoria ('AUSENCIA' o 'ADICIONAL') filtra por ella.
    """
    query = (
        get_supabase()
        .table("tipos_novedad")
        .select("id, codigo, descripcion, categoria, requiere_cantidad, requiere_importe")
        .eq("activo", True)
        .order("categoria, descripcion")
    )
    if categoria:
        query = query.eq("categoria", categoria)

    return query.execute().data or []


# ══════════════════════════════════════════════════════════════
# NOVEDADES — LECTURA
# ══════════════════════════════════════════════════════════════

def get_novedades_del_dia(sucursal_id: int, fecha: date) -> list[dict]:
    """
    Devuelve TODAS las novedades de una sucursal en una fecha.
    Usa la vista v_novedades_completas para evitar N+1.
    UNA sola query con JOIN en la vista.
    """
    resp = (
        get_supabase()
        .table("v_novedades_completas")
        .select("*")
        .eq("sucursal_id", sucursal_id)
        .eq("fecha", str(fecha))
        .order("apellido")
        .execute()
    )
    return resp.data or []


def get_novedad_por_empleado_fecha(empleado_id: str, fecha: date) -> dict | None:
    """
    Busca el registro maestro de novedad de un empleado en una fecha.
    Devuelve None si no existe todavía.
    """
    resp = (
        get_supabase()
        .table("novedades")
        .select("id, confirmado")
        .eq("empleado_id", empleado_id)
        .eq("fecha", str(fecha))
        .execute()
    )
    return resp.data[0] if resp.data else None


def get_detalle_novedad(novedad_id: int) -> list[dict]:
    """
    Devuelve el detalle de una novedad (sus líneas de tipo_novedad).
    """
    resp = (
        get_supabase()
        .table("novedades_detalle")
        .select("id, tipo_novedad_id, cantidad, importe, observaciones, tipos_novedad(descripcion, categoria)")
        .eq("novedad_id", novedad_id)
        .execute()
    )
    return resp.data or []


def get_novedades_por_empleado(empleado_id: str, fecha_desde: date, fecha_hasta: date) -> list[dict]:
    """
    Historial de novedades de UN empleado en un rango de fechas.
    UNA query — usa la vista con JOIN.
    """
    resp = (
        get_supabase()
        .table("v_novedades_completas")
        .select("*")
        .eq("empleado_id", empleado_id)
        .gte("fecha", str(fecha_desde))
        .lte("fecha", str(fecha_hasta))
        .order("fecha")
        .execute()
    )
    return resp.data or []


def get_novedades_por_sucursal(sucursal_id: int, fecha_desde: date, fecha_hasta: date) -> list[dict]:
    """
    Novedades de una sucursal en un rango.
    UNA query con JOIN en la vista.
    """
    resp = (
        get_supabase()
        .table("v_novedades_completas")
        .select("*")
        .eq("sucursal_id", sucursal_id)
        .gte("fecha", str(fecha_desde))
        .lte("fecha", str(fecha_hasta))
        .order("fecha, apellido")
        .execute()
    )
    return resp.data or []


def get_prelistado_mensual(sucursal_id: int, periodo: str) -> list[dict]:
    """
    Prelistado mensual para una sucursal.
    periodo = 'YYYY-MM'
    Usa la vista v_resumen_mensual.
    """
    resp = (
        get_supabase()
        .table("v_resumen_mensual")
        .select("*")
        .eq("sucursal_id", sucursal_id)
        .eq("periodo", periodo)
        .order("empleado_nombre_completo, tipo_novedad")
        .execute()
    )
    return resp.data or []


def get_novedades_mes_para_confirmar(sucursal_id: int, periodo: str) -> list[dict]:
    """
    Devuelve todos los registros de novedades del mes aún no confirmados.
    Se usa para el proceso de confirmación mensual.
    """
    fecha_desde = f"{periodo}-01"
    # Último día del mes: truco con el mes siguiente - 1 día
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    if mes == 12:
        fecha_hasta = f"{anio+1}-01-01"
    else:
        fecha_hasta = f"{anio}-{mes+1:02d}-01"

    resp = (
        get_supabase()
        .table("novedades")
        .select("id")
        .eq("sucursal_id", sucursal_id)
        .eq("confirmado", False)
        .gte("fecha", fecha_desde)
        .lt("fecha", fecha_hasta)
        .execute()
    )
    return resp.data or []


# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════

def get_configuracion(clave: str) -> str | None:
    """Lee un valor de la tabla configuracion."""
    resp = (
        get_supabase()
        .table("configuracion")
        .select("valor")
        .eq("clave", clave)
        .execute()
    )
    return resp.data[0]["valor"] if resp.data else None


def set_configuracion(clave: str, valor: str):
    """Actualiza o inserta un valor en la tabla configuracion."""
    get_supabase().table("configuracion").upsert({
        "clave": clave,
        "valor": valor,
        "updated_at": "now()",
    }).execute()
