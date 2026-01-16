"""
Módulo de Transferencias Bancarias
Integrado al Sistema de Cajas Diarias
"""

import streamlit as st
import os
from datetime import datetime, timedelta
import pandas as pd

SUPABASE_BUCKET = "transferencias"

def main(supabase):
    """
    Función principal del módulo de transferencias
    
    Args:
        supabase: Cliente de Supabase (pasado desde cajas_diarias.py)
    """
    
    # Imports condicionales (solo se cargan cuando se usa el módulo)
    try:
        import fitz  # PyMuPDF
        import requests
        from openpyxl import Workbook
        import tempfile
        import zipfile
        from io import BytesIO
        import re
    except ImportError as e:
        st.error(f"❌ Falta instalar dependencias: {str(e)}")
        st.info("""
        **Para usar este módulo, agrega a requirements.txt:**
        ```
        PyMuPDF
        requests
        openpyxl
        ```
        """)
        return
    
    if not supabase:
        st.error("❌ No se pudo conectar a Supabase.")
        return
    
    # Título del módulo
    st.markdown("### 💸 Gestión de Transferencias Bancarias")
    st.markdown("---")
    
    # Tabs principales
    tab1, tab2 = st.tabs(["📤 Procesar PDF", "🔍 Consultar Transferencias"])
    
    # ============================================================================
    # TAB 1: PROCESAR PDF
    # ============================================================================
    with tab1:
        st.markdown("#### Sube el PDF con el histórico de transferencias")
        
        uploaded_file = st.file_uploader(
            "Selecciona el archivo PDF",
            type=['pdf'],
            key="upload_pdf_transferencias"
        )
        
        if uploaded_file is not None:
            with st.spinner('🔄 Procesando PDF...'):
                # Directorios temporales
                temp_dir = tempfile.mkdtemp()
                output_dir = os.path.join(temp_dir, "transferencias")
                os.makedirs(output_dir, exist_ok=True)
                
                # Guardar archivo
                input_path = os.path.join(temp_dir, uploaded_file.name)
                with open(input_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Abrir PDF
                doc = fitz.open(input_path)
                
                # Excel
                wb = Workbook()
                ws = wb.active
                ws.title = "Resumen Transferencias"
                ws.append(["OP", "Razón social / Nombre", "CUIT", "Monto", "URL"])
                
                total = 0.0
                cantidad = 0
                resultados = []
                errores = []
                
                # Fecha y usuario
                now = datetime.now()
                year = now.strftime("%Y")
                month = now.strftime("%m")
                usuario_upload = st.session_state.get('email', 'sin_usuario')
                
                # Procesar páginas
                progress_bar = st.progress(0)
                total_pages = len(doc)
                
                for page_num in range(total_pages):
                    page = doc.load_page(page_num)
                    text = page.get_text("text")
                    
                    # Búsqueda de OP
                    op_number = None
                    op_digits = re.search(r"Comentarios\s+OP\s*(\d+)", text, re.I)
                    if op_digits:
                        op_number = op_digits.group(1)
                    else:
                        if re.search(r"Comentarios\s+OP\s+(?!\d)", text, re.I):
                            op_number = "OP sin numero"
                    
                    # CUIT
                    cuit_match = re.search(r"([0-9]{2}-[0-9]{8}-[0-9])\s*CUIT/CUIL", text)
                    if not cuit_match:
                        cuit_match = re.search(r"CUIT/CUIL\s+([0-9\-]+)", text)
                    cuit = cuit_match.group(1).strip() if cuit_match else None
                    
                    # Razón social
                    razon_match = re.search(r"Razón social/Nombre\s*\n([^\n]+)", text)
                    razon_social = razon_match.group(1).strip() if razon_match else None
                    
                    # Importe
                    importe_match = re.search(r"Pago a proveedores\s*\n\$\s?([0-9\.\,]+)", text)
                    if importe_match:
                        importe_str = importe_match.group(1).replace(".", "").replace(",", ".")
                        try:
                            importe = float(importe_str)
                        except ValueError:
                            importe = 0.0
                    else:
                        importe = 0.0
                    
                    # Si tenemos datos, crear PDF y subir
                    if op_number and cuit and razon_social:
                        filename = f"OP_{op_number}__{cuit}__{razon_social}.pdf"
                        filename = filename.replace("/", "-").replace("\\", "-")
                        output_path = os.path.join(output_dir, filename)
                        
                        # Crear PDF individual
                        new_doc = fitz.open()
                        new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                        new_doc.save(output_path)
                        new_doc.close()
                        
                        # Subir a Supabase
                        archivo_url = None
                        try:
                            storage_path = f"{year}/{month}/{filename}"
                            
                            with open(output_path, 'rb') as f:
                                file_data = f.read()
                            
                            # Intentar subir con upsert (sobrescribe si existe)
                            try:
                                supabase.storage.from_(SUPABASE_BUCKET).upload(
                                    path=storage_path,
                                    file=file_data,
                                    file_options={"content-type": "application/pdf", "upsert": "true"}
                                )
                            except Exception as upload_error:
                                # Si falla con upsert, intentar eliminar y subir de nuevo
                                try:
                                    supabase.storage.from_(SUPABASE_BUCKET).remove([storage_path])
                                    supabase.storage.from_(SUPABASE_BUCKET).upload(
                                        path=storage_path,
                                        file=file_data,
                                        file_options={"content-type": "application/pdf"}
                                    )
                                except:
                                    # Si todo falla, al menos obtenemos la URL
                                    pass
                            
                            archivo_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(storage_path)
                            
                            # Usar upsert en lugar de insert para actualizar si ya existe
                            # Esto evita errores de duplicados en la tabla
                            supabase.table('transferencias').upsert({
                                'op_number': op_number,
                                'cuit': cuit,
                                'razon_social': razon_social,
                                'monto': float(importe),
                                'archivo_nombre': filename,
                                'archivo_url': archivo_url,
                                'bucket_path': storage_path,
                                'usuario_upload': usuario_upload
                            }, on_conflict='op_number,cuit').execute()
                            
                        except Exception as e:
                            errores.append(f"OP {op_number} - Error: {str(e)}")
                            archivo_url = "Error"
                        
                        ws.append([op_number, razon_social, cuit, importe, archivo_url or "Local"])
                        total += importe
                        cantidad += 1
                        
                        resultados.append({
                            'op': op_number,
                            'razon_social': razon_social,
                            'cuit': cuit,
                            'importe': importe,
                            'archivo': filename,
                            'url': archivo_url
                        })
                    else:
                        errores.append(f"Página {page_num + 1} - Faltan datos")
                    
                    progress_bar.progress((page_num + 1) / total_pages)
                
                # Totales en Excel
                ws.append([])
                ws.append(["", "Total de transferencias:", "", cantidad, ""])
                ws.append(["", "Importe total:", "", f"${total:,.2f}", ""])
                
                excel_path = os.path.join(output_dir, "Resumen_Transferencias.xlsx")
                wb.save(excel_path)
                
                doc.close()
                progress_bar.empty()
                
                # Resultados
                st.success(f"✅ Procesamiento completado: {cantidad} transferencias")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Transferencias", cantidad)
                with col2:
                    st.metric("Importe Total", f"${total:,.2f}")
                
                # Tabla
                if resultados:
                    st.markdown("#### 📊 Detalle de Transferencias")
                    df = pd.DataFrame(resultados)
                    df['importe_formateado'] = df['importe'].apply(lambda x: f"${x:,.2f}")
                    
                    display_df = df[['op', 'cuit', 'razon_social', 'importe_formateado']].rename(columns={
                        'op': 'OP',
                        'cuit': 'CUIT',
                        'razon_social': 'Razón Social',
                        'importe_formateado': 'Importe'
                    })
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # Errores
                if errores:
                    with st.expander(f"⚠️ {len(errores)} errores"):
                        for error in errores:
                            st.warning(error)
                
                # Descargas
                st.markdown("#### 📥 Descargas")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # ZIP
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for filename in os.listdir(output_dir):
                            filepath = os.path.join(output_dir, filename)
                            zip_file.write(filepath, filename)
                    
                    zip_buffer.seek(0)
                    
                    st.download_button(
                        label="⬇️ Descargar ZIP",
                        data=zip_buffer,
                        file_name=f"transferencias_{year}_{month}.zip",
                        mime="application/zip"
                    )
                
                with col2:
                    # Excel
                    with open(excel_path, 'rb') as f:
                        st.download_button(
                            label="📊 Descargar Excel",
                            data=f,
                            file_name="Resumen_Transferencias.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
        
        else:
            st.info("👆 Sube un archivo PDF para comenzar")
    
    
    # ============================================================================
    # TAB 2: CONSULTAR TRANSFERENCIAS
    # ============================================================================
    with tab2:
        st.markdown("#### Busca y descarga comprobantes de transferencias")
        
        # Filtros en columnas
        col1, col2, col3 = st.columns(3)
        
        with col1:
            buscar_op = st.text_input("🔢 Número de OP", key="buscar_op_tab2")
        with col2:
            buscar_cuit = st.text_input("🆔 CUIT", key="buscar_cuit_tab2")
        with col3:
            buscar_razon = st.text_input("🏢 Razón Social", key="buscar_razon_tab2")
        
        # Fechas y montos
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            fecha_desde = st.date_input("📅 Desde", value=datetime.now() - timedelta(days=30), key="fecha_desde_tab2")
        with col2:
            fecha_hasta = st.date_input("📅 Hasta", value=datetime.now(), key="fecha_hasta_tab2")
        with col3:
            monto_min = st.number_input("💵 Monto mín", value=0.0, step=1000.0, key="monto_min_tab2")
        with col4:
            monto_max = st.number_input("💵 Monto máx", value=0.0, step=1000.0, key="monto_max_tab2")
        
        # Botón buscar
        if st.button("🔍 Buscar", type="primary", key="btn_buscar_tab2"):
            with st.spinner('Buscando...'):
                try:
                    query = supabase.table('transferencias').select('*')
                    
                    if fecha_desde:
                        query = query.gte('fecha_upload', fecha_desde.isoformat())
                    if fecha_hasta:
                        query = query.lte('fecha_upload', fecha_hasta.isoformat())
                    if buscar_op:
                        query = query.ilike('op_number', f'%{buscar_op}%')
                    if buscar_cuit:
                        query = query.ilike('cuit', f'%{buscar_cuit}%')
                    if buscar_razon:
                        query = query.ilike('razon_social', f'%{buscar_razon}%')
                    if monto_min > 0:
                        query = query.gte('monto', monto_min)
                    if monto_max > 0:
                        query = query.lte('monto', monto_max)
                    
                    query = query.order('fecha_upload', desc=True)
                    response = query.execute()
                    datos = response.data
                    
                    if datos:
                        df = pd.DataFrame(datos)
                        df['fecha_upload'] = pd.to_datetime(df['fecha_upload']).dt.strftime('%Y-%m-%d %H:%M')
                        df['monto_formateado'] = df['monto'].apply(lambda x: f"${float(x):,.2f}")
                        
                        # Métricas
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("📄 Total", len(df))
                        with col2:
                            st.metric("💰 Monto Total", f"${df['monto'].astype(float).sum():,.2f}")
                        with col3:
                            st.metric("📊 Promedio", f"${df['monto'].astype(float).mean():,.2f}")
                        
                        st.markdown("---")
                        
                        # Tabla
                        st.markdown("#### 📋 Resultados")
                        display_df = df[['op_number', 'cuit', 'razon_social', 'monto_formateado', 'fecha_upload']].copy()
                        display_df.columns = ['OP', 'CUIT', 'Razón Social', 'Monto', 'Fecha']
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                        
                        st.markdown("---")
                        
                        # Descargar individual
                        st.markdown("#### 📥 Descargar comprobante individual")
                        opciones = [f"OP {row['op_number']} - {row['razon_social']}" for _, row in df.iterrows()]
                        seleccion = st.selectbox("Selecciona una transferencia", opciones, key="selector_individual")
                        
                        idx = opciones.index(seleccion)
                        url_seleccionada = df.iloc[idx]['archivo_url']
                        
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            st.link_button(
                                "🔗 Abrir PDF",
                                url_seleccionada,
                                type="primary",
                                use_container_width=True
                            )
                        with col2:
                            st.caption(f"📄 {df.iloc[idx]['archivo_nombre']}")
                        
                        st.markdown("---")
                        
                        # Descargar del día
                        st.markdown("#### 📦 Descarga rápida del día")
                        
                        fecha_descarga = st.date_input(
                            "Selecciona fecha",
                            value=datetime.now(),
                            key="fecha_zip_tab2"
                        )
                        
                        df_dia = df[pd.to_datetime(df['fecha_upload']).dt.date == fecha_descarga]
                        cant_dia = len(df_dia)
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            if cant_dia > 0:
                                st.info(f"📄 {cant_dia} transferencias para {fecha_descarga.strftime('%d/%m/%Y')}")
                            else:
                                st.warning("📭 No hay transferencias para esta fecha")
                        with col2:
                            st.metric("PDFs", cant_dia)
                        
                        if cant_dia > 0:
                            with st.spinner(f'Preparando {cant_dia} PDFs...'):
                                zip_buffer = BytesIO()
                                
                                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                    for idx, row in df_dia.iterrows():
                                        try:
                                            response = requests.get(row['archivo_url'], timeout=30)
                                            if response.status_code == 200:
                                                zip_file.writestr(row['archivo_nombre'], response.content)
                                        except:
                                            pass
                                
                                zip_buffer.seek(0)
                            
                            st.download_button(
                                label=f"⬇️ DESCARGAR {cant_dia} PDFs en ZIP",
                                data=zip_buffer.getvalue(),
                                file_name=f"transferencias_{fecha_descarga.strftime('%Y%m%d')}.zip",
                                mime="application/zip",
                                type="primary",
                                use_container_width=True,
                                key="download_zip_dia_tab2"
                            )
                        
                        st.markdown("---")
                        
                        # Exportar Excel y URLs
                        st.markdown("#### 💾 Exportar resultados")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # Excel
                            wb = Workbook()
                            ws = wb.active
                            ws.title = "Transferencias"
                            ws.append(['OP', 'CUIT', 'Razón Social', 'Monto', 'Fecha', 'URL'])
                            
                            for _, row in df.iterrows():
                                ws.append([
                                    row['op_number'],
                                    row['cuit'],
                                    row['razon_social'],
                                    float(row['monto']),
                                    row['fecha_upload'],
                                    row['archivo_url']
                                ])
                            
                            excel_buffer = BytesIO()
                            wb.save(excel_buffer)
                            excel_buffer.seek(0)
                            
                            st.download_button(
                                label="📊 Descargar Excel",
                                data=excel_buffer,
                                file_name=f"transferencias_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key="download_excel_tab2"
                            )
                        
                        with col2:
                            # URLs
                            urls_text = "\n".join([f"OP {row['op_number']}: {row['archivo_url']}" for _, row in df.iterrows()])
                            
                            st.download_button(
                                label="🔗 Descargar lista de URLs",
                                data=urls_text,
                                file_name=f"urls_{datetime.now().strftime('%Y%m%d')}.txt",
                                mime="text/plain",
                                use_container_width=True,
                                key="download_urls_tab2"
                            )
                    
                    else:
                        st.info("🔍 No se encontraron transferencias con los criterios seleccionados")
                        
                except Exception as e:
                    st.error(f"Error: {str(e)}")
