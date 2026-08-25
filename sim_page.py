import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# Minimalist styling function for charts
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='black')
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgray')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='black', gridcolor='lightgray')
    return fig

st.title("Inventory Policy Simulator")

# ------------------------------------------------
# Sidebar Inputs
# ------------------------------------------------
st.sidebar.header("Inventory Inputs")

reorder_point = st.sidebar.number_input("Reorder Point", value=200)[cite: 1]

# Set opening balance default based on the reorder point
opening_balance = st.sidebar.number_input("Opening Balance", value=int(1.25 * reorder_point))

st.sidebar.subheader("Demand Variability")
dist_type = st.sidebar.selectbox("Distribution Type", ["Normal", "Uniform"])

if dist_type == "Normal":
    avg_demand = st.sidebar.number_input("Average Demand", value=25)[cite: 1]
    std_dev = st.sidebar.number_input("Standard Deviation", value=15.0)
else:
    min_demand = st.sidebar.number_input("Minimum Demand", value=5)
    max_demand = st.sidebar.number_input("Maximum Demand", value=45)
    avg_demand = (min_demand + max_demand) / 2  # Used for EOQ estimation

lead_time = st.sidebar.number_input("Lead Time (Days)", value=3)[cite: 1]
order_qty = st.sidebar.number_input("Order Quantity", value=300)[cite: 1]
unit_value = st.sidebar.number_input("Value Per Unit", value=100)[cite: 1]
holding_cost_percent = st.sidebar.number_input("Holding Cost (% of Inventory Value)", value=20.0)[cite: 1]
ordering_cost = st.sidebar.number_input("Ordering Cost Per Order", value=500)[cite: 1]
num_days = st.sidebar.slider("Simulation Days", 100, 2000, 365)[cite: 1]

holding_cost_rate = holding_cost_percent / 100[cite: 1]

st.sidebar.divider()
include_pipeline = st.sidebar.checkbox("Include Pipeline Inventory in KPIs", value=False)

# ------------------------------------------------
# Demand Generation
# ------------------------------------------------
if "demand_sequence" not in st.session_state:
    st.session_state.demand_sequence = None

if st.button("Reset Demand Scenario"):[cite: 1]
    st.session_state.demand_sequence = None[cite: 1]

if st.session_state.demand_sequence is None:[cite: 1]
    if dist_type == "Normal":
        st.session_state.demand_sequence = np.maximum(0, np.random.normal(avg_demand, std_dev, num_days)).round()
    else:
        st.session_state.demand_sequence = np.random.randint(min_demand, max_demand + 1, num_days)

demand = st.session_state.demand_sequence[cite: 1]
dates = pd.date_range(start="2024-01-01", periods=num_days)[cite: 1]

# ------------------------------------------------
# Inventory Simulation
# ------------------------------------------------
inventory = opening_balance[cite: 1]
pipeline_orders = [][cite: 1]
data = [][cite: 1]

for day in range(num_days):[cite: 1]
    shipment_received = 0[cite: 1]

    for order in pipeline_orders.copy():[cite: 1]
        if order[0] == day:[cite: 1]
            shipment_received += order[1][cite: 1]
            pipeline_orders.remove(order)[cite: 1]

    opening = inventory[cite: 1]
    inventory += shipment_received[cite: 1]

    demand_today = demand[day][cite: 1]
    inventory -= demand_today[cite: 1]

    if inventory < 0:[cite: 1]
        inventory = 0[cite: 1]

    pipeline_qty = sum(qty for arrival, qty in pipeline_orders)[cite: 1]
    inventory_position = opening - demand_today + shipment_received + pipeline_qty[cite: 1]

    new_order = 0[cite: 1]
    if inventory_position < reorder_point:[cite: 1]
        new_order = order_qty[cite: 1]
        pipeline_orders.append((day + lead_time, order_qty))[cite: 1]

    closing = inventory[cite: 1]
    closing_with_pipeline = closing + sum(qty for arrival, qty in pipeline_orders)[cite: 1]

    data.append([
        dates[day], opening, demand_today, shipment_received, 
        pipeline_qty, inventory_position, new_order, closing, closing_with_pipeline
    ])[cite: 1]

df = pd.DataFrame(data, columns=[
    "Date", "Opening Balance", "Demand", "Shipment Received", 
    "Pipeline Order", "Inventory Position", "New Order", 
    "Closing Balance", "Closing Balance Including Pipeline"
])[cite: 1]

# ------------------------------------------------
# Toggle Logic for Display
# ------------------------------------------------
display_col = "Closing Balance Including Pipeline" if include_pipeline else "Closing Balance"

# ------------------------------------------------
# KPI Calculations & Display
# ------------------------------------------------
st.subheader("Inventory KPIs")
c1, c2, c3, c4 = st.columns(4)

stockout_days = (df["Closing Balance"] == 0).sum()[cite: 1]
average_inventory = df[display_col].mean()
average_age_inventory = average_inventory / df["Demand"].mean()[cite: 1]

df["Blocked Working Capital"] = df[display_col] * unit_value

c1.metric("Stockout Days", stockout_days)[cite: 1]
c2.metric("Average Age of Inventory", round(average_age_inventory, 1))[cite: 1]
c3.metric(f"Avg Inventory ({'Total' if include_pipeline else 'Physical'})", round(average_inventory, 0))
c4.metric("Avg Working Capital", round(df["Blocked Working Capital"].mean(), 0))[cite: 1]

# ------------------------------------------------
# Inventory Behaviour Chart
# ------------------------------------------------
st.subheader("Inventory Behaviour")

fig = go.Figure()[cite: 1]
fig.add_trace(go.Scatter(x=df["Date"], y=df["Closing Balance"], name="Closing Inventory", line=dict(color='blue')))

if include_pipeline:
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Closing Balance Including Pipeline"], name="Inventory Position", line=dict(color='lightblue', dash='dash')))

fig.add_hline(y=reorder_point, line_dash="dash", line_color="black", annotation_text="Reorder Point")[cite: 1]

# Stockout markers
stockouts = df[df["Closing Balance"] == 0][cite: 1]
fig.add_trace(go.Scatter(
    x=stockouts["Date"], y=stockouts["Closing Balance"],[cite: 1]
    mode="markers", name="Stockout", marker=dict(color="red", size=9)[cite: 1]
))[cite: 1]

fig = style_plotly_fig(fig)
st.plotly_chart(fig, use_container_width=True)[cite: 1]
