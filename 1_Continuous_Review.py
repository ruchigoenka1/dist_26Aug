import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Continuous Review Policy", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-left: 2rem;
        padding-right: 2rem;
        padding-top: 2rem;
    }
    [data-testid="column"]:first-child {
        border-right: 1px solid rgba(255, 255, 255, 0.1);
        padding-right: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.header("Continuous Review")
st.divider()

# Main split layout
input_col, output_col = st.columns([1, 3])

# ================================================
# LEFT PANEL: INPUTS
# ================================================
with input_col:
    st.subheader("⚙️ Parameters")
    
    st.markdown("**Basic Settings**")
    opening_balance = st.number_input("Opening Balance", value=500, key="sim_ob_t4")
    unit_value = st.number_input("Value Per Unit", value=100, key="sim_vu_t4")
    num_days = st.slider("Simulation Days", 100, 2000, 365, key="sim_nd_t4")
    
    st.markdown("**Demand Settings**")
    avg_demand = st.number_input("Average Demand", value=25, key="sim_ad_t4")
    cov = st.number_input("Demand CoV", value=0.8, key="sim_cov_t4")
    
    if "demand_sequence_tab4" not in st.session_state:
        st.session_state.demand_sequence_tab4 = None

    if st.button("🔄 Generate New Demand", key="reset_dem_t4", use_container_width=True):
        st.session_state.demand_sequence_tab4 = None
        
    st.markdown("**Policy Settings**")
    lead_time = st.number_input("Lead Time (Days)", value=3, key="sim_lt_t4")
    reorder_point = st.number_input("Reorder Point", value=200, key="sim_rp_t4")
    order_qty = st.number_input("Order Quantity", value=300, key="sim_oq_t4")
    
    st.markdown("**Cost Metrics**")
    holding_cost_percent = st.number_input("Holding Cost (%)", value=20.0, key="sim_hc_t4")
    ordering_cost = st.number_input("Ordering Cost / Order", value=500, key="sim_oc_t4")

# ================================================
# BACKGROUND CALCULATIONS
# ================================================
holding_cost_rate = holding_cost_percent / 100
std_demand = avg_demand * cov

if st.session_state.demand_sequence_tab4 is None:
    st.session_state.demand_sequence_tab4 = np.maximum(
        0,
        np.random.normal(avg_demand, std_demand, num_days)
    ).round()

demand = st.session_state.demand_sequence_tab4
dates = pd.date_range(start="2024-01-01", periods=num_days)

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
        dates[day], opening, demand_today, shipment_received, pipeline_qty,
        inventory_position, new_order, closing, closing_with_pipeline
    ])

df = pd.DataFrame(data, columns=[
    "Date", "Opening Balance", "Demand", "Shipment Received", "Pipeline Order",
    "Inventory Position", "New Order", "Closing Balance", "Closing Balance Including Pipeline"
])

# KPI logic execution
stockout_days = (df["Closing Balance"] == 0).sum()
average_inventory = df["Closing Balance Including Pipeline"].mean()
average_age_inventory = average_inventory / df["Demand"].mean() if df["Demand"].mean() > 0 else 0

df["Blocked Working Capital"] = df["Inventory Position"] * unit_value
average_working_capital = df["Blocked Working Capital"].mean()

min_inventory = df["Closing Balance"].min()
max_inventory = df["Closing Balance"].max()
min_wc = df["Blocked Working Capital"].min()
max_wc = df["Blocked Working Capital"].max()

df["Inventory Value"] = df["Closing Balance Including Pipeline"] * unit_value
df["Holding Cost"] = df["Inventory Value"] * holding_cost_rate / 365
total_holding_cost = df["Holding Cost"].sum()

number_of_orders = (df["New Order"] > 0).sum()
total_ordering_cost = number_of_orders * ordering_cost
total_inventory_cost = total_holding_cost + total_ordering_cost

annual_demand = avg_demand * 365
holding_cost_per_unit = unit_value * holding_cost_rate
eoq = np.sqrt((2 * annual_demand * ordering_cost) / holding_cost_per_unit) if holding_cost_per_unit > 0 else 0

def simulate_inventory_cost(order_quantity):
    sim_inv = opening_balance
    sim_pipeline = []
    holding_cost_total = 0
    orders_count = 0

    for day in range(num_days):
        shipment_rec = 0
        for order in sim_pipeline.copy():
            if order[0] == day:
                shipment_rec += order[1]
                sim_pipeline.remove(order)

        sim_inv += shipment_rec
        dem_today = demand[day]
        sim_inv -= dem_today

        if sim_inv < 0:
            sim_inv = 0

        pip_qty = sum(qty for arrival, qty in sim_pipeline)
        inv_pos = sim_inv + pip_qty

        if inv_pos < reorder_point:
            sim_pipeline.append((day + lead_time, order_quantity))
            orders_count += 1

        close_w_pip = sim_inv + sum(qty for arrival, qty in sim_pipeline)
        inv_val = close_w_pip * unit_value
        hold_cost_today = inv_val * holding_cost_rate / 365
        holding_cost_total += hold_cost_today

    order_cost_tot = orders_count * ordering_cost
    return holding_cost_total + order_cost_tot

