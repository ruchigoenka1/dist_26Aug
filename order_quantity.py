import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm

st.set_page_config(page_title="Order Quantity Optimization", layout="wide")

# Custom CSS to reduce metric font size and prevent text clipping
st.markdown("""
<style>
[data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
}
</style>
""", unsafe_allow_html=True)

# Styling function for dark mode
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
    st.subheader("Demand Profile & Policy")
    avg_demand = st.number_input("Average Daily Demand", value=50.0, step=5.0)
    std_demand = st.number_input("Demand Standard Deviation", value=15.0, step=1.0)
    lead_time = st.number_input("Lead Time (Days)", value=5, step=1)
    target_service_level = st.slider("Target Service Level (%)", min_value=50.0, max_value=99.9, value=95.0, step=0.1)

# EOQ & ROP Math
annual_demand = avg_demand * 365
effective_unit_cost = unit_value + var_order_cost
annual_holding_rate = (cost_of_capital + other_holding) / 100.0
H = effective_unit_cost * annual_holding_rate
S = fixed_order_cost

eoq = 0
total_eoq_cost = 0
if H > 0 and S > 0:
    eoq = np.sqrt((2 * annual_demand * S) / H)
    total_eoq_cost = (eoq / 2) * H + (annual_demand / eoq) * S + (annual_demand * var_order_cost)

z_score = norm.ppf(target_service_level / 100.0)
recommended_rop = (avg_demand * lead_time) + (z_score * std_demand * np.sqrt(lead_time))

st.success(f"✨ **Deterministic EOQ:** {int(eoq)} Units &nbsp; | &nbsp; **Recommended ROP ({target_service_level}%):** {int(recommended_rop)} Units &nbsp; | &nbsp; **Total Annual Cost:** ${total_eoq_cost:,.2f}")
st.caption("Note: The Total Annual Cost above assumes zero demand variation and perfectly smooth consumption over 365 days.")

st.divider()

# =====================================================================
# SECTION 2: Stochastic Simulation & Policy Comparison
# =====================================================================
st.header("2. Stochastic Cost Simulation (EOQ vs. Custom)")
st.markdown("Simulate 365-day periods to evaluate the actual cost distribution of your Custom Order Quantity against the theoretical EOQ baseline under volatile demand.")

sc1, sc2, sc3, sc4 = st.columns(4)
with sc1:
    custom_order_qty = st.number_input("Custom Order Quantity", value=int(eoq) if eoq > 0 else 500, step=50, help="Test a real-world batch size (e.g., supplier constraints).")
with sc2:
    sim_rop = st.number_input("Reorder Point (ROP)", value=int(recommended_rop), step=10)
with sc3:
    num_runs = st.number_input("Number of Simulation Runs", value=200, min_value=10, max_value=1000, step=50)
with sc4:
    st.write("<br>", unsafe_allow_html=True)
    include_pipeline = st.checkbox("Include Pipeline in Avg Inventory", value=False)

# --- Execute Parallel Simulations ---
if st.button("🚀 Run Comparative Simulation", use_container_width=True, type="primary"):
    with st.spinner(f"Simulating {num_runs} independent years..."):
        np.random.seed(42)
        demand_matrix = np.clip(np.random.normal(avg_demand, std_demand, (num_runs, 365)), 0, None).round()
        
        sim_results_custom = {"Total Cost": [], "Holding Cost": [], "Fixed Ordering Cost": [], "Variable Ordering Cost": []}
        sim_results_eoq = {"Total Cost": []}
        
        def simulate_year(qty_to_order):
            inventory = sim_rop + qty_to_order
            pipeline = []
            daily_inv = np.zeros(365)
            orders = 0
            
            for day in range(365):
                received = sum(qty for arr, qty in pipeline if arr == day)
                pipeline = [(arr, qty) for arr, qty in pipeline if arr > day]
                
                inventory += received
                inventory -= demand_profile[day]
                if inventory < 0: inventory = 0
                    
                pipeline_qty = sum(qty for arr, qty in pipeline)
                inv_position = inventory + pipeline_qty
                
                if inv_position < sim_rop:
                    pipeline.append((day + lead_time, qty_to_order))
                    orders += 1
                
                daily_inv[day] = (inventory + pipeline_qty) if include_pipeline else inventory

            avg_inv = np.mean(daily_inv)
            hc = avg_inv * H
            fc = orders * S
            vc = (orders * qty_to_order) * var_order_cost
            return hc + fc + vc, hc, fc, vc

        for run in range(num_runs):
            demand_profile = demand_matrix[run]
            
            tc_eoq, _, _, _ = simulate_year(max(1, int(eoq)))
            sim_results_eoq["Total Cost"].append(tc_eoq)
            
            tc_cust, hc_cust, fc_cust, vc_cust = simulate_year(custom_order_qty)
            sim_results_custom["Total Cost"].append(tc_cust)
            sim_results_custom["Holding Cost"].append(hc_cust)
            sim_results_custom["Fixed Ordering Cost"].append(fc_cust)
            sim_results_custom["Variable Ordering Cost"].append(vc_cust)
            
        st.session_state.sim_custom = sim_results_custom
        st.session_state.sim_eoq = sim_results_eoq
        st.session_state.det_cost = total_eoq_cost

