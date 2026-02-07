import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import zipfile
import plotly.express as px
from datetime import date
import random
import joblib
import requests
import numpy as np

@st.cache_resource
def cargar_recursos():
    model = joblib.load('modelo_incendios_rf.pkl')
    # Asegúrate de haber exportado estos archivos desde tu notebook de entrenamiento
    return model

model = cargar_recursos()

# Apply the cleaning function (reusing the one defined earlier in cell aZrz6PLmbLFb)
def limpiar_decimales(val):
    if pd.isna(val): return np.nan
    if isinstance(val, (int, float)): return float(val)
    val = str(val).replace(',', '.')
    try:
        return float(val)
    except:
        return np.nan

def fetch_aemet_values(station_id, fecha_fin):

    AEMET_API_KEY = st.secrets["AEMET_API_KEY"]

    fecha_ini = fecha_fin - pd.DateOffset(days=30)

    # Transform to 'YYYY-MM-DDTHH:MM:SSUTC' format
    fecha_fin_formatted = fecha_fin.strftime('%Y-%m-%dT%H:%M:%SUTC')
    fecha_ini_formatted = fecha_ini.strftime('%Y-%m-%dT%H:%M:%SUTC')
    
    #base_url = f"https://opendata.aemet.es/opendata/api/valores/climatologicos/valoresextremos/parametro/P/estacion/{station_id}"
    base_url = f"https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/fechaini/{fecha_ini_formatted}/fechafin/{fecha_fin_formatted}/estacion/{station_id}"
    headers = {
        'cache-control': "no-cache",
        'api_key': AEMET_API_KEY
    }

    try:
        # Step 1: Request the data URL
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        res_json = response.json()
        
        if res_json['estado'] == 200:
            data_url = res_json['datos']
            # Step 2: Download the actual data from the provided link
            data_response = requests.get(data_url)
            extremes_data = data_response.json()
            return extremes_data
        else:
            print(f"Error AEMET: {res_json['descripcion']}")
            return None
    except Exception as e:
        print(f"Error de conexión: {e}")
        return None

def predecir(datos):

    try:
        # Predict probability using the transformed NumPy array
        prediction_proba = model.predict_proba(datos)[0][1]
        return round(prediction_proba * 100, 2)
    except Exception as e:
        print(f"Error during prediction: {e}")
        return 0.0

# ------------------------------------------------------
# 1. CONFIGURACIÓN DE LA PÁGINA
# ------------------------------------------------------
st.set_page_config(
    page_title="Monitor de Incendios Forestales",
    page_icon="🔥",
    layout="wide"
)

st.sidebar.title("Menú")
pagina = st.sidebar.radio(
    "Selecciona una opción",
    ("Inicio", "Predicción")
)

model = joblib.load('modelo_incendios.pkl')

# ------------------------------------------------------
# 2. CARGA DE DATOS Y MAESTROS
# ------------------------------------------------------

