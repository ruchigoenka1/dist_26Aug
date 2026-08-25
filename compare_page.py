import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

# Minimalist styling function with a white background and blue accents
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='white', 
        paper_bgcolor='white',
        font=dict(color='black'),
        title_font=dict(color='black'),
        legend=dict(
            font=dict(color='black'),
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='black', gridcolor='#e6e6e6')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='black', gridcolor='#e6e6e6', rangemode="tozero")
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
st.write("Upload your historical inventory data. The system will extract your daily demand ranges, run a simulation, and compare the average inventory levels.")

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
        
        actual_min_demand = int(df_filled['Derived Demand'].min())
        actual_max_demand = int(df_filled['Derived Demand'].max())
        
        # ------------------------------------------------
        # Sidebar Inputs
        # ------------------------------------------------
        st.sidebar.header("Simulation Parameters")
        st.sidebar.info(f"**Extracted Demand:**\nMin: {actual_min_demand} / Max: {actual_max_demand}")
        
        reorder_point = st.sidebar.number_input("Reorder Point", value=200)
        opening_balance = st.sidebar.number_input("Opening Balance", value=int(1.25 * reorder_point))
        lead_time = st.sidebar.number_input("Lead Time (Days)", value=3)
        order_qty = st.sidebar.number_input("Order Quantity", value=300)
        
        # ------------------------------------------------
        # Simulation Logic
        # ------------------------------------------------
        num_days = len(df_filled)
        
        # Generate uniform demand based on extracted min/max
        sim_demand = np.random.randint(actual_min_demand, actual_max_demand + 1, num_days)
        
        inventory = opening_balance
        pipeline_orders = []
        sim_closing_balances = []
        
        for day in range(num_days):
            shipment_received = 0
            for order in pipeline_orders.copy():
                if order[0] == day:
                    shipment_received += order[1]
                    pipeline_orders.remove(order)
                    
            inventory += shipment_received
            demand_today = sim_demand[day]
            inventory -= demand_today
            
            if inventory < 0:
                inventory = 0
                
            pipeline_qty = sum(qty for arrival, qty in pipeline_orders)
            inventory_position = inventory + pipeline_qty
            
            if inventory_position < reorder_point:
                pipeline_orders.append((day + lead_time, order_qty))
                
            sim_closing_balances.append(inventory)
            
        df_filled['Simulated Balance'] = sim_closing_balances
        
        # ------------------------------------------------
        # Output & Comparison KPIs
        # ------------------------------------------------
        st.subheader("Average Inventory Comparison")
        
        avg_hist = df_filled[balance_col].mean()
        avg_sim = df_filled['Simulated Balance'].mean()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Historical Average", round(avg_hist, 0))
        c2.metric("Simulated Average", round(avg_sim, 0))
        diff = avg_sim - avg_hist
        c3.metric("Difference", round(diff, 0), delta=round(diff, 0), delta_color="inverse")
        
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
            line=dict(color="#0052cc", width=2) # Standard blue
        ))
        
        fig = style_plotly_fig(fig)
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error processing file: {e}")
