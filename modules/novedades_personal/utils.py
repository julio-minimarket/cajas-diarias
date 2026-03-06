"""
modules/novedades_personal/utils.py
=====================================
Funciones utilitarias reutilizables en todo el módulo.
"""

from datetime import date
import calendar
import pandas as pd


def periodo_a_rango_fechas(periodo: str) -> tuple[date, date]:
    """
    Convierte 'YYYY-MM' al primer y último día del mes.
    Ejemplo: '2025-03' → (date(2025,3,1), date(2025,3,31))
    """
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
    return primer_dia, ultimo_dia


def fecha_a_periodo(fecha: date) -> str:
    """Convierte un date a formato 'YYYY-MM'."""
    return fecha.strftime("%Y-%m")


def lista_a_opciones_selectbox(lista: list[dict], campo_id: str, campo_nombre: str) -> dict:
    """
    Convierte una lista de dicts a un dict {nombre: id}
    para usar en st.selectbox de Streamlit.
    Ejemplo: {"Sucursal Centro": 1, "Sucursal Norte": 2}
    """
    return {item[campo_nombre]: item[campo_id] for item in lista}


def novedades_a_dataframe(novedades: list[dict]) -> pd.DataFrame:
    """
    Convierte la lista de novedades completas a un DataFrame
    listo para mostrar en Streamlit con las columnas formateadas.
    """
    if not novedades:
        return pd.DataFrame()

    df = pd.DataFrame(novedades)

    # Seleccionar y renombrar columnas para la vista
    columnas_mapa = {
        "empleado_nombre_completo": "Empleado",
        "sucursal_nombre":          "Sucursal",
        "fecha":                    "Fecha",
        "tipo_descripcion":         "Novedad",
        "categoria":                "Categoría",
        "cantidad":                 "Cantidad",
        "importe":                  "Importe",
        "observaciones":            "Observaciones",
        "confirmado":               "Confirmado",
        "usuario_carga":            "Usuario",
    }

    cols_presentes = {k: v for k, v in columnas_mapa.items() if k in df.columns}
    df = df[list(cols_presentes.keys())].rename(columns=cols_presentes)

    # Formatear importe como moneda si existe
    if "Importe" in df.columns:
        df["Importe"] = df["Importe"].apply(
            lambda x: f"${x:,.2f}" if pd.notna(x) and x else ""
        )

    return df


def resumen_a_dataframe(resumen: list[dict]) -> pd.DataFrame:
    """
    Convierte el resumen mensual a un DataFrame para el prelistado.
    """
    if not resumen:
        return pd.DataFrame()

    df = pd.DataFrame(resumen)

    columnas_mapa = {
        "empleado_nombre_completo": "Empleado",
        "tipo_novedad":             "Novedad",
        "categoria":                "Categoría",
        "cantidad_registros":       "Días/Veces",
        "total_cantidad":           "Total Hs.",
        "total_importe":            "Total $",
        "todo_confirmado":          "Confirmado",
    }

    cols_presentes = {k: v for k, v in columnas_mapa.items() if k in df.columns}
    df = df[list(cols_presentes.keys())].rename(columns=cols_presentes)

    return df


def nombre_mes(periodo: str) -> str:
    """
    Devuelve el nombre del mes en español.
    Ejemplo: '2025-03' → 'Marzo 2025'
    """
    meses = [
        "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
    ]
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    return f"{meses[mes-1]} {anio}"