if pagina == "Inicio":
    def cargar_maestros():
        """Carga los metadatos y devuelve diccionarios para traducir IDs a Texto."""
        archivo_meta = 'master_data.xlsx'
        maestros = {}
    
        try:
            df_meta = pd.read_excel(archivo_meta)
    
            # 1. Comunidades
            if 'idcomunidad' in df_meta.columns and 'comunidad' in df_meta.columns:
                df_com = df_meta[['idcomunidad', 'comunidad']].dropna()
                maestros['comunidades'] = dict(zip(df_com['idcomunidad'], df_com['comunidad']))
    
            # 2. Provincias
            if 'idprovincia' in df_meta.columns and 'provincia' in df_meta.columns:
                df_prov = df_meta[['idprovincia', 'provincia']].dropna()
                maestros['provincias'] = dict(zip(df_prov['idprovincia'], df_prov['provincia']))
    
            # 3. Causas (CORREGIDO)
            # Usamos 'causa' y 'causa_label' porque así se llaman en tu Excel master_data
            if 'causa' in df_meta.columns and 'causa_label' in df_meta.columns:
                df_causa = df_meta[['causa', 'causa_label']].dropna()
                # ¡Aquí estaba el error! Usamos las mismas columnas que acabamos de leer
                maestros['causas'] = dict(zip(df_causa['causa'], df_causa['causa_label']))
    
        except FileNotFoundError:
            st.warning(f"⚠️ No se encuentra '{archivo_meta}'. Se verán solo códigos numéricos.")
            return {}
        except Exception as e:
            st.warning(f"⚠️ Error leyendo metadatos: {e}")
            return {}
        
        return maestros
    
    @st.cache_data
    def cargar_datos():
        archivo_zip = 'fires-all.csv.zip' 
        
        try:
            # 1. Cargamos diccionarios
            diccionarios = cargar_maestros()
            
            with zipfile.ZipFile(archivo_zip) as z:
                archivos_csv = [f for f in z.namelist() if f.endswith('.csv') and '__MACOSX' not in f]
                
                if not archivos_csv:
                    return pd.DataFrame()
    
                with z.open(archivos_csv[0]) as f:
                    df = pd.read_csv(f, parse_dates=['fecha'], index_col='fecha')
                    
                    # --- TRADUCCIÓN ROBUSTA (Conversion de Tipos) ---
                    # Convertimos a numérico antes de mapear para evitar errores de tipo (texto vs numero)
                    
                    # 1. COMUNIDADES
                    if 'idcomunidad' in df.columns:
                        # Forzamos a numero, los errores se vuelven NaN
                        df['idcomunidad'] = pd.to_numeric(df['idcomunidad'], errors='coerce')
                        if 'comunidades' in diccionarios:
                            df['nombre_comunidad'] = df['idcomunidad'].map(diccionarios['comunidades'])
                            # Rellenamos los que no crucen con el ID original
                            df['nombre_comunidad'] = df['nombre_comunidad'].fillna(df['idcomunidad'].astype(str))
                    else:
                        df['nombre_comunidad'] = "Desconocido"
    
                    # 2. PROVINCIAS
                    if 'idprovincia' in df.columns:
                        df['idprovincia'] = pd.to_numeric(df['idprovincia'], errors='coerce')
                        if 'provincias' in diccionarios:
                            df['nombre_provincia'] = df['idprovincia'].map(diccionarios['provincias'])
                            df['nombre_provincia'] = df['nombre_provincia'].fillna(df['idprovincia'].astype(str))
                    else:
                        df['nombre_provincia'] = "Desconocido"
    
                    # 3. CAUSAS
                    # IMPORTANTE: Revisa si tu columna en el CSV de incendios es 'causa' (general 1-6)
                    # o 'causa_desc' (detallada 200-400).
                    # Aquí intentamos usar 'causa' (general) primero porque coincide con tu master_data
                    col_causa_id = 'causa' 
                    
                    # Si no existe 'causa', probamos 'idcausa' o 'causa_desc'
                    if col_causa_id not in df.columns:
                         if 'idcausa' in df.columns: col_causa_id = 'idcausa'
                         elif 'causa_desc' in df.columns: col_causa_id = 'causa_desc'
    
                    if col_causa_id in df.columns:
                        df[col_causa_id] = pd.to_numeric(df[col_causa_id], errors='coerce')
                        if 'causas' in diccionarios:
                            df['causa_texto'] = df[col_causa_id].map(diccionarios['causas'])
                            df['causa_texto'] = df['causa_texto'].fillna("Causa " + df[col_causa_id].astype(str))
                        else:
                             df['causa_texto'] = df[col_causa_id]
                    else:
                        df['causa_texto'] = "No especificado"
    
                    # Conversión de numéricos para cálculos
                    cols_num = ['superficie', 'gastos', 'perdidas', 'lat', 'lng']
                    for col in cols_num:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    return df
                    
        except Exception as e:
            st.error(f"Error cargando datos: {e}")
            return pd.DataFrame()
    
    df = cargar_datos()
    
    if df.empty:
        st.info("Esperando datos. Asegúrate de tener 'fires-all.csv.zip' y 'master_data.xlsx'.")
        st.stop()
    
    # ------------------------------------------------------
    # 3. BARRA LATERAL (FILTROS)
    # ------------------------------------------------------
    st.sidebar.header("🔍 Filtros de Búsqueda")
    
    # A. Filtro por Años
    años = sorted(df.index.year.unique())
    min_year, max_year = st.sidebar.select_slider("Rango de años", options=años, value=(min(años), max(años)))
    df_filtrado = df[(df.index.year >= min_year) & (df.index.year <= max_year)]
    
    # B. Filtros Geográficos (USANDO LOS NOMBRES)
    # Comunidad
    lista_comunidades = ["Todas"] + sorted(df_filtrado['nombre_comunidad'].astype(str).unique().tolist())
    comunidad_sel = st.sidebar.selectbox("Comunidad Autónoma", lista_comunidades)
    
    if comunidad_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado['nombre_comunidad'] == comunidad_sel]
    
    # Provincia
    lista_provincias = ["Todas"] + sorted(df_filtrado['nombre_provincia'].astype(str).unique().tolist())
    provincia_sel = st.sidebar.selectbox("Provincia", lista_provincias)
    
    if provincia_sel != "Todas":
        df_filtrado = df_filtrado[df_filtrado['nombre_provincia'] == provincia_sel]
    
    # Municipio
    lista_municipios = ["Todos"] + sorted(df_filtrado['municipio'].astype(str).unique().tolist())
    municipio_sel = st.sidebar.selectbox("Municipio", lista_municipios)
    
    if municipio_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado['municipio'] == municipio_sel]
    
    # ------------------------------------------------------
    # 4. DASHBOARD 
    # ------------------------------------------------------
    st.title("🔥 Visualización de Incendios en España")
    st.markdown(f"Mostrando datos: **{min_year}** - **{max_year}**")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Incendios", f"{len(df_filtrado):,}")
    col2.metric("Superficie (ha)", f"{df_filtrado['superficie'].sum():,.2f}")
    col3.metric("Gastos Extinción", f"{df_filtrado['gastos'].fillna(0).sum():,.0f} €") 
    col4.metric("Pérdidas Económicas", f"{df_filtrado['perdidas'].fillna(0).sum():,.0f} €")
    
    st.divider()
    
    # --- MAPA ---
    st.subheader(f"📍 Mapa de incidentes")
    # Para el mapa, quitamos los que no tienen coordenadas
    df_mapa = df_filtrado.dropna(subset=['lat', 'lng'])
    
    if not df_mapa.empty:
        if len(df_mapa) > 2000:
            st.warning(f"⚠️ Hay {len(df_mapa)} puntos. Se muestran los primeros 1000 para optimizar.")
            df_mapa = df_mapa.head(1000) 
        
        centro = [df_mapa['lat'].mean(), df_mapa['lng'].mean()]
        m = folium.Map(location=centro, zoom_start=6)
    
        for i, row in df_mapa.iterrows():
            sup = row['superficie']
            color = "darkred" if sup > 50 else "orange" if sup > 10 else "green"
    
            # Popup
            html_popup = f"""
            <b>Muni:</b> {row.get('municipio', '')}<br>
            <b>Prov:</b> {row.get('nombre_provincia', '')}<br>
            <b>Sup:</b> {sup:.2f} ha<br>
            <b>Causa:</b> {row.get('causa_texto', 'N/A')}
            """
            
            folium.CircleMarker(
                location=[row['lat'], row['lng']],
                radius=4, 
                popup=folium.Popup(html_popup, max_width=200),
                color=color, fill=True, fill_opacity=0.7
            ).add_to(m)
    
        st_folium(m, width="100%", height=500)
    else:
        st.info("No hay datos con coordenadas para mostrar en el mapa.")
    
    st.divider()
    
    # --- GRÁFICOS ---
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("📈 Evolución Anual")
        df_anual = df_filtrado.resample('YE')['superficie'].sum().reset_index()
        if not df_anual.empty:
            st.plotly_chart(
                px.line(df_anual, x='fecha', y='superficie', markers=True), 
                use_container_width=True
            )
    
    with c2:
        st.subheader("📋 Causas")
        if 'causa_texto' in df_filtrado.columns:
            conteo = df_filtrado['causa_texto'].value_counts().reset_index()
            conteo.columns = ['Causa', 'Incidentes']
            st.plotly_chart(
                px.pie(conteo.head(10), values='Incidentes', names='Causa', hole=0.4), 
                use_container_width=True
            )
