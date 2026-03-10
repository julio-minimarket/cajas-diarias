"""
modules/novedades_personal/services.py
=======================================
Lógica de negocio del módulo de Novedades de Personal.
Las UI (Streamlit) llaman a estos servicios, no a queries directamente.
"""

from datetime import date
from .db import get_supabase
from . import queries


# ══════════════════════════════════════════════════════════════
# VALIDACIONES DE NEGOCIO
# ══════════════════════════════════════════════════════════════

class NovedadError(Exception):
    """Error controlado de negocio — se muestra al usuario."""
    pass


def _verificar_cierre_mensual(fecha: date):
    """
    Lanza NovedadError si el período está cerrado.
    El cierre se guarda como 'YYYY-MM' en configuracion.
    """
    cierre = queries.get_configuracion("fecha_cierre_novedades")
    if cierre:
        periodo_fecha = f"{fecha.year}-{fecha.month:02d}"
        if periodo_fecha <= cierre:
            raise NovedadError(
                f"El período {periodo_fecha} está cerrado. "
                f"No se pueden cargar ni modificar novedades."
            )


def _verificar_no_confirmada(empleado_id: str, fecha: date):
    """Lanza NovedadError si la novedad del día ya fue confirmada."""
    existente = queries.get_novedad_por_empleado_fecha(empleado_id, fecha)
    if existente and existente.get("confirmado"):
        raise NovedadError(
            "Esta novedad ya fue confirmada y no puede modificarse."
        )


# ══════════════════════════════════════════════════════════════
# OPERACIONES DE NOVEDADES
# ══════════════════════════════════════════════════════════════

def crear_novedad_diaria(
    empleado_id: str,
    sucursal_id: int,
    fecha: date,
    usuario_carga: str,
) -> int:
    """
    Crea el registro maestro de novedad para un empleado en una fecha.
    Si ya existe, devuelve el ID del existente (idempotente).
    Lanza NovedadError si el período está cerrado.
    Devuelve el ID de la novedad.
    """
    _verificar_cierre_mensual(fecha)

    existente = queries.get_novedad_por_empleado_fecha(empleado_id, fecha)
    if existente:
        return existente["id"]

    resp = get_supabase().table("novedades").insert({
        "empleado_id":    empleado_id,
        "sucursal_id":    sucursal_id,
        "fecha":          str(fecha),
        "usuario_carga":  usuario_carga,
        "confirmado":     False,
    }).execute()

    return resp.data[0]["id"]


def agregar_detalle_novedad(
    novedad_id: int,
    tipo_novedad_id: int,
    cantidad: float | None = None,
    importe: float | None = None,
    observaciones: str | None = None,
) -> int:
    """
    Agrega una línea de detalle a la novedad.
    Devuelve el ID del detalle creado.
    """
    resp = get_supabase().table("novedades_detalle").insert({
        "novedad_id":      novedad_id,
        "tipo_novedad_id": tipo_novedad_id,
        "cantidad":        cantidad,
        "importe":         importe,
        "observaciones":   observaciones,
    }).execute()

    return resp.data[0]["id"]


def guardar_novedades_empleado(
    empleado_id: str,
    sucursal_id: int,
    fecha: date,
    usuario_carga: str,
    detalles: list[dict],
) -> dict:
    """
    Operación completa de guardado para un empleado:
    1. Valida período no cerrado y no confirmado.
    2. Crea o recupera el maestro de novedad.
    3. Elimina detalles anteriores (para permitir re-edición).
    4. Inserta los nuevos detalles.

    detalles = [
        {"tipo_novedad_id": 1, "cantidad": 3, "importe": None, "observaciones": ""},
        ...
    ]

    Devuelve {"ok": True, "novedad_id": 123} o lanza NovedadError.
    """
    _verificar_cierre_mensual(fecha)
    _verificar_no_confirmada(empleado_id, fecha)

    # Validación básica de detalles
    if not detalles:
        raise NovedadError("Debe cargar al menos una novedad.")

    supabase = get_supabase()

    # Crear o recuperar maestro
    novedad_id = crear_novedad_diaria(empleado_id, sucursal_id, fecha, usuario_carga)

    # Eliminar detalles anteriores (re-edición limpia)
    supabase.table("novedades_detalle").delete().eq("novedad_id", novedad_id).execute()

    # Insertar nuevos detalles en batch (una sola operación)
    filas = [
        {
            "novedad_id":      novedad_id,
            "tipo_novedad_id": d["tipo_novedad_id"],
            "cantidad":        d.get("cantidad"),
            "importe":         d.get("importe"),
            "observaciones":   d.get("observaciones", ""),
        }
        for d in detalles
        if d.get("tipo_novedad_id")  # ignorar filas sin tipo
    ]

    if filas:
        supabase.table("novedades_detalle").insert(filas).execute()

    return {"ok": True, "novedad_id": novedad_id}


