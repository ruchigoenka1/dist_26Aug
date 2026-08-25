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

reorder_point = st.sidebar.number_input("Reorder Point", value=200)

# Set opening balance default based on the reorder point
opening_balance = st.sidebar.number_input("Opening Balance", value=int(1.25 * reorder_point))

st.sidebar.subheader("Demand Variability")
dist_type = st.sidebar.selectbox("Distribution Type", ["Normal", "Uniform"])

if dist_type == "Normal":
    avg_demand = st.sidebar.number_input("Average Demand", value=25)
    std_dev = st.sidebar.number_input("Standard Deviation", value=15.0)
else:
    min_demand = st.sidebar.number_input("Minimum Demand", value=5)
    max_demand = st.sidebar.number_input("Maximum Demand", value=45)
    avg_demand = (min_demand + max_demand) / 2  # Used for EOQ estimation

lead_time = st.sidebar.number_input("Lead Time (Days)", value=3)
order_qty = st.sidebar.number_input("Order Quantity", value=300)
unit_value = st.sidebar.number_input("Value Per Unit", value=100)
holding_cost_percent = st.sidebar.number_input("Holding Cost (% of Inventory Value)", value=20.0)
ordering_cost = st.sidebar.number_input("Ordering Cost Per Order", value=500)
num_days = st.sidebar.slider("Simulation Days", 100, 2000, 365)

holding_cost_rate = holding_cost_percent / 100

st.sidebar.divider()
include_pipeline = st.sidebar.checkbox("Include Pipeline Inventory in KPIs", value=False)

# ------------------------------------------------
# Demand Generation
# ------------------------------------------------
if "demand_sequence" not in st.session_state:
    st.session_state.demand_sequence = None

if st.button("Reset Demand Scenario"):
    st.session_state.demand_sequence = None

if st.session_state.demand_sequence is None:
    if dist_type == "Normal":
        st.session_state.demand_sequence = np.maximum(0, np.random.normal(avg_demand, std_dev, num_days)).round()
    else:
        st.session_state.demand_sequence = np.random.randint(min_demand, max_demand + 1, num_days)

demand = st.session_state.demand_sequence
dates = pd.date_range(start="2024-01-01", periods=num_days)

# ------------------------------------------------
# Inventory Simulation
# ------------------------------------------------
inventory = opening_balance
pipeline_orders = []
data = []

for day in range(num_days):
    shipment_received = 0

    for order in pipeline_orders.copy():
        if order[0] == day:
            shipment_received += order[1]
            pipeline_orders.remove(order)

    opening = inventory
    inventory += shipment_received

    demand_today = demand[day]
    inventory -= demand_today

    if inventory < 0:
        inventory = 0

    pipeline_qty = sum(qty for arrival, qty in pipeline_orders)
    inventory_position = opening - demand_today + shipment_received + pipeline_qty

    new_order = 0
    if inventory_position < reorder_point:
        new_order = order_qty
        pipeline_orders.append((day + lead_time, order_qty))

    closing = inventory
    closing_with_pipeline = closing + sum(qty for arrival, qty in pipeline_orders)

    data.append([
        dates[day], opening, demand_today, shipment_received, 
        pipeline_qty, inventory_position, new_order, closing, closing_with_pipeline
    ])

df = pd.DataFrame(data, columns=[
    "Date", "Opening Balance", "Demand", "Shipment Received", 
    "Pipeline Order", "Inventory Position", "New Order", 
    "Closing Balance", "Closing Balance Including Pipeline"
])

# ------------------------------------------------
# Toggle Logic for Display
# ------------------------------------------------
display_col = "Closing Balance Including Pipeline" if include_pipeline else "Closing Balance"

# ------------------------------------------------
# KPI Calculations & Display
# ------------------------------------------------
st.subheader("Inventory KPIs")
c1, c2, c3, c4 = st.columns(4)

stockout_days = (df["Closing Balance"] == 0).sum()
average_inventory = df[display_col].mean()
average_age_inventory = average_inventory / df["Demand"].mean()

df["Blocked Working Capital"] = df[display_col] * unit_value

c1.metric("Stockout Days", stockout_days)
c2.metric("Average Age of Inventory", round(average_age_inventory, 1))
c3.metric(f"Avg Inventory ({'Total' if include_pipeline else 'Physical'})", round(average_inventory, 0))
c4.metric("Avg Working Capital", round(df["Blocked Working Capital"].mean(), 0))

# ------------------------------------------------
# Inventory Behaviour Chart
# ------------------------------------------------
st.subheader("Inventory Behaviour")

fig = go.Figure()

# Closing Inventory (Light blue to stand out on dark background)
fig.add_trace(go.Scatter(
    x=df["Date"], 
    y=df["Closing Balance"], 
    name="Closing Inventory", 
    line=dict(color='skyblue', width=2)
))

# Inventory Position (Standard blue, shown if toggled on)
if include_pipeline:
    fig.add_trace(go.Scatter(
        x=df["Date"], 
        y=df["Closing Balance Including Pipeline"], 
        name="Inventory Position", 
        line=dict(color='#1f77b4', width=2) 
    ))

# Add Reorder Trigger markers (Green triangles)
reorders = df[df["New Order"] > 0]
fig.add_trace(go.Scatter(
    x=reorders["Date"],
    y=reorders["Closing Balance"],
    mode="markers",
    name="Reorder Trigger",
    marker=dict(color="green", symbol="triangle-up", size=10)
))

# Stockout markers
stockouts = df[df["Closing Balance"] == 0]
fig.add_trace(go.Scatter(
    x=stockouts["Date"], 
    y=stockouts["Closing Balance"],
    mode="markers", 
    name="Stockout", 
    marker=dict(color="red", symbol="triangle-up", size=7) # Added triangle symbol and reduced size
))

# Reorder Point Line
fig.add_hline(
    y=reorder_point, 
    line_dash="dash", 
    line_color="gray", 
    annotation_text="Reorder Point", 
    annotation_font_color="white"
)

# Colored background zones (Red, Yellow, Green)
max_y = df["Closing Balance Including Pipeline"].max() * 1.2 if include_pipeline else df["Closing Balance"].max() * 1.2
fig.add_hrect(y0=0, y1=reorder_point*0.5, fillcolor="red", opacity=0.1)
fig.add_hrect(y0=reorder_point*0.5, y1=reorder_point, fillcolor="yellow", opacity=0.1)
fig.add_hrect(y0=reorder_point, y1=max_y, fillcolor="green", opacity=0.05)

# Force black/dark background and styling for this specific chart
fig.update_layout(
    plot_bgcolor='#0E1117', # Dark background matching Streamlit's dark mode
    paper_bgcolor='#0E1117',
    font=dict(color='white'),
    legend=dict(
        orientation="v",
        yanchor="top",
        y=1,
        xanchor="left",
        x=1.02
    )
)

fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")

st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------
# Simulation Data Table
# ------------------------------------------------
st.subheader("Simulation Data")

# Display the dataframe; it will automatically adapt to Streamlit's dark mode
st.dataframe(df, use_container_width=True)
