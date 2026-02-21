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
        
        