cost_current_policy = simulate_inventory_cost(order_qty)
cost_eoq_policy = simulate_inventory_cost(int(eoq))


# ================================================
# RIGHT PANEL: OUTPUTS & DASHBOARD
# ================================================
with output_col:
    
    # Matrix Collapsible Section 1: Core KPIs
    with st.expander("📊 View Core Inventory & Financial Metrics", expanded=True):
        st.markdown("#### Primary KPIs")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Stockout Days", stockout_days)
        c2.metric("Avg Age of Inventory", round(average_age_inventory, 1))
        c3.metric("Average Inventory", round(average_inventory, 0))
        c4.metric("Avg Working Capital", f"${round(average_working_capital, 0):,}")

        st.markdown("#### Inventory & Capital Ranges")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Minimum Inventory", round(min_inventory, 0))
        r2.metric("Maximum Inventory", round(max_inventory, 0))
        r3.metric("Min Working Capital", f"${round(min_wc, 0):,}")
        r4.metric("Max Working Capital", f"${round(max_wc, 0):,}")

        st.markdown("#### Cost Metrics Breakdown")
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Total Holding Cost", f"${round(total_holding_cost, 0):,}")
        cc2.metric("Total Ordering Cost", f"${round(total_ordering_cost, 0):,}")
        cc3.metric("Total Inventory Cost", f"${round(total_inventory_cost, 0):,}")

    # Matrix Collapsible Section 2: Optimization
    with st.expander("💡 View EOQ & Policy Optimization", expanded=False):
        st.markdown("#### Economic Order Quantity (EOQ)")
        e1, e2 = st.columns(2)
        e1.metric("Economic Order Quantity (EOQ)", round(eoq, 0))
        e2.metric("Selected Order Quantity", order_qty)
        
        st.markdown("#### Policy Financial Comparison")
        k1, k2, k3 = st.columns(3)
        k1.metric("Cost with Current Policy", f"${round(cost_current_policy, 0):,}")
        k2.metric("Cost with EOQ Policy", f"${round(cost_eoq_policy, 0):,}")
        k3.metric("Savings Using EOQ", f"${round(cost_current_policy - cost_eoq_policy, 0):,}")

    # Main Behaviour Chart
    st.markdown("#### Inventory Behaviour")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Closing Balance"], name="Closing Inventory"))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Closing Balance Including Pipeline"], name="Inventory Position"))
    fig.add_hline(y=reorder_point, line_dash="dash", annotation_text="Reorder Point")

    stockouts = df[df["Closing Balance"] == 0]
    fig.add_trace(go.Scatter(x=stockouts["Date"], y=stockouts["Closing Balance"], mode="markers", name="Stockout", marker=dict(color="red", size=9)))

    reorders = df[df["New Order"] > 0]
    fig.add_trace(go.Scatter(x=reorders["Date"], y=reorders["Closing Balance"], mode="markers", name="Reorder Trigger", marker=dict(color="green", symbol="triangle-up", size=10)))

    fig.add_hrect(y0=0, y1=reorder_point*0.5, fillcolor="red", opacity=0.08)
    fig.add_hrect(y0=reorder_point*0.5, y1=reorder_point, fillcolor="yellow", opacity=0.08)
    fig.add_hrect(y0=reorder_point, y1=df["Closing Balance Including Pipeline"].max()*1.2, fillcolor="green", opacity=0.05)
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=400)
    fig.update_yaxes(rangemode="tozero")
    
    st.plotly_chart(fig, use_container_width=True)
    st.divider()

    # Secondary Charts (Grid Layout)
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("#### Blocked Working Capital")
        fig_wc = px.line(df, x="Date", y="Blocked Working Capital")
        fig_wc.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=280)
        st.plotly_chart(fig_wc, use_container_width=True)

        st.markdown("#### Demand Distribution")
        fig_hist = px.histogram(df, x="Demand", nbins=20)
        fig_hist.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=280)
        st.plotly_chart(fig_hist, use_container_width=True)

    with chart_col2:
        st.markdown("#### Pipeline Orders")
        fig_pipeline = px.line(df, x="Date", y="Pipeline Order")
        fig_pipeline.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=280)
        st.plotly_chart(fig_pipeline, use_container_width=True)

        st.markdown("#### Orders Placed")
        orders = df[df["New Order"] > 0]
        fig_orders = px.scatter(orders, x="Date", y="New Order")
        fig_orders.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=280)
        st.plotly_chart(fig_orders, use_container_width=True)

    st.divider()

    # Deep Dives (Expanders to conserve vertical space)
    with st.expander("📊 View Interactive Waterfall Analysis & Raw Data"):
        st.markdown("#### Inventory Flow Waterfall")
        selected_day = st.slider("Select Day for Waterfall Analysis", 0, len(df)-1, 0, key="waterfall_slider_t4")
        row = df.iloc[selected_day]

        fig_waterfall = go.Figure(go.Waterfall(
            measure=["absolute", "relative", "relative", "total"],
            x=["Opening Balance", "Demand", "Shipment Received", "Closing Balance"],
            y=[row["Opening Balance"], -row["Demand"], row["Shipment Received"], row["Closing Balance"]]
        ))
        fig_waterfall.update_layout(margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
        st.markdown("#### Simulation Output Table")
        st.dataframe(df, use_container_width=True)
