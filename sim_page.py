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

st.title("Inventory Policy Simulator (with Backorders)")

# ------------------------------------------------
# Sidebar Inputs
# ------------------------------------------------
st.sidebar.header("Inventory Inputs")

reorder_point = st.sidebar.number_input("Reorder Point", value=200)
opening_balance = st.sidebar.number_input("Opening Balance", value=int(1.25 * reorder_point))

st.sidebar.subheader("Backorder Policy")
max_wait_time = st.sidebar.number_input("Max Customer Wait Time (Days)", value=5, min_value=0, help="0 means no backorders allowed (instant lost sales).")

st.sidebar.subheader("Demand Variability")
dist_type = st.sidebar.selectbox("Distribution Type", ["Normal", "Uniform"])

if dist_type == "Normal":
    avg_demand = st.sidebar.number_input("Average Demand", value=25)
    std_dev = st.sidebar.number_input("Standard Deviation", value=15.0)
else:
    min_demand = st.sidebar.number_input("Minimum Demand", value=5)
    max_demand = st.sidebar.number_input("Maximum Demand", value=45)
    avg_demand = (min_demand + max_demand) / 2

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
# Inventory Simulation with Backorders
# ------------------------------------------------
inventory = opening_balance
pipeline_orders = []
backorder_queue = [] # Structure: [{'qty': amount, 'day_created': day}]
data = []

total_demand_overall = 0
total_lost_sales = 0

for day in range(num_days):
    demand_today = demand[day]
    total_demand_overall += demand_today
    
    # 1. Expire unfulfilled backorders based on max wait time
    active_backorders = []
    for bo in backorder_queue:
        if (day - bo['day_created']) > max_wait_time:
            total_lost_sales += bo['qty']
        else:
            active_backorders.append(bo)
    backorder_queue = active_backorders

    # 2. Receive shipments
    shipment_received = 0
    for order in pipeline_orders.copy():
        if order[0] == day:
            shipment_received += order[1]
            pipeline_orders.remove(order)

    # 3. Fulfill existing backorders first with received shipment (FIFO)
    while shipment_received > 0 and backorder_queue:
        if shipment_received >= backorder_queue[0]['qty']:
            shipment_received -= backorder_queue[0]['qty']
            backorder_queue.pop(0)
        else:
            backorder_queue[0]['qty'] -= shipment_received
            shipment_received = 0

    opening_phys = inventory
    inventory += shipment_received # Physical inventory updates

    # 4. Process today's demand
    if inventory >= demand_today:
        inventory -= demand_today
    else:
        unmet = demand_today - inventory
        inventory = 0
        if max_wait_time > 0:
            backorder_queue.append({'qty': unmet, 'day_created': day})
        else:
            total_lost_sales += unmet

    # Calculate Current Metrics
    current_backorders = sum(bo['qty'] for bo in backorder_queue)
    net_inventory = inventory - current_backorders
    pipeline_qty = sum(qty for arrival, qty in pipeline_orders)
    inventory_position = net_inventory + pipeline_qty # Ordering logic uses Net Inventory

    # 5. Order Triggers
    new_order = 0
    if inventory_position < reorder_point:
        new_order = order_qty
        pipeline_orders.append((day + lead_time, order_qty))

    closing_net_with_pipeline = net_inventory + pipeline_qty

    data.append([
        dates[day], opening_phys, demand_today, shipment_received, 
        current_backorders, net_inventory, inventory, pipeline_qty, 
        inventory_position, new_order, closing_net_with_pipeline
    ])

df = pd.DataFrame(data, columns=[
    "Date", "Opening Physical", "Demand", "Shipment Received", 
    "Active Backorders", "Net Inventory", "Physical Inventory", "Pipeline Order", 
    "Inventory Position", "New Order", "Closing Net Including Pipeline"
])

# ------------------------------------------------
# KPI Calculations & Display
# ------------------------------------------------
st.subheader("Inventory & Service KPIs")

