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
        
        # Convierto la fecha
        if 'Fecha E.' in df.columns:
            df['Fecha'] = pd.to_datetime(df['Fecha E.'], format='%d/%m/%Y', errors='coerce')
        
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


def obtener_sucursal_id_desde_nombre(nombre_empresa, mapeo_sucursales):
    """
    Obtiene el sucursal_id a partir del nombre de la empresa
    Intenta varias estrategias de matching
    """
    if not nombre_empresa or pd.isna(nombre_empresa):
        return None
    
    nombre_empresa = str(nombre_empresa).strip()
    
    # Estrategia 1: Coincidencia exacta
    if nombre_empresa in mapeo_sucursales:
        return mapeo_sucursales[nombre_empresa]
    
    # Estrategia 2: Coincidencia normalizada
    nombre_norm = nombre_empresa.upper().replace(' ', '').replace('.', '').replace(',', '')
    if nombre_norm in mapeo_sucursales:
        return mapeo_sucursales[nombre_norm]
    
    # Estrategia 3: Por palabras clave
    palabras = nombre_empresa.upper().split()
    if len(palabras) > 0:
        # Primera palabra
        if palabras[0] in mapeo_sucursales:
            return mapeo_sucursales[palabras[0]]
        # Primeras dos palabras
        if len(palabras) > 1:
            clave = f"{palabras[0]} {palabras[1]}"
            if clave in mapeo_sucursales:
                return mapeo_sucursales[clave]
    
    # Estrategia 4: Búsqueda parcial (contiene)
    for nombre_mapeado, suc_id in mapeo_sucursales.items():
        if nombre_empresa.upper() in nombre_mapeado.upper():
            return suc_id
        if nombre_mapeado.upper() in nombre_empresa.upper():
            return suc_id
    
    return None


