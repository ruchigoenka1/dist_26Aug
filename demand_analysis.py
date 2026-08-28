import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats

# ------------------------------------------------
# Minimalist Chart Styling (Dark Theme)
# ------------------------------------------------
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117',
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        title_font=dict(color='white'),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# ------------------------------------------------
# Core Analysis UI (Used in both tabs)
# ------------------------------------------------
def demand_analysis_ui(daily_demand, tab_key):
    if len(daily_demand) == 0:
        st.warning("No demand data available.")
        return
        
    # ------------------------------------------------
    # Section 1: Lead Time Demand Analysis
    # ------------------------------------------------
    st.subheader("Section 1: Rolling Demand Analysis")
    
    T = st.number_input(f"Time Window (T in days)", min_value=1, max_value=365, value=7, key=f"T_{tab_key}")
    
    # Calculate T-period rolling demand
    rolling_demand = daily_demand.rolling(window=T).sum().dropna()
    
    if len(rolling_demand) == 0:
        st.error("Not enough data to calculate rolling demand for this time window.")
        return
        
    actual_min = rolling_demand.min()
    actual_max = rolling_demand.max()
    actual_mean = rolling_demand.mean()
    actual_std = rolling_demand.std()
    actual_cov = actual_std / actual_mean if actual_mean > 0 else 0
    
    # Expanded to 5 columns to include the Average Demand
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(f"Min Demand ({T} Days)", round(actual_min, 2))
    c2.metric(f"Max Demand ({T} Days)", round(actual_max, 2))
    c3.metric(f"Avg Demand ({T} Days)", round(actual_mean, 2))
    c4.metric("Standard Deviation", round(actual_std, 2))
    c5.metric("Coefficient of Variation", round(actual_cov, 3))
    
    st.markdown("**Frequency Distribution**")
    
    data_range = actual_max - actual_min
    if data_range == 0:
        st.info("Demand is constant. No distribution to show.")
        return
        
    # ------------------------------------------------
    # Rolling Demand Binning Options
    # ------------------------------------------------
    bin_method_actual = st.radio(
        "Choose Binning Method:", 
        ["Number of Bins", "Bin Width"], 
        horizontal=True, 
        key=f"r_bin_method_{tab_key}"
    )
    
    fig1 = go.Figure()
    
    if bin_method_actual == "Number of Bins":
        actual_bins = st.number_input("Number of Bins", min_value=5, max_value=200, value=10, step=1, key=f"r_bins_count_{tab_key}")
        
        fig1.add_trace(go.Histogram(
            x=rolling_demand,
            nbinsx=actual_bins,
            marker_color='rgba(173, 216, 230, 0.8)', # Light pastel blue fill
            marker_line=dict(color='#3399ff', width=2), # Solid light blue outline
            name="Frequency"
        ))
        
        counts, bin_edges = np.histogram(rolling_demand, bins=actual_bins)
        
    else:
        max_width = max(1, int(data_range))
        default_width = max(1, int(data_range / 10)) if data_range >= 10 else 1
        
        bin_width = st.number_input("Bin Width", min_value=1, max_value=max_width, value=default_width, step=1, key=f"r_bins_width_{tab_key}")
        
        fig1.add_trace(go.Histogram(
            x=rolling_demand,
            xbins=dict(start=actual_min, end=actual_max + bin_width, size=bin_width),
            marker_color='rgba(173, 216, 230, 0.8)', 
            marker_line=dict(color='#3399ff', width=2),
            name="Frequency"
        ))
        
        bins_array = np.arange(actual_min, actual_max + bin_width + 1, bin_width)
        counts, bin_edges = np.histogram(rolling_demand, bins=bins_array)

    fig1.update_layout(title=f"Demand Frequency over {T} Days", xaxis_title="Demand Quantity", yaxis_title="Absolute Count")
    fig1 = style_plotly_fig(fig1)
    st.plotly_chart(fig1, use_container_width=True)
    
    freq_df = pd.DataFrame({
        "Bin Start": np.round(bin_edges[:-1], 2),
        "Bin End": np.round(bin_edges[1:], 2),
        "Absolute Count": counts
    })
    
    # Add Percentage Columns
    total_count_1 = freq_df["Absolute Count"].sum()
    if total_count_1 > 0:
        freq_df["% of Total"] = np.round((freq_df["Absolute Count"] / total_count_1) * 100, 2)
        freq_df["Cumulative %"] = np.round(freq_df["% of Total"].cumsum(), 2)
    else:
        freq_df["% of Total"] = 0.0
        freq_df["Cumulative %"] = 0.0
        
    st.dataframe(freq_df, use_container_width=True)
    
    st.divider()
    
    # ------------------------------------------------
    # Section 2: Forecasted Demand Scaling
    # ------------------------------------------------
    st.subheader("Section 2: Forecasted Demand Scaling")
    st.markdown("Generate a new distribution based on your expected average demand, dynamically scaled to your time window (T).")
    
    col1, col2 = st.columns(2)
    with col1:
        avg_demand_input = st.number_input("Forecasted Average Demand", min_value=1.0, value=100.0, key=f"avg_{tab_key}")
    with col2:
        duration_T2 = st.number_input("Duration of Average Demand (T2 in days)", min_value=1, value=30, key=f"T2_{tab_key}")
        
    forecast_avg_T = (avg_demand_input / duration_T2) * T
    forecast_std_T = forecast_avg_T * actual_cov
    
    st.info(f"Scaled **{T}-Day** Forecast Average: {round(forecast_avg_T, 2)} | Scaled Std Dev: {round(forecast_std_T, 2)}")
    
   ## ------------------------------------------------
    # Generate Forecast via Dynamic Model Selection
    # ------------------------------------------------
    np.random.seed(42)
    
    # Logic 1: Stable / Fast-moving (Normal)
    if actual_cov <= 0.5:
        simulated_forecast = np.maximum(0, np.random.normal(forecast_avg_T, forecast_std_T, 10000))
        st.caption("🤖 **Auto-Selected Model:** Normal Distribution (Optimized for stable, low-variability inventory)")
        
    # Logic 2: Volatile / Lumpy (Empirical Bootstrapping)
    else:
        if actual_mean > 0:
            raw_samples = np.random.choice(rolling_demand, size=10000, replace=True)
            scaling_factor = forecast_avg_T / actual_mean
            simulated_forecast = raw_samples * scaling_factor
        else:
            simulated_forecast = np.full(10000, forecast_avg_T)
            
        simulated_forecast = np.maximum(0, simulated_forecast)
        st.caption("🤖 **Auto-Selected Model:** Empirical Bootstrapping (Optimized for volatile, lumpy demand)")
    
    forecast_min = simulated_forecast.min()
    forecast_max = simulated_forecast.max()
    forecast_range = forecast_max - forecast_min
    
    # ------------------------------------------------
    # Forecast Binning Options
    # ------------------------------------------------
    bin_method = st.radio("Choose Binning Method for Forecast:", ["Number of Bins", "Bin Width"], horizontal=True, key=f"f_bin_method_{tab_key}")
    
    fig2 = go.Figure()
    
    if bin_method == "Number of Bins":
        forecast_bins = st.number_input("Number of Bins", min_value=5, max_value=200, value=30, step=1, key=f"f_bins_count_{tab_key}")
        
        fig2.add_trace(go.Histogram(
            x=simulated_forecast,
            nbinsx=forecast_bins,
            marker_color='rgba(173, 216, 230, 0.8)', # Light pastel blue fill
            marker_line=dict(color='#3399ff', width=2),
            name="Forecast Frequency"
        ))
        
        # Calculate table edges based on number of bins
        counts_f, edges_f = np.histogram(simulated_forecast, bins=forecast_bins)
        
    else:
        # Prevent division by zero if forecast is entirely flat
        max_width = max(1, int(forecast_range))
        default_width = max(1, int(forecast_range / 30)) if forecast_range >= 30 else 1
        
        bin_width = st.number_input("Bin Width", min_value=1, max_value=max_width, value=default_width, step=1, key=f"f_bins_width_{tab_key}")
        
        fig2.add_trace(go.Histogram(
            x=simulated_forecast,
            xbins=dict(start=forecast_min, end=forecast_max + bin_width, size=bin_width),
            marker_color='rgba(173, 216, 230, 0.8)', 
            marker_line=dict(color='#3399ff', width=2),
            name="Forecast Frequency"
        ))
        
        # Calculate table edges based on exact bin width
        bins_array = np.arange(forecast_min, forecast_max + bin_width + 1, bin_width)
        counts_f, edges_f = np.histogram(simulated_forecast, bins=bins_array)

    fig2.update_layout(title=f"Forecasted Demand Distribution ({T} Days)", xaxis_title="Demand Quantity", yaxis_title="Absolute Count")
    fig2 = style_plotly_fig(fig2)
    st.plotly_chart(fig2, use_container_width=True)
    
    forecast_freq_df = pd.DataFrame({
        "Bin Start": np.round(edges_f[:-1], 2),
        "Bin End": np.round(edges_f[1:], 2),
        "Absolute Count": counts_f
    })
    
    # Add Percentage Columns
    total_count_2 = forecast_freq_df["Absolute Count"].sum()
    if total_count_2 > 0:
        forecast_freq_df["% of Total"] = np.round((forecast_freq_df["Absolute Count"] / total_count_2) * 100, 2)
        forecast_freq_df["Cumulative %"] = np.round(forecast_freq_df["% of Total"].cumsum(), 2)
    else:
        forecast_freq_df["% of Total"] = 0.0
        forecast_freq_df["Cumulative %"] = 0.0
    
    with st.expander("View Forecasted Frequency Table"):
        st.dataframe(forecast_freq_df, use_container_width=True)
        
    st.divider()

    
    # ------------------------------------------------
    # Section 3: Service Level Simulator
    # ------------------------------------------------
    st.subheader(f"Section 3: Service Level Diagnostics ({T} Days)")
    
    c_sl1, c_sl2 = st.columns(2)
    
    with c_sl1:
        st.markdown("**Calculate Inventory Target**")
        target_sl = st.slider("Target Service Level (%)", min_value=50.0, max_value=99.9, value=95.0, step=0.1, key=f"sl_target_{tab_key}")
        required_inv = np.percentile(simulated_forecast, target_sl)
        st.metric(f"Inventory Required for {target_sl}% ({T} Days)", round(required_inv, 0))
        
    with c_sl2:
        st.markdown("**Audit Achieved Service Level**")
        inv_amount = st.number_input("Test Inventory Amount", min_value=0.0, value=float(round(forecast_avg_T,0)), key=f"inv_amount_{tab_key}")
        achieved_sl = stats.percentileofscore(simulated_forecast, inv_amount)
        st.metric(f"Achieved Service Level ({T} Days)", f"{round(achieved_sl, 1)}%")

    st.divider()
    
    # ------------------------------------------------
    # Section 4: Historical Demand Simulation
    # ------------------------------------------------
    st.subheader("Section 4: Historical Demand Simulation")
    st.markdown("Simulate inventory performance using the actual historical demand profile against specific trigger points.")
    
    c_sim1, c_sim2, c_sim3, c_sim4 = st.columns(4)
    with c_sim1:
        sim_rop = st.number_input("Reorder Point (ROP)", min_value=0, value=int(actual_mean), key=f"sim_rop_{tab_key}")
    with c_sim2:
        sim_oq = st.number_input("Order Quantity (OQ)", min_value=1, value=int(actual_mean * 2), key=f"sim_oq_{tab_key}")
    with c_sim3:
        sim_ob = st.number_input("Opening Balance", min_value=0, value=int(1.25 * sim_rop), key=f"sim_ob_{tab_key}")
    with c_sim4:
        sim_lt = st.number_input("Lead Time (Days)", min_value=1, value=int(T), key=f"sim_lt_{tab_key}")

    # Simulation Logic
    phys_inv = sim_ob
    pipe_inv = 0
    pending_orders = {} 
    
    dates = daily_demand.index if isinstance(daily_demand.index, pd.DatetimeIndex) else np.arange(1, len(daily_demand) + 1)
    
    sim_results = {
        "Day/Date": [], "Demand": [], "Physical Inventory": [], 
        "Total Inventory": [], "Pipeline Inventory": [], 
        "Orders Placed": [], "Orders Received": [], 
        "Reorder Flag": [], "Stockout Flag": [], "Unmet Demand": []
    }
    
    for i, demand in enumerate(daily_demand):
        # 1. Receive Orders
        received_today = pending_orders.get(i, 0)
        phys_inv += received_today
        pipe_inv -= received_today
        
        # 2. Fulfill Demand
        met = min(phys_inv, demand)
        phys_inv -= met
        unmet = demand - met
        
        stockout = 1 if phys_inv == 0 and demand > 0 else 0
        
        tot_inv = phys_inv + pipe_inv
        
        # 3. Check ROP
        placed_today = 0
        reorder_flag = 0
        if tot_inv <= sim_rop:
            placed_today = sim_oq
            pipe_inv += placed_today
            arrival_day = i + sim_lt
            pending_orders[arrival_day] = pending_orders.get(arrival_day, 0) + placed_today
            reorder_flag = 1
            tot_inv = phys_inv + pipe_inv
            
        sim_results["Day/Date"].append(dates[i])
        sim_results["Demand"].append(demand)
        sim_results["Physical Inventory"].append(phys_inv)
        sim_results["Total Inventory"].append(tot_inv)
        sim_results["Pipeline Inventory"].append(pipe_inv)
        sim_results["Orders Placed"].append(placed_today)
        sim_results["Orders Received"].append(received_today)
        sim_results["Reorder Flag"].append(reorder_flag)
        sim_results["Stockout Flag"].append(stockout)
        sim_results["Unmet Demand"].append(unmet)
        
    df_sim = pd.DataFrame(sim_results)
    
    # KPI Calculations
    total_dem = df_sim["Demand"].sum()
    total_unmet = df_sim["Unmet Demand"].sum()
    fill_rate = 100 * (1 - total_unmet / total_dem) if total_dem > 0 else 100.0
    
    st.markdown("**Simulation KPIs**")
    c_k1, c_k2, c_k3, c_k4, c_k5 = st.columns(5)
    c_k1.metric("Avg Physical Inventory", round(df_sim["Physical Inventory"].mean(), 1))
    c_k2.metric("Min Physical Inventory", round(df_sim["Physical Inventory"].min(), 1))
    c_k3.metric("Max Physical Inventory", round(df_sim["Physical Inventory"].max(), 1))
    c_k4.metric("Stockout Days", int(df_sim["Stockout Flag"].sum()))
    c_k5.metric("Fill Rate", f"{round(fill_rate, 2)}%")
    
    # Plotting
    show_pipeline = st.checkbox("Include Pipeline & Total Inventory", value=False, key=f"show_pipe_{tab_key}")
    
    fig_sim = go.Figure()
    
    fig_sim.add_trace(go.Scatter(x=df_sim["Day/Date"], y=df_sim["Physical Inventory"], mode='lines', name='Physical Inventory', line=dict(color='#3399ff', width=2)))
    
    if show_pipeline:
        fig_sim.add_trace(go.Scatter(x=df_sim["Day/Date"], y=df_sim["Total Inventory"], mode='lines', name='Total Inventory', line=dict(color='rgba(173, 216, 230, 0.6)', width=2, dash='dash')))
        
    fig_sim.add_trace(go.Scatter(x=df_sim["Day/Date"], y=[sim_rop]*len(df_sim), mode='lines', name='Reorder Point (ROP)', line=dict(color='orange', width=2, dash='dot')))
    
    reorders = df_sim[df_sim["Reorder Flag"] == 1]
    if not reorders.empty:
        fig_sim.add_trace(go.Scatter(x=reorders["Day/Date"], y=reorders["Physical Inventory"], mode='markers', name='Reorder Placed', marker=dict(symbol='triangle-up', color='green', size=12)))
        
    stockouts = df_sim[df_sim["Stockout Flag"] == 1]
    if not stockouts.empty:
        fig_sim.add_trace(go.Scatter(x=stockouts["Day/Date"], y=stockouts["Physical Inventory"], mode='markers', name='Stockout', marker=dict(symbol='triangle-down', color='red', size=12)))
        
    fig_sim.update_layout(title="Inventory Simulation over Time", xaxis_title="Timeline", yaxis_title="Units")
    fig_sim = style_plotly_fig(fig_sim)
    st.plotly_chart(fig_sim, use_container_width=True)
    
    # Tables
    with st.expander("View Daily Simulation Data"):
        st.dataframe(df_sim.drop(columns=["Reorder Flag", "Stockout Flag", "Unmet Demand"]), use_container_width=True)
        
    st.markdown("**Closing Balance Frequency Distribution**")
    
    cb_num_bins = 10
    counts_cb, bin_edges_cb = np.histogram(df_sim["Physical Inventory"], bins=cb_num_bins)
    cb_freq_df = pd.DataFrame({
        "Bin Start": np.round(bin_edges_cb[:-1], 2),
        "Bin End": np.round(bin_edges_cb[1:], 2),
        "Absolute Count": counts_cb
    })
    
    total_cb = counts_cb.sum()
    if total_cb > 0:
        cb_freq_df["% of Total"] = np.round((cb_freq_df["Absolute Count"] / total_cb) * 100, 2)
        cb_freq_df["Cumulative %"] = np.round(cb_freq_df["% of Total"].cumsum(), 2)
    else:
        cb_freq_df["% of Total"] = 0.0
        cb_freq_df["Cumulative %"] = 0.0
        
    cb_freq_df["% of Total"] = cb_freq_df["% of Total"].astype(str) + "%"
    cb_freq_df["Cumulative %"] = cb_freq_df["Cumulative %"].astype(str) + "%"
    
    st.dataframe(cb_freq_df, use_container_width=True)


