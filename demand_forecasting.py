import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from statsmodels.tsa.statespace.sarimax import SARIMAX
from prophet import Prophet
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="Demand Forecasting", layout="wide")

# =====================================================================
# STYLING
# =====================================================================
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117',
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        title_font=dict(color='white'),
        legend=dict(font=dict(color='white'), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# =====================================================================
# HEADER & UPLOAD
# =====================================================================
st.title("📈 Demand Forecasting Engine")
st.markdown("Generate future demand predictions using statistical (SARIMA) and AI-driven (Prophet) models.")

# Generate Sample File for Download
@st.cache_data
def convert_df(df):
    return df.to_csv(index=False).encode('utf-8')

sample_df = pd.DataFrame({
    'Date': pd.date_range(start="2024-01-01", periods=365).strftime('%Y-%m-%d'),
    'Demand/Sales': np.random.poisson(lam=100, size=365)
})
sample_csv = convert_df(sample_df)

c1, c2 = st.columns([3, 1])
with c1:
    uploaded_file = st.file_uploader("Upload Historical Demand Data", type=["csv", "xlsx"])
with c2:
    st.markdown("<br>", unsafe_allow_html=True) # Spacer
    st.download_button(
        label="📥 Download Sample Template",
        data=sample_csv,
        file_name='sample_demand_template.csv',
        mime='text/csv',
    )

if uploaded_file is not None:
    try:
        # Parse File
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        time_col = 'Date'
        demand_col = 'Demand/Sales'
        
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col)
        
        st.divider()
        
        # =====================================================================
        # AGGREGATION & CONFIGURATION
        # =====================================================================
        st.subheader("⚙️ Forecast Configuration")
        
        cfg1, cfg2, cfg3 = st.columns(3)
        with cfg1:
            granularity = st.selectbox("Forecast Granularity", ["Daily", "Weekly", "Monthly"])
        with cfg2:
            forecast_horizon = st.number_input("Forecast Horizon (Periods)", min_value=1, max_value=365, value=30)
            
        # Resample data based on user selection
        df_resampled = df.set_index(time_col)[[demand_col]].copy()
        
        if granularity == "Daily":
            df_resampled = df_resampled.resample('D').sum().fillna(0)
            freq_str = 'D'
            default_seasonality = 7 # Weekly cycle in daily data
        elif granularity == "Weekly":
            df_resampled = df_resampled.resample('W-MON').sum().fillna(0)
            freq_str = 'W-MON'
            default_seasonality = 52 # Yearly cycle in weekly data
        else:
            df_resampled = df_resampled.resample('MS').sum().fillna(0)
            freq_str = 'MS'
            default_seasonality = 12 # Yearly cycle in monthly data
            
        df_resampled = df_resampled.reset_index()
        
        st.info(f"Dataset aggregated to **{granularity}** level. Total periods available for training: **{len(df_resampled)}**")
        
        st.divider()

        # =====================================================================
        # MODELING TABS
        # =====================================================================
        tab_sarima, tab_prophet = st.tabs(["📊 SARIMA (Statistical)", "🧠 Prophet (AI-Driven)"])
        
        # ---------------------------------------------------------------------
        # TAB 1: SARIMA
        # ---------------------------------------------------------------------
        with tab_sarima:
            st.markdown("#### Seasonal Autoregressive Integrated Moving Average")
            st.write("A robust traditional statistical model that relies on historical lags, differencing, and moving averages.")
            
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                st.markdown("**Trend Parameters (p, d, q)**")
                p = st.number_input("AR (p) - Autoregression", min_value=0, max_value=5, value=1)
                d = st.number_input("I (d) - Differencing", min_value=0, max_value=2, value=1)
                q = st.number_input("MA (q) - Moving Average", min_value=0, max_value=5, value=1)
            
            with s_col2:
                st.markdown("**Seasonal Parameters (P, D, Q, s)**")
                P = st.number_input("Seasonal AR (P)", min_value=0, max_value=2, value=1)
                D = st.number_input("Seasonal I (D)", min_value=0, max_value=1, value=0)
                Q = st.number_input("Seasonal MA (Q)", min_value=0, max_value=2, value=1)
                s = st.number_input("Seasonality (s)", min_value=0, max_value=365, value=default_seasonality, help="Periods per season (e.g., 7 for daily, 12 for monthly)")
                
            if st.button("Run SARIMA Forecast", type="primary"):
                with st.spinner("Fitting SARIMA model... (This may take a moment for large datasets)"):
                    try:
                        # Fit Model
                        ts_data = df_resampled[demand_col].values
                        model = SARIMAX(ts_data, order=(p, d, q), seasonal_order=(P, D, Q, s), enforce_stationarity=False, enforce_invertibility=False)
                        sarima_result = model.fit(disp=False)
                        
                        # Forecast
                        forecast_values = sarima_result.get_forecast(steps=forecast_horizon)
                        pred_mean = forecast_values.predicted_mean
                        pred_ci = forecast_values.conf_int(alpha=0.05) # 95% CI
                        
                        # Generate future dates
                        last_date = df_resampled[time_col].iloc[-1]
                        future_dates = pd.date_range(start=last_date, periods=forecast_horizon + 1, freq=freq_str)[1:]
                        
                        # Plot
                        fig_sarima = go.Figure()
                        
                        # Historical
                        fig_sarima.add_trace(go.Scatter(x=df_resampled[time_col], y=df_resampled[demand_col], mode='lines', name='Historical Demand', line=dict(color='#1f77b4', width=2)))
                        
                        # Confidence Interval
                        fig_sarima.add_trace(go.Scatter(
                            x=list(future_dates) + list(future_dates)[::-1],
                            y=list(pred_ci[:, 1]) + list(pred_ci[:, 0])[::-1],
                            fill='toself', fillcolor='rgba(255, 127, 14, 0.2)', line=dict(color='rgba(255,255,255,0)'),
                            hoverinfo="skip", showlegend=True, name='95% Confidence Interval'
                        ))
                        
                        # Forecast Line
                        fig_sarima.add_trace(go.Scatter(x=future_dates, y=pred_mean, mode='lines', name='SARIMA Forecast', line=dict(color='#ff7f0e', width=3, dash='dash')))
                        
                        fig_sarima.update_layout(title=f"SARIMA {granularity} Forecast ({forecast_horizon} Periods)", xaxis_title="Date", yaxis_title="Demand")
                        st.plotly_chart(style_plotly_fig(fig_sarima), use_container_width=True)
                        
                        # Output Table
                        st.markdown("##### Forecasted Values (SARIMA)")
                        df_out_sarima = pd.DataFrame({
                            "Date": future_dates.strftime('%Y-%m-%d'),
                            "Expected Demand": np.round(pred_mean, 0),
                            "Lower Bound (95%)": np.maximum(0, np.round(pred_ci[:, 0], 0)),
                            "Upper Bound (95%)": np.round(pred_ci[:, 1], 0)
                        })
                        st.dataframe(df_out_sarima, use_container_width=True, hide_index=True)
                        
                    except Exception as e:
                        st.error(f"SARIMA Model Failed to Converge. Try adjusting the parameters or checking your data for extreme outliers. Error: {e}")

        # ---------------------------------------------------------------------
        # TAB 2: PROPHET
        # ---------------------------------------------------------------------
        with tab_prophet:
            st.markdown("#### Meta Prophet (AI-Driven Additive Model)")
            st.write("An open-source ML forecasting tool designed to handle missing data, dramatic trend shifts, and complex seasonality automatically.")
            
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                changepoint_scale = st.slider("Trend Flexibility", min_value=0.01, max_value=0.5, value=0.05, step=0.01, help="Higher values allow the trend to change more rapidly (risks overfitting).")
            with p_col2:
                seasonality_mode = st.radio("Seasonality Mode", ["additive", "multiplicative"], horizontal=True, help="Use multiplicative if seasonal fluctuations grow with the overall trend.")
                
            if st.button("Run Prophet Forecast", type="primary"):
                with st.spinner("Training Prophet AI..."):
                    try:
                        # Prepare data for Prophet (Requires 'ds' and 'y' columns)
                        df_prophet = df_resampled.rename(columns={time_col: 'ds', demand_col: 'y'})
                        
                        # Initialize and fit
                        m = Prophet(changepoint_prior_scale=changepoint_scale, seasonality_mode=seasonality_mode)
                        
                        if granularity == "Daily":
                            m.add_country_holidays(country_name='US') # Optional: Can be parameterized
                        
                        m.fit(df_prophet)
                        
                        # Forecast
                        future = m.make_future_dataframe(periods=forecast_horizon, freq=freq_str)
                        forecast = m.predict(future)
                        
                        # Split historical and future for cleaner plotting
                        forecast_hist = forecast[forecast['ds'] <= df_prophet['ds'].max()]
                        forecast_fut = forecast[forecast['ds'] > df_prophet['ds'].max()]
                        
                        # Plot
                        fig_prophet = go.Figure()
                        
                        # Actuals
                        fig_prophet.add_trace(go.Scatter(x=df_prophet['ds'], y=df_prophet['y'], mode='markers', name='Actual Demand', marker=dict(color='white', size=4)))
                        
                        # Model Fit (Historical)
                        fig_prophet.add_trace(go.Scatter(x=forecast_hist['ds'], y=forecast_hist['yhat'], mode='lines', name='Prophet Fit', line=dict(color='#1f77b4', width=2)))
                        
                        # Confidence Interval (Future)
                        fig_prophet.add_trace(go.Scatter(
                            x=list(forecast_fut['ds']) + list(forecast_fut['ds'])[::-1],
                            y=list(forecast_fut['yhat_upper']) + list(forecast_fut['yhat_lower'])[::-1],
                            fill='toself', fillcolor='rgba(44, 160, 44, 0.2)', line=dict(color='rgba(255,255,255,0)'),
                            hoverinfo="skip", showlegend=True, name='Uncertainty Interval'
                        ))
                        
                        # Forecast Line (Future)
                        fig_prophet.add_trace(go.Scatter(x=forecast_fut['ds'], y=forecast_fut['yhat'], mode='lines', name='Prophet Forecast', line=dict(color='#2ca02c', width=3, dash='dash')))
                        
                        fig_prophet.update_layout(title=f"Prophet AI {granularity} Forecast ({forecast_horizon} Periods)", xaxis_title="Date", yaxis_title="Demand")
                        st.plotly_chart(style_plotly_fig(fig_prophet), use_container_width=True)
                        
                        # Output Table
                        st.markdown("##### Forecasted Values (Prophet)")
                        df_out_prophet = pd.DataFrame({
                            "Date": forecast_fut['ds'].dt.strftime('%Y-%m-%d'),
                            "Expected Demand": np.round(forecast_fut['yhat'], 0),
                            "Lower Bound": np.maximum(0, np.round(forecast_fut['yhat_lower'], 0)),
                            "Upper Bound": np.round(forecast_fut['yhat_upper'], 0)
                        })
                        st.dataframe(df_out_prophet, use_container_width=True, hide_index=True)
                        
                    except Exception as e:
                        st.error(f"Prophet Model encountered an error: {e}")

    except Exception as e:
        st.error(f"Error processing the uploaded file: {e}")
