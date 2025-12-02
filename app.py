# 1. importar librerias 
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import zipfile
# 2. Configuración de la página
st.set_page_config(
    page_title="Monitor de Incendios Forestales España",
    page_icon="🔥",
    layout="wide"
)
# 3. Carga de datos optimizada
@st.cache_data
def cargar_datos():
    archivo_zip = 'fires-all.csv.zip'
    
    try:
        with zipfile.ZipFile(archivo_zip) as z:
            # Truco para evitar la carpeta __MACOSX oculta
            nombre_csv = [f for f in z.namelist() if f.endswith('.csv') and '__MACOSX' not in f][0]
            
            with z.open(nombre_csv) as f:
                df = pd.read_csv(f, usecols=cols, parse_dates=['fecha'], index_col='fecha')
        
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame() # Devuelve vacío si falla

# Cargamos los datos
df = cargar_datos()

# Si no hay datos, paramos aquí
if df.empty:
    st.stop()

# 4. Barra lateral filtros 
st.sidebar.header("Filtros de Búsqueda")

# A. Filtro por Años
años_disponibles = sorted(df.index.year.unique())
año_seleccionado = st.sidebar.select_slider(
    "Selecciona el rango de años",
    options=años_disponibles,
    value=(min(años_disponibles), max(años_disponibles))
)

# Filtrar por año primero
df_filtrado = df[(df.index.year >= año_seleccionado[0]) & (df.index.year <= año_seleccionado[1])]

# B. Filtros Geográficos (En Cascada)
# 1. Comunidad
lista_comunidades = ["Todas"] + sorted(df_filtrado['idcomunidad'].unique().tolist())
comunidad_sel = st.sidebar.selectbox("Comunidad Autónoma", lista_comunidades)

if comunidad_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado['idcomunidad'] == comunidad_sel]

# 2. Provincia (Solo mostramos provincias que existen en la comunidad filtrada)
lista_provincias = ["Todas"] + sorted(df_filtrado['idprovincia'].unique().tolist())
provincia_sel = st.sidebar.selectbox("Provincia (ID)", lista_provincias)

if provincia_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado['idprovincia'] == provincia_sel]

# 3. Municipio
lista_municipios = ["Todos"] + sorted(df_filtrado['municipio'].unique().tolist())
municipio_sel = st.sidebar.selectbox("Municipio", lista_municipios)

if municipio_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado['municipio'] == municipio_sel]
  # 4. Dasboard principal
st.title("Visualizacion de Incendios en España")
st.markdown(f"Mostrando datos entre **{año_seleccionado[0]}** y **{año_seleccionado[1]}**")

# KPIs (Indicadores Clave)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Incendios", f"{len(df_filtrado):,}")
col2.metric("Superficie Quemada (ha)", f"{df_filtrado['superficie'].sum():,.2f}")
col3.metric("Gastos de extinción (€)", f"{df_filtrado['gastos'].sum():,.0f} €")
col4.metric("Perdidas económicas (€)", int(df_filtrado['perdidas'].sum()))

st.divider()

# --- SECCIÓN MAPA (TU PETICIÓN) ---
st.subheader(f"📍 Mapa de Incendios: {comunidad_sel} > {provincia_sel} > {municipio_sel}")

# 1. Preparación de datos para el mapa
# Quitamos filas sin coordenadas
df_mapa = df_filtrado.dropna(subset=['lat', 'lng']).copy()

if not df_mapa.empty:
    # Centrar el mapa
    centro_mapa = [df_mapa['lat'].mean(), df_mapa['lng'].mean()]
    
    # Creamos el mapa base
    m = folium.Map(location=centro_mapa, zoom_start=6 if comunidad_sel == "Todas" else 9)

    # Pintar los puntos 
    for index, row in df_mapa.iterrows():
        # Definir color según la gravedad (superficie)
        color_borde = "red"
        if row['superficie'] > 50:
            color_relleno = "darkred"
        elif row['superficie'] > 10:
            color_relleno = "orange"
        else:
            color_relleno = "yellow"

        info_popup = f"""
        <b>Municipio:</b> {row['municipio']}<br>
        <b>Fecha:</b> {index.date()}<br>
        <b>Superficie:</b> {row['superficie']:.2f} ha<br>
        <b>Causa:</b> {row['causa_desc']}
        """

        folium.CircleMarker(
            location=[row['lat'], row['lng']],
            radius=5,  
            popup=folium.Popup(info_popup, max_width=300),
            color=color_borde,
            fill=True,
            fill_color=color_relleno,
            fill_opacity=0.7
        ).add_to(m)

    # Mostrar mapa en Streamlit
    st_folium(m, width="100%", height=500)

else:
    st.info("No hay datos geográficos disponibles para la selección actual.")

st.divider()

# --- SECCIÓN GRÁFICOS ---

c1, c2 = st.columns(2)

with c1:
    st.subheader("📈 Evolución Temporal")
    # Agrupamos por año para ver la tendencia
    df_anual = df_filtrado.resample('Y')['superficie'].sum().reset_index()
    # Usamos el índice (fecha) como eje X
    fig_line = px.line(
        df_anual, 
        x=df_anual.columns[0], # La columna de fecha
        y='superficie', 
        title="Superficie quemada por año",
        markers=True
    )
    st.plotly_chart(fig_line, use_container_width=True)

with c2:
    st.subheader("🔥 Causas de los Incendios")
    if 'causa_desc' in df_filtrado.columns:
        conteo_causas = df_filtrado['causa_desc'].value_counts().reset_index()
        conteo_causas.columns = ['Causa', 'Cantidad']
        
        fig_pie = px.pie(
            conteo_causas, 
            values='Cantidad', 
            names='Causa', 
            title="Distribución de Causas",
            hole=0.4 # Donut chart
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.write("No hay datos de causas disponibles.")

# --- SECCIÓN TABLA DE DATOS ---
with st.expander("Ver Datos en Bruto (Tabla Detallada)"):
    st.dataframe(df_filtrado.sort_index(ascending=False))
  
