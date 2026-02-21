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
    model = joblib.load('modelo_incendios_completo.pkl')
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
        st.write("predecir")
        expected_features = model['modelo'].feature_names_in_

        for col in expected_features:
            if col not in datos.columns:
                st.write(col)
                datos[col] = 0

        datos = datos[expected_features]
        datos = datos.fillna(0)
        st.write("Columnas entrenamiento:", len(model["columnas"]))
        st.write("Columnas entrada:", len(datos.columns))
        # Predict probability using the transformed NumPy array
        prediction_proba = model['modelo'].predict_proba(datos)[0][1]
        st.write(prediction_proba)
        return round(prediction_proba * 100, 2)
    except Exception as e:
        print(f"Error during prediction: {e}")
        st.error(e)
        return 0.0

def carga_datos_earth(municipio):
    df_earth = pd.read_excel("municipios_earth.xlsx")   
    return df_earth[df_earth['municipio']==municipio]     
        
        
def new_features(df):
  
    for col in df.columns:
        if col != 'superficie':
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '.'),
                errors='coerce'
            )

    df['regla_30_30_30'] = (
        (df['tmax'] >= 30) &
        (df['hrMedia'] <= 30) &
        (df['velmedia'] >= 30)
    ).astype(int)

    # 2. Índices de propagación del fuego
    df['temp_x_viento'] = df['tmax'] * df['velmedia']  # Factor de propagación
    df['sequedad'] = 100 - df['hrMedia']  # Sequedad del aire
    df['viento_seco'] = df['velmedia'] * df['sequedad']  # Viento seco

    # 3. Variaciones térmicas y de presión
    df['rango_termico'] = df['tmax'] - df['tmin']  # Variación térmica diaria
    df['rango_presion'] = df['presMax'] - df['presMin']  # Variación de presión

    # 4. Medias móviles 7 días (tendencias recientes)
    for col in ['tmax', 'tmin', 'prec', 'tmed', 'velmedia', 'hrMedia', 'sol', 'presMax']:
        if col in df.columns:
            df[f'{col}_7d'] = df[col].rolling(7, min_periods=1).mean()

    # 5. Indicadores de sequía
    df['dia_seco'] = (df['prec'] < 1).astype(int)
    df['lluvia_semana'] = df['prec'].rolling(7, min_periods=1).sum()
    df['lluvia_mes'] = df['prec'].rolling(30, min_periods=1).sum()
    df['deficit_lluvia'] = (5 - df['prec']).clip(lower=0)
    # 6. Interacciones importantes
    df['temp_humedad'] = df['tmax'] * df['hrMedia']  # Interacción temperatura-humedad
    df['presion_baja'] = (df['presMin'] < 1010).astype(int)  # Indicador presión baja

    # 7. Estacionalidad
    df['mes'] = df.index.month
    df['dia_año'] = df.index.dayofyear
    df['es_verano'] = df['mes'].isin([6, 7, 8, 9]).astype(int)

    print(f"\n✓ Total de variables en el dataset: {len(df.columns)}")

    # 8 Sistema Canadiense - estándar internacional

    def calcular_fwi_simple(temp, hr, viento, prec):
        """Fire Weather Index simplificado"""
        # FFMC - Fine Fuel Moisture
        mo = 147.2 * (101 - hr) / (59.5 + hr)
        ffmc = 59.5 * (250 - mo) / (147.2 + mo) if mo < 250 else 101

        # ISI - Initial Spread Index
        fw = np.exp(0.05039 * viento)
        fm = 147.2 * (101 - ffmc) / (59.5 + ffmc)
        isi = fw * np.exp(0.000055 * fm)

        # FWI simplificado
        fwi = 0.1 * isi * (50 + temp)  # Versión simplificada

        return max(0, min(fwi, 100))

    # Aplicar
    df['fwi'] = df.apply(
        lambda row: calcular_fwi_simple(
          row['tmax'] if pd.notna(row['tmax']) else 20,
          row['hrMedia'] if pd.notna(row['hrMedia']) else 50,
          row['velmedia'] if pd.notna(row['velmedia']) else 10,
          row['prec'] if pd.notna(row['prec']) else 0
        ), axis=1
    )

    # 9 Persistencia de condiciones peligrosas
    df['dias_sin_lluvia'] = (df['prec'] < 1).groupby(
        (df['prec'] >= 1).cumsum()
    ).cumsum()

    df['dias_calor'] = (df['tmax'] > 30).groupby(
        (df['tmax'] <= 30).cumsum()
    ).cumsum()

    df['dias_viento'] = (df['velmedia'] > 20).groupby(
        (df['velmedia'] <= 20).cumsum()
    ).cumsum()

    # Triple amenaza
    df['triple_amenaza'] = (
        (df['dias_sin_lluvia'] >= 7) &
        (df['dias_calor'] >= 3) &
        (df['dias_viento'] >= 2)
    ).astype(int)  

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


