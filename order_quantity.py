import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Order Quantity Optimization", layout="wide")

# Styling function
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

st.title("Order Quantity & Cost Simulation")
st.markdown("Calculate the theoretical Economic Order Quantity (EOQ) under deterministic conditions, then simulate real-world cost distributions resulting from demand variability.")

# =====================================================================
# SECTION 1: Inputs & Deterministic EOQ
# =====================================================================
st.header("1. Cost Parameters & EOQ Calculation")

c1, c2, c3 = st.columns(3)

with c1:
    st.subheader("Ordering Costs")
    fixed_order_cost = st.number_input("Fixed Cost Per Order ($)", value=500.0, step=50.0)
    var_order_cost = st.number_input("Variable Cost Per Piece ($)", value=2.0, step=0.5, help="E.g., per-unit freight or handling.")

with c2:
    st.subheader("Holding Costs")
    cost_of_capital = st.number_input("Cost of Capital (%)", value=12.0, step=1.0)
    other_holding = st.number_input("Other Holding Costs (%)", value=8.0, step=1.0, help="E.g., storage, insurance, shrinkage.")
    unit_value = st.number_input("Base Unit Value ($)", value=100.0, step=10.0)

with c3:
    st.subheader("Demand Profile")
    avg_demand = st.number_input("Average Daily Demand", value=50.0, step=5.0)
    std_demand = st.number_input("Demand Standard Deviation", value=15.0, step=1.0)
    lead_time = st.number_input("Lead Time (Days)", value=5, step=1)

# EOQ Math
annual_demand = avg_demand * 365
effective_unit_cost = unit_value + var_order_cost
annual_holding_rate = (cost_of_capital + other_holding) / 100.0
H = effective_unit_cost * annual_holding_rate
S = fixed_order_cost

eoq = 0
if H > 0:
    eoq = np.sqrt((2 * annual_demand * S) / H)

st.info(f"**Deterministic EOQ:** {int(eoq)} Units (Assumes zero variation and smooth annual demand of {int(annual_demand):,} units)")

st.divider()

# =====================================================================
# SECTION 2: Stochastic Simulation (Cost Distribution)
# =====================================================================
st.header("2. Stochastic Cost Simulation")
st.markdown("Simulate 365-day periods across multiple iterations to evaluate the distribution of total annual inventory costs.")

sc1, sc2, sc3, sc4 = st.columns(4)
with sc1:
    sim_order_qty = st.number_input("Simulation Order Quantity", value=int(eoq) if eoq > 0 else 500, step=50)
with sc2:
    sim_rop = st.number_input("Reorder Point (ROP)", value=int(avg_demand * lead_time + (1.645 * std_demand * np.sqrt(lead_time))), step=10)
with sc3:
    num_runs = st.number_input("Number of Simulation Runs", value=200, min_value=10, max_value=1000, step=50, help="Higher runs provide better distributions but take longer to calculate.")
with sc4:
    st.write("<br>", unsafe_allow_html=True)
    include_pipeline = st.checkbox("Include Pipeline in Avg Inventory", value=False)

# --- Execute Simulation ---
if st.button("🚀 Run Cost Simulation", use_container_width=True, type="primary"):
    with st.spinner(f"Simulating {num_runs} independent years of inventory behavior..."):
        
        np.random.seed(42)
        # Pre-generate matrix of demand profiles for performance
        demand_matrix = np.clip(np.random.normal(avg_demand, std_demand, (num_runs, 365)), 0, None).round()
        
        sim_results = []
        
        for run in range(num_runs):
            demand_profile = demand_matrix[run]
            inventory = sim_rop + sim_order_qty # Start with healthy inventory
            pipeline = []
            
            daily_inv_levels = np.zeros(365)
            orders_placed = 0
            
            for day in range(365):
                # Receive orders
                received = sum(qty for arr, qty in pipeline if arr == day)
                pipeline = [(arr, qty) for arr, qty in pipeline if arr > day]
                
                inventory += received
                inventory -= demand_profile[day]
                if inventory < 0: 
                    inventory = 0
                    
                pipeline_qty = sum(qty for arr, qty in pipeline)
                inv_position = inventory + pipeline_qty
                
                if inv_position < sim_rop:
                    pipeline.append((day + lead_time, sim_order_qty))
                    orders_placed += 1
                
                daily_inv_levels[day] = (inventory + pipeline_qty) if include_pipeline else inventory

            avg_inventory_year = np.mean(daily_inv_levels)
            
            # Calculate annual costs for this specific run
            run_holding_cost = avg_inventory_year * H
            run_fixed_ordering = orders_placed * S
            run_var_ordering = (orders_placed * sim_order_qty) * var_order_cost
            total_annual_cost = run_holding_cost + run_fixed_ordering + run_var_ordering
            
            sim_results.append(total_annual_cost)
            
        st.session_state.sim_costs = sim_results

# --- Display Results ---
if "sim_costs" in st.session_state:
    costs = st.session_state.sim_costs
    min_cost = min(costs)
    max_cost = max(costs)
    avg_cost = np.mean(costs)
    
    st.markdown("### Total Annual Cost Distribution")
    metric_c1, metric_c2, metric_c3 = st.columns(3)
    metric_c1.metric("Min Simulated Cost", f"${min_cost:,.0f}")
    metric_c2.metric("Average Simulated Cost", f"${avg_cost:,.0f}")
    metric_c3.metric("Max Simulated Cost", f"${max_cost:,.0f}")
    
    # Histogram Control
    bin_width = st.slider("Adjust Histogram Bin Width ($)", min_value=100, max_value=5000, value=1000, step=100)
    
    # Create specific bin edges based on user width
    b_min = np.floor(min_cost / bin_width) * bin_width
    b_max = np.ceil(max_cost / bin_width) * bin_width
    bins = np.arange(b_min, b_max + bin_width, bin_width)
    
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=costs, 
        xbins=dict(start=b_min, end=b_max, size=bin_width),
        marker_color='skyblue',
        opacity=0.8
    ))
    
    fig.update_layout(
        xaxis_title="Total Annual Cost ($)", 
        yaxis_title="Frequency (Number of Runs)",
        bargap=0.05
    )
    fig = style_plotly_fig(fig)
    st.plotly_chart(fig, use_container_width=True)
    
    # Frequency Table Generation
    counts, edges = np.histogram(costs, bins=bins)
    freq_df = pd.DataFrame({
        "Bin Start ($)": np.round(edges[:-1], 2),
        "Bin End ($)": np.round(edges[1:], 2),
        "Absolute Count": counts
    })
    
    total_runs = counts.sum()
    if total_runs > 0:
        freq_df["% of Total"] = np.round((freq_df["Absolute Count"] / total_runs) * 100, 2)
        freq_df["Cumulative %"] = np.round(freq_df["% of Total"].cumsum(), 2)
    else:
        freq_df["% of Total"] = 0.0
        freq_df["Cumulative %"] = 0.0
        
    freq_df["% of Total"] = freq_df["% of Total"].astype(str) + "%"
    freq_df["Cumulative %"] = freq_df["Cumulative %"].astype(str) + "%"
    
    st.markdown("### Cost Frequency Distribution Table")
    st.dataframe(freq_df.style.format({"Bin Start ($)": "{:,.0f}", "Bin End ($)": "{:,.0f}"}), use_container_width=True, hide_index=True)