def guardar_gastos_en_db(supabase, df_gastos, mes, anio, usuario=None, mapeo_sucursales=None):
    """
    Guarda los gastos procesados en la base de datos
    Mapea automáticamente nombres de empresas a sucursal_id
    
    Parámetros:
    -----------
    mapeo_sucursales : dict, opcional
        Diccionario de mapeo nombre -> id. Si no se provee, se crea automáticamente
    
    Retorna:
    --------
    dict con 'exitosos': int, 'errores': list, 'sin_sucursal': list
    """
    exitosos = 0
    errores = []
    sin_sucursal = []
    
    # Crear mapeo si no se proporciona
    if mapeo_sucursales is None:
        mapeo_sucursales = crear_mapeo_sucursales(supabase)
    
    try:
        for idx, row in df_gastos.iterrows():
            try:
                # Obtener nombre de la empresa
                nombre_empresa = row.get('Empresa', '')
                
                # Mapear a sucursal_id
                sucursal_id = obtener_sucursal_id_desde_nombre(nombre_empresa, mapeo_sucursales)
                
                if sucursal_id is None:
                    sin_sucursal.append({
                        'fila': idx + 1,
                        'empresa': nombre_empresa,
                        'fecha': row.get('Fecha', ''),
                        'total': row.get('TOTAL_GASTO', 0)
                    })
                    continue
                
                # Preparar datos para inserción
                gasto_data = {
                    'sucursal_id': sucursal_id,
                    'mes': mes,
                    'anio': anio,
                    'fecha': str(row['Fecha'].date()) if pd.notna(row['Fecha']) else None,
                    'tipo_comprobante': row.get('Tipo Comprobante', ''),
                    'numero_comprobante': row.get('Comprobante', ''),
                    'proveedor': row.get('Proveedor', ''),
                    'cuit': row.get('Cuit', ''),
                    'rubro': row.get('Rubro', ''),
                    'subrubro': row.get('Subrubro', ''),
                    'neto': float(row['NETO']),
                    'iva_percepciones': float(row['IVA_PERCEPCIONES']),
                    'total': float(row['TOTAL_GASTO']),
                    # Detalles de importes
                    'importe_neto_21': float(row.get('Importe Neto 21', 0)),
                    'importe_neto_10_5': float(row.get('Importe Neto 10_5', 0)),
                    'importe_neto_27': float(row.get('Importe Neto 27', 0)),
                    'impuestos_internos': float(row.get('Impuestos Internos', 0)),
                    'percepcion_iva': float(row.get('Percepcion Iva', 0)),
                    'otras_percepciones': float(row.get('Otras Percepciones', 0)),
                    'percepcion_iibb': float(row.get('Percepcion IIBB', 0)),
                    'iva_21': float(row.get('Iva 21', 0)),
                    'iva_10_5': float(row.get('Iva 10,5', 0)),
                    'iva_27': float(row.get('Iva 27', 0)),
                    'usuario_importacion': usuario
                }
                
                # Insertar en base de datos
                supabase.table("gastos_mensuales").insert(gasto_data).execute()
                exitosos += 1
                
            except Exception as e:
                errores.append(f"Fila {idx + 1}: {str(e)}")
        
        return {
            'exitosos': exitosos,
            'errores': errores,
            'sin_sucursal': sin_sucursal
        }
        
    except Exception as e:
        return {
            'exitosos': exitosos,
            'errores': [f"Error general: {str(e)}"] + errores,
            'sin_sucursal': sin_sucursal
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
        
        # Filtrar solo ingresos
        query = query.eq("tipo", "ingreso")
        
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
            .eq("tipo", "ingreso")\
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
    """
    st.subheader("📁 Importar Gastos desde CSV")
    
    st.info("💡 **Tip**: El CSV puede contener gastos de múltiples sucursales. El sistema las detectará automáticamente.")
    
    # Crear mapeo de sucursales
    mapeo_sucursales = crear_mapeo_sucursales(supabase)
    
    if not mapeo_sucursales:
        st.error("❌ No se pudieron cargar las sucursales. Verifica la conexión a Supabase.")
        return
    
    # Mostrar sucursales disponibles
    with st.expander("🏪 Sucursales configuradas en el sistema"):
        st.write("Las siguientes sucursales están disponibles para mapeo automático:")
        for nombre, suc_id in mapeo_sucursales.items():
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
                sucursal_id = obtener_sucursal_id_desde_nombre(empresa, mapeo_sucursales)
                total_empresa = df_gastos[df_gastos['Empresa'] == empresa]['TOTAL_GASTO'].sum()
                
                if sucursal_id:
                    # Encontrar nombre de sucursal
                    nombre_sucursal = next((k for k, v in mapeo_sucursales.items() if v == sucursal_id and (' ' in k or '.' in k)), empresa)
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
            
            # Verificar si ya existen gastos para alguna sucursal en este período
            st.markdown("---")
            st.subheader("⚠️ Verificación de Duplicados")
            
            gastos_existentes_por_sucursal = {}
            for empresa_info in empresas_mapeadas:
                sucursal_id = obtener_sucursal_id_desde_nombre(empresa_info['CSV'], mapeo_sucursales)
                if sucursal_id:
                    gastos_existentes = verificar_gastos_existentes(supabase, sucursal_id, mes_seleccionado, anio_seleccionado)
                    if gastos_existentes['existe']:
                        gastos_existentes_por_sucursal[empresa_info['Sucursal']] = gastos_existentes
            
            if gastos_existentes_por_sucursal:
                st.warning("⚠️ **Ya existen gastos para algunas sucursales en este período:**")
                for sucursal, info in gastos_existentes_por_sucursal.items():
                    st.write(f"- **{sucursal}**: {info['cantidad']} registros (${info['total']:,.2f})".replace(',', 'X').replace('.', ',').replace('X', '.'))
                
                st.write("")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Reemplazar TODOS los gastos existentes", type="secondary"):
                        with st.spinner("Eliminando gastos existentes..."):
                            for empresa_info in empresas_mapeadas:
                                sucursal_id = obtener_sucursal_id_desde_nombre(empresa_info['CSV'], mapeo_sucursales)
                                if sucursal_id:
                                    eliminar_gastos_periodo(supabase, sucursal_id, mes_seleccionado, anio_seleccionado)
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
                            mes_seleccionado, 
                            anio_seleccionado,
                            usuario_actual,
                            mapeo_sucursales
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
                            
                            st.info("💡 Los gastos fueron guardados. Ve a la pestaña 'Análisis del Período' o 'Evolución Histórica'.")
                        
                        if resultado['sin_sucursal']:
                            st.warning(f"⚠️ {len(resultado['sin_sucursal'])} registros no pudieron ser mapeados a ninguna sucursal:")
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
    
    # Obtener datos de la DB
    with st.spinner("Cargando datos..."):
        df_gastos = obtener_gastos_db(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
        df_ingresos = obtener_ingresos_mensuales(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
    
    if df_gastos.empty:
        st.warning("⚠️ No hay gastos registrados para este período. Ve a la pestaña 'Importar Gastos' para cargar datos.")
        return
    
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
        
        tab1, tab2 = st.tabs(["Composición de Gastos", "Comparativa con Benchmarks"])
        
        with tab1:
            import plotly.express as px
            
            fig = px.pie(
                df_analisis,
                values='gasto',
                names='rubro',
                title='Distribución de Gastos por Rubro'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            import plotly.graph_objects as go
            
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
                ruta_archivo = f"/home/claude/{nombre_archivo}"
                
                with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
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
                
                with open(ruta_archivo, 'rb') as f:
                    st.download_button(
                        label="⬇️ Descargar Reporte",
                        data=f,
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
    
    import plotly.graph_objects as go
    
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
    Función principal del módulo P&L Simples v2.0
    """
    st.header("📊 P&L Simples - Informe Mensual de Resultados")
    st.caption("v2.0 - Con persistencia y evolución histórica")
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
            "📅 Mes",
            options=list(meses.keys()),
            format_func=lambda x: meses[x],
            index=mes_actual - 1
        )
    
    with col2:
        anio_actual = datetime.now().year
        anio_seleccionado = st.selectbox(
            "📅 Año",
            options=range(anio_actual - 2, anio_actual + 1),
            index=2
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
