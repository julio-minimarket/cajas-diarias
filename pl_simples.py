"""
Módulo P&L Simples - Profit & Loss Simple (v2.3 con Diseño Ejecutivo)
Genera informes mensuales de Ingresos vs. Egresos por sucursal
Incluye análisis de composición del gasto, estadísticas comparativas y evolución histórica

Autor: Julio Becker
Fecha: Enero 2026
Integrado a: cajas_diarias.py
Versión: 2.3 - Mejora estética: Reporte Granular estilo Ejecutivo
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
from pathlib import Path
import calendar
from io import BytesIO

# ==================== FUNCIONES DE PROCESAMIENTO DE GASTOS ====================

# ============================================================
# MAPEO MANUAL: CSV -> SUCURSALES
# ============================================================

# Mapeo hardcoded (usado si no hay tabla mapeo_sucursales_csv)
MAPEO_CSV_HARDCODED = {
    'Belfast S.A.': 4,
    'Chicken Chill Minimarket S.A.': 8,
    'Costumbres Argentinas-Minimarket S.A.': 10,
    'Destileria Open 24 S.A.': 13,
    'Friends S.A.S. Patagonia': 5,
    'Liverpool Minimarket S.A.': 7,
    'Minimarket S.A. ': 1,  # Con espacio al final
    'Minimarket S.A.': 1,
    'Open 24 Minimarket S.A.': 11,
    'Pocillos S.A.S. 1885 ': 3,  # Con espacio al final
    'Pocillos S.A.S. 1885': 3,
    'Pocillos S.A.S.Napoles Rgl': 2,
    'Rincon Chico S.A.S. Napoles Calafate': 6,
    'Temple Minimarket S.A.': 9,
    # NOTA: "Andes Food S.A." no mapeada - no existe sucursal
}

def obtener_mapeo_manual(supabase):
    """
    Obtiene mapeo manual desde tabla o hardcoded
    Prioridad:
    1. Tabla mapeo_sucursales_csv en Supabase (si existe)
    2. MAPEO_CSV_HARDCODED (fallback)
    """
    mapeo = {}
    
    # Intentar obtener de la tabla
    try:
        result = supabase.table("mapeo_sucursales_csv")\
            .select("nombre_csv, sucursal_id")\
            .eq("activo", True)\
            .execute()
        
        if result.data:
            # Usar mapeo de la tabla
            for row in result.data:
                # Mapeo exacto
                mapeo[row['nombre_csv']] = row['sucursal_id']
                
                # Mapeo normalizado
                nombre_norm = row['nombre_csv'].upper().replace(' ', '').replace('.', '').replace(',', '')
                mapeo[nombre_norm] = row['sucursal_id']
            
            return mapeo
    except Exception as e:
        # Tabla no existe o error al consultar
        print(f"[INFO] No se pudo obtener mapeo de DB, usando hardcoded: {e}")
    
    # Usar mapeo hardcoded si no hay tabla o está vacía
    if not mapeo:
        mapeo = MAPEO_CSV_HARDCODED.copy()
        
        # Agregar versiones normalizadas
        for nombre_csv, sucursal_id in MAPEO_CSV_HARDCODED.items():
            nombre_norm = nombre_csv.upper().replace(' ', '').replace('.', '').replace(',', '')
            mapeo[nombre_norm] = sucursal_id
    
    return mapeo


# ============================================================
# FUNCIONES DE MAPEO
# ============================================================

def convertir_importe(valor):
    """
    Convierte importes en diferentes formatos a float
    Maneja formato argentino ($1.234.567,89) y formato numérico (1234567.89)
    """
    valor = str(valor).strip()
    
    # Si tiene $ y puntos (formato argentino: $1.234.567,89)
    if '$' in valor:
        valor = valor.replace('$', '').strip()
        valor = valor.replace('.', '')  # Elimino separadores de miles
        valor = valor.replace(',', '.')  # Coma decimal a punto
    # Si tiene coma pero no $ (formato: 1.234.567,89)
    elif ',' in valor:
        valor = valor.replace('.', '')  # Elimino separadores de miles
        valor = valor.replace(',', '.')  # Coma decimal a punto
    
    try:
        return float(valor)
    except:
        return 0.0


def procesar_archivo_gastos(archivo_csv):
    """
    Procesa un archivo CSV de gastos/facturas y retorna un DataFrame con los datos calculados
    Maneja múltiples formatos de fecha
    """
    try:
        # Cargo el archivo
        df = pd.read_csv(archivo_csv)
        
        # Elimino la última fila (totales del mes) si existe
        if len(df) > 0 and pd.isna(df.iloc[-1]['Empresa']):
            df = df[:-1]
        
        # Columnas para calcular NETO
        columnas_neto = ['Importe Neto 21', 'Importe Neto 10_5', 'Importe Neto 27', 'Impuestos Internos']
        
        # Columnas para calcular IVA
        columnas_iva = ['Percepcion Iva', 'Otras Percepciones', 'Percepcion IIBB', 
                        'Iva 21', 'Iva 10,5', 'Iva 27']
        
        # Convierto todas las columnas necesarias
        for col in columnas_neto + columnas_iva:
            if col in df.columns:
                df[col] = df[col].apply(convertir_importe)
        
        # Convertir fechas - Priorizar Fecha C. (Contabilización) sobre Fecha E. (Emisión)
        # Intentar primero con Fecha C.
        if 'Fecha C.' in df.columns:
            df['Fecha'] = pd.to_datetime(df['Fecha C.'], format='%d/%m/%Y', errors='coerce')
        
        # Si no hay Fecha C. o hay NaN, usar Fecha E.
        if 'Fecha E.' in df.columns:
            if 'Fecha' not in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha E.'], format='%d/%m/%Y', errors='coerce')
            else:
                # Rellenar NaN de Fecha con Fecha E.
                mask = df['Fecha'].isna()
                df.loc[mask, 'Fecha'] = pd.to_datetime(df.loc[mask, 'Fecha E.'], format='%d/%m/%Y', errors='coerce')
        
        # Calculo NETO e IVA para cada fila
        df['NETO'] = df[columnas_neto].sum(axis=1)
        df['IVA_PERCEPCIONES'] = df[columnas_iva].sum(axis=1)
        df['TOTAL_GASTO'] = df['NETO'] + df['IVA_PERCEPCIONES']
        
        # Elimino filas sin datos válidos
        df = df.dropna(subset=['Empresa'])
        df = df[df['TOTAL_GASTO'] > 0]
        
        return df
        
    except Exception as e:
        st.error(f"❌ Error procesando archivo de gastos: {str(e)}")
        return None


def verificar_gastos_existentes(supabase, sucursal_id, mes, anio):
    """
    Verifica si ya existen gastos cargados para una sucursal en un período específico
    """
    try:
        query = supabase.table("gastos_mensuales").select("*")
        
        if sucursal_id is not None:
            query = query.eq("sucursal_id", sucursal_id)
        
        query = query.eq("mes", mes).eq("anio", anio)
        
        result = query.execute()
        
        if result.data and len(result.data) > 0:
            total = sum(r['total'] for r in result.data)
            return {
                'existe': True,
                'cantidad': len(result.data),
                'total': total,
                'fecha_importacion': result.data[0].get('fecha_importacion')
            }
        else:
            return {'existe': False, 'cantidad': 0, 'total': 0}
            
    except Exception as e:
        st.error(f"❌ Error verificando gastos existentes: {str(e)}")
        return {'existe': False, 'cantidad': 0, 'total': 0}


def crear_mapeo_sucursales(supabase):
    """
    Crea un diccionario de mapeo: nombre_empresa -> sucursal_id
    Soporta coincidencias parciales y variaciones de nombres
    """
    try:
        result = supabase.table("sucursales").select("id, nombre").execute()
        if not result.data:
            return {}
        
        mapeo = {}
        for sucursal in result.data:
            nombre = sucursal['nombre']
            sucursal_id = sucursal['id']
            
            # Mapeo exacto
            mapeo[nombre] = sucursal_id
            
            # Mapeo normalizado (sin espacios, mayúsculas, puntos)
            nombre_norm = nombre.upper().replace(' ', '').replace('.', '').replace(',', '')
            mapeo[nombre_norm] = sucursal_id
            
            # Mapeo por palabras clave (primeras palabras significativas)
            palabras = nombre.upper().split()
            if len(palabras) > 0:
                # Primera palabra
                mapeo[palabras[0]] = sucursal_id
                # Primeras dos palabras
                if len(palabras) > 1:
                    mapeo[f"{palabras[0]} {palabras[1]}"] = sucursal_id
        
        return mapeo
    except Exception as e:
        st.error(f"❌ Error creando mapeo de sucursales: {str(e)}")
        return {}


def obtener_sucursal_id_desde_nombre(nombre_empresa, mapeo_manual, mapeo_automatico):
    """
    Obtiene el sucursal_id desde el nombre de la empresa del CSV
    """
    if not nombre_empresa or pd.isna(nombre_empresa):
        return None
    
    nombre_empresa = str(nombre_empresa).strip()
    
    # PRIORIDAD 1: Mapeo manual EXACTO
    if nombre_empresa in mapeo_manual:
        return mapeo_manual[nombre_empresa]
    
    # PRIORIDAD 2: Mapeo manual NORMALIZADO
    nombre_norm = nombre_empresa.upper().replace(' ', '').replace('.', '').replace(',', '')
    if nombre_norm in mapeo_manual:
        return mapeo_manual[nombre_norm]
    
    # PRIORIDAD 3: Mapeo automático
    # Estrategia 1: Coincidencia exacta
    if nombre_empresa in mapeo_automatico:
        return mapeo_automatico[nombre_empresa]
    
    # Estrategia 2: Coincidencia normalizada
    if nombre_norm in mapeo_automatico:
        return mapeo_automatico[nombre_norm]
    
    # Estrategia 3: Por palabras clave
    palabras = nombre_empresa.upper().split()
    if len(palabras) > 0:
        # Primera palabra
        if palabras[0] in mapeo_automatico:
            return mapeo_automatico[palabras[0]]
        # Primeras dos palabras
        if len(palabras) > 1:
            clave = f"{palabras[0]} {palabras[1]}"
            if clave in mapeo_automatico:
                return mapeo_automatico[clave]
    
    # Estrategia 4: Búsqueda parcial (contiene)
    for nombre_mapeado, suc_id in mapeo_automatico.items():
        if nombre_empresa.upper() in nombre_mapeado.upper():
            return suc_id
        if nombre_mapeado.upper() in nombre_empresa.upper():
            return suc_id
    
    return None


def guardar_gastos_en_db(supabase, df_gastos, usuario=None):
    """
    Guarda los gastos procesados en la base de datos
    Mapea automáticamente nombres de empresas a sucursal_id
    """
    exitosos = 0
    errores = []
    sin_sucursal = []
    sin_fecha = []
    duplicados = []  # Registros que ya existen en DB
    
    # Obtener AMBOS mapeos
    mapeo_manual = obtener_mapeo_manual(supabase)
    mapeo_automatico = crear_mapeo_sucursales(supabase)
    
    try:
        for idx, row in df_gastos.iterrows():
            try:
                # Obtener nombre de la empresa
                nombre_empresa = row.get('Empresa', '')
                
                # Mapear a sucursal_id usando mapeo híbrido
                sucursal_id = obtener_sucursal_id_desde_nombre(
                    nombre_empresa, 
                    mapeo_manual, 
                    mapeo_automatico
                )
                
                if sucursal_id is None:
                    sin_sucursal.append({
                        'fila': idx + 1,
                        'empresa': nombre_empresa,
                        'fecha': row.get('Fecha', ''),
                        'total': row.get('TOTAL_GASTO', 0),
                        'sugerencia': '💡 Verifica que la sucursal exista en Supabase'
                    })
                    continue
                
                # IMPORTANTE: Extraer mes y año de la fecha del CSV
                fecha_contable = None
                if 'Fecha C.' in row and pd.notna(row['Fecha C.']):
                    try:
                        fecha_contable = pd.to_datetime(row['Fecha C.'], format='%d/%m/%Y', errors='coerce')
                    except:
                        pass
                
                if fecha_contable is None or pd.isna(fecha_contable):
                    if 'Fecha E.' in row and pd.notna(row['Fecha E.']):
                        try:
                            fecha_contable = pd.to_datetime(row['Fecha E.'], format='%d/%m/%Y', errors='coerce')
                        except:
                            pass
                
                if fecha_contable is None or pd.isna(fecha_contable):
                    if 'Fecha' in row and pd.notna(row['Fecha']):
                        fecha_contable = row['Fecha']
                
                if fecha_contable is None or pd.isna(fecha_contable):
                    sin_fecha.append({
                        'fila': idx + 1,
                        'empresa': nombre_empresa,
                        'fecha_e': row.get('Fecha E.', ''),
                        'fecha_c': row.get('Fecha C.', ''),
                        'total': row.get('TOTAL_GASTO', 0)
                    })
                    continue
                
                mes = fecha_contable.month
                anio = fecha_contable.year
                
                # Función auxiliar para convertir valores de forma segura
                def convertir_a_float_seguro(valor):
                    """Convierte un valor a float, reemplazando nan, inf, None con 0"""
                    try:
                        if pd.isna(valor) or valor is None:
                            return 0.0
                        val_float = float(valor)
                        if not pd.isna(val_float) and val_float != float('inf') and val_float != float('-inf'):
                            return val_float
                        else:
                            return 0.0
                    except (ValueError, TypeError):
                        return 0.0
                
                # Preparar datos para inserción con conversión segura
                gasto_data = {
                    'sucursal_id': sucursal_id,
                    'mes': mes,
                    'anio': anio,
                    'fecha': str(fecha_contable.date()),
                    'tipo_comprobante': str(row.get('Tipo Comprobante', '')) if pd.notna(row.get('Tipo Comprobante')) else '',
                    'numero_comprobante': str(row.get('Comprobante', '')) if pd.notna(row.get('Comprobante')) else '',
                    'proveedor': str(row.get('Proveedor', '')) if pd.notna(row.get('Proveedor')) else '',
                    'cuit': str(row.get('Cuit', '')) if pd.notna(row.get('Cuit')) else '',
                    'rubro': str(row.get('Rubro', '')) if pd.notna(row.get('Rubro')) else '',
                    'subrubro': str(row.get('Subrubro', '')) if pd.notna(row.get('Subrubro')) else '',
                    'neto': convertir_a_float_seguro(row['NETO']),
                    'iva_percepciones': convertir_a_float_seguro(row['IVA_PERCEPCIONES']),
                    'total': convertir_a_float_seguro(row['TOTAL_GASTO']),
                    'importe_neto_21': convertir_a_float_seguro(row.get('Importe Neto 21', 0)),
                    'importe_neto_10_5': convertir_a_float_seguro(row.get('Importe Neto 10_5', 0)),
                    'importe_neto_27': convertir_a_float_seguro(row.get('Importe Neto 27', 0)),
                    'impuestos_internos': convertir_a_float_seguro(row.get('Impuestos Internos', 0)),
                    'percepcion_iva': convertir_a_float_seguro(row.get('Percepcion Iva', 0)),
                    'otras_percepciones': convertir_a_float_seguro(row.get('Otras Percepciones', 0)),
                    'percepcion_iibb': convertir_a_float_seguro(row.get('Percepcion IIBB', 0)),
                    'iva_21': convertir_a_float_seguro(row.get('Iva 21', 0)),
                    'iva_10_5': convertir_a_float_seguro(row.get('Iva 10,5', 0)),
                    'iva_27': convertir_a_float_seguro(row.get('Iva 27', 0)),
                    'usuario_importacion': usuario
                }
                
                # Insertar en base de datos
                supabase.table("gastos_mensuales").insert(gasto_data).execute()
                exitosos += 1
                
            except Exception as e:
                error_str = str(e)
                # Detectar duplicados
                if 'duplicate key' in error_str.lower() and 'unique_gasto_registro' in error_str.lower():
                    duplicados.append({
                        'fila': idx + 1,
                        'sucursal_id': sucursal_id,
                        'empresa': nombre_empresa,
                        'proveedor': row.get('Proveedor', ''),
                        'total': row.get('TOTAL_GASTO', 0),
                        'fecha': str(fecha_contable.date()) if fecha_contable else ''
                    })
                else:
                    # Error real (no duplicado)
                    errores.append(f"Fila {idx + 1}: {error_str}")
        
        return {
            'exitosos': exitosos,
            'errores': errores,
            'sin_sucursal': sin_sucursal,
            'sin_fecha': sin_fecha,
            'duplicados': duplicados
        }
        
    except Exception as e:
        return {
            'exitosos': exitosos,
            'errores': [f"Error general: {str(e)}"] + errores,
            'sin_sucursal': sin_sucursal,
            'sin_fecha': sin_fecha
        }


def eliminar_gastos_periodo(supabase, sucursal_id, mes, anio):
    """
    Elimina todos los gastos de un período específico
    """
    try:
        supabase.table("gastos_mensuales")\
            .delete()\
            .eq("sucursal_id", sucursal_id)\
            .eq("mes", mes)\
            .eq("anio", anio)\
            .execute()
        return True
    except Exception as e:
        st.error(f"❌ Error eliminando gastos: {str(e)}")
        return False


@st.cache_data(ttl=30)  # 🚀 OPTIMIZACIÓN: Cachear por 30 segundos
def obtener_gastos_db(_supabase, mes, anio, sucursal_id=None):
    """
    Obtiene los gastos desde la base de datos
    """
    try:
        query = _supabase.table("gastos_mensuales").select("*")
        
        query = query.eq("mes", mes)
        query = query.eq("anio", anio)
        
        if sucursal_id is not None:
            query = query.eq("sucursal_id", sucursal_id)
        
        result = query.execute()
        
        if result.data:
            return pd.DataFrame(result.data)
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Error obteniendo gastos de DB: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=30)  # 🚀 OPTIMIZACIÓN: Cachear por 30 segundos
def obtener_ingresos_mensuales(_supabase, mes, anio, sucursal_id=None):
    """
    Obtiene los ingresos mensuales de la base de datos de cajas_diarias
    """
    try:
        # Construir fechas de inicio y fin del mes
        primer_dia = date(anio, mes, 1)
        ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
        
        # Query base
        query = _supabase.table("movimientos_diarios").select("*")
        
        # Filtrar por fechas
        query = query.gte("fecha", str(primer_dia))
        query = query.lte("fecha", str(ultimo_dia))
        
        # Filtrar por sucursal si se especifica
        if sucursal_id is not None:
            query = query.eq("sucursal_id", sucursal_id)
        
        # Filtrar solo ventas (ingresos)
        query = query.eq("tipo", "venta")
        
        # Ejecutar query
        result = query.execute()
        
        if result.data:
            df = pd.DataFrame(result.data)
            return df
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Error obteniendo ingresos: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=30)  # 🚀 OPTIMIZACIÓN: Cachear por 30 segundos
def obtener_evolucion_historica(_supabase, sucursal_id, meses_atras=12):
    """
    Obtiene la evolución histórica de gastos e ingresos
    """
    try:
        # Obtener gastos históricos
        result_gastos = _supabase.table("gastos_mensuales")\
            .select("anio, mes, total")\
            .eq("sucursal_id", sucursal_id)\
            .execute()
        
        if not result_gastos.data:
            return pd.DataFrame()
        
        # Convertir a DataFrame y agrupar
        df_gastos = pd.DataFrame(result_gastos.data)
        df_gastos_agg = df_gastos.groupby(['anio', 'mes'])['total'].sum().reset_index()
        df_gastos_agg.columns = ['anio', 'mes', 'total_gastos']
        
        # Crear columna de período
        df_gastos_agg['periodo'] = pd.to_datetime(
            df_gastos_agg['anio'].astype(str) + '-' + 
            df_gastos_agg['mes'].astype(str).str.zfill(2) + '-01'
        )
        
        # Obtener ingresos históricos
        fecha_limite = pd.Timestamp.now() - pd.DateOffset(months=meses_atras)
        
        result_ingresos = _supabase.table("movimientos_diarios")\
            .select("fecha, monto")\
            .eq("sucursal_id", sucursal_id)\
            .eq("tipo", "venta")\
            .gte("fecha", str(fecha_limite.date()))\
            .execute()
        
        if result_ingresos.data:
            df_ingresos = pd.DataFrame(result_ingresos.data)
            df_ingresos['fecha'] = pd.to_datetime(df_ingresos['fecha'])
            df_ingresos['anio'] = df_ingresos['fecha'].dt.year
            df_ingresos['mes'] = df_ingresos['fecha'].dt.month
            df_ingresos['periodo'] = df_ingresos['fecha'].dt.to_period('M').dt.to_timestamp()
            
            df_ingresos_agg = df_ingresos.groupby(['anio', 'mes', 'periodo'])['monto'].sum().reset_index()
            df_ingresos_agg.columns = ['anio', 'mes', 'periodo', 'total_ingresos']
        else:
            df_ingresos_agg = pd.DataFrame(columns=['anio', 'mes', 'periodo', 'total_ingresos'])
        
        # Merge de gastos e ingresos
        df_evolucion = pd.merge(
            df_gastos_agg,
            df_ingresos_agg,
            on=['anio', 'mes', 'periodo'],
            how='outer'
        ).fillna(0)
        
        # Calcular resultado y margen
        df_evolucion['resultado'] = df_evolucion['total_ingresos'] - df_evolucion['total_gastos']
        df_evolucion['margen'] = (df_evolucion['resultado'] / df_evolucion['total_ingresos'] * 100).fillna(0)
        
        # Ordenar por período
        df_evolucion = df_evolucion.sort_values('periodo', ascending=False)
        
        # Limitar a últimos N meses
        df_evolucion = df_evolucion.head(meses_atras)
        
        return df_evolucion.sort_values('periodo')
        
    except Exception as e:
        st.error(f"❌ Error obteniendo evolución histórica: {str(e)}")
        return pd.DataFrame()


def limpiar_cache_pl_simples():
    """
    Limpia el caché de las consultas de P&L Simples.
    """
    try:
        obtener_gastos_db.clear()
        obtener_ingresos_mensuales.clear()
        obtener_evolucion_historica.clear()
        return True
    except Exception as e:
        st.warning(f"⚠️ No se pudo limpiar el caché: {str(e)}")
        return False


def calcular_benchmarks_gastronomia():
    """
    Retorna benchmarks estándar del rubro gastronómico
    Basado en estadísticas de la industria argentina
    """
    return {
        'ALIMENTOS': {'porcentaje_ideal': 30.0, 'rango_min': 25.0, 'rango_max': 35.0},
        'BEBIDAS': {'porcentaje_ideal': 8.0, 'rango_min': 6.0, 'rango_max': 10.0},
        'SUELDOS': {'porcentaje_ideal': 30.0, 'rango_min': 25.0, 'rango_max': 35.0},
        'SERVICIOS': {'porcentaje_ideal': 15.0, 'rango_min': 12.0, 'rango_max': 18.0},
        'ALQUILER': {'porcentaje_ideal': 8.0, 'rango_min': 6.0, 'rango_max': 10.0},
        'INSUMOS Y DESCARTABLES': {'porcentaje_ideal': 4.0, 'rango_min': 3.0, 'rango_max': 5.0},
        'IMPUESTOS': {'porcentaje_ideal': 5.0, 'rango_min': 4.0, 'rango_max': 6.0},
        'MATERIALES': {'porcentaje_ideal': 3.0, 'rango_min': 2.0, 'rango_max': 5.0}
    }


def analizar_composicion_gastos(df_gastos, ingresos_totales):
    """
    Analiza la composición de gastos y compara con benchmarks
    """
    # Determinar columna de totales
    col_total = 'TOTAL_GASTO' if 'TOTAL_GASTO' in df_gastos.columns else 'total'
    col_rubro = 'Rubro' if 'Rubro' in df_gastos.columns else 'rubro'
    
    # Agrupar por rubro
    gastos_por_rubro = df_gastos.groupby(col_rubro)[col_total].sum().sort_values(ascending=False)
    
    # Calcular porcentajes sobre ingresos
    total_gastos = gastos_por_rubro.sum()
    
    analisis = {
        'total_gastos': total_gastos,
        'ingresos': ingresos_totales,
        'resultado': ingresos_totales - total_gastos,
        'margen_porcentaje': ((ingresos_totales - total_gastos) / ingresos_totales * 100) if ingresos_totales > 0 else 0,
        'rubros': []
    }
    
    benchmarks = calcular_benchmarks_gastronomia()
    
    for rubro, gasto in gastos_por_rubro.items():
        porcentaje_real = (gasto / ingresos_totales * 100) if ingresos_totales > 0 else 0
        
        # Buscar benchmark
        rubro_upper = str(rubro).upper()
        benchmark = None
        estado = "neutral"
        
        # Buscar benchmark exacto o parcial
        for key in benchmarks.keys():
            if key in rubro_upper or rubro_upper in key:
                benchmark = benchmarks[key]
                
                # Evaluar estado
                if porcentaje_real < benchmark['rango_min']:
                    estado = "bajo"
                elif porcentaje_real > benchmark['rango_max']:
                    estado = "alto"
                else:
                    estado = "ok"
                break
        
        analisis['rubros'].append({
            'rubro': rubro,
            'gasto': gasto,
            'porcentaje_real': porcentaje_real,
            'benchmark': benchmark,
            'estado': estado
        })
    
    return analisis


# ==================== INTERFAZ STREAMLIT ====================

def mostrar_tab_importacion(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada):
    """
    Tab de importación de gastos desde CSV
    Soporta múltiples sucursales en un mismo CSV con mapeo automático
    Las fechas se extraen automáticamente de cada registro del CSV
    """
    st.subheader("📁 Importar Gastos desde CSV")
    
    st.info("💡 **Importación Inteligente**: El sistema detecta automáticamente las sucursales Y las fechas de cada gasto desde el CSV. No necesitas seleccionar mes/año manualmente.")
    
    # Crear AMBOS mapeos
    mapeo_manual = obtener_mapeo_manual(supabase)
    mapeo_automatico = crear_mapeo_sucursales(supabase)
    
    if not mapeo_automatico:
        st.error("❌ No se pudieron cargar las sucursales. Verifica la conexión a Supabase.")
        return
    
    # Mostrar información de mapeo
    with st.expander("🏪 Información de Mapeo"):
        if mapeo_manual:
            st.write("✅ **Mapeo Manual Activo** (prioridad alta)")
            st.write(f"   - {len(set(mapeo_manual.values()))} empresas CSV -> sucursales")
        else:
            st.write("⚠️ **Mapeo Manual No Configurado** (solo mapeo automático)")
        
        st.write("")
        st.write("📋 **Sucursales disponibles:**")
        for nombre, suc_id in mapeo_automatico.items():
            if ' ' in nombre or '.' in nombre:  # Mostrar solo nombres completos
                st.write(f"- {nombre} (ID: {suc_id})")
    
    # Formulario de importación
    archivo_gastos = st.file_uploader(
        "Selecciona el archivo CSV de gastos del mes",
        type=['csv'],
        help="Archivo CSV exportado del sistema de facturas de compra"
    )
    
    if archivo_gastos is not None:
        # Procesar archivo
        with st.spinner("Procesando archivo CSV..."):
            df_gastos = procesar_archivo_gastos(archivo_gastos)
        
        if df_gastos is not None and len(df_gastos) > 0:
            st.success(f"✅ Archivo procesado: {len(df_gastos)} registros detectados")
            
            # Analizar períodos en el CSV
            if 'Fecha' in df_gastos.columns and df_gastos['Fecha'].notna().any():
                fechas_validas = df_gastos[df_gastos['Fecha'].notna()]['Fecha']
                fecha_min = fechas_validas.min()
                fecha_max = fechas_validas.max()
                
                periodos = df_gastos[df_gastos['Fecha'].notna()].copy()
                periodos['periodo'] = periodos['Fecha'].dt.to_period('M')
                periodos_unicos = periodos['periodo'].unique()
                
                st.info(f"📅 **Períodos detectados en el CSV**: {fecha_min.strftime('%d/%m/%Y')} hasta {fecha_max.strftime('%d/%m/%Y')} ({len(periodos_unicos)} mes(es))")
                
                # Mostrar resumen por período
                with st.expander("📊 Ver distribución por período"):
                    resumen_periodo = periodos.groupby('periodo').size().reset_index(name='registros')
                    resumen_periodo['periodo_str'] = resumen_periodo['periodo'].astype(str)
                    st.dataframe(
                        resumen_periodo[['periodo_str', 'registros']].rename(columns={
                            'periodo_str': 'Período',
                            'registros': 'Cantidad de Registros'
                        }),
                        hide_index=True
                    )
            
            # Analizar sucursales en el CSV
            st.markdown("---")
            st.subheader("🔍 Análisis de Sucursales Detectadas")
            
            empresas_detectadas = df_gastos['Empresa'].value_counts()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Total de Empresas en CSV", len(empresas_detectadas))
            
            # Verificar mapeo para cada empresa
            empresas_mapeadas = []
            empresas_sin_mapear = []
            
            for empresa, cantidad in empresas_detectadas.items():
                sucursal_id = obtener_sucursal_id_desde_nombre(empresa, mapeo_manual, mapeo_automatico)
                total_empresa = df_gastos[df_gastos['Empresa'] == empresa]['TOTAL_GASTO'].sum()
                
                if sucursal_id:
                    # Encontrar nombre de sucursal
                    nombre_sucursal = next((k for k, v in mapeo_automatico.items() if v == sucursal_id and (' ' in k or '.' in k)), empresa)
                    empresas_mapeadas.append({
                        'CSV': empresa,
                        'Sucursal': nombre_sucursal,
                        'Registros': cantidad,
                        'Total': total_empresa
                    })
                else:
                    empresas_sin_mapear.append({
                        'Empresa': empresa,
                        'Registros': cantidad,
                        'Total': total_empresa
                    })
            
            with col2:
                st.metric("Empresas Mapeadas ✅", len(empresas_mapeadas))
            
            # Mostrar empresas mapeadas
            if empresas_mapeadas:
                st.success("✅ **Empresas que se importarán correctamente:**")
                df_mapeadas = pd.DataFrame(empresas_mapeadas)
                df_mapeadas['Total Formateado'] = df_mapeadas['Total'].apply(
                    lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                )
                st.dataframe(
                    df_mapeadas[['CSV', 'Sucursal', 'Registros', 'Total Formateado']],
                    hide_index=True,
                    use_container_width=True
                )
            
            # Mostrar empresas sin mapear
            if empresas_sin_mapear:
                st.error("⚠️ **Empresas SIN MAPEAR (no se importarán):**")
                df_sin_mapear = pd.DataFrame(empresas_sin_mapear)
                df_sin_mapear['Total Formateado'] = df_sin_mapear['Total'].apply(
                    lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                )
                st.dataframe(
                    df_sin_mapear[['Empresa', 'Registros', 'Total Formateado']],
                    hide_index=True,
                    use_container_width=True
                )
                
                st.warning("💡 **Solución**: Crea estas sucursales en el sistema o ajusta los nombres en el CSV para que coincidan.")
            
            # Vista previa de datos
            with st.expander("👁️ Vista previa de primeros 10 registros"):
                st.dataframe(
                    df_gastos[['Empresa', 'Fecha', 'Rubro', 'Subrubro', 'Proveedor', 
                              'NETO', 'IVA_PERCEPCIONES', 'TOTAL_GASTO']].head(10),
                    hide_index=True
                )
            
            # Verificar si ya existen gastos para alguna sucursal en los períodos del CSV
            st.markdown("---")
            st.subheader("⚠️ Verificación de Duplicados")
            
            # Obtener períodos únicos del CSV
            periodos_csv = set()
            if 'Fecha' in df_gastos.columns:
                for fecha in df_gastos[df_gastos['Fecha'].notna()]['Fecha']:
                    periodos_csv.add((fecha.year, fecha.month))
            
            gastos_existentes_info = []
            for empresa_info in empresas_mapeadas:
                sucursal_id = obtener_sucursal_id_desde_nombre(empresa_info['CSV'], mapeo_manual, mapeo_automatico)
                if sucursal_id:
                    for anio, mes in periodos_csv:
                        gastos_existentes = verificar_gastos_existentes(supabase, sucursal_id, mes, anio)
                        if gastos_existentes['existe']:
                            gastos_existentes_info.append({
                                'sucursal': empresa_info['Sucursal'],
                                'periodo': f"{mes:02d}/{anio}",
                                'cantidad': gastos_existentes['cantidad'],
                                'total': gastos_existentes['total'],
                                'sucursal_id': sucursal_id,
                                'mes': mes,
                                'anio': anio
                            })
            
            if gastos_existentes_info:
                st.warning("⚠️ **Ya existen gastos para algunos períodos:**")
                for info in gastos_existentes_info:
                    st.write(f"- **{info['sucursal']}** ({info['periodo']}): {info['cantidad']} registros (${info['total']:,.2f})".replace(',', 'X').replace('.', ',').replace('X', '.'))
                
                st.write("")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Reemplazar TODOS los gastos existentes", type="secondary"):
                        with st.spinner("Eliminando gastos existentes..."):
                            for info in gastos_existentes_info:
                                eliminar_gastos_periodo(supabase, info['sucursal_id'], info['mes'], info['anio'])
                            st.success("✅ Gastos eliminados. Puedes importar nuevos datos.")
                            st.session_state['gastos_eliminados'] = True
                            st.rerun()
                
                with col2:
                    if st.button("❌ Cancelar y mantener existentes"):
                        st.info("Operación cancelada. Los gastos existentes se mantienen.")
                        return
                
                if 'gastos_eliminados' not in st.session_state or not st.session_state['gastos_eliminados']:
                    st.info("⚠️ Debes decidir si reemplazar o cancelar antes de continuar.")
                    st.stop()
            
            # Resumen antes de guardar
            st.markdown("---")
            st.subheader("📊 Resumen de la Importación")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Registros", len(df_gastos))
            with col2:
                registros_a_importar = sum(e['Registros'] for e in empresas_mapeadas)
                st.metric("Se Importarán", registros_a_importar)
            with col3:
                st.metric("Total Neto", f"${df_gastos['NETO'].sum():,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            with col4:
                st.metric("Total General", f"${df_gastos['TOTAL_GASTO'].sum():,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            
            # Botón de importación
            st.markdown("---")
            usuario_actual = st.session_state.get('usuario', {}).get('usuario', 'desconocido')
            
            puede_importar = len(empresas_mapeadas) > 0
            
            if not puede_importar:
                st.error("❌ No se puede importar porque ninguna empresa fue mapeada correctamente.")
                st.info("💡 Crea las sucursales en el sistema o ajusta los nombres en el CSV.")
            else:
                if st.button("💾 Guardar en Base de Datos", type="primary", use_container_width=True, disabled=not puede_importar):
                    with st.spinner("Guardando gastos en la base de datos..."):
                        resultado = guardar_gastos_en_db(
                            supabase, 
                            df_gastos,
                            usuario_actual
                        )
                        
                        if resultado['exitosos'] > 0:
                            st.success(f"✅ {resultado['exitosos']} registros guardados exitosamente")
                            
                            # Mostrar detalle por sucursal
                            if empresas_mapeadas:
                                st.info("📊 **Registros guardados por sucursal:**")
                                for empresa_info in empresas_mapeadas:
                                    st.write(f"- {empresa_info['Sucursal']}: {empresa_info['Registros']} registros")
                            
                            # Limpiar cache y session_state
                            if 'gastos_eliminados' in st.session_state:
                                del st.session_state['gastos_eliminados']
                            
                            # 🚀 OPTIMIZACIÓN: Limpiar solo caché de P&L (más eficiente que limpiar todo)
                            limpiar_cache_pl_simples()
                            
                            st.info("💡 Los gastos fueron guardados con sus fechas originales del CSV. Ve a 'Análisis del Período' o 'Evolución Histórica'.")
                        
                        # Mostrar duplicados agrupados por sucursal
                        if resultado.get('duplicados'):
                            # Agrupar duplicados por sucursal
                            duplicados_por_sucursal = {}
                            for dup in resultado['duplicados']:
                                suc_id = dup['sucursal_id']
                                if suc_id not in duplicados_por_sucursal:
                                    # Buscar nombre de sucursal
                                    nombre_suc = next(
                                        (k for k, v in mapeo_automatico.items() if v == suc_id and (' ' in k or '.' in k)), 
                                        dup['empresa']
                                    )
                                    duplicados_por_sucursal[suc_id] = {
                                        'nombre': nombre_suc,
                                        'cantidad': 0
                                    }
                                duplicados_por_sucursal[suc_id]['cantidad'] += 1
                            
                            # Mostrar mensaje agrupado
                            st.warning(f"⚠️ **{len(resultado['duplicados'])} registros no se importaron porque ya existen en la BD:**")
                            for suc_id, info in duplicados_por_sucursal.items():
                                st.write(f"  • **{info['nombre']}**: {info['cantidad']} registro(s)")
                            
                            with st.expander("🔍 Ver detalle de duplicados"):
                                for dup in resultado['duplicados'][:20]:
                                    st.write(f"  - Fila {dup['fila']}: {dup['proveedor']} (${dup['total']:,.2f}) - {dup['fecha']}")
                                if len(resultado['duplicados']) > 20:
                                    st.write(f"  ... y {len(resultado['duplicados'])-20} más")
                        
                        if resultado.get('sin_fecha'):
                            st.warning(f"⚠️ {len(resultado['sin_fecha'])} registros sin fecha válida (no importados):")
                            for item in resultado['sin_fecha'][:10]:
                                st.write(f"  • Fila {item['fila']}: {item['empresa']} - Fecha E: {item.get('fecha_e')} - Fecha C: {item.get('fecha_c')}")
                            if len(resultado['sin_fecha']) > 10:
                                st.write(f"  ... y {len(resultado['sin_fecha'])-10} más")
                        
                        if resultado['sin_sucursal']:
                            st.warning(f"⚠️ {len(resultado['sin_sucursal'])} registros sin sucursal mapeada (no importados):")
                            for item in resultado['sin_sucursal'][:10]:
                                st.write(f"  • Fila {item['fila']}: {item['empresa']} (${item['total']:,.2f})".replace(',', 'X').replace('.', ',').replace('X', '.'))
                            if len(resultado['sin_sucursal']) > 10:
                                st.write(f"  ... y {len(resultado['sin_sucursal'])-10} más")
                        
                        if resultado['errores']:
                            st.error(f"❌ {len(resultado['errores'])} errores durante la importación:")
                            for error in resultado['errores'][:5]:
                                st.error(f"  • {error}")
                            if len(resultado['errores']) > 5:
                                st.error(f"  ... y {len(resultado['errores'])-5} errores más")
        
        else:
            st.error("❌ No se pudo procesar el archivo de gastos")


def mostrar_tab_analisis(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada):
    """
    Tab de análisis del período actual con diseño profesional de informe financiero
    """
    # Header con botón de refrescar
    col_header, col_refresh = st.columns([4, 1])
    
    with col_header:
        st.subheader("📊 Estado de Resultados Profesional")
    
    with col_refresh:
        if st.button("🔄 Refrescar", key="refresh_analisis", use_container_width=True, help="Actualizar datos desde la base de datos"):
            limpiar_cache_pl_simples()
            st.success("✅ Datos actualizados")
            st.rerun()
    
    sucursal_id = sucursal_seleccionada['id'] if sucursal_seleccionada else None
    sucursal_nombre = sucursal_seleccionada['nombre'] if sucursal_seleccionada else "Todas las sucursales"
    
    # Obtener datos de la DB
    with st.spinner("Cargando datos..."):
        df_gastos = obtener_gastos_db(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
        df_ingresos = obtener_ingresos_mensuales(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
    
    if df_gastos.empty:
        st.warning(f"⚠️ No hay gastos registrados para **{sucursal_nombre}** en **{mes_seleccionado}/{anio_seleccionado}**.")
        st.info("💡 Ve a la pestaña 'Importar Gastos' para cargar datos.")
        return
    
    # Verificar si los gastos son de sucursales diferentes a la seleccionada
    if sucursal_seleccionada:
        sucursales_en_gastos = df_gastos['sucursal_id'].unique()
        if sucursal_id not in sucursales_en_gastos:
            st.warning(f"⚠️ Los gastos de este período pertenecen a otras sucursales.")
            st.info(f"💡 Sucursales con gastos en {mes_seleccionado}/{anio_seleccionado}:")
            for suc_id in sucursales_en_gastos:
                suc = next((s for s in sucursales if s['id'] == suc_id), None)
                if suc:
                    cantidad = len(df_gastos[df_gastos['sucursal_id'] == suc_id])
                    st.write(f"   - {suc['nombre']}: {cantidad} registros")
            st.info("💡 Selecciona una de estas sucursales en el selector de arriba para ver su análisis.")
            return
    
    # Calcular totales
    total_ingresos = df_ingresos['monto'].sum() if not df_ingresos.empty else 0
    total_gastos = df_gastos['total'].sum()
    resultado = total_ingresos - total_gastos
    margen_porcentaje = (resultado / total_ingresos * 100) if total_ingresos > 0 else 0
    
    # INICIO: DISEÑO PROFESIONAL DE INFORME FINANCIERO
    st.markdown("---")
    
    # Título del informe
    meses = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    nombre_mes = meses[mes_seleccionado]
    
    st.markdown(f"""
    <div style="text-align: center; padding: 20px; background-color: #f8f9fa; border-radius: 10px; margin-bottom: 30px;">
        <h1 style="color: #2c3e50; margin-bottom: 10px;">ESTADO DE RESULTADOS</h1>
        <h2 style="color: #34495e; margin-bottom: 5px;">{nombre_mes.upper()} {anio_seleccionado}</h2>
        <h3 style="color: #7f8c8d; font-weight: normal;">{sucursal_nombre.upper()}</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # KPIs principales en tarjetas profesionales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        color_ingresos = "#27ae60" if total_ingresos > 0 else "#95a5a6"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); 
                    padding: 20px; border-radius: 10px; text-align: center; 
                    border-left: 5px solid {color_ingresos}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="color: #7f8c8d; font-size: 12px; font-weight: bold; margin-bottom: 5px;">INGRESOS</div>
            <div style="color: {color_ingresos}; font-size: 24px; font-weight: bold;">
                ${total_ingresos:,.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        color_gastos = "#e74c3c"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); 
                    padding: 20px; border-radius: 10px; text-align: center; 
                    border-left: 5px solid {color_gastos}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="color: #7f8c8d; font-size: 12px; font-weight: bold; margin-bottom: 5px;">GASTOS</div>
            <div style="color: {color_gastos}; font-size: 24px; font-weight: bold;">
                ${total_gastos:,.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        color_resultado = "#27ae60" if resultado >= 0 else "#e74c3c"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); 
                    padding: 20px; border-radius: 10px; text-align: center; 
                    border-left: 5px solid {color_resultado}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="color: #7f8c8d; font-size: 12px; font-weight: bold; margin-bottom: 5px;">RESULTADO</div>
            <div style="color: {color_resultado}; font-size: 24px; font-weight: bold;">
                ${resultado:,.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        color_margen = "#27ae60" if margen_porcentaje >= 0 else "#e74c3c"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); 
                    padding: 20px; border-radius: 10px; text-align: center; 
                    border-left: 5px solid {color_margen}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="color: #7f8c8d; font-size: 12px; font-weight: bold; margin-bottom: 5px;">MARGEN</div>
            <div style="color: {color_margen}; font-size: 24px; font-weight: bold;">
                {margen_porcentaje:.2f}%
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # SECCIÓN DE INGRESOS
    st.markdown("""
    <div style="background-color: #34495e; color: white; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
        <h3 style="margin: 0; font-size: 18px;">VENTAS/INGRESOS</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Agrupar ingresos por categoría si hay datos
    if not df_ingresos.empty:
        # Aquí podrías agregar lógica para agrupar por tipo de ingreso si tienes esa información
        ingresos_df = pd.DataFrame({
            'Concepto': ['Ventas Salon'],
            'Monto': [total_ingresos]
        })
        
        for _, row in ingresos_df.iterrows():
            st.markdown(f"""
            <div style="padding: 8px 0; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between;">
                <span style="color: #2c3e50;">{row['Concepto']}</span>
                <span style="color: #2c3e50; font-weight: 500;">${row['Monto']:,.2f}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="padding: 8px 0; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between;">
            <span style="color: #2c3e50;">Sin ingresos registrados</span>
            <span style="color: #2c3e50; font-weight: 500;">$0.00</span>
        </div>
        """, unsafe_allow_html=True)
    
    # Total de ingresos
    st.markdown(f"""
    <div style="padding: 12px 0; margin-top: 10px; border-top: 2px solid #34495e; display: flex; justify-content: space-between;">
        <span style="color: #2c3e50; font-weight: bold; font-size: 16px;">TOTAL INGRESOS</span>
        <span style="color: #2c3e50; font-weight: bold; font-size: 16px;">${total_ingresos:,.2f}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # SECCIÓN DE GASTOS
    st.markdown("""
    <div style="background-color: #34495e; color: white; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
        <h3 style="margin: 0; font-size: 18px;">COMPRAS/EGRESOS</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Agrupar gastos por rubro con subtotales
    if 'rubro' in df_gastos.columns:
        gastos_agrupados = df_gastos.groupby('rubro')['total'].sum().sort_values(ascending=False)
        
        # Definir orden y categorías principales
        categorias_principales = {
            'ALIMENTOS': {'subcategorias': []},
            'BEBIDAS': {'subcategorias': []},
            'SUELDOS': {'subcategorias': ['Cargas Sociales']},
            'SERVICIOS': {'subcategorias': []},
            'ALQUILER': {'subcategorias': []},
            'INSUMOS Y DESCARTABLES': {'subcategorias': []},
            'IMPUESTOS': {'subcategorias': []},
            'MATERIALES': {'subcategorias': []}
        }
        
        # Procesar cada categoría principal
        for categoria, config in categorias_principales.items():
            # Buscar gastos de esta categoría
            gastos_categoria = gastos_agrupados[gastos_agrupados.index.str.contains(categoria, case=False, na=False)]
            
            if not gastos_categoria.empty:
                # Mostrar categoría principal
                total_categoria = gastos_categoria.sum()
                st.markdown(f"""
                <div style="padding: 8px 0; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between;">
                    <span style="color: #2c3e50; font-weight: 500;">{categoria.title()}</span>
                    <span style="color: #2c3e50; font-weight: 500;">${total_categoria:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)
                
                # Mostrar subcategorías si existen
                for subcat in config['subcategorias']:
                    gastos_subcat = gastos_agrupados[gastos_agrupados.index.str.contains(subcat, case=False, na=False)]
                    if not gastos_subcat.empty:
                        for subcat_nombre, monto in gastos_subcat.items():
                            st.markdown(f"""
                            <div style="padding: 6px 0 6px 20px; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between; font-size: 14px;">
                                <span style="color: #7f8c8d;">└─ {subcat_nombre}</span>
                                <span style="color: #7f8c8d;">${monto:,.2f}</span>
                            </div>
                            """, unsafe_allow_html=True)
        
        # Mostrar otras categorías no incluidas en las principales
        otras_categorias = []
        for categoria, monto in gastos_agrupados.items():
            es_principal = any(cat in categoria.upper() for cat in categorias_principales.keys())
            if not es_principal:
                otras_categorias.append((categoria, monto))
        
        if otras_categorias:
            st.markdown("""
            <div style="padding: 8px 0; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between;">
                <span style="color: #2c3e50; font-weight: 500;">Otros Gastos</span>
                <span style="color: #2c3e50; font-weight: 500;">$0.00</span>
            </div>
            """, unsafe_allow_html=True)
            
            for categoria, monto in otras_categorias:
                st.markdown(f"""
                <div style="padding: 6px 0 6px 20px; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between; font-size: 14px;">
                    <span style="color: #7f8c8d;">└─ {categoria}</span>
                    <span style="color: #7f8c8d;">${monto:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        # Si no hay rubro, mostrar total general
        st.markdown(f"""
        <div style="padding: 8px 0; border-bottom: 1px solid #ecf0f1; display: flex; justify-content: space-between;">
            <span style="color: #2c3e50;">Gastos Operativos</span>
            <span style="color: #2c3e50; font-weight: 500;">${total_gastos:,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
    
    # Total de egresos
    st.markdown(f"""
    <div style="padding: 12px 0; margin-top: 10px; border-top: 2px solid #34495e; display: flex; justify-content: space-between;">
        <span style="color: #2c3e50; font-weight: bold; font-size: 16px;">TOTAL EGRESOS</span>
        <span style="color: #2c3e50; font-weight: bold; font-size: 16px;">${total_gastos:,.2f}</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # RESULTADO OPERATIVO
    color_resultado_final = "#27ae60" if resultado >= 0 else "#e74c3c"
    st.markdown(f"""
    <div style="background-color: {color_resultado_final}20; padding: 20px; border-radius: 10px; border-left: 5px solid {color_resultado_final}; margin-bottom: 30px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: {color_resultado_final}; font-weight: bold; font-size: 18px;">RESULTADO OPERATIVO</span>
            <span style="color: {color_resultado_final}; font-weight: bold; font-size: 24px;">${resultado:,.2f}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ANÁLISIS DE COMPOSICIÓN
    st.markdown("""
    <div style="background-color: #34495e; color: white; padding: 10px; border-radius: 5px; margin-bottom: 15px;">
        <h3 style="margin: 0; font-size: 18px;">ANÁLISIS DE COMPOSICIÓN</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Calcular porcentajes y comparar con benchmarks
    benchmarks = calcular_benchmarks_gastronomia()
    
    if 'rubro' in df_gastos.columns:
        gastos_por_rubro = df_gastos.groupby('rubro')['total'].sum()
        
        for rubro_key, benchmark in benchmarks.items():
            # Buscar gastos que coincidan con este rubro
            gastos_rubro = gastos_por_rubro[gastos_por_rubro.index.str.contains(rubro_key, case=False, na=False)]
            
            if not gastos_rubro.empty:
                total_rubro = gastos_rubro.sum()
                porcentaje_real = (total_rubro / total_ingresos * 100) if total_ingresos > 0 else 0
                
                # Determinar estado
                if porcentaje_real < benchmark['rango_min']:
                    estado = "BAJO"
                    icono = "⬇️"
                    color = "#3498db"
                elif porcentaje_real > benchmark['rango_max']:
                    estado = "ALTO"
                    icono = "⬆️"
                    color = "#e74c3c"
                else:
                    estado = "OK"
                    icono = "✅"
                    color = "#27ae60"
                
                st.markdown(f"""
                <div style="padding: 10px; margin-bottom: 10px; background-color: #f8f9fa; border-radius: 5px; border-left: 3px solid {color};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #2c3e50; font-weight: 500;">{icono} {rubro_key.replace('_', ' ').title()} sobre Ventas</span>
                        <span style="color: {color}; font-weight: bold;">{porcentaje_real:.2f}%</span>
                    </div>
                    <div style="font-size: 12px; color: #7f8c8d; margin-top: 5px;">
                        Ideal: {benchmark['rango_min']:.0f}%-{benchmark['rango_max']:.0f}% | Estado: {estado}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
    # Margen neto
    if margen_porcentaje >= 10:
        estado_margen = "EXCELENTE"
        icono_margen = "🟢"
        color_margen = "#27ae60"
    elif margen_porcentaje >= 5:
        estado_margen = "ACEPTABLE"
        icono_margen = "🟡"
        color_margen = "#f39c12"
    else:
        estado_margen = "CRÍTICO"
        icono_margen = "🔴"
        color_margen = "#e74c3c"
    
    st.markdown(f"""
    <div style="padding: 10px; margin-bottom: 10px; background-color: #f8f9fa; border-radius: 5px; border-left: 3px solid {color_margen};">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #2c3e50; font-weight: 500;">{icono_margen} Margen Neto</span>
            <span style="color: {color_margen}; font-weight: bold;">{margen_porcentaje:.2f}%</span>
        </div>
        <div style="font-size: 12px; color: #7f8c8d; margin-top: 5px;">
            Ideal: 10%-15% | Estado: {estado_margen}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Pie del informe
    st.markdown("---")
    st.markdown(f"""
    <div style="text-align: center; color: #7f8c8d; font-size: 12px; padding: 20px;">
        Informe generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | 
        Período: {nombre_mes} {anio_seleccionado} | 
        Sucursal: {sucursal_nombre}
    </div>
    """, unsafe_allow_html=True)


def mostrar_tab_evolucion(supabase, sucursales, sucursal_seleccionada):
    """
    Tab de evolución histórica
    """
    # Header con botón de refrescar
    col_header, col_refresh = st.columns([4, 1])
    
    with col_header:
        st.subheader("📈 Evolución Histórica")
    
    with col_refresh:
        if st.button("🔄 Refrescar", key="refresh_evolucion", use_container_width=True, help="Actualizar datos desde la base de datos"):
            limpiar_cache_pl_simples()
            st.success("✅ Datos actualizados")
            st.rerun()
    
    if sucursal_seleccionada is None:
        st.warning("⚠️ Selecciona una sucursal para ver su evolución histórica")
        return
    
    sucursal_id = sucursal_seleccionada['id']
    
    # Selector de meses a mostrar
    meses_atras = st.slider("Meses a mostrar", min_value=3, max_value=24, value=12, step=1)
    
    # Obtener datos (ahora con caché)
    with st.spinner("Cargando evolución histórica..."):
        df_evolucion = obtener_evolucion_historica(supabase, sucursal_id, meses_atras)
    
    if df_evolucion.empty:
        st.warning("⚠️ No hay datos históricos suficientes para esta sucursal")
        return
    
    # Tabla de evolución
    st.markdown("### 📊 Tabla de Evolución")
    
    df_display = df_evolucion.copy()
    df_display['Período'] = df_display['periodo'].dt.strftime('%Y-%m')
    df_display['Ingresos'] = df_display['total_ingresos'].apply(
        lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    df_display['Gastos'] = df_display['total_gastos'].apply(
        lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    df_display['Resultado'] = df_display['resultado'].apply(
        lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    df_display['Margen %'] = df_display['margen'].apply(lambda x: f"{x:.1f}%")
    
    st.dataframe(
        df_display[['Período', 'Ingresos', 'Gastos', 'Resultado', 'Margen %']],
        hide_index=True,
        use_container_width=True
    )
    
    # Gráficos de tendencia
    st.markdown("---")
    st.markdown("### 📈 Gráficos de Tendencia")
    
    # Verificar si plotly está disponible
    try:
        import plotly.graph_objects as go
        plotly_disponible = True
    except ImportError:
        plotly_disponible = False
        st.warning("⚠️ **Plotly no está instalado**. Los gráficos no están disponibles.")
        st.info("💡 Para ver gráficos, instala plotly: `pip install plotly --break-system-packages`")
    
    if plotly_disponible:
        # Gráfico 1: Ingresos vs Gastos
        fig1 = go.Figure()
        
        fig1.add_trace(go.Scatter(
            x=df_evolucion['periodo'],
            y=df_evolucion['total_ingresos'],
            mode='lines+markers',
            name='Ingresos',
            line=dict(color='green', width=2),
            marker=dict(size=8)
        ))
        
        fig1.add_trace(go.Scatter(
            x=df_evolucion['periodo'],
            y=df_evolucion['total_gastos'],
            mode='lines+markers',
            name='Gastos',
            line=dict(color='red', width=2),
            marker=dict(size=8)
        ))
        
        fig1.update_layout(
            title='Evolución de Ingresos vs. Gastos',
            xaxis_title='Período',
            yaxis_title='Monto ($)',
            hovermode='x unified'
        )
        
        st.plotly_chart(fig1, use_container_width=True)
        
        # Gráfico 2: Margen
        fig2 = go.Figure()
        
        # Color según margen
        colors = ['green' if m >= 10 else 'orange' if m >= 5 else 'red' for m in df_evolucion['margen']]
        
        fig2.add_trace(go.Bar(
            x=df_evolucion['periodo'],
            y=df_evolucion['margen'],
            name='Margen %',
            marker_color=colors
        ))
        
        # Línea de referencia en 10%
        fig2.add_hline(y=10, line_dash="dash", line_color="gray", annotation_text="Meta: 10%")
        
        fig2.update_layout(
            title='Evolución del Margen de Ganancia',
            xaxis_title='Período',
            yaxis_title='Margen (%)',
            hovermode='x unified'
        )
        
        st.plotly_chart(fig2, use_container_width=True)
    
    # Estadísticas
    st.markdown("---")
    st.markdown("### 📊 Estadísticas del Período Analizado")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Margen Promedio",
            f"{df_evolucion['margen'].mean():.1f}%"
        )
    
    with col2:
        mejor_mes = df_evolucion.loc[df_evolucion['margen'].idxmax()]
        st.metric(
            "Mejor Mes",
            mejor_mes['periodo'].strftime('%Y-%m'),
            delta=f"{mejor_mes['margen']:.1f}%"
        )
    
    with col3:
        peor_mes = df_evolucion.loc[df_evolucion['margen'].idxmin()]
        st.metric(
            "Peor Mes",
            peor_mes['periodo'].strftime('%Y-%m'),
            delta=f"{peor_mes['margen']:.1f}%",
            delta_color="inverse"
        )
    
    with col4:
        # Tendencia
        tendencia = "📈 Mejorando" if df_evolucion['margen'].iloc[-1] > df_evolucion['margen'].iloc[0] else "📉 Decreciendo"
        st.metric(
            "Tendencia",
            tendencia
        )


# ================================================================================
# ESTADO DE RESULTADO GRANULAR (AQUÍ ESTÁ LA MODIFICACIÓN ESTÉTICA)
# ================================================================================

def cargar_mapeo_erg_desde_excel(supabase, archivo_excel):
    """
    Carga el mapeo de Estado de Resultado Granular desde Excel a Supabase.
    """
    try:
        # Leer hoja "Conjunto Datos"
        df_mapeo = pd.read_excel(archivo_excel, sheet_name="Conjunto Datos")
        
        # Definir grupos para subtotales (basado en la estructura del informe)
        grupos = {
            1: [1, 2, 3, 4],      # CMC, Sueldos, Cargas sociales, Sindicatos
            2: [5, 6],             # Alquiler, Servicios
            3: [7, 8],             # Honorarios, Publicidad
            4: [9, 10, 11],        # Materiales, Mantenimiento, Bienes de uso
            5: [12, 18],           # Royalties, Servicios admin
            6: [19],               # Retiros
            7: [13, 14, 15, 16, 17]  # Gastos financieros e impuestos
        }
        
        # Crear diccionario cod_inf -> orden_grupo
        cod_inf_to_grupo = {}
        for grupo, cod_infs in grupos.items():
            for cod_inf in cod_infs:
                cod_inf_to_grupo[cod_inf] = grupo
        
        # Procesar cada fila del mapeo
        registros = []
        
        for idx, row in df_mapeo.iterrows():
            cod_inf = int(row['Cod_Inf'])
            item = str(row['Item']).strip()
            orden_grupo = cod_inf_to_grupo.get(cod_inf, 1)
            
            # Recopilar todos los subrubros
            for col in df_mapeo.columns:
                if 'Subrubro' in col:
                    subrubro = row[col]
                    if pd.notna(subrubro) and str(subrubro).strip() != '':
                        registros.append({
                            'cod_inf': cod_inf,
                            'item': item,
                            'subrubro': str(subrubro).strip().upper(),
                            'orden_grupo': orden_grupo
                        })
        
        # Limpiar tabla existente
        try:
            supabase.table("mapeo_estado_resultado_granular")\
                .delete()\
                .neq('id', 0)\
                .execute()
        except:
            pass
        
        # Insertar registros en batch
        if registros:
            supabase.table("mapeo_estado_resultado_granular")\
                .insert(registros)\
                .execute()
        
        return {
            'exitoso': True,
            'registros': len(registros),
            'items': len(df_mapeo),
            'mensaje': f"✅ {len(registros)} relaciones cargadas ({len(df_mapeo)} items)"
        }
        
    except Exception as e:
        return {
            'exitoso': False,
            'registros': 0,
            'items': 0,
            'mensaje': f"❌ Error: {str(e)}"
        }


@st.cache_data(ttl=300)  # Cachear 5 minutos
def obtener_mapeo_erg(_supabase):
    """
    Obtiene el mapeo ERG desde Supabase.
    """
    try:
        result = _supabase.table("mapeo_estado_resultado_granular")\
            .select("*")\
            .execute()
        
        if result.data:
            df = pd.DataFrame(result.data)
            df['subrubro'] = df['subrubro'].str.upper().str.strip()
            return df
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"❌ Error obteniendo mapeo: {str(e)}")
        return pd.DataFrame()


def agrupar_gastos_erg(df_gastos, df_mapeo):
    """
    Agrupa gastos según el mapeo ERG.
    """
    if df_gastos.empty or df_mapeo.empty:
        return pd.DataFrame()
    
    try:
        # Normalizar subrubros
        df_gastos['subrubro_norm'] = df_gastos['subrubro'].str.upper().str.strip()
        
        # Merge con mapeo
        df_merged = df_gastos.merge(
            df_mapeo[['cod_inf', 'item', 'subrubro', 'orden_grupo']],
            left_on='subrubro_norm',
            right_on='subrubro',
            how='left'
        )
        
        # Agrupar por cod_inf, item, orden_grupo
        df_agrupado = df_merged.groupby(['cod_inf', 'item', 'orden_grupo']).agg({
            'total': 'sum'
        }).reset_index()
        
        # Eliminar filas sin mapeo (cod_inf nulo)
        df_agrupado = df_agrupado[df_agrupado['cod_inf'].notna()]
        
        # Ordenar por cod_inf
        df_agrupado = df_agrupado.sort_values('cod_inf')
        
        return df_agrupado
        
    except Exception as e:
        st.error(f"❌ Error agrupando gastos: {str(e)}")
        return pd.DataFrame()


def generar_estado_resultado_granular(df_gastos_agrupados, total_ingresos, sucursal_nombre, mes, anio):
    """
    Genera el Estado de Resultado Granular con estructura jerárquica.
    """
    reporte = []
    
    # Header
    reporte.append({
        'tipo': 'titulo',
        'descripcion': 'Estado de Resultados',
        'monto': None
    })
    
    # Ventas
    reporte.append({
        'tipo': 'seccion',
        'descripcion': 'VENTAS / INGRESOS',
        'monto': None
    })
    
    reporte.append({
        'tipo': 'item',
        'descripcion': 'Salon',
        'monto': total_ingresos
    })
    
    reporte.append({
        'tipo': 'item',
        'descripcion': 'Delivery',
        'monto': 0
    })
    
    reporte.append({
        'tipo': 'item',
        'descripcion': 'Distribuidora/Otros',
        'monto': 0
    })
    
    reporte.append({
        'tipo': 'total',
        'descripcion': 'TOTAL INGRESOS',
        'monto': total_ingresos
    })
    
    # Egresos
    reporte.append({
        'tipo': 'seccion',
        'descripcion': 'COMPRAS / EGRESOS',
        'monto': None
    })
    
    # Procesar por grupos (1-7)
    total_compras = 0
    
    for grupo in range(1, 8):
        df_grupo = df_gastos_agrupados[df_gastos_agrupados['orden_grupo'] == grupo]
        
        if not df_grupo.empty:
            subtotal_grupo = 0
            
            # Items del grupo
            for idx, row in df_grupo.iterrows():
                monto = row['total']
                subtotal_grupo += monto
                
                reporte.append({
                    'tipo': 'item_gasto',
                    'descripcion': row['item'],
                    'monto': monto,
                    'cod_inf': row['cod_inf']
                })
            
            # Subtotal del grupo
            reporte.append({
                'tipo': 'subtotal',
                'descripcion': 'Subtotal Grupo',
                'monto': subtotal_grupo
            })
            
            total_compras += subtotal_grupo
    
    # Resultado
    resultado_operativo = total_ingresos - total_compras
    
    reporte.append({
        'tipo': 'resultado',
        'descripcion': 'RESULTADO OPERATIVO ESTIMADO',
        'monto': resultado_operativo
    })
    
    return reporte

# ==================== RENDERIZADO HTML (NUEVO) ====================

def renderizar_reporte_html(reporte, sucursal_nombre, mes, anio):
    """
    Genera el HTML con estilos CSS para el reporte ejecutivo "Paper Style"
    """
    estilo_css = """
    <style>
        .report-wrapper {
            background-color: #f0f2f6;
            padding: 20px;
            border-radius: 10px;
        }
        .report-container {
            background-color: white;
            padding: 50px;
            border-radius: 4px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #333;
            max-width: 900px;
            margin: auto;
            border: 1px solid #e0e0e0;
        }
        .report-header {
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid #2c3e50;
            padding-bottom: 20px;
        }
        .report-title { font-size: 26px; font-weight: 700; color: #2c3e50; letter-spacing: 1px; margin: 0; }
        .report-subtitle { font-size: 14px; color: #7f8c8d; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
        
        table.pl-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 8px 12px; }
        
        .row-section { 
            background-color: #f8f9fa; 
            font-weight: 800; 
            text-transform: uppercase; 
            font-size: 13px; 
            color: #2c3e50;
            padding-top: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }
        .row-item { border-bottom: 1px solid #f9f9f9; font-size: 14px; color: #555; }
        .row-subtotal { 
            font-weight: 600; 
            font-style: italic; 
            background-color: #fafafa;
            border-top: 1px solid #ccc;
            font-size: 14px;
            color: #444;
        }
        .row-total { 
            font-weight: 800; 
            font-size: 15px; 
            border-top: 2px solid #333; 
            background-color: #f1f3f5;
            color: #000;
        }
        .row-result {
            font-size: 20px;
            font-weight: bold;
            color: white;
            padding: 20px;
            text-align: center;
            margin-top: 30px;
            border-radius: 6px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .amount { text-align: right; font-family: 'Consolas', 'Monaco', monospace; font-size: 14px; }
        .amount-bold { font-weight: bold; }
        .indent { padding-left: 30px; }
        
        .positive { background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); }
        .negative { background: linear-gradient(135deg, #c0392b 0%, #e74c3c 100%); }
        .neutral  { background-color: #95a5a6; }
        
        /* Impresion friendly */
        @media print {
            .report-wrapper { background-color: white; padding: 0; }
            .report-container { box-shadow: none; border: none; }
        }
    </style>
    """

    html = f"{estilo_css}<div class='report-wrapper'><div class='report-container'>"
    
    # Encabezado
    html += f"""
        <div class='report-header'>
            <div class='report-title'>ESTADO DE RESULTADOS</div>
            <div class='report-subtitle'>{sucursal_nombre} &nbsp;|&nbsp; PERÍODO: {mes:02d}/{anio}</div>
        </div>
        <table class='pl-table'>
    """

    # Cuerpo de la tabla
    for fila in reporte:
        tipo = fila['tipo']
        desc = fila['descripcion']
        monto = fila['monto']
        
        # Formateo de moneda
        monto_str = ""
        if isinstance(monto, (int, float)):
            monto_str = f"${monto:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif monto is not None:
            monto_str = str(monto)

        if tipo == 'seccion':
            html += f"<tr><td colspan='2' class='row-section'>{desc}</td></tr>"
        
        elif tipo == 'item' or tipo == 'item_gasto':
            html += f"<tr class='row-item'><td class='indent'>{desc}</td><td class='amount'>{monto_str}</td></tr>"
        
        elif tipo == 'subtotal':
            html += f"<tr class='row-subtotal'><td>{desc}</td><td class='amount'>{monto_str}</td></tr>"
            html += "<tr><td colspan='2' style='height:8px'></td></tr>" # Espaciador
            
        elif tipo == 'total':
            html += f"<tr class='row-total'><td>{desc}</td><td class='amount amount-bold'>{monto_str}</td></tr>"
            html += "<tr><td colspan='2' style='height:25px'></td></tr>" # Espaciador grande

    html += "</table>"

    # Resultado Final (Badge grande abajo)
    resultado_row = next((x for x in reporte if x['tipo'] == 'resultado'), None)
    if resultado_row:
        res_monto = resultado_row['monto']
        res_str = f"${res_monto:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        clase_color = "positive" if res_monto >= 0 else "negative"
        
        html += f"""
            <div class='row-result {clase_color}'>
                RESULTADO OPERATIVO ESTIMADO<br>
                <span style='font-size: 28px; margin-top: 10px; display: block;'>{res_str}</span>
            </div>
        """

    html += "</div></div>" # Cierre container y wrapper
    
    return html

# ============================================================================
# FUNCIÓN 5: Tab - Estado de Resultado Granular (ACTUALIZADA)
# ============================================================================

def mostrar_tab_estado_resultado_granular(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada):
    """
    Tab de Estado de Resultado Granular
    """
    # Header
    col_header, col_refresh = st.columns([4, 1])
    
    with col_header:
        st.subheader("📊 Estado de Resultado Granular")
    
    with col_refresh:
        if st.button("🔄 Refrescar", key="refresh_erg", use_container_width=True):
            st.cache_data.clear()
            st.success("✅ Datos actualizados")
            st.rerun()
    
    sucursal_id = sucursal_seleccionada['id'] if sucursal_seleccionada else None
    sucursal_nombre = sucursal_seleccionada['nombre'] if sucursal_seleccionada else "Todas las sucursales"
    
    # ===========================================================================
    # VERIFICAR MAPEO
    # ===========================================================================
    df_mapeo = obtener_mapeo_erg(supabase)
    
    if df_mapeo.empty:
        st.warning("⚠️ **No hay mapeo configurado**")
        st.info("💡 Primero debes cargar el mapeo desde el archivo Excel.")
        
        with st.expander("⚙️ Cargar Mapeo desde Excel", expanded=True):
            st.markdown("### 📤 Subir archivo de mapeo")
            st.markdown("""
            El archivo debe tener una hoja llamada **"Conjunto Datos"** con:
            - **Cod_Inf**: Código del item
            - **Item**: Nombre del item para el informe
            - **Subrubros**: Columnas con los subrubros que pertenecen a cada item
            """)
            
            archivo_mapeo = st.file_uploader(
                "Selecciona el archivo Excel",
                type=['xlsx', 'xls'],
                key="upload_mapeo_erg"
            )
            
            if archivo_mapeo:
                if st.button("📥 Cargar Mapeo", type="primary", use_container_width=True):
                    with st.spinner("Cargando mapeo..."):
                        resultado = cargar_mapeo_erg_desde_excel(supabase, archivo_mapeo)
                        
                        if resultado['exitoso']:
                            st.success(resultado['mensaje'])
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(resultado['mensaje'])
        
        return
    
    # ===========================================================================
    # MOSTRAR INFO DEL MAPEO
    # ===========================================================================
    with st.expander("ℹ️ Información del Mapeo"):
        items_unicos = df_mapeo.groupby('item').agg({
            'cod_inf': 'first',
            'subrubro': lambda x: list(x)
        }).reset_index().sort_values('cod_inf')
        
        st.write(f"**Total items configurados:** {len(items_unicos)}")
        st.write(f"**Total subrubros mapeados:** {len(df_mapeo)}")
        
        st.markdown("### Items Configurados:")
        for idx, row in items_unicos.iterrows():
            cod_inf = row['cod_inf']
            item = row['item']
            subrubros = sorted(row['subrubro'])
            st.write(f"**{cod_inf}. {item}** ({len(subrubros)} subrubros)")
            st.caption(", ".join(subrubros))
    
    # ===========================================================================
    # OBTENER DATOS
    # ===========================================================================
    with st.spinner("Cargando datos..."):
        df_gastos = obtener_gastos_db(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
        df_ingresos = obtener_ingresos_mensuales(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
    
    if df_gastos.empty:
        st.warning(f"⚠️ No hay gastos para **{sucursal_nombre}** en **{mes_seleccionado}/{anio_seleccionado}**")
        st.info("💡 Ve a 'Importar Gastos' para cargar datos.")
        return
    
    # Total ingresos
    total_ingresos = df_ingresos['monto'].sum() if not df_ingresos.empty else 0
    
    # ===========================================================================
    # AGRUPAR GASTOS
    # ===========================================================================
    df_gastos_agrupados = agrupar_gastos_erg(df_gastos, df_mapeo)
    
    if df_gastos_agrupados.empty:
        st.warning("⚠️ No se pudieron agrupar los gastos según el mapeo")
        st.info("💡 Verifica que los subrubros de tus gastos coincidan con el mapeo configurado")
        
        # Mostrar subrubros que no tienen mapeo
        subrubros_sin_mapeo = set(df_gastos['subrubro'].str.upper().str.strip()) - set(df_mapeo['subrubro'])
        
        if subrubros_sin_mapeo:
            with st.expander("🔍 Subrubros sin mapeo"):
                st.write("Los siguientes subrubros no están en el mapeo:")
                for subrubro in sorted(subrubros_sin_mapeo):
                    st.write(f"- {subrubro}")
        
        return
    
    # ===========================================================================
    # GENERAR REPORTE (DATOS)
    # ===========================================================================
    reporte = generar_estado_resultado_granular(
        df_gastos_agrupados,
        total_ingresos,
        sucursal_nombre,
        mes_seleccionado,
        anio_seleccionado
    )
    
    # ===========================================================================
    # RENDERIZAR REPORTE VISUAL (NUEVO DISEÑO EJECUTIVO)
    # ===========================================================================
    st.markdown("---")
    
    html_reporte = renderizar_reporte_html(reporte, sucursal_nombre, mes_seleccionado, anio_seleccionado)
    st.markdown(html_reporte, unsafe_allow_html=True)
    
    # ===========================================================================
    # BOTÓN DESCARGAR EXCEL
    # ===========================================================================
    st.markdown("---")
    
    if st.button("📥 Descargar Estado de Resultado (Excel)", type="primary"):
        with st.spinner("Generando Excel..."):
            # Convertir reporte a DataFrame
            df_reporte = pd.DataFrame([
                {
                    'Descripción': f['descripcion'],
                    'Monto': f['monto'] if f['monto'] is not None else ''
                }
                for f in reporte
            ])
            
            # Generar Excel
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_reporte.to_excel(writer, sheet_name='Estado Resultado', index=False)
            
            buffer.seek(0)
            
            nombre_archivo = f"Estado_Resultado_Granular_{sucursal_nombre}_{mes_seleccionado:02d}_{anio_seleccionado}.xlsx"
            
            st.download_button(
                label="⬇️ Descargar Excel",
                data=buffer,
                file_name=nombre_archivo,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


# ============================================================================

# ================================================================================

def main(supabase):
    """
    Función principal del módulo P&L Simples v2.3
    """
    st.header("📊 P&L Simples - Informe Mensual de Resultados")
    st.caption("v2.3 - Con persistencia, evolución histórica y mapeo automático de fechas")
    st.markdown("---")
    
    # Configuración
    col1, col2, col3 = st.columns(3)
    
    with col1:
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        mes_actual = datetime.now().month
        mes_seleccionado = st.selectbox(
            "📅 Mes (para análisis)",
            options=list(meses.keys()),
            format_func=lambda x: meses[x],
            index=mes_actual - 1,
            help="Selecciona el mes que quieres analizar. No afecta la importación (las fechas vienen del CSV)."
        )
    
    with col2:
        anio_actual = datetime.now().year
        anio_seleccionado = st.selectbox(
            "📅 Año (para análisis)",
            options=range(anio_actual - 2, anio_actual + 1),
            index=2,
            help="Selecciona el año que quieres analizar. No afecta la importación (las fechas vienen del CSV)."
        )
    
    with col3:
        sucursales = []
        try:
            result = supabase.table("sucursales").select("*").execute()
            if result.data:
                sucursales = result.data
        except:
            pass
        
        sucursal_seleccionada = st.selectbox(
            "🏪 Sucursal (para análisis)",
            options=[None] + sucursales,
            format_func=lambda x: "Todas las sucursales" if x is None else x['nombre'],
            help="Selecciona una sucursal para ver su análisis. Para importar, el sistema detectará automáticamente las sucursales del CSV."
        )
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📁 Importar Gastos", "📊 Análisis del Período", "📈 Evolución Histórica", "📊 Estado de Resultado Granular"])
    
    with tab1:
        mostrar_tab_importacion(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada)
    
    with tab2:
        mostrar_tab_analisis(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada)
    
    with tab3:
        mostrar_tab_evolucion(supabase, sucursales, sucursal_seleccionada)
    
    with tab4:
        mostrar_tab_estado_resultado_granular(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada)


if __name__ == "__main__":
    st.warning("⚠️ Este módulo debe ejecutarse desde cajas_diarias.py")
