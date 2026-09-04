import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# Minimalist styling function for charts
def style_plotly_fig(fig):
    fig.update_layout(
        plot_bgcolor='#0E1117',
        paper_bgcolor='#0E1117',
        font=dict(color='white'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    fig.update_xaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b')
    fig.update_yaxes(showline=True, linewidth=1, linecolor='gray', gridcolor='#2b2b2b', rangemode="tozero")
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
    daily_lost_sales = 0 # Track lost sales for this specific day
    
    # 1. Expire unfulfilled backorders based on max wait time
    active_backorders = []
    for bo in backorder_queue:
        if (day - bo['day_created']) > max_wait_time:
            daily_lost_sales += bo['qty']
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
            daily_lost_sales += unmet
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
        inventory_position, new_order, closing_net_with_pipeline, daily_lost_sales
    ])

df = pd.DataFrame(data, columns=[
    "Date", "Opening Physical", "Demand", "Shipment Received", 
    "Active Backorders", "Net Inventory", "Physical Inventory", "Pipeline Order", 
    "Inventory Position", "New Order", "Closing Net Including Pipeline", "Daily Lost Sales"
])

# ------------------------------------------------
# KPI Calculations & Display
# ------------------------------------------------
st.subheader("Inventory & Service KPIs")

display_col = "Closing Net Including Pipeline" if include_pipeline else "Net Inventory"

# Now we define stockout days strictly as days where we LOST a sale
stockout_days = (df["Daily Lost Sales"] > 0).sum()
average_inventory = df["Physical Inventory"].mean() if not include_pipeline else df["Closing Net Including Pipeline"].mean()
average_age_inventory = df["Physical Inventory"].mean() / df["Demand"].mean()

df["Blocked Working Capital"] = df["Physical Inventory"] * unit_value
fill_rate = ((total_demand_overall - total_lost_sales) / total_demand_overall) * 100 if total_demand_overall > 0 else 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("Fill Rate", f"{round(fill_rate, 2)}%")
c2.metric("Lost Sale Days (Stockouts)", stockout_days)
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
# Data Visualizations
# ------------------------------------------------
st.subheader("Inventory & Demand Behaviour")

st.markdown("### Physical Inventory")
# Graph 1: Physical Inventory (Stops at 0, only marks actual lost sales)
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Date"], y=df["Physical Inventory"], name="Physical Inventory", line=dict(color='skyblue', width=2)))

reorders = df[df["New Order"] > 0]
fig1.add_trace(go.Scatter(x=reorders["Date"], y=reorders["Physical Inventory"], mode="markers", name="Reorder Trigger", marker=dict(color="green", symbol="triangle-up", size=10)))

actual_stockouts = df[df["Daily Lost Sales"] > 0]
fig1.add_trace(go.Scatter(x=actual_stockouts["Date"], y=actual_stockouts["Physical Inventory"], mode="markers", name="Lost Sale (Stockout)", marker=dict(color="red", symbol="triangle-up", size=10)))

fig1.add_hline(y=reorder_point, line_dash="dash", line_color="gray", annotation_text="Reorder Point", annotation_font_color="white")

max_y = df["Physical Inventory"].max() * 1.2
fig1.add_hrect(y0=0, y1=reorder_point*0.5, fillcolor="red", opacity=0.1)
fig1.add_hrect(y0=reorder_point*0.5, y1=reorder_point, fillcolor="yellow", opacity=0.1)
fig1.add_hrect(y0=reorder_point, y1=max_y, fillcolor="green", opacity=0.05)

fig1 = style_plotly_fig(fig1)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

st.markdown("### Total Inventory (Physical + Pipeline)")
# Graph 2: Total Inventory
fig_total = go.Figure()
fig_total.add_trace(go.Scatter(x=df["Date"], y=df["Physical Inventory"], name="Physical Inventory", line=dict(color='skyblue', width=2, dash='dot')))
fig_total.add_trace(go.Scatter(x=df["Date"], y=df["Physical Inventory"] + df["Pipeline Order"], name="Total Inventory", line=dict(color='teal', width=2)))
fig_total.add_hline(y=reorder_point, line_dash="dash", line_color="gray", annotation_text="Reorder Point", annotation_font_color="white")
fig_total = style_plotly_fig(fig_total)
st.plotly_chart(fig_total, use_container_width=True)

st.divider()

st.markdown("### Net Inventory")
# Graph 3: Net Inventory (Can drop below 0)
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["Date"], y=df["Net Inventory"], name="Net Inventory (Includes Backorders)", line=dict(color='orange', width=2)))

if include_pipeline:
    fig2.add_trace(go.Scatter(x=df["Date"], y=df["Closing Net Including Pipeline"], name="Inventory Position", line=dict(color='#1f77b4', width=2)))

# Add Reorder Triggers to the Net Inventory line
reorders = df[df["New Order"] > 0]
fig2.add_trace(go.Scatter(
    x=reorders["Date"], 
    y=reorders["Net Inventory"], 
    mode="markers", 
    name="Reorder Trigger", 
    marker=dict(color="green", symbol="triangle-up", size=10)
))

# Add stockout markers to the Net Inventory line
actual_stockouts = df[df["Daily Lost Sales"] > 0]
fig2.add_trace(go.Scatter(
    x=actual_stockouts["Date"], 
    y=actual_stockouts["Net Inventory"], 
    mode="markers", 
    name="Lost Sale (Stockout)", 
    marker=dict(color="red", symbol="triangle-up", size=10)
))
    
fig2.add_hline(y=reorder_point, line_dash="dash", line_color="gray", annotation_text="Reorder Point", annotation_font_color="white")
fig2.add_hline(y=0, line_color="red", line_width=1) # Zero line reference

fig2 = style_plotly_fig(fig2)
# Net inventory chart shouldn't strictly range to zero on the Y axis because it goes negative
fig2.update_yaxes(rangemode="normal") 
st.plotly_chart(fig2, use_container_width=True)
st.divider()

st.markdown("### Lost Sales (Stockouts)")
# Graph 4: Lost Sales (Stockout Quantity)
fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=df["Date"], y=df["Daily Lost Sales"], name="Lost Sales Qty", line=dict(color='red', width=2), fill='tozeroy', fillcolor='rgba(255,0,0,0.1)'))
fig3 = style_plotly_fig(fig3)
st.plotly_chart(fig3, use_container_width=True)

st.divider()

st.markdown("### Active Backorders")
# Graph 5: Active Backorders
fig4 = go.Figure()
fig4.add_trace(go.Scatter(x=df["Date"], y=df["Active Backorders"], name="Active Backorders", line=dict(color='#ffaa00', width=2), fill='tozeroy', fillcolor='rgba(255,170,0,0.1)'))
fig4 = style_plotly_fig(fig4)
st.plotly_chart(fig4, use_container_width=True)

st.divider()

st.markdown("### Pipeline Orders")
# Graph 6: Pipeline Orders
fig5 = go.Figure()
fig5.add_trace(go.Scatter(x=df["Date"], y=df["Pipeline Order"], name="Pipeline Qty", line=dict(color='purple', width=2), fill='tozeroy', fillcolor='rgba(128,0,128,0.1)'))
fig5 = style_plotly_fig(fig5)
st.plotly_chart(fig5, use_container_width=True)

st.divider()

# ------------------------------------------------
# Simulation Data Table
# ------------------------------------------------

st.subheader("Simulation Data")
st.dataframe(df, use_container_width=True)
