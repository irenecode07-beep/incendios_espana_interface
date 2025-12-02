# ------------------------------------------------------
# 0. IMPORTAR LIBRERIAS (tienen que estar en requirements.txt
# ------------------------------------------------------
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
# 2. CARGA DE DATOS
# ------------------------------------------------------
@st.cache_data
def cargar_datos():
    # Asegúrate de que este archivo existe en la misma carpeta
    archivo_zip = 'fires-all.csv.zip' 
    
    try:
        with zipfile.ZipFile(archivo_zip) as z:
            # Buscamos el primer archivo CSV dentro del ZIP ignorando carpetas de sistema
            archivos_csv = [f for f in z.namelist() if f.endswith('.csv') and '__MACOSX' not in f]
            
            if not archivos_csv:
                st.error("No se encontró ningún archivo .csv dentro del zip.")
                return pd.DataFrame()

            with z.open(archivos_csv[0]) as f:
                # Importante: parse_dates convierte la columna fecha a formato tiempo real
                df = pd.read_csv(f, parse_dates=['fecha'], index_col='fecha')
                
                # Aseguramos que las columnas numéricas no tengan valores nulos (NaN)
                cols_num = ['superficie', 'gastos', 'perdidas', 'lat', 'lng']
                for col in cols_num:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                return df
                
    except FileNotFoundError:
        st.error(f"No se encontró el archivo '{archivo_zip}'. Por favor verifica la ruta.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error inesperado: {e}")
        return pd.DataFrame()

df = cargar_datos()

if df.empty:
    st.warning("Esperando datos... Por favor asegúrate de tener el archivo 'fires-all.csv.zip' en la carpeta.")
    st.stop()

# ------------------------------------------------------
# 3. BARRA LATERAL (FILTROS)
# ------------------------------------------------------
st.sidebar.header("🔍 Filtros de Búsqueda")

# A. Filtro por Años
años_disponibles = sorted(df.index.year.unique())
min_year, max_year = st.sidebar.select_slider(
    "Rango de años",
    options=años_disponibles,
    value=(min(años_disponibles), max(años_disponibles))
)

# Aplicar filtro de año
df_filtrado = df[(df.index.year >= min_year) & (df.index.year <= max_year)]

# B. Filtros Geográficos (En Cascada)
# Comunidad
lista_comunidades = ["Todas"] + sorted(df_filtrado['idcomunidad'].dropna().unique().tolist())
comunidad_sel = st.sidebar.selectbox("Comunidad Autónoma", lista_comunidades)

if comunidad_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado['idcomunidad'] == comunidad_sel]

# Provincia
lista_provincias = ["Todas"] + sorted(df_filtrado['idprovincia'].dropna().unique().tolist())
provincia_sel = st.sidebar.selectbox("Provincia", lista_provincias)

if provincia_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado['idprovincia'] == provincia_sel]

# Municipio
lista_municipios = ["Todos"] + sorted(df_filtrado['municipio'].dropna().unique().tolist())
municipio_sel = st.sidebar.selectbox("Municipio", lista_municipios)

if municipio_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado['municipio'] == municipio_sel]

# ------------------------------------------------------
# 4. DASHBOARD PRINCIPAL
# ------------------------------------------------------
st.title("🔥 Visualización de Incendios en España")
st.markdown(f"Datos visualizados entre **{min_year}** y **{max_year}**")

# --- KPIs ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Incendios", f"{len(df_filtrado):,}")
col2.metric("Superficie (ha)", f"{df_filtrado['superficie'].sum():,.2f}")
# Usamos fillna(0) para evitar errores si la suma es NaN
col3.metric("Gastos Extinción", f"{df_filtrado['gastos'].fillna(0).sum():,.0f} €") 
col4.metric("Pérdidas Económicas", f"{df_filtrado['perdidas'].fillna(0).sum():,.0f} €")

st.divider()

# --- MAPA ---
st.subheader(f"📍 Mapa de calor e incidentes")

# Limpiamos datos sin coordenadas
df_mapa = df_filtrado.dropna(subset=['lat', 'lng'])

if not df_mapa.empty:
    # Lógica de seguridad: Si hay demasiados puntos, el navegador se cuelga
    if len(df_mapa) > 2000:
        st.warning(f"⚠️ Hay {len(df_mapa)} puntos para mostrar. El mapa podría ir lento. Filtra más para ver los puntos individuales.")
        # Mostramos solo un mapa simple si hay muchos datos, o los primeros 1000
        df_mapa = df_mapa.head(1000) 
    
    # Centro del mapa
    centro = [df_mapa['lat'].mean(), df_mapa['lng'].mean()]
    m = folium.Map(location=centro, zoom_start=6 if comunidad_sel == "Todas" else 9)

    # Pintar puntos
    for i, row in df_mapa.iterrows():
        # Lógica de color
        sup = row['superficie']
        if sup > 50:
            color = "darkred"
        elif sup > 10:
            color = "orange"
        else:
            color = "green"

        # Popup con HTML seguro
        html_popup = f"""
        <b>Municipio:</b> {row.get('municipio', 'N/A')}<br>
        <b>Sup:</b> {sup:.2f} ha<br>
        <b>Fecha:</b> {i.date()}
        """
        
        folium.CircleMarker(
            location=[row['lat'], row['lng']],
            radius=4,
            popup=folium.Popup(html_popup, max_width=200),
            color=color,
            fill=True,
            fill_opacity=0.7
        ).add_to(m)

    st_folium(m, width="100%", height=500)
else:
    st.info("No hay datos geográficos con coordenadas para esta selección.")

st.divider()

# --- GRÁFICOS ---
c1, c2 = st.columns(2)

with c1:
    st.subheader("📈 Evolución Anual")
    # 'YE' es el nuevo estándar de pandas para 'Year End' (Fin de año)
    # Si usas pandas antiguo y falla, cambia 'YE' por 'Y'
    df_anual = df_filtrado.resample('YE')['superficie'].sum().reset_index()
    
    if not df_anual.empty:
        fig_line = px.line(
            df_anual, 
            x='fecha', 
            y='superficie',
            markers=True,
            title="Hectáreas quemadas por año"
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.write("Sin datos suficientes para el gráfico temporal.")

with c2:
    st.subheader("📋 Causas Principales")
    if 'causa_desc' in df_filtrado.columns:
        conteo = df_filtrado['causa_desc'].value_counts().reset_index()
        conteo.columns = ['Causa', 'Incidentes']
        
        fig_pie = px.pie(
            conteo, 
            values='Incidentes', 
            names='Causa', 
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Columna 'causa_desc' no encontrada.")

# --- DATOS RAW ---
with st.expander("📂 Ver Tabla de Datos"):
    st.dataframe(df_filtrado.sort_index(ascending=False).head(1000))