if pagina == "Predicción":
    st.title("📈 Predicción de Incendios")
    
    comunidad = st.sidebar.selectbox(
        "Comunidad Autónoma", 
        "Galicia",
        disabled=True  # Esto bloquea el widget
    )

    provincia = st.selectbox(
        "Provincia",
        "A Coruña",
        disabled=True
    )

    fecha_actual = st.date_input(
        "Fecha para calcular",
        value=date.today()
    )

    if st.button("Calcular"):
        with st.spinner('Obteniendo datos climáticos y calculando...'):
            fecha_fin = pd.to_datetime(fecha_actual)
    
            extremes_data_dict = fetch_aemet_values(1387,fecha_fin)

            if extremes_data_dict:
                df_extremes_formatted = pd.DataFrame(extremes_data_dict)
            
                # Limpieza de columnas
                cols_to_correct = ['tmed', 'prec', 'velmedia', 'hrMedia']
                for col in cols_to_correct:
                    if col in df_extremes_formatted.columns:
                        df_extremes_formatted[col] = df_extremes_formatted[col].apply(limpiar_decimales)
                
                # Recalcular features (asegúrate de que AEMET devuelva suficientes días para el rolling)
                df_extremes_formatted['lluvia_acum_30d'] = df_extremes_formatted['prec'].rolling(window=30, min_periods=1).sum()
                df_extremes_formatted['temp_media_30d'] = df_extremes_formatted['tmed'].rolling(window=30, min_periods=1).mean()
                df_extremes_formatted['viento_medio_7d'] = df_extremes_formatted['velmedia'].rolling(window=7, min_periods=1).mean()
                
                df_extremes_formatted['fecha'] = pd.to_datetime(df_extremes_formatted['fecha'])
                df_extremes_formatted['dia_del_ano'] = df_extremes_formatted['fecha'].dt.dayofyear
                df_extremes_formatted['mes'] = df_extremes_formatted['fecha'].dt.month

                # Define the desired order of columns
                desired_column_order = [
                    'mes', 'dia_del_ano',
                    'tmed', 'prec', 'velmedia', 'hrMedia',
                    'lluvia_acum_30d', 'temp_media_30d', 'viento_medio_7d'
                ]
                
                # Filter and reorder the DataFrame columns
                df_extremes_formatted = df_extremes_formatted[desired_column_order]
    
                # Realizar predicción real
                valor_predicho = predecir(df_extremes_formatted.head(0))
    
                # Mostrar resultados
                st.success("Predicción completada")
                
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric(label="Probabilidad de Incendio", value=f"{valor_predicho} %")
                
                with col_res2:
                    # Mostrar un semáforo visual según el riesgo
                    if valor_predicho < 20:
                        st.info("Riesgo Bajo")
                    elif valor_predicho < 50:
                        st.warning("Riesgo Moderado")
                    else:
                        st.error("Riesgo Alto")
            else:
                st.error("No se pudieron obtener datos de AEMET para esa fecha.")
    
            
            