# ------------------------------------------------------
# 2. CARGA DE DATOS Y MAESTROS
# ------------------------------------------------------

if pagina == "Inicio":
    def cargar_maestros():
        """Carga los metadatos y devuelve diccionarios para traducir IDs a Texto."""
        archivo_meta = 'master_data_new.xlsx'
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
            print(diccionarios)
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

    lista_municipios = [
        "ABEGONDO","AMES","ARANGA","ARES","ARTEIXO","ARZÚA","BAÑA, A",
        "BETANZOS","BOIMORTO","BOIRO","BOQUEIXÓN-CASANOVA","BRIÓN",
        "CABANA DE BERGANTIÑOS","CAMARIÑAS","CAMBRE","CAPELA, A",
        "CARBALLO","CARNOTA","CARRAL","CEDEIRA","CEE","CERCEDA",
        "CERDIDO","CESURAS","COIRÓS","CORISTANCO","CORUÑA, A",
        "CULLEREDO","CURTIS","DODRO","DUMBRÍA","FENE","FERROL",
        "FISTERRA","FRADES","IRIXOA","LAXE","LARACHA, A","LOUSAME",
        "MALPICA DE BERGANTIÑOS","MAÑÓN","MAZARICOS","MELIDE",
        "MESÍA","MOECHE","MONFERO","MUXÍA","MUROS","NARÓN","NEDA",
        "NEGREIRA","NOIA","OLEIROS","ORDES","OROSO","ORTIGUEIRA",
        "OUTES","OZA DOS RÍOS","PADERNE","PADRÓN","PINO, O",
        "POBRA DO CARAMIÑAL, A","PONTECESO","PONTEDEUME",
        "PONTES DE GARCIA RODRIGUEZ, AS","PORTO DO SON","RIANXO",
        "RIBEIRA","ROIS","SADA","SAN SADURNIÑO","SANTA COMBA",
        "SANTIAGO DE COMPOSTELA","SANTISO","SOBRADO","SOMOZAS, AS",
        "TEO","TOQUES","TORDOIA","TOURO","TRAZO","VALDOVIÑO",
        "VAL DO DUBRA","VEDRA","VILASANTAR","VILARMAIOR",
        "VIMIANZO","ZAS","CARIÑO","OZA-CESURAS","OTRA PROVINCIA"
    ]

    municipio = st.selectbox(
        "Municipio",
        sorted(lista_municipios)
    )

    fecha_actual = st.date_input(
        "Fecha para calcular",
        value=date.today()
    )

    # ------------------------------------------------------
    # AEMET STATIONS POR MUNICIPIO (A CORUÑA)
    # ------------------------------------------------------
    
    station_por_municipio = {
    
        # Santiago area
        "SANTIAGO DE COMPOSTELA": 1475,
        "AMES": 1475,
        "TEO": 1475,
        "BRIÓN": 1475,
        "VEDRA": 1475,
        "BOQUEIXÓN-CASANOVA": 1475,
        "VAL DO DUBRA": 1475,
    
        # A Coruña city / coast
        "CORUÑA, A": 1387,
        "ARTEIXO": 1387,
        "CAMBRE": 1387,
        "CULLEREDO": 1387,
        "OLEIROS": 1387,
        "SADA": 1387,
        "CARRAL": 1387,
    
        # Ferrol area
        "FERROL": 1111,
        "NARÓN": 1111,
        "NEDA": 1111,
        "FENE": 1111,
        "SAN SADURNIÑO": 1111,
        "VALDOVIÑO": 1111,
        "MOECHE": 1111,
        "SOMOZAS, AS": 1111,
    
        # Bergantiños / Costa da Morte
        "CARBALLO": 1428,
        "MALPICA DE BERGANTIÑOS": 1428,
        "PONTECESO": 1428,
        "CABANA DE BERGANTIÑOS": 1428,
        "CORISTANCO": 1428,
        "LAXE": 1428,
        "ZAS": 1428,
        "VIMIANZO": 1428,
        "CAMARIÑAS": 1428,
        "CEE": 1428,
        "FISTERRA": 1428,
        "MUXÍA": 1428,
        "DUMBRÍA": 1428,
        "CARNOTA": 1428,
    
        # Interior
        "ARZÚA": 1505,
        "MELIDE": 1505,
        "BOIMORTO": 1505,
        "FRADES": 1505,
        "MESÍA": 1505,
        "SOBRADO": 1505,
        "TOURO": 1505,
        "SANTISO": 1505,
        "CURTIS": 1505,
        "VILASANTAR": 1505,
        "IRIXOA": 1505,
        "MONFERO": 1505,
        "ARANGA": 1505,
        "BETANZOS": 1505,
        "PADERNE": 1505,
        "COIRÓS": 1505,
        "CESURAS": 1505,
        "OZA DOS RÍOS": 1505,
        "OZA-CESURAS": 1505,
        "VILARMAIOR": 1505,
        "MAÑÓN": 1505,
        "CARIÑO": 1505,
        "ORTIGUEIRA": 1505,
    
        # Default fallback
        "OTRA PROVINCIA": 1387
    }

    if st.button("Calcular"):
        with st.spinner('Obteniendo datos climáticos y calculando...'):
            fecha_fin = pd.to_datetime(fecha_actual)
    
            station_id = station_por_municipio.get(municipio, 1387)
            extremes_data_dict = fetch_aemet_values(station_id, fecha_fin)

            if extremes_data_dict:
                df_extremes_formatted = pd.DataFrame(extremes_data_dict)
                df_extremes_formatted["municipio"] = municipio
                
                df_earth = carga_datos_earth(municipio)
                
                df_extremes_formatted["elevation"] = df_earth["elevation"].values[0]
                df_extremes_formatted["slope"] = df_earth["slope"].values[0]
                df_extremes_formatted["ndvi"] = df_earth["ndvi"].values[0]
                
                if 'fecha' in df_extremes_formatted.columns:
                    df_extremes_formatted.set_index('fecha', inplace=True)
                df_extremes_formatted.index = pd.to_datetime(df_extremes_formatted.index)

                st.write(df_extremes_formatted.tail(1))
                
                new_features(df_extremes_formatted)

                st.write(df_extremes_formatted.tail(1))
                
                  # Define the desired order of columns
                desired_column_order = ['tmed', 'tmin', 'tmax', 'prec', 'dir', 'velmedia',
                       'racha', 'sol', 'presMax', 'presMin', 'hrMedia', 'elevation', 'slope',
                       'ndvi', 'regla_30_30_30', 'temp_x_viento',
                       'sequedad', 'viento_seco', 'rango_termico', 'rango_presion', 'tmax_7d',
                       'tmin_7d', 'tmed_7d', 'prec_7d', 'velmedia_7d', 'hrMedia_7d', 'sol_7d',
                       'presMax_7d', 'dia_seco', 'lluvia_semana', 'lluvia_mes',
                       'deficit_lluvia', 'temp_humedad', 'presion_baja', 'mes', 'dia_año',
                       'es_verano', 'fwi', 'dias_sin_lluvia', 'dias_calor', 'dias_viento',
                       'triple_amenaza']
                
                # Filter and reorder the DataFrame columns
                df_extremes_formatted = df_extremes_formatted[desired_column_order]

                st.write(df_extremes_formatted.tail(1))
                
                # Realizar predicción real
                valor_predicho = predecir(df_extremes_formatted.tail(1))

                st.write(valor_predicho)
    
                # Mostrar resultados
                st.success("Predicción completada")
                
                # Mostramos el porcentaje directamente en el mensaje de estado
                if valor_predicho < 20:
                    st.info(f"Riesgo Bajo: {valor_predicho}% de probabilidad")
                elif valor_predicho < 50:
                    st.warning(f"Riesgo Moderado: {valor_predicho}% de probabilidad")
                else:
                    st.error(f"Riesgo Alto: {valor_predicho}% de probabilidad")
            else:
                st.error("No se pudieron obtener datos de AEMET para esa fecha.")
    
            
            