# ------------------------------------------------
# Main Page Layout & Tabs
# ------------------------------------------------
st.title("Demand Analysis & Forecasting")

tab1, tab2 = st.tabs(["Simulated Base Demand", "Actual Uploaded Demand"])

with tab1:
    st.markdown("### Generate Simulated Base Demand")
    colA, colB, colC = st.columns(3)
    with colA:
        sim_avg = st.number_input("Daily Avg Demand", value=25.0)
    with colB:
        sim_std = st.number_input("Daily Std Dev", value=10.0)
    with colC:
        sim_days = st.number_input("Simulation Days", value=365)
        
    np.random.seed(123)
    simulated_daily_demand = pd.Series(np.maximum(0, np.random.normal(sim_avg, sim_std, sim_days)).round())
    
    st.divider()
    demand_analysis_ui(simulated_daily_demand, "simulated")

with tab2:
    st.markdown("### Upload Historical Data")
    
    uploaded_file = st.file_uploader("Upload Data (Excel format)", type=["csv", "xlsx"], key="file_upload")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_actual = pd.read_csv(uploaded_file)
            else:
                df_actual = pd.read_excel(uploaded_file)
                
            if 'Demand/Sales' not in df_actual.columns:
                st.error("Error: The uploaded file must contain a 'Demand/Sales' column.")
            else:
                actual_daily_demand = df_actual['Demand/Sales'].fillna(0)
                st.divider()
                demand_analysis_ui(actual_daily_demand, "actual")
                
        except Exception as e:
            st.error(f"Error processing file: {e}")