display_col = "Closing Net Including Pipeline" if include_pipeline else "Net Inventory"
stockout_days = (df["Physical Inventory"] == 0).sum()
average_inventory = df["Physical Inventory"].mean() if not include_pipeline else df["Closing Net Including Pipeline"].mean()
average_age_inventory = df["Physical Inventory"].mean() / df["Demand"].mean()

df["Blocked Working Capital"] = df["Physical Inventory"] * unit_value
fill_rate = ((total_demand_overall - total_lost_sales) / total_demand_overall) * 100 if total_demand_overall > 0 else 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("Fill Rate", f"{round(fill_rate, 2)}%")
c2.metric("Stockout Days", stockout_days)
c3.metric(f"Avg Inventory ({'Total' if include_pipeline else 'Physical'})", round(average_inventory, 1))
c4.metric("Average Backorders", round(df["Active Backorders"].mean(), 1))

st.subheader("Financial & Range Metrics")
r1, r2, r3, r4 = st.columns(4)

min_inventory = df[display_col].min()
max_inventory = df[display_col].max()
avg_wc = df["Blocked Working Capital"].mean()
max_wc = df["Blocked Working Capital"].max()

r1.metric("Min Net Inventory", round(min_inventory, 1))
r2.metric("Max Net Inventory", round(max_inventory, 1))
r3.metric("Average Working Capital", round(avg_wc, 1))
r4.metric("Maximum Working Capital", round(max_wc, 1))

# ------------------------------------------------
# Inventory Behaviour Chart
# ------------------------------------------------
st.subheader("Inventory Behaviour")

fig = go.Figure()

# Net Inventory (Can go below zero - red/orange dashed line)
fig.add_trace(go.Scatter(
    x=df["Date"], 
    y=df["Net Inventory"], 
    name="Net Inventory (Includes Backorders)", 
    line=dict(color='orange', width=2, dash='dash')
))

# Physical Inventory (Stops at zero - solid blue line)
fig.add_trace(go.Scatter(
    x=df["Date"], 
    y=df["Physical Inventory"], 
    name="Physical Inventory", 
    line=dict(color='skyblue', width=2)
))

if include_pipeline:
    fig.add_trace(go.Scatter(
        x=df["Date"], 
        y=df["Closing Net Including Pipeline"], 
        name="Inventory Position", 
        line=dict(color='#1f77b4', width=2) 
    ))

reorders = df[df["New Order"] > 0]
fig.add_trace(go.Scatter(
    x=reorders["Date"],
    y=reorders["Physical Inventory"],
    mode="markers",
    name="Reorder Trigger",
    marker=dict(color="green", symbol="triangle-up", size=10)
))

stockouts = df[df["Physical Inventory"] == 0]
fig.add_trace(go.Scatter(
    x=stockouts["Date"], 
    y=stockouts["Physical Inventory"],
    mode="markers", 
    name="Stockout", 
    marker=dict(color="red", symbol="triangle-up", size=10)
))

fig.add_hline(
    y=reorder_point, 
    line_dash="dash", 
    line_color="gray", 
    annotation_text="Reorder Point", 
    annotation_font_color="white"
)

# Zero Line reference
fig.add_hline(y=0, line_color="red", line_width=1)

max_y = df["Closing Net Including Pipeline"].max() * 1.2 if include_pipeline else df["Physical Inventory"].max() * 1.2
fig.add_hrect(y0=0, y1=reorder_point*0.5, fillcolor="red", opacity=0.1)
fig.add_hrect(y0=reorder_point*0.5, y1=reorder_point, fillcolor="yellow", opacity=0.1)
fig.add_hrect(y0=reorder_point, y1=max_y, fillcolor="green", opacity=0.05)

fig.update_layout(
    plot_bgcolor='#0E1117',
    paper_bgcolor='#0E1117',
    font=dict(color='white'),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')

st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------
# Simulation Data Table
# ------------------------------------------------
st.subheader("Simulation Data")
st.dataframe(df, use_container_width=True)
