🔥 Monitor de Incendios Forestales en España

Este proyecto es una aplicación web interactiva desarrollada en Python con Streamlit para visualizar y analizar datos históricos de incendios forestales en España.
El objetivo es proporcionar un cuadro de mandos (dashboard) sencillo que permita filtrar datos por fechas y ubicación geográfica, visualizando métricas clave, mapas de incendios y causas principales de los siniestros.

🚀 Funcionalidades Principales

Filtros Dinámicos: Selección de rango de años, Comunidad Autónoma, Provincia y Municipio.
KPIs en Tiempo Real: Cálculo automático de total de incendios, superficie quemada, gastos de extinción y pérdidas estimadas.
Mapa Interactivo: Visualización geoespacial de incidentes usando Folium. Los puntos cambian de color según la gravedad (superficie quemada).
Gráficos Estadísticos:
Evolución temporal de superficie quemada (Línea).
Distribución de causas de los incendios (Pastel).

Gestión de Metadatos: Traducción automática de códigos numéricos (IDs) a nombres legibles (ej. "1" -> "Andalucía") mediante un archivo maestro de Excel.

📂 Estructura del Proyecto

app.py: Código principal. Contiene toda la lógica de la aplicación, interfaz gráfica y procesamiento de datos.
fires-all.csv.zip: Base de datos. Archivo comprimido con el histórico de partes de incendios.
master_data.xlsx: Maestro de etiquetas. Archivo Excel auxiliar que actúa como diccionario para traducir los IDs de Comunidades, Provincias y Causas a "labels".
requirements.txt: Lista de librerías necesarias para ejecutar el proyecto.

📊 Origen de los Datos

https://datos.civio.es/dataset/todos-los-incendios-forestales/

⚠️ Notas Técnicas

Rendimiento del Mapa: Para evitar que el navegador se bloquee, si el filtro seleccionado devuelve más de 2.000 puntos, el mapa solo mostrará los primeros 1.000. Se recomienda filtrar por Provincia o Año para ver detalles específicos.
Carga de Datos: La primera vez que ejecutes la app puede tardar unos segundos en descomprimir y leer el CSV. Streamlit guardará estos datos en caché (@st.cache_data) para que las siguientes interacciones sean instantáneas.
