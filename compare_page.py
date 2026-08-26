import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# Updated styling function for a dark background
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117', 
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        title_font=dict(color='white'),
        legend=dict(
            font=dict(color='white'),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
    return fig

# ------------------------------------------------
# Sample Excel Generator
# ------------------------------------------------
def generate_sample_excel():
    df_sample = pd.DataFrame({
        "Date": ["2024-01-01", "2024-01-03", "2024-01-07", "2024-01-10", "2024-01-12"],
        "Closing Balance": [500, 439, 358, 600, 520]
    })
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_sample.to_excel(writer, index=False, sheet_name='Sample Data')
    return buffer.getvalue()

st.title("Historical vs Simulated Comparison")
st.write("Upload your historical inventory data. The system extracts exact daily demand, runs a simulation using your current policy parameters, and compares the outcomes.")

# ------------------------------------------------
# Download Template Section
# ------------------------------------------------
st.download_button(
    label="📥 Download Sample Excel Template",
    data=generate_sample_excel(),
    file_name="inventory_sample_template.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.divider()

# ------------------------------------------------
# File Upload & Demand Extraction
# ------------------------------------------------
uploaded_file = st.file_uploader("Upload Historical Data", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        # Load Data
        if uploaded_file.name.endswith('.csv'):
            df_hist = pd.read_csv(uploaded_file)
        else:
            df_hist = pd.read_excel(uploaded_file)
            
        time_col = df_hist.columns[0]
        balance_col = df_hist.columns[1]
        
        # Handle gaps in dates/days
        is_numeric_index = pd.api.types.is_numeric_dtype(df_hist[time_col])
        if not is_numeric_index:
            df_hist[time_col] = pd.to_datetime(df_hist[time_col])
            
        df_hist = df_hist.sort_values(by=time_col)
        df_hist.set_index(time_col, inplace=True)
        
        if is_numeric_index:
            full_range = range(int(df_hist.index.min()), int(df_hist.index.max()) + 1)
        else:
            full_range = pd.date_range(start=df_hist.index.min(), end=df_hist.index.max())
        
        df_filled = df_hist.reindex(full_range).ffill()
        df_filled.reset_index(inplace=True)
        df_filled.rename(columns={'index': time_col}, inplace=True)
        
        # Extract daily demand by finding the day-over-day drop in closing balance
        df_filled['Previous Balance'] = df_filled[balance_col].shift(1)
        
        # If balance drops, the difference is demand. If it rises, it's a replenishment (demand = 0)
        df_filled['Derived Demand'] = np.where(
            df_filled['Previous Balance'] > df_filled[balance_col], 
            df_filled['Previous Balance'] - df_filled[balance_col], 
            0
        )
        df_filled['Derived Demand'] = df_filled['Derived Demand'].fillna(0)
        
        # ------------------------------------------------
        # Sidebar Inputs
        # ------------------------------------------------
        st.sidebar.header("Simulation Parameters")
        
        reorder_point = st.sidebar.number_input("Reorder Point", value=200)
        opening_balance = st.sidebar.number_input("Opening Balance", value=int(1.25 * reorder_point))
        lead_time = st.sidebar.number_input("Lead Time (Days)", value=3)
        order_qty = st.sidebar.number_input("Order Quantity", value=300)
        
        # ------------------------------------------------
        # Simulation Logic (Using Exact Historical Demand)
        # ------------------------------------------------
        num_days = len(df_filled)
        sim_demand = df_filled['Derived Demand'].values
        
        inventory = opening_balance
        pipeline_orders = []
        sim_closing_balances = []
        
        total_demand = 0
        total_unmet_demand = 0
        
        for day in range(num_days):
            shipment_received = 0
            for order in pipeline_orders.copy():
                if order[0] == day:
                    shipment_received += order[1]
                    pipeline_orders.remove(order)
                    
            inventory += shipment_received
            
            demand_today = sim_demand[day]
            total_demand += demand_today
            
            inventory -= demand_today
            
            # Track stockouts and unmet demand for Fill Rate
            unmet_today = 0
            if inventory < 0:
                unmet_today = abs(inventory)
                inventory = 0
                
            total_unmet_demand += unmet_today
                
            pipeline_qty = sum(qty for arrival, qty in pipeline_orders)
            inventory_position = inventory + pipeline_qty
            
            if inventory_position < reorder_point:
                pipeline_orders.append((day + lead_time, order_qty))
                
            sim_closing_balances.append(inventory)
            
        df_filled['Simulated Balance'] = sim_closing_balances
        
        # ------------------------------------------------
        # Output & Comparison KPIs
        # ------------------------------------------------
        st.subheader("Comparison & Performance KPIs")
        
        # --- Calculations ---
        avg_hist = df_filled[balance_col].mean()
        avg_sim = df_filled['Simulated Balance'].mean()
        min_hist = df_filled[balance_col].min()
        max_hist = df_filled[balance_col].max()
        min_sim = df_filled['Simulated Balance'].min()
        max_sim = df_filled['Simulated Balance'].max()
        
        avg_demand = df_filled['Derived Demand'].mean()
        std_demand = df_filled['Derived Demand'].std()
        cov_demand = std_demand / avg_demand if avg_demand > 0 else 0
        min_demand = df_filled['Derived Demand'].min()
        max_demand = df_filled['Derived Demand'].max()
        
        stockout_days = (df_filled['Simulated Balance'] == 0).sum()
        
        fill_rate = 100.0
        if total_demand > 0:
            fill_rate = ((total_demand - total_unmet_demand) / total_demand) * 100
        
        # --- Display Row 1: Averages & Performance ---
        st.markdown("**Averages & Performance**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Historical Avg Inventory", round(avg_hist, 0))
        
        diff = avg_sim - avg_hist
        c2.metric("Simulated Avg Inventory", round(avg_sim, 0), delta=round(diff, 0), delta_color="inverse")
        
        c3.metric("Simulated Stockout Days", stockout_days)
        c4.metric("Simulated Fill Rate", f"{round(fill_rate, 2)}%")
        
        # --- Display Row 2: Inventory Ranges ---
        st.markdown("**Inventory Ranges**")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Historical Min Balance", round(min_hist, 0))
        r2.metric("Historical Max Balance", round(max_hist, 0))
        r3.metric("Simulated Min Balance", round(min_sim, 0))
        r4.metric("Simulated Max Balance", round(max_sim, 0))

        # --- Display Row 3: Demand Statistics ---
        st.markdown("**Historical Demand Statistics**")
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Avg Daily Demand", round(avg_demand, 1))
        d2.metric("Demand Std Dev", round(std_demand, 1))
        d3.metric("CoV", round(cov_demand, 2))
        d4.metric("Min Daily Demand", round(min_demand, 0))
        d5.metric("Max Daily Demand", round(max_demand, 0))
        
        # ------------------------------------------------
        # Plotting the Comparison
        # ------------------------------------------------
        st.subheader("Closing Balance Timeline")
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df_filled[time_col],
            y=df_filled[balance_col],
            mode="lines",
            name="Historical Balance",
            line=dict(color="gray", width=2, dash="dash")
        ))
        
        fig.add_trace(go.Scatter(
            x=df_filled[time_col],
            y=df_filled['Simulated Balance'],
            mode="lines",
            name="Simulated Balance",
            line=dict(color="skyblue", width=2)
        ))
        
        fig = style_plotly_fig(fig)
        st.plotly_chart(fig, use_container_width=True)
        
        # ------------------------------------------------
        # Data Tables
        # ------------------------------------------------
        st.divider()
        st.subheader("Historical Data")
        st.dataframe(df_filled[[time_col, balance_col, 'Derived Demand']], use_container_width=True)
        
        st.subheader("Simulated Data")
        st.dataframe(df_filled[[time_col, 'Derived Demand', 'Simulated Balance']], use_container_width=True)
        
    except Exception as e:
        st.error(f"Error processing file: {e}")
