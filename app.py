import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import zipfile
import plotly.express as px

# ------------------------------------------------------
# 1. CONFIGURACIÓN DE LA PÁGINA
# ------------------------------------------------------
st.set_page_config(
    page_title="Monitor de Incendios Forestales",
    page_icon="🔥",
    layout="wide"
)

# ------------------------------------------------------
# 2. CARGA DE DATOS Y MAESTROS
# ------------------------------------------------------

# Función auxiliar para cargar el Excel de metadatos
def cargar_maestros():
    archivo_meta = 'master_data.xlsx' # ¡Ojo con las comillas!
    maestros = {}

    try:
        # Cargamos el excel (asegúrate que las cabeceras del Excel coincidan con estos nombres)
        df_meta = pd.read_excel(archivo_meta)

        # 1. Comunidades
        df_com = df_meta[['idcomunidad', 'comunidad']].dropna()
        maestros['comunidades'] = dict(zip(df_com['idcomunidad'], df_com['comunidad']))

        # 2. Provincias
        df_prov = df_meta[['idprovincia', 'provincia']].dropna()
        maestros['provincias'] = dict(zip(df_prov['idprovincia'], df_prov['provincia']))

        # 3. Causas
        # Nota: Asumo que en el Excel las columnas se llaman 'idcausa' y 'causa_desc'
        # Ajusta esto si tus cabeceras son diferentes
        df_causa = df_meta[['causa', 'causa_label']].dropna() 
        maestros['causas'] = dict(zip(df_causa['idcausa'], df_causa['causa_desc']))

    except FileNotFoundError:
        st.error(f"⚠️ No encuentro el archivo '{archivo_meta}'")
        return {}
    except Exception as e:
        # Si falla, no rompemos la app, solo devolvemos diccionarios vacíos
        st.warning(f"⚠️ No se pudieron cargar las etiquetas: {e}")
        return {}
    
    return maestros

@st.cache_data
def cargar_datos():
    archivo_zip = 'fires-all.csv.zip' 
    
    try:
        # 1. Primero cargamos los diccionarios de traducción
        diccionarios = cargar_maestros()
        
        with zipfile.ZipFile(archivo_zip) as z:
            archivos_csv = [f for f in z.namelist() if f.endswith('.csv') and '__MACOSX' not in f]
            
            if not archivos_csv:
                return pd.DataFrame()

            with z.open(archivos_csv[0]) as f:
                df = pd.read_csv(f, parse_dates=['fecha'], index_col='fecha')
                
                # --- APLICAMOS LA TRADUCCIÓN (CRUCE DE DATOS) ---
                
                # Traducir Comunidades
                if 'idcomunidad' in df.columns and 'comunidades' in diccionarios:
                    df['nombre_comunidad'] = df['idcomunidad'].map(diccionarios['comunidades']).fillna("Desconocido")
                else:
                    df['nombre_comunidad'] = df['idcomunidad'] # Si falla, dejamos el ID

                # Traducir Provincias
                if 'idprovincia' in df.columns and 'provincias' in diccionarios:
                    df['nombre_provincia'] = df['idprovincia'].map(diccionarios['provincias']).fillna("Desconocido")
                else:
                    df['nombre_provincia'] = df['idprovincia']

                # Traducir Causas (Asumiendo que la columna de IDs en el CSV es 'causa_desc' o similar)
                # Revisa cual es la columna numérica de causas en tu CSV de incendios
                col_causa_id = 'causa_desc' # <--- CAMBIA ESTO si tu columna de ID de causa tiene otro nombre
                
                if col_causa_id in df.columns and 'causas' in diccionarios:
                    # Nos aseguramos que sea numérico para que coincida con el diccionario
                    df[col_causa_id] = pd.to_numeric(df[col_causa_id], errors='coerce')
                    df['causa_texto'] = df[col_causa_id].map(diccionarios['causas']).fillna("No especificado")
                
                # Conversión de numéricos
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
    st.stop()

# ------------------------------------------------------
# 3. BARRA LATERAL (FILTROS ACTUALIZADOS)
# ------------------------------------------------------
st.sidebar.header("🔍 Filtros de Búsqueda")

# A. Filtro por Años
años = sorted(df.index.year.unique())
min_year, max_year = st.sidebar.select_slider("Rango de años", options=años, value=(min(años), max(años)))
df_filtrado = df[(df.index.year >= min_year) & (df.index.year <= max_year)]

# B. Filtros Geográficos (USANDO LOS NOMBRES, NO LOS IDs)
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
st.markdown(f"Datos: **{min_year}** - **{max_year}**")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Incendios", f"{len(df_filtrado):,}")
col2.metric("Superficie (ha)", f"{df_filtrado['superficie'].sum():,.2f}")
col3.metric("Gastos Extinción", f"{df_filtrado['gastos'].fillna(0).sum():,.0f} €") 
col4.metric("Pérdidas Económicas", f"{df_filtrado['perdidas'].fillna(0).sum():,.0f} €")

st.divider()

# --- MAPA ---
st.subheader(f"📍 Mapa de incidentes")
df_mapa = df_filtrado.dropna(subset=['lat', 'lng'])

if not df_mapa.empty:
    if len(df_mapa) > 2000:
        st.warning(f"⚠️ Mostrando los primeros 1000 incidentes de {len(df_mapa)} encontrados.")
        df_mapa = df_mapa.head(1000) 
    
    centro = [df_mapa['lat'].mean(), df_mapa['lng'].mean()]
    m = folium.Map(location=centro, zoom_start=6)

    for i, row in df_mapa.iterrows():
        # Color según gravedad
        sup = row['superficie']
        color = "darkred" if sup > 50 else "orange" if sup > 10 else "green"

        # Popup: Usamos los nombres reales
        html_popup = f"""
        <b>Muni:</b> {row.get('municipio', '')}<br>
        <b>Prov:</b> {row.get('nombre_provincia', '')}<br>
        <b>Sup:</b> {sup:.2f} ha<br>
        <b>Causa:</b> {row.get('causa_texto', 'N/A')}
        """
        
        folium.CircleMarker(
            location=[row['lat'], row['lng']],
            radius=4, popup=folium.Popup(html_popup, max_width=200),
            color=color, fill=True, fill_opacity=0.7
        ).add_to(m)

    st_folium(m, width="100%", height=500)
else:
    st.info("No hay datos geográficos para mostrar.")

st.divider()

# --- GRÁFICOS ---
c1, c2 = st.columns(2)

with c1:
    st.subheader("📈 Evolución Anual")
    df_anual = df_filtrado.resample('YE')['superficie'].sum().reset_index()
    if not df_anual.empty:
        st.plotly_chart(px.line(df_anual, x='fecha', y='superficie', markers=True), use_container_width=True)

with c2:
    st.subheader("📋 Causas")
    # Usamos la columna traducida 'causa_texto'
    if 'causa_texto' in df_filtrado.columns:
        conteo = df_filtrado['causa_texto'].value_counts().reset_index()
        conteo.columns = ['Causa', 'Incidentes']
        st.plotly_chart(px.pie(conteo.head(10), values='Incidentes', names='Causa', hole=0.4), use_container_width=True)
