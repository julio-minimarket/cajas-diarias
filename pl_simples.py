"""
Módulo P&L Simples - Profit & Loss Simple (v2.0 con persistencia)
Genera informes mensuales de Ingresos vs. Egresos por sucursal
Incluye análisis de composición del gasto, estadísticas comparativas y evolución histórica

Autor: Julio Becker
Fecha: Enero 2026
Integrado a: cajas_diarias.py
Versión: 2.0 - Agregado: Persistencia en DB y evolución histórica
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
from pathlib import Path
import calendar

# ==================== FUNCIONES DE PROCESAMIENTO DE GASTOS ====================

# ============================================================
# MAPEO MANUAL: CSV → SUCURSALES
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
    
    Returns:
        dict: {nombre_csv: sucursal_id}
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
    
    Parámetros:
    -----------
    sucursal_id : int o None
        ID de la sucursal. Si es None, verifica para todas las sucursales
    
    Retorna:
    --------
    dict con 'existe': bool, 'cantidad': int, 'total': float
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
    
    Prioridades:
    1. Mapeo manual EXACTO (desde tabla o hardcoded)
    2. Mapeo manual NORMALIZADO
    3. Mapeo automático (4 estrategias)
    
    Args:
        nombre_empresa (str): Nombre de la empresa del CSV
        mapeo_manual (dict): Mapeo manual {nombre: id}
        mapeo_automatico (dict): Mapeo automático {nombre: id}
    
    Returns:
        int or None: sucursal_id o None si no se encuentra
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
    IMPORTANTE: Usa la fecha de cada registro del CSV, no una fecha global
    
    Usa mapeo HÍBRIDO:
    1. Mapeo manual (tabla mapeo_sucursales_csv o hardcoded)
    2. Mapeo automático (tabla sucursales con estrategias)
    
    Retorna:
    --------
    dict con 'exitosos': int, 'errores': list, 'sin_sucursal': list, 'sin_fecha': list, 'duplicados': list
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
                # Intentar primero con 'Fecha C.' (Fecha de Contabilización)
                fecha_contable = None
                if 'Fecha C.' in row and pd.notna(row['Fecha C.']):
                    try:
                        fecha_contable = pd.to_datetime(row['Fecha C.'], format='%d/%m/%Y', errors='coerce')
                    except:
                        pass
                
                # Si no hay 'Fecha C.', usar 'Fecha E.' (Fecha de Emisión)
                if fecha_contable is None or pd.isna(fecha_contable):
                    if 'Fecha E.' in row and pd.notna(row['Fecha E.']):
                        try:
                            fecha_contable = pd.to_datetime(row['Fecha E.'], format='%d/%m/%Y', errors='coerce')
                        except:
                            pass
                
                # Si no hay ninguna fecha válida, usar la fecha procesada 'Fecha'
                if fecha_contable is None or pd.isna(fecha_contable):
                    if 'Fecha' in row and pd.notna(row['Fecha']):
                        fecha_contable = row['Fecha']
                
                # Verificar que tenemos una fecha válida
                if fecha_contable is None or pd.isna(fecha_contable):
                    sin_fecha.append({
                        'fila': idx + 1,
                        'empresa': nombre_empresa,
                        'fecha_e': row.get('Fecha E.', ''),
                        'fecha_c': row.get('Fecha C.', ''),
                        'total': row.get('TOTAL_GASTO', 0)
                    })
                    continue
                
                # Extraer mes y año de la fecha
                mes = fecha_contable.month
                anio = fecha_contable.year
                
                # Función auxiliar para convertir valores de forma segura
                def convertir_a_float_seguro(valor):
                    """Convierte un valor a float, reemplazando nan, inf, None con 0"""
                    try:
                        if pd.isna(valor) or valor is None:
                            return 0.0
                        val_float = float(valor)
                        # Verificar si es nan, inf o -inf
                        if not pd.isna(val_float) and val_float != float('inf') and val_float != float('-inf'):
                            return val_float
                        else:
                            return 0.0
                    except (ValueError, TypeError):
                        return 0.0
                
                # Preparar datos para inserción con conversión segura
                gasto_data = {
                    'sucursal_id': sucursal_id,
                    'mes': mes,  # Extraído de la fecha del CSV
                    'anio': anio,  # Extraído de la fecha del CSV
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
                    # Detalles de importes con conversión segura
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


def obtener_gastos_db(supabase, mes, anio, sucursal_id=None):
    """
    Obtiene los gastos desde la base de datos
    """
    try:
        query = supabase.table("gastos_mensuales").select("*")
        
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


def obtener_ingresos_mensuales(supabase, mes, anio, sucursal_id=None):
    """
    Obtiene los ingresos mensuales de la base de datos de cajas_diarias
    """
    try:
        # Construir fechas de inicio y fin del mes
        primer_dia = date(anio, mes, 1)
        ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
        
        # Query base
        query = supabase.table("movimientos_diarios").select("*")
        
        # Filtrar por fechas
        query = query.gte("fecha", str(primer_dia))
        query = query.lte("fecha", str(ultimo_dia))
        
        # Filtrar por sucursal si se especifica
        if sucursal_id is not None:
            query = query.eq("sucursal_id", sucursal_id)
        
        # Filtrar solo ventas (ingresos)
        query = query.eq("tipo", "venta")  # ✅ CORREGIDO: era "ingreso"
        
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


def obtener_evolucion_historica(supabase, sucursal_id, meses_atras=12):
    """
    Obtiene la evolución histórica de gastos e ingresos
    """
    try:
        # Obtener gastos históricos
        result_gastos = supabase.table("gastos_mensuales")\
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
        
        result_ingresos = supabase.table("movimientos_diarios")\
            .select("fecha, monto")\
            .eq("sucursal_id", sucursal_id)\
            .eq("tipo", "venta")\
            .gte("fecha", str(fecha_limite.date()))\
            .execute()  # ✅ CORREGIDO: tipo era "ingreso", ahora "venta"
        
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
            st.write(f"   - {len(set(mapeo_manual.values()))} empresas CSV → sucursales")
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
                            
                            st.cache_data.clear()
                            
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
    Tab de análisis del período actual
    """
    st.subheader("📊 Análisis del Período Actual")
    
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
            
            # Mostrar qué sucursales tienen gastos
            for suc_id in sucursales_en_gastos:
                suc = next((s for s in sucursales if s['id'] == suc_id), None)
                if suc:
                    cantidad = len(df_gastos[df_gastos['sucursal_id'] == suc_id])
                    st.write(f"   - {suc['nombre']}: {cantidad} registros")
            
            st.info("💡 Selecciona una de estas sucursales en el selector de arriba para ver su análisis.")
            return
    
    # Si no hay ingresos pero sí gastos, mostrar advertencia
    if df_ingresos.empty and not df_gastos.empty:
        st.warning(f"⚠️ **Atención**: Hay gastos registrados pero NO hay ingresos para **{sucursal_nombre}** en **{mes_seleccionado}/{anio_seleccionado}**.")
        st.info("💡 Esto puede deberse a:")
        st.write("   1. Los ingresos no se han registrado en ese período")
        st.write("   2. Los ingresos están registrados con un nombre de sucursal diferente")
        st.write("   3. Los ingresos están en la tabla 'movimientos_diarios' con un sucursal_id diferente")
        
        # Mostrar información de debug
        with st.expander("🔍 Información de Debug"):
            st.write(f"**Buscando ingresos para:**")
            st.write(f"   - Sucursal ID: {sucursal_id}")
            st.write(f"   - Sucursal nombre: {sucursal_nombre}")
            st.write(f"   - Mes: {mes_seleccionado}")
            st.write(f"   - Año: {anio_seleccionado}")
            
            st.write(f"**Gastos encontrados:**")
            st.write(f"   - Total: {len(df_gastos)} registros")
            st.write(f"   - Suma: ${df_gastos['total'].sum():,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            
            # Buscar si hay ingresos con otros sucursal_id en ese período
            st.write(f"**Verificando ingresos en movimientos_diarios...**")
            try:
                from datetime import date
                import calendar
                primer_dia = date(anio_seleccionado, mes_seleccionado, 1)
                ultimo_dia = date(anio_seleccionado, mes_seleccionado, calendar.monthrange(anio_seleccionado, mes_seleccionado)[1])
                
                result_all = supabase.table("movimientos_diarios")\
                    .select("sucursal_id, fecha, monto")\
                    .gte("fecha", str(primer_dia))\
                    .lte("fecha", str(ultimo_dia))\
                    .eq("tipo", "venta")\
                    .execute()  # ✅ CORREGIDO: tipo era "ingreso", ahora "venta"
                
                if result_all.data:
                    df_all = pd.DataFrame(result_all.data)
                    sucursales_con_ingresos = df_all.groupby('sucursal_id')['monto'].sum()
                    
                    st.write(f"**Ingresos encontrados en el período (todas las sucursales):**")
                    for suc_id, total in sucursales_con_ingresos.items():
                        suc = next((s for s in sucursales if s['id'] == suc_id), None)
                        suc_name = suc['nombre'] if suc else f"ID: {suc_id}"
                        st.write(f"   - {suc_name}: ${total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                else:
                    st.write("   - No hay ingresos registrados en todo el mes")
            except Exception as e:
                st.error(f"Error verificando ingresos: {str(e)}")
    
    # Calcular totales
    total_ingresos = df_ingresos['monto'].sum() if not df_ingresos.empty else 0
    total_gastos = df_gastos['total'].sum()
    resultado = total_ingresos - total_gastos
    margen = (resultado / total_ingresos * 100) if total_ingresos > 0 else 0
    
    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Ingresos Totales",
            f"${total_ingresos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        )
    
    with col2:
        st.metric(
            "Gastos Totales",
            f"${total_gastos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
            delta=f"-{(total_gastos/total_ingresos*100):.1f}%" if total_ingresos > 0 else None,
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "Resultado",
            f"${resultado:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
            delta=f"{margen:.1f}%",
            delta_color="normal" if resultado >= 0 else "inverse"
        )
    
    with col4:
        if margen >= 15:
            st.metric("Estado", "🟢 Excelente", delta=f"{margen:.1f}%")
        elif margen >= 10:
            st.metric("Estado", "🟡 Bueno", delta=f"{margen:.1f}%")
        elif margen >= 5:
            st.metric("Estado", "🟠 Ajustado", delta=f"{margen:.1f}%")
        else:
            st.metric("Estado", "🔴 Crítico", delta=f"{margen:.1f}%")
    
    # Análisis de composición
    st.markdown("---")
    st.subheader("📊 Composición del Gasto")
    
    analisis = analizar_composicion_gastos(df_gastos, total_ingresos)
    
    df_analisis = pd.DataFrame(analisis['rubros'])
    
    if not df_analisis.empty:
        # Formatear para visualización
        df_display = df_analisis.copy()
        df_display['Gasto'] = df_display['gasto'].apply(
            lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        )
        df_display['% Real'] = df_display['porcentaje_real'].apply(lambda x: f"{x:.1f}%")
        df_display['% Ideal'] = df_display['benchmark'].apply(
            lambda x: f"{x['porcentaje_ideal']:.1f}%" if x else "N/A"
        )
        df_display['Rango Óptimo'] = df_display['benchmark'].apply(
            lambda x: f"{x['rango_min']:.1f}% - {x['rango_max']:.1f}%" if x else "N/A"
        )
        df_display['Estado'] = df_display['estado'].apply(
            lambda x: "🟢 OK" if x == "ok" else ("🔴 Alto" if x == "alto" else ("🟡 Bajo" if x == "bajo" else "⚪"))
        )
        
        st.dataframe(
            df_display[['rubro', 'Gasto', '% Real', '% Ideal', 'Rango Óptimo', 'Estado']].rename(columns={
                'rubro': 'Rubro'
            }),
            hide_index=True,
            use_container_width=True
        )
        
        # Alertas
        st.markdown("---")
        st.subheader("💡 Alertas y Recomendaciones")
        
        alertas = []
        for item in analisis['rubros']:
            if item['estado'] == 'alto':
                alertas.append({
                    'tipo': '⚠️ ALERTA',
                    'mensaje': f"**{item['rubro']}** está en {item['porcentaje_real']:.1f}% (ideal: {item['benchmark']['porcentaje_ideal']:.1f}%)",
                    'severidad': 'warning'
                })
            elif item['estado'] == 'bajo':
                alertas.append({
                    'tipo': '💡 OPORTUNIDAD',
                    'mensaje': f"**{item['rubro']}** está en {item['porcentaje_real']:.1f}% (ideal: {item['benchmark']['porcentaje_ideal']:.1f}%)",
                    'severidad': 'info'
                })
        
        if alertas:
            for alerta in alertas:
                if alerta['severidad'] == 'warning':
                    st.warning(f"{alerta['tipo']}: {alerta['mensaje']}")
                else:
                    st.info(f"{alerta['tipo']}: {alerta['mensaje']}")
        else:
            st.success("✅ Todos los rubros están dentro de los rangos óptimos")
        
        # Gráficos
        st.markdown("---")
        st.subheader("📈 Visualizaciones")
        
        # Verificar si plotly está disponible
        try:
            import plotly.express as px
            import plotly.graph_objects as go
            plotly_disponible = True
        except ImportError:
            plotly_disponible = False
            st.warning("⚠️ **Plotly no está instalado**. Los gráficos no están disponibles.")
            st.info("💡 Para ver gráficos, instala plotly: `pip install plotly --break-system-packages`")
        
        if plotly_disponible:
            tab1, tab2 = st.tabs(["Composición de Gastos", "Comparativa con Benchmarks"])
            
            with tab1:
                fig = px.pie(
                    df_analisis,
                    values='gasto',
                    names='rubro',
                    title='Distribución de Gastos por Rubro'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                df_comp = df_analisis[df_analisis['benchmark'].notna()].copy()
                
                if not df_comp.empty:
                    fig = go.Figure()
                    
                    fig.add_trace(go.Bar(
                        x=df_comp['rubro'],
                        y=df_comp['porcentaje_real'],
                        name='% Real',
                        marker_color='lightblue'
                    ))
                    
                    fig.add_trace(go.Bar(
                        x=df_comp['rubro'],
                        y=df_comp['benchmark'].apply(lambda x: x['porcentaje_ideal']),
                        name='% Ideal',
                        marker_color='lightgreen'
                    ))
                    
                    fig.update_layout(
                        title='Comparativa: Real vs. Ideal (% sobre Ingresos)',
                        xaxis_title='Rubro',
                        yaxis_title='Porcentaje',
                        barmode='group'
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
        
        # Exportar
        st.markdown("---")
        if st.button("📥 Generar Reporte Excel", type="primary"):
            with st.spinner("Generando reporte..."):
                meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
                
                sucursal_nombre = sucursal_seleccionada['nombre'] if sucursal_seleccionada else "Todas"
                nombre_archivo = f"PL_Simple_{meses[mes_seleccionado]}_{anio_seleccionado}_{sucursal_nombre}.xlsx"
                
                # 🔴 FIX: Usar BytesIO en lugar de guardar en disco (Streamlit Cloud no tiene /home/claude/)
                from io import BytesIO
                
                buffer = BytesIO()
                
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    # Hoja 1: Resumen
                    resumen_exec = pd.DataFrame([{
                        'Período': f"{meses[mes_seleccionado]} {anio_seleccionado}",
                        'Sucursal': sucursal_nombre,
                        'Ingresos': total_ingresos,
                        'Gastos': total_gastos,
                        'Resultado': resultado,
                        'Margen %': margen
                    }])
                    resumen_exec.to_excel(writer, sheet_name='Resumen Ejecutivo', index=False)
                    
                    # Hoja 2: Composición
                    df_display.to_excel(writer, sheet_name='Composición Gastos', index=False)
                    
                    # Hoja 3: Detalle Gastos
                    df_gastos.to_excel(writer, sheet_name='Detalle Gastos', index=False)
                    
                    # Hoja 4: Detalle Ingresos
                    if not df_ingresos.empty:
                        df_ingresos.to_excel(writer, sheet_name='Detalle Ingresos', index=False)
                
                st.success("✅ Reporte generado exitosamente")
                
                # Preparar el buffer para descarga
                buffer.seek(0)
                
                st.download_button(
                    label="⬇️ Descargar Reporte Excel",
                    data=buffer,
                    file_name=nombre_archivo,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )


def mostrar_tab_evolucion(supabase, sucursales, sucursal_seleccionada):
    """
    Tab de evolución histórica
    """
    st.subheader("📈 Evolución Histórica")
    
    if sucursal_seleccionada is None:
        st.warning("⚠️ Selecciona una sucursal para ver su evolución histórica")
        return
    
    sucursal_id = sucursal_seleccionada['id']
    
    # Selector de meses a mostrar
    meses_atras = st.slider("Meses a mostrar", min_value=3, max_value=24, value=12, step=1)
    
    # Obtener datos
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


def main(supabase):
    """
    Función principal del módulo P&L Simples v2.2
    """
    st.header("📊 P&L Simples - Informe Mensual de Resultados")
    st.caption("v2.2 - Con persistencia, evolución histórica y mapeo automático de fechas")
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
    tab1, tab2, tab3 = st.tabs(["📁 Importar Gastos", "📊 Análisis del Período", "📈 Evolución Histórica"])
    
    with tab1:
        mostrar_tab_importacion(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada)
    
    with tab2:
        mostrar_tab_analisis(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada)
    
    with tab3:
        mostrar_tab_evolucion(supabase, sucursales, sucursal_seleccionada)


if __name__ == "__main__":
    st.warning("⚠️ Este módulo debe ejecutarse desde cajas_diarias.py")
