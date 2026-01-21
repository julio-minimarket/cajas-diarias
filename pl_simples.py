"""
Módulo P&L Simples - Profit & Loss Simple (v2.3 con Diseño Ejecutivo)
Genera informes mensuales de Ingresos vs. Egresos por sucursal
Incluye análisis de composición, evolución y reporte granular estilizado.

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

MAPEO_CSV_HARDCODED = {
    'Belfast S.A.': 4,
    'Chicken Chill Minimarket S.A.': 8,
    'Costumbres Argentinas-Minimarket S.A.': 10,
    'Destileria Open 24 S.A.': 13,
    'Friends S.A.S. Patagonia': 5,
    'Liverpool Minimarket S.A.': 7,
    'Minimarket S.A. ': 1,
    'Minimarket S.A.': 1,
    'Open 24 Minimarket S.A.': 11,
    'Pocillos S.A.S. 1885 ': 3,
    'Pocillos S.A.S. 1885': 3,
    'Pocillos S.A.S.Napoles Rgl': 2,
    'Rincon Chico S.A.S. Napoles Calafate': 6,
    'Temple Minimarket S.A.': 9,
}

def obtener_mapeo_manual(supabase):
    mapeo = {}
    try:
        result = supabase.table("mapeo_sucursales_csv")\
            .select("nombre_csv, sucursal_id")\
            .eq("activo", True)\
            .execute()
        
        if result.data:
            for row in result.data:
                mapeo[row['nombre_csv']] = row['sucursal_id']
                nombre_norm = row['nombre_csv'].upper().replace(' ', '').replace('.', '').replace(',', '')
                mapeo[nombre_norm] = row['sucursal_id']
            return mapeo
    except Exception as e:
        print(f"[INFO] No se pudo obtener mapeo de DB, usando hardcoded: {e}")
    
    if not mapeo:
        mapeo = MAPEO_CSV_HARDCODED.copy()
        for nombre_csv, sucursal_id in MAPEO_CSV_HARDCODED.items():
            nombre_norm = nombre_csv.upper().replace(' ', '').replace('.', '').replace(',', '')
            mapeo[nombre_norm] = sucursal_id
    
    return mapeo

def convertir_importe(valor):
    valor = str(valor).strip()
    if '$' in valor:
        valor = valor.replace('$', '').strip()
        valor = valor.replace('.', '')
        valor = valor.replace(',', '.')
    elif ',' in valor:
        valor = valor.replace('.', '')
        valor = valor.replace(',', '.')
    try:
        return float(valor)
    except:
        return 0.0

def procesar_archivo_gastos(archivo_csv):
    try:
        df = pd.read_csv(archivo_csv)
        if len(df) > 0 and pd.isna(df.iloc[-1]['Empresa']):
            df = df[:-1]
        
        columnas_neto = ['Importe Neto 21', 'Importe Neto 10_5', 'Importe Neto 27', 'Impuestos Internos']
        columnas_iva = ['Percepcion Iva', 'Otras Percepciones', 'Percepcion IIBB', 'Iva 21', 'Iva 10,5', 'Iva 27']
        
        for col in columnas_neto + columnas_iva:
            if col in df.columns:
                df[col] = df[col].apply(convertir_importe)
        
        if 'Fecha C.' in df.columns:
            df['Fecha'] = pd.to_datetime(df['Fecha C.'], format='%d/%m/%Y', errors='coerce')
        if 'Fecha E.' in df.columns:
            if 'Fecha' not in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha E.'], format='%d/%m/%Y', errors='coerce')
            else:
                mask = df['Fecha'].isna()
                df.loc[mask, 'Fecha'] = pd.to_datetime(df.loc[mask, 'Fecha E.'], format='%d/%m/%Y', errors='coerce')
        
        df['NETO'] = df[columnas_neto].sum(axis=1)
        df['IVA_PERCEPCIONES'] = df[columnas_iva].sum(axis=1)
        df['TOTAL_GASTO'] = df['NETO'] + df['IVA_PERCEPCIONES']
        
        df = df.dropna(subset=['Empresa'])
        df = df[df['TOTAL_GASTO'] > 0]
        
        return df
    except Exception as e:
        st.error(f"❌ Error procesando archivo de gastos: {str(e)}")
        return None

def verificar_gastos_existentes(supabase, sucursal_id, mes, anio):
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
    try:
        result = supabase.table("sucursales").select("id, nombre").execute()
        if not result.data:
            return {}
        mapeo = {}
        for sucursal in result.data:
            nombre = sucursal['nombre']
            sucursal_id = sucursal['id']
            mapeo[nombre] = sucursal_id
            nombre_norm = nombre.upper().replace(' ', '').replace('.', '').replace(',', '')
            mapeo[nombre_norm] = sucursal_id
            palabras = nombre.upper().split()
            if len(palabras) > 0:
                mapeo[palabras[0]] = sucursal_id
                if len(palabras) > 1:
                    mapeo[f"{palabras[0]} {palabras[1]}"] = sucursal_id
        return mapeo
    except Exception as e:
        st.error(f"❌ Error creando mapeo de sucursales: {str(e)}")
        return {}

def obtener_sucursal_id_desde_nombre(nombre_empresa, mapeo_manual, mapeo_automatico):
    if not nombre_empresa or pd.isna(nombre_empresa):
        return None
    nombre_empresa = str(nombre_empresa).strip()
    
    if nombre_empresa in mapeo_manual:
        return mapeo_manual[nombre_empresa]
    
    nombre_norm = nombre_empresa.upper().replace(' ', '').replace('.', '').replace(',', '')
    if nombre_norm in mapeo_manual:
        return mapeo_manual[nombre_norm]
    
    if nombre_empresa in mapeo_automatico:
        return mapeo_automatico[nombre_empresa]
    if nombre_norm in mapeo_automatico:
        return mapeo_automatico[nombre_norm]
    
    palabras = nombre_empresa.upper().split()
    if len(palabras) > 0:
        if palabras[0] in mapeo_automatico:
            return mapeo_automatico[palabras[0]]
        if len(palabras) > 1:
            clave = f"{palabras[0]} {palabras[1]}"
            if clave in mapeo_automatico:
                return mapeo_automatico[clave]
    
    for nombre_mapeado, suc_id in mapeo_automatico.items():
        if nombre_empresa.upper() in nombre_mapeado.upper() or nombre_mapeado.upper() in nombre_empresa.upper():
            return suc_id
    
    return None

def guardar_gastos_en_db(supabase, df_gastos, usuario=None):
    exitosos = 0
    errores = []
    sin_sucursal = []
    sin_fecha = []
    duplicados = []
    
    mapeo_manual = obtener_mapeo_manual(supabase)
    mapeo_automatico = crear_mapeo_sucursales(supabase)
    
    try:
        for idx, row in df_gastos.iterrows():
            try:
                nombre_empresa = row.get('Empresa', '')
                sucursal_id = obtener_sucursal_id_desde_nombre(nombre_empresa, mapeo_manual, mapeo_automatico)
                
                if sucursal_id is None:
                    sin_sucursal.append({
                        'fila': idx + 1,
                        'empresa': nombre_empresa,
                        'fecha': row.get('Fecha', ''),
                        'total': row.get('TOTAL_GASTO', 0),
                        'sugerencia': '💡 Verifica que la sucursal exista en Supabase'
                    })
                    continue
                
                fecha_contable = None
                if 'Fecha C.' in row and pd.notna(row['Fecha C.']):
                    try:
                        fecha_contable = pd.to_datetime(row['Fecha C.'], format='%d/%m/%Y', errors='coerce')
                    except: pass
                
                if fecha_contable is None or pd.isna(fecha_contable):
                    if 'Fecha E.' in row and pd.notna(row['Fecha E.']):
                        try:
                            fecha_contable = pd.to_datetime(row['Fecha E.'], format='%d/%m/%Y', errors='coerce')
                        except: pass
                
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
                
                def convertir_a_float_seguro(valor):
                    try:
                        if pd.isna(valor) or valor is None: return 0.0
                        val_float = float(valor)
                        if not pd.isna(val_float) and val_float != float('inf') and val_float != float('-inf'):
                            return val_float
                        else: return 0.0
                    except: return 0.0
                
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
                
                supabase.table("gastos_mensuales").insert(gasto_data).execute()
                exitosos += 1
                
            except Exception as e:
                error_str = str(e)
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
    try:
        supabase.table("gastos_mensuales").delete().eq("sucursal_id", sucursal_id).eq("mes", mes).eq("anio", anio).execute()
        return True
    except Exception as e:
        st.error(f"❌ Error eliminando gastos: {str(e)}")
        return False

@st.cache_data(ttl=30)
def obtener_gastos_db(_supabase, mes, anio, sucursal_id=None):
    try:
        query = _supabase.table("gastos_mensuales").select("*").eq("mes", mes).eq("anio", anio)
        if sucursal_id is not None:
            query = query.eq("sucursal_id", sucursal_id)
        result = query.execute()
        return pd.DataFrame(result.data) if result.data else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error obteniendo gastos de DB: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def obtener_ingresos_mensuales(_supabase, mes, anio, sucursal_id=None):
    try:
        primer_dia = date(anio, mes, 1)
        ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
        query = _supabase.table("movimientos_diarios").select("*").gte("fecha", str(primer_dia)).lte("fecha", str(ultimo_dia))
        if sucursal_id is not None:
            query = query.eq("sucursal_id", sucursal_id)
        query = query.eq("tipo", "venta")
        result = query.execute()
        return pd.DataFrame(result.data) if result.data else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error obteniendo ingresos: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def obtener_evolucion_historica(_supabase, sucursal_id, meses_atras=12):
    try:
        result_gastos = _supabase.table("gastos_mensuales").select("anio, mes, total").eq("sucursal_id", sucursal_id).execute()
        if not result_gastos.data: return pd.DataFrame()
        
        df_gastos = pd.DataFrame(result_gastos.data)
        df_gastos_agg = df_gastos.groupby(['anio', 'mes'])['total'].sum().reset_index()
        df_gastos_agg.columns = ['anio', 'mes', 'total_gastos']
        df_gastos_agg['periodo'] = pd.to_datetime(df_gastos_agg['anio'].astype(str) + '-' + df_gastos_agg['mes'].astype(str).str.zfill(2) + '-01')
        
        fecha_limite = pd.Timestamp.now() - pd.DateOffset(months=meses_atras)
        result_ingresos = _supabase.table("movimientos_diarios").select("fecha, monto").eq("sucursal_id", sucursal_id).eq("tipo", "venta").gte("fecha", str(fecha_limite.date())).execute()
        
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
        
        df_evolucion = pd.merge(df_gastos_agg, df_ingresos_agg, on=['anio', 'mes', 'periodo'], how='outer').fillna(0)
        df_evolucion['resultado'] = df_evolucion['total_ingresos'] - df_evolucion['total_gastos']
        df_evolucion['margen'] = (df_evolucion['resultado'] / df_evolucion['total_ingresos'] * 100).fillna(0)
        df_evolucion = df_evolucion.sort_values('periodo', ascending=False).head(meses_atras)
        return df_evolucion.sort_values('periodo')
    except Exception as e:
        st.error(f"❌ Error obteniendo evolución histórica: {str(e)}")
        return pd.DataFrame()

def limpiar_cache_pl_simples():
    try:
        obtener_gastos_db.clear()
        obtener_ingresos_mensuales.clear()
        obtener_evolucion_historica.clear()
        return True
    except Exception as e:
        st.warning(f"⚠️ No se pudo limpiar el caché: {str(e)}")
        return False

def calcular_benchmarks_gastronomia():
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
    col_total = 'TOTAL_GASTO' if 'TOTAL_GASTO' in df_gastos.columns else 'total'
    col_rubro = 'Rubro' if 'Rubro' in df_gastos.columns else 'rubro'
    gastos_por_rubro = df_gastos.groupby(col_rubro)[col_total].sum().sort_values(ascending=False)
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
        rubro_upper = str(rubro).upper()
        benchmark = None
        estado = "neutral"
        
        for key in benchmarks.keys():
            if key in rubro_upper or rubro_upper in key:
                benchmark = benchmarks[key]
                if porcentaje_real < benchmark['rango_min']: estado = "bajo"
                elif porcentaje_real > benchmark['rango_max']: estado = "alto"
                else: estado = "ok"
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
    st.subheader("📁 Importar Gastos desde CSV")
    st.info("💡 **Importación Inteligente**: El sistema detecta automáticamente las sucursales Y las fechas de cada gasto desde el CSV.")
    
    mapeo_manual = obtener_mapeo_manual(supabase)
    mapeo_automatico = crear_mapeo_sucursales(supabase)
    
    if not mapeo_automatico:
        st.error("❌ No se pudieron cargar las sucursales.")
        return
    
    with st.expander("🏪 Información de Mapeo"):
        if mapeo_manual: st.write("✅ **Mapeo Manual Activo**")
        else: st.write("⚠️ **Mapeo Manual No Configurado**")
    
    archivo_gastos = st.file_uploader("Selecciona el archivo CSV de gastos", type=['csv'])
    
    if archivo_gastos is not None:
        with st.spinner("Procesando archivo CSV..."):
            df_gastos = procesar_archivo_gastos(archivo_gastos)
        
        if df_gastos is not None and len(df_gastos) > 0:
            st.success(f"✅ Archivo procesado: {len(df_gastos)} registros detectados")
            
            empresas_detectadas = df_gastos['Empresa'].value_counts()
            col1, col2 = st.columns(2)
            with col1: st.metric("Total de Empresas en CSV", len(empresas_detectadas))
            
            empresas_mapeadas = []
            empresas_sin_mapear = []
            
            for empresa, cantidad in empresas_detectadas.items():
                sucursal_id = obtener_sucursal_id_desde_nombre(empresa, mapeo_manual, mapeo_automatico)
                total_empresa = df_gastos[df_gastos['Empresa'] == empresa]['TOTAL_GASTO'].sum()
                
                if sucursal_id:
                    nombre_sucursal = next((k for k, v in mapeo_automatico.items() if v == sucursal_id and (' ' in k or '.' in k)), empresa)
                    empresas_mapeadas.append({'CSV': empresa, 'Sucursal': nombre_sucursal, 'Registros': cantidad, 'Total': total_empresa})
                else:
                    empresas_sin_mapear.append({'Empresa': empresa, 'Registros': cantidad, 'Total': total_empresa})
            
            with col2: st.metric("Empresas Mapeadas ✅", len(empresas_mapeadas))
            
            if empresas_mapeadas:
                st.success("✅ **Empresas que se importarán correctamente:**")
                df_mapeadas = pd.DataFrame(empresas_mapeadas)
                df_mapeadas['Total'] = df_mapeadas['Total'].apply(lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                st.dataframe(df_mapeadas, hide_index=True, use_container_width=True)
            
            if empresas_sin_mapear:
                st.error("⚠️ **Empresas SIN MAPEAR (no se importarán):**")
                st.dataframe(pd.DataFrame(empresas_sin_mapear), hide_index=True)

            usuario_actual = st.session_state.get('usuario', {}).get('usuario', 'desconocido')
            puede_importar = len(empresas_mapeadas) > 0
            
            if st.button("💾 Guardar en Base de Datos", type="primary", disabled=not puede_importar):
                with st.spinner("Guardando gastos..."):
                    resultado = guardar_gastos_en_db(supabase, df_gastos, usuario_actual)
                    if resultado['exitosos'] > 0:
                        st.success(f"✅ {resultado['exitosos']} registros guardados")
                        limpiar_cache_pl_simples()
                    if resultado['duplicados']:
                        st.warning(f"⚠️ {len(resultado['duplicados'])} registros duplicados omitidos.")
                    if resultado['errores']:
                        st.error(f"❌ {len(resultado['errores'])} errores.")

def mostrar_tab_analisis(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada):
    col_header, col_refresh = st.columns([4, 1])
    with col_header: st.subheader("📊 Análisis del Período Actual")
    with col_refresh:
        if st.button("🔄 Refrescar", key="refresh_analisis"):
            limpiar_cache_pl_simples()
            st.rerun()
    
    sucursal_id = sucursal_seleccionada['id'] if sucursal_seleccionada else None
    
    with st.spinner("Cargando datos..."):
        df_gastos = obtener_gastos_db(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
        df_ingresos = obtener_ingresos_mensuales(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
    
    if df_gastos.empty:
        st.warning(f"⚠️ No hay gastos registrados para este período.")
        return
    
    total_ingresos = df_ingresos['monto'].sum() if not df_ingresos.empty else 0
    total_gastos = df_gastos['total'].sum()
    resultado = total_ingresos - total_gastos
    margen = (resultado / total_ingresos * 100) if total_ingresos > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Ingresos Totales", f"${total_ingresos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    with col2: st.metric("Gastos Totales", f"${total_gastos:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), delta=f"-{(total_gastos/total_ingresos*100):.1f}%" if total_ingresos>0 else None, delta_color="inverse")
    with col3: st.metric("Resultado", f"${resultado:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), delta=f"{margen:.1f}%")
    with col4: st.metric("Estado", "🟢 Excelente" if margen>=15 else ("🟡 Bueno" if margen>=10 else ("🟠 Ajustado" if margen>=5 else "🔴 Crítico")))
    
    st.markdown("---")
    st.subheader("📊 Composición del Gasto")
    analisis = analizar_composicion_gastos(df_gastos, total_ingresos)
    df_analisis = pd.DataFrame(analisis['rubros'])
    
    if not df_analisis.empty:
        df_display = df_analisis.copy()
        df_display['Gasto'] = df_display['gasto'].apply(lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        df_display['% Real'] = df_display['porcentaje_real'].apply(lambda x: f"{x:.1f}%")
        df_display['Estado'] = df_display['estado'].apply(lambda x: "🟢 OK" if x == "ok" else ("🔴 Alto" if x == "alto" else "🟡 Bajo"))
        st.dataframe(df_display[['rubro', 'Gasto', '% Real', 'Estado']], hide_index=True, use_container_width=True)

def mostrar_tab_evolucion(supabase, sucursales, sucursal_seleccionada):
    col_header, col_refresh = st.columns([4, 1])
    with col_header: st.subheader("📈 Evolución Histórica")
    with col_refresh:
        if st.button("🔄 Refrescar", key="refresh_evolucion"):
            limpiar_cache_pl_simples()
            st.rerun()
    
    if sucursal_seleccionada is None:
        st.warning("⚠️ Selecciona una sucursal para ver su evolución histórica")
        return
    
    meses_atras = st.slider("Meses a mostrar", 3, 24, 12)
    with st.spinner("Cargando evolución histórica..."):
        df_evolucion = obtener_evolucion_historica(supabase, sucursal_seleccionada['id'], meses_atras)
    
    if not df_evolucion.empty:
        st.markdown("### 📊 Tabla de Evolución")
        df_display = df_evolucion.copy()
        df_display['Período'] = df_display['periodo'].dt.strftime('%Y-%m')
        for col in ['total_ingresos', 'total_gastos', 'resultado']:
            df_display[col] = df_display[col].apply(lambda x: f"${x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        df_display['Margen %'] = df_display['margen'].apply(lambda x: f"{x:.1f}%")
        st.dataframe(df_display[['Período', 'total_ingresos', 'total_gastos', 'resultado', 'Margen %']], hide_index=True, use_container_width=True)

# ==================== ESTADO DE RESULTADO GRANULAR ====================

def cargar_mapeo_erg_desde_excel(supabase, archivo_excel):
    try:
        df_mapeo = pd.read_excel(archivo_excel, sheet_name="Conjunto Datos")
        grupos = {1: [1, 2, 3, 4], 2: [5, 6], 3: [7, 8], 4: [9, 10, 11], 5: [12, 18], 6: [19], 7: [13, 14, 15, 16, 17]}
        cod_inf_to_grupo = {c: g for g, cods in grupos.items() for c in cods}
        
        registros = []
        for _, row in df_mapeo.iterrows():
            cod_inf = int(row['Cod_Inf'])
            item = str(row['Item']).strip()
            orden_grupo = cod_inf_to_grupo.get(cod_inf, 1)
            for col in df_mapeo.columns:
                if 'Subrubro' in col and pd.notna(row[col]):
                    registros.append({'cod_inf': cod_inf, 'item': item, 'subrubro': str(row[col]).strip().upper(), 'orden_grupo': orden_grupo})
        
        try: supabase.table("mapeo_estado_resultado_granular").delete().neq('id', 0).execute()
        except: pass
        
        if registros: supabase.table("mapeo_estado_resultado_granular").insert(registros).execute()
        return {'exitoso': True, 'mensaje': f"✅ {len(registros)} relaciones cargadas"}
    except Exception as e:
        return {'exitoso': False, 'mensaje': f"❌ Error: {str(e)}"}

@st.cache_data(ttl=300)
def obtener_mapeo_erg(_supabase):
    try:
        result = _supabase.table("mapeo_estado_resultado_granular").select("*").execute()
        if result.data:
            df = pd.DataFrame(result.data)
            df['subrubro'] = df['subrubro'].str.upper().str.strip()
            return df
        return pd.DataFrame()
    except: return pd.DataFrame()

def agrupar_gastos_erg(df_gastos, df_mapeo):
    if df_gastos.empty or df_mapeo.empty: return pd.DataFrame()
    df_gastos['subrubro_norm'] = df_gastos['subrubro'].str.upper().str.strip()
    df_merged = df_gastos.merge(df_mapeo[['cod_inf', 'item', 'subrubro', 'orden_grupo']], left_on='subrubro_norm', right_on='subrubro', how='left')
    df_agrupado = df_merged.groupby(['cod_inf', 'item', 'orden_grupo']).agg({'total': 'sum'}).reset_index()
    return df_agrupado[df_agrupado['cod_inf'].notna()].sort_values('cod_inf')

def generar_estado_resultado_granular(df_gastos_agrupados, total_ingresos, sucursal_nombre, mes, anio):
    reporte = []
    
    # Header Info (para usar en el renderer)
    reporte.append({'tipo': 'info_meta', 'descripcion': 'Local', 'valor': sucursal_nombre})
    reporte.append({'tipo': 'info_meta', 'descripcion': 'Período', 'valor': f"{mes:02d}/{anio}"})

    # Ingresos
    reporte.append({'tipo': 'seccion', 'descripcion': 'VENTAS / INGRESOS', 'monto': None})
    reporte.append({'tipo': 'item', 'descripcion': 'Salon', 'monto': total_ingresos})
    reporte.append({'tipo': 'item', 'descripcion': 'Delivery', 'monto': 0})
    reporte.append({'tipo': 'item', 'descripcion': 'Distribuidora/Otros', 'monto': 0})
    reporte.append({'tipo': 'total', 'descripcion': 'TOTAL INGRESOS', 'monto': total_ingresos})
    
    # Egresos
    reporte.append({'tipo': 'seccion', 'descripcion': 'COMPRAS / EGRESOS', 'monto': None})
    total_compras = 0
    for grupo in range(1, 8):
        df_grupo = df_gastos_agrupados[df_gastos_agrupados['orden_grupo'] == grupo]
        if not df_grupo.empty:
            subtotal_grupo = 0
            for _, row in df_grupo.iterrows():
                reporte.append({'tipo': 'item_gasto', 'descripcion': row['item'], 'monto': row['total']})
                subtotal_grupo += row['total']
            reporte.append({'tipo': 'subtotal', 'descripcion': 'Subtotal Grupo', 'monto': subtotal_grupo})
            total_compras += subtotal_grupo
    
    resultado_operativo = total_ingresos - total_compras
    reporte.append({'tipo': 'resultado', 'descripcion': 'RESULTADO OPERATIVO', 'monto': resultado_operativo})
    
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

def mostrar_tab_estado_resultado_granular(supabase, sucursales, mes_seleccionado, anio_seleccionado, sucursal_seleccionada):
    col_header, col_refresh = st.columns([4, 1])
    with col_header: st.subheader("📊 Estado de Resultado Granular")
    with col_refresh:
        if st.button("🔄 Refrescar", key="refresh_erg"):
            st.cache_data.clear()
            st.rerun()
    
    sucursal_id = sucursal_seleccionada['id'] if sucursal_seleccionada else None
    sucursal_nombre = sucursal_seleccionada['nombre'] if sucursal_seleccionada else "Todas las sucursales"
    
    df_mapeo = obtener_mapeo_erg(supabase)
    if df_mapeo.empty:
        st.warning("⚠️ **No hay mapeo configurado**")
        with st.expander("⚙️ Cargar Mapeo desde Excel"):
            archivo_mapeo = st.file_uploader("Selecciona el archivo Excel", type=['xlsx', 'xls'])
            if archivo_mapeo and st.button("📥 Cargar Mapeo"):
                res = cargar_mapeo_erg_desde_excel(supabase, archivo_mapeo)
                if res['exitoso']: st.success(res['mensaje']); st.cache_data.clear(); st.rerun()
                else: st.error(res['mensaje'])
        return
    
    with st.spinner("Cargando datos..."):
        df_gastos = obtener_gastos_db(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
        df_ingresos = obtener_ingresos_mensuales(supabase, mes_seleccionado, anio_seleccionado, sucursal_id)
    
    if df_gastos.empty:
        st.warning(f"⚠️ No hay gastos para el período seleccionado.")
        return
    
    total_ingresos = df_ingresos['monto'].sum() if not df_ingresos.empty else 0
    df_gastos_agrupados = agrupar_gastos_erg(df_gastos, df_mapeo)
    
    if df_gastos_agrupados.empty:
        st.warning("⚠️ No se pudieron agrupar los gastos según el mapeo.")
        subrubros_sin_mapeo = set(df_gastos['subrubro'].str.upper().str.strip()) - set(df_mapeo['subrubro'])
        if subrubros_sin_mapeo:
            with st.expander("🔍 Subrubros sin mapeo"):
                for s in sorted(subrubros_sin_mapeo): st.write(f"- {s}")
        return
    
    # Generar estructura de datos
    reporte = generar_estado_resultado_granular(df_gastos_agrupados, total_ingresos, sucursal_nombre, mes_seleccionado, anio_seleccionado)
    
    # RENDERIZAR REPORTE EJECUTIVO (HTML)
    st.markdown("---")
    html_reporte = renderizar_reporte_html(reporte, sucursal_nombre, mes_seleccionado, anio_seleccionado)
    st.markdown(html_reporte, unsafe_allow_html=True)
    
    # Botón Descargar Excel
    st.markdown("---")
    if st.button("📥 Descargar Reporte (Excel)", type="primary"):
        with st.spinner("Generando Excel..."):
            df_reporte = pd.DataFrame([{'Descripción': f['descripcion'], 'Monto': f['monto']} for f in reporte if f['tipo'] not in ['info_meta']])
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_reporte.to_excel(writer, sheet_name='Estado Resultado', index=False)
            buffer.seek(0)
            st.download_button("⬇️ Descargar Excel", data=buffer, file_name=f"ER_Granular_{sucursal_nombre}_{mes_seleccionado}_{anio_seleccionado}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def main(supabase):
    st.header("📊 P&L Simples - Informe Mensual")
    st.caption("v2.3 - Reporte Ejecutivo")
    
    meses = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
    col1, col2, col3 = st.columns(3)
    with col1: mes_sel = st.selectbox("📅 Mes", list(meses.keys()), format_func=lambda x: meses[x], index=datetime.now().month - 1)
    with col2: anio_sel = st.selectbox("📅 Año", range(datetime.now().year - 2, datetime.now().year + 1), index=2)
    with col3:
        try: sucursales = supabase.table("sucursales").select("*").execute().data
        except: sucursales = []
        sucursal_sel = st.selectbox("🏪 Sucursal", [None] + sucursales, format_func=lambda x: "Todas" if x is None else x['nombre'])
    
    tab1, tab2, tab3, tab4 = st.tabs(["📁 Importar", "📊 Análisis", "📈 Evolución", "📄 Reporte Granular"])
    with tab1: mostrar_tab_importacion(supabase, sucursales, mes_sel, anio_sel, sucursal_sel)
    with tab2: mostrar_tab_analisis(supabase, sucursales, mes_sel, anio_sel, sucursal_sel)
    with tab3: mostrar_tab_evolucion(supabase, sucursales, sucursal_sel)
    with tab4: mostrar_tab_estado_resultado_granular(supabase, sucursales, mes_sel, anio_sel, sucursal_sel)

if __name__ == "__main__":
    st.warning("⚠️ Ejecutar desde cajas_diarias.py")