def eliminar_novedad_empleado_fecha(empleado_id: str, fecha: date):
    """
    Elimina la novedad completa (maestro + detalles) de un empleado en una fecha.
    Las FK con ON DELETE CASCADE eliminan los detalles automáticamente.
    """
    _verificar_cierre_mensual(fecha)
    _verificar_no_confirmada(empleado_id, fecha)

    novedad = queries.get_novedad_por_empleado_fecha(empleado_id, fecha)
    if novedad:
        get_supabase().table("novedades").delete().eq("id", novedad["id"]).execute()


# ══════════════════════════════════════════════════════════════
# CONFIRMACIÓN MENSUAL
# ══════════════════════════════════════════════════════════════

def confirmar_novedades_mes(sucursal_id: int, periodo: str, usuario: str) -> dict:
    """
    Confirma todas las novedades del mes para una sucursal.
    periodo = 'YYYY-MM'
    Una vez confirmadas, no se pueden modificar ni eliminar.
    Devuelve {"ok": True, "confirmadas": N}.
    """
    pendientes = queries.get_novedades_mes_para_confirmar(sucursal_id, periodo)

    if not pendientes:
        return {"ok": True, "confirmadas": 0, "mensaje": "No hay novedades pendientes de confirmar."}

    ids = [r["id"] for r in pendientes]

    # Actualizar en batch — UNA sola operación
    get_supabase().table("novedades").update({
        "confirmado":          True,
        "fecha_confirmacion":  "now()",
        "usuario_carga":       usuario,
    }).in_("id", ids).execute()

    return {"ok": True, "confirmadas": len(ids)}


def cerrar_periodo(periodo: str):
    """
    Cierra el período mensual (no se pueden cargar más novedades).
    periodo = 'YYYY-MM'
    """
    queries.set_configuracion("fecha_cierre_novedades", periodo)


def reabrir_periodo():
    """Reabre el período eliminando el cierre."""
    queries.set_configuracion("fecha_cierre_novedades", "")


# ══════════════════════════════════════════════════════════════
# DATOS PARA REPORTES (llamadas simples a queries)
# ══════════════════════════════════════════════════════════════

def obtener_novedades_por_empleado(empleado_id: str, fecha_desde: date, fecha_hasta: date):
    return queries.get_novedades_por_empleado(empleado_id, fecha_desde, fecha_hasta)


def obtener_novedades_por_sucursal(sucursal_id: int, fecha_desde: date, fecha_hasta: date):
    return queries.get_novedades_por_sucursal(sucursal_id, fecha_desde, fecha_hasta)


def generar_prelistado_mensual(sucursal_id: int, periodo: str):
    return queries.get_prelistado_mensual(sucursal_id, periodo)


def obtener_datos_reporte_pdf(
    sucursal_id: int | None,
    periodo: str,
) -> dict:
    """
    Reúne resumen y detalle día a día para el reporte PDF mensual.
    sucursal_id=None → consolida TODAS las sucursales.
    Devuelve {"resumen": [...], "detalle": [...]}
    """
    if sucursal_id is not None:
        from .utils import periodo_a_rango_fechas
        fd, fh = periodo_a_rango_fechas(periodo)
        resumen = queries.get_prelistado_mensual(sucursal_id, periodo)
        detalle = queries.get_novedades_por_sucursal(sucursal_id, fd, fh)
    else:
        resumen = queries.get_prelistado_todas_sucursales(periodo)
        detalle = queries.get_novedades_todas_sucursales_mes(periodo)
    return {"resumen": resumen, "detalle": detalle}