# --- Display Comparative Results ---
if "sim_custom" in st.session_state:
    res_custom = st.session_state.sim_custom
    res_eoq = st.session_state.sim_eoq
    
    avg_custom_cost = np.mean(res_custom["Total Cost"])
    avg_eoq_cost = np.mean(res_eoq["Total Cost"])
    diff = avg_custom_cost - avg_eoq_cost
    
    st.markdown("### Simulation Output & Performance")
    metric_c1, metric_c2, metric_c3 = st.columns(3)
    metric_c1.metric("Avg Cost (Simulated EOQ)", f"${avg_eoq_cost:,.0f}")
    metric_c2.metric("Avg Cost (Custom Qty)", f"${avg_custom_cost:,.0f}", delta=f"${diff:,.0f} vs EOQ", delta_color="inverse")
    metric_c3.metric("Cost Gap (%)", f"{(diff / avg_eoq_cost * 100):.2f}%" if avg_eoq_cost > 0 else "0%")
    
    st.divider()
    
    # Min / Avg / Max Matrix for Overall Total Cost (Custom Qty) above the first graph
    st.markdown("### Total Annual Cost Summary (Custom Quantity)")
    tc_vals = res_custom["Total Cost"]
    tc_m1, tc_m2, tc_m3 = st.columns(3)
    tc_m1.metric("Min Total Cost", f"${min(tc_vals):,.0f}")
    tc_m2.metric("Avg Total Cost", f"${np.mean(tc_vals):,.0f}")
    tc_m3.metric("Max Total Cost", f"${max(tc_vals):,.0f}")
    
    # Comparative Histogram
    bin_width = st.slider("Adjust Histogram Bin Width ($)", min_value=100, max_value=5000, value=1000, step=100)
    
    all_costs = res_custom["Total Cost"] + res_eoq["Total Cost"]
    b_min = np.floor(min(all_costs) / bin_width) * bin_width
    b_max = np.ceil(max(all_costs) / bin_width) * bin_width
    
    fig_comp = go.Figure()
    fig_comp.add_trace(go.Histogram(x=res_eoq["Total Cost"], xbins=dict(start=b_min, end=b_max, size=bin_width), marker_color='rgba(173, 216, 230, 0.6)', name="EOQ Distribution"))
    fig_comp.add_trace(go.Histogram(x=res_custom["Total Cost"], xbins=dict(start=b_min, end=b_max, size=bin_width), marker_color='rgba(255, 127, 14, 0.8)', name="Custom Qty Distribution"))
    
    fig_comp.update_layout(barmode='overlay', xaxis_title="Total Annual Cost ($)", yaxis_title="Frequency", bargap=0.05)
    st.plotly_chart(style_plotly_fig(fig_comp), use_container_width=True)
    
    st.divider()
    
    # Plot Broken Down Costs for Custom Quantity with Min/Avg/Max Metrics
    st.markdown("### Component Cost Drivers (Custom Quantity)")
    
    hc_col, fc_col, vc_col = st.columns(3)
    
    with hc_col:
        st.markdown("#### Holding Cost")
        hc_vals = res_custom["Holding Cost"]
        hm1, hm2, hm3 = st.columns(3)
        hm1.metric("Min", f"${min(hc_vals):,.0f}")
        hm2.metric("Avg", f"${np.mean(hc_vals):,.0f}")
        hm3.metric("Max", f"${max(hc_vals):,.0f}")
        
        fig_hc = go.Figure(go.Histogram(x=hc_vals, marker_color='#1f77b4'))
        fig_hc.update_layout(xaxis_title="Cost ($)", yaxis_title="Frequency", height=280, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(style_plotly_fig(fig_hc), use_container_width=True)
        
    with fc_col:
        st.markdown("#### Fixed Ordering Cost")
        fc_vals = res_custom["Fixed Ordering Cost"]
        fm1, fm2, fm3 = st.columns(3)
        fm1.metric("Min", f"${min(fc_vals):,.0f}")
        fm2.metric("Avg", f"${np.mean(fc_vals):,.0f}")
        fm3.metric("Max", f"${max(fc_vals):,.0f}")
        
        fig_fc = go.Figure(go.Histogram(x=fc_vals, marker_color='#ff7f0e'))
        fig_fc.update_layout(xaxis_title="Cost ($)", yaxis_title="Frequency", height=280, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(style_plotly_fig(fig_fc), use_container_width=True)
        
    with vc_col:
        st.markdown("#### Var. Ordering Cost")
        vc_vals = res_custom["Variable Ordering Cost"]
        vm1, vm2, vm3 = st.columns(3)
        vm1.metric("Min", f"${min(vc_vals):,.0f}")
        vm2.metric("Avg", f"${np.mean(vc_vals):,.0f}")
        vm3.metric("Max", f"${max(vc_vals):,.0f}")
        
        fig_vc = go.Figure(go.Histogram(x=vc_vals, marker_color='#2ca02c'))
        fig_vc.update_layout(xaxis_title="Cost ($)", yaxis_title="Frequency", height=280, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(style_plotly_fig(fig_vc), use_container_width=True)

    st.divider()

    # Frequency Table (Custom Quantity)
    counts, edges = np.histogram(res_custom["Total Cost"], bins=np.arange(b_min, b_max + bin_width, bin_width))
    freq_df = pd.DataFrame({"Bin Start ($)": np.round(edges[:-1], 2), "Bin End ($)": np.round(edges[1:], 2), "Absolute Count": counts})
    
    total_runs = counts.sum()
    if total_runs > 0:
        freq_df["% of Total"] = np.round((freq_df["Absolute Count"] / total_runs) * 100, 2)
        freq_df["Cumulative %"] = np.round(freq_df["% of Total"].cumsum(), 2)
    else:
        freq_df["% of Total"] = 0.0; freq_df["Cumulative %"] = 0.0
        
    freq_df["% of Total"] = freq_df["% of Total"].astype(str) + "%"
    freq_df["Cumulative %"] = freq_df["Cumulative %"].astype(str) + "%"
    
    st.markdown("### Total Cost Frequency Table (Custom Quantity)")
    st.dataframe(freq_df.style.format({"Bin Start ($)": "{:,.0f}", "Bin End ($)": "{:,.0f}"}), use_container_width=True, hide_index=True)
