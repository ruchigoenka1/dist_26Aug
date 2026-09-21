import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm, gamma

st.set_page_config(page_title="Dual Procurement Strategy", layout="wide")

# =====================================================================
# STYLING & HELPERS
# =====================================================================
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

@st.cache_data(show_spinner=False)
def generate_adaptive_demand(mu, sigma, days, seed):
    np.random.seed(seed)
    if sigma == 0:
        return np.full(days, mu)
    cov = sigma / mu if mu > 0 else 0
    if cov <= 0.5:
        return np.maximum(0, np.random.normal(mu, sigma, days)).round()
    else:
        shape = (mu / sigma) ** 2
        scale = (sigma ** 2) / mu
        return np.random.gamma(shape, scale, days).round()

def get_optimal_params(mu, sigma, lt, sl_decimal, holding_rate, unit_cost, order_cost, policy_type, review_period=7):
    cov = sigma / mu if mu > 0 else 0
    if cov <= 0.5:
        s = int(mu * lt + norm.ppf(sl_decimal) * sigma * np.sqrt(lt))
        S = int(mu * (lt + review_period) + norm.ppf(sl_decimal) * sigma * np.sqrt(lt + review_period))
    else:
        shape = (mu / sigma) ** 2
        scale = (sigma ** 2) / mu
        s = int(gamma.ppf(sl_decimal, a=shape * lt, scale=scale)) if sigma > 0 else int(mu * lt)
        S = int(gamma.ppf(sl_decimal, a=shape * (lt + review_period), scale=scale)) if sigma > 0 else int(mu * (lt + review_period))
        
    daily_hc = (unit_cost * holding_rate) / 365.0
    Q = max(1, int(np.sqrt((2 * mu * 365 * order_cost) / max(0.01, daily_hc * 365))))
    
    if policy_type == "Continuous Review (s, Q)":
        return s, Q
    else:
        return review_period, S

# =====================================================================
# SIMULATION ENGINES
# =====================================================================
def simulate_single_sourcing(demand, sim_days, lt, policy, p1, p2, unit_cost, order_cost, holding_rate, initial_inv):
    inv = initial_inv
    pipeline = []
    
    hist_inv = np.zeros(sim_days)
    hist_orders = np.zeros(sim_days)
    hist_lost = np.zeros(sim_days)
    
    daily_hc_rate = holding_rate / 365.0
    total_hc = 0.0
    
    for day in range(sim_days):
        received = sum([qty for arr_day, qty in pipeline if arr_day == day])
        pipeline = [(arr_day, qty) for arr_day, qty in pipeline if arr_day != day]
        inv += received
        
        dem = demand[day]
        sold = min(inv, dem)
        lost = dem - sold
        inv -= sold
        
        hist_inv[day] = inv
        hist_lost[day] = lost
        total_hc += (inv * unit_cost * daily_hc_rate)
        
        in_transit = sum([q for d, q in pipeline])
        inv_pos = inv + in_transit
        
        order_qty = 0
        if policy == "Continuous Review (s, Q)":
            if inv_pos < p1:
                order_qty = p2
                pipeline.append((day + lt, order_qty))
        elif policy == "Periodic Review (R, S)":
            if day % int(p1) == 0:
                if inv_pos < p2:
                    order_qty = p2 - inv_pos
                    pipeline.append((day + lt, order_qty))
                    
        hist_orders[day] = order_qty

    total_units = hist_orders.sum()
    total_oc = np.count_nonzero(hist_orders) * order_cost
    total_purchase = total_units * unit_cost
    
    return {
        "total_system_cost": total_purchase + total_oc + total_hc,
        "total_purchase_cost": total_purchase,
        "total_order_cost": total_oc,
        "total_holding_cost": total_hc,
        "fill_rate": 100 * (1 - (hist_lost.sum() / demand.sum())) if demand.sum() > 0 else 100
    }

def simulate_dual_sourcing(
    demand, sim_days, 
    slow_lt, slow_freq, slow_qty, slow_unit_cost, slow_order_cost,
    fast_lt, fast_policy, fast_p1, fast_p2, fast_unit_cost, fast_order_cost,
    holding_rate, initial_inv
):
    inv = initial_inv
    slow_pipeline = []
    fast_pipeline = []
    
    hist_inv = np.zeros(sim_days)
    hist_inv_pos = np.zeros(sim_days)
    hist_slow_arrivals = np.zeros(sim_days)
    hist_fast_arrivals = np.zeros(sim_days)
    hist_slow_orders = np.zeros(sim_days)
    hist_fast_orders = np.zeros(sim_days)
    hist_lost_sales = np.zeros(sim_days)
    
    daily_holding_pct = holding_rate / 365.0
    total_holding_cost = 0.0
    
    for day in range(sim_days):
        slow_received = sum([qty for arr_day, qty in slow_pipeline if arr_day == day])
        fast_received = sum([qty for arr_day, qty in fast_pipeline if arr_day == day])
        
        slow_pipeline = [(arr_day, qty) for arr_day, qty in slow_pipeline if arr_day != day]
        fast_pipeline = [(arr_day, qty) for arr_day, qty in fast_pipeline if arr_day != day]
        
        inv += (slow_received + fast_received)
        hist_slow_arrivals[day] = slow_received
        hist_fast_arrivals[day] = fast_received
        
        demand_today = demand[day]
        sold = min(inv, demand_today)
        lost = demand_today - sold
        inv -= sold
        
        hist_lost_sales[day] = lost
        hist_inv[day] = inv
        
        # Blended proxy holding cost based on end-of-day physical inventory
        total_holding_cost += (inv * slow_unit_cost * daily_holding_pct)
        
        in_transit = sum([q for d, q in slow_pipeline]) + sum([q for d, q in fast_pipeline])
        inv_pos = inv + in_transit
        
        # Base Load Trigger
        if day % slow_freq == 0:
            slow_pipeline.append((day + slow_lt, slow_qty))
            hist_slow_orders[day] = slow_qty
            inv_pos += slow_qty 
            
        # Agile Surge Trigger
        fast_order_qty = 0
        if fast_policy == "Continuous Review (s, Q)":
            if inv_pos < fast_p1:
                fast_order_qty = fast_p2
                fast_pipeline.append((day + fast_lt, fast_order_qty))
        elif fast_policy == "Periodic Review (R, S)":
            if day % fast_p1 == 0:
                if inv_pos < fast_p2:
                    fast_order_qty = fast_p2 - inv_pos
                    fast_pipeline.append((day + fast_lt, fast_order_qty))
                    
        hist_fast_orders[day] = fast_order_qty
        hist_inv_pos[day] = inv_pos + fast_order_qty
        
    total_slow_units = hist_slow_orders.sum()
    total_fast_units = hist_fast_orders.sum()
    total_units = total_slow_units + total_fast_units
    
    blended_unit_cost = ((total_slow_units * slow_unit_cost) + (total_fast_units * fast_unit_cost)) / total_units if total_units > 0 else 0
    total_purchase_cost = (total_slow_units * slow_unit_cost) + (total_fast_units * fast_unit_cost)
    
    total_slow_order_cost = np.count_nonzero(hist_slow_orders) * slow_order_cost
    total_fast_order_cost = np.count_nonzero(hist_fast_orders) * fast_order_cost
    
    total_system_cost = total_purchase_cost + total_slow_order_cost + total_fast_order_cost + total_holding_cost
    
    df_sim = pd.DataFrame({
        "Day": np.arange(1, sim_days + 1),
        "Demand": demand,
        "Physical Inventory": hist_inv,
        "Inventory Position": hist_inv_pos,
        "Slow Arrivals": hist_slow_arrivals,
        "Fast Arrivals": hist_fast_arrivals,
        "Slow Orders Placed": hist_slow_orders,
        "Fast Orders Placed": hist_fast_orders,
        "Lost Sales": hist_lost_sales
    })
    
    return {
        "df": df_sim,
        "total_system_cost": total_system_cost,
        "total_purchase_cost": total_purchase_cost,
        "total_order_cost": total_slow_order_cost + total_fast_order_cost,
        "total_holding_cost": total_holding_cost,
        "blended_unit_cost": blended_unit_cost,
        "slow_units": total_slow_units,
        "fast_units": total_fast_units,
        "slow_order_cost": total_slow_order_cost,
        "fast_order_cost": total_fast_order_cost,
        "fill_rate": 100 * (1 - (hist_lost_sales.sum() / demand.sum())) if demand.sum() > 0 else 100
    }

# =====================================================================
# UI LAYOUT
# =====================================================================
st.title("⚖️ Dual Procurement Policy Optimization")
st.markdown("Compare a single-vendor supply chain against a **Base-Surge Strategy**, utilizing a slow/cheap supplier for base volume and a fast/expensive supplier for demand spikes.")

# --- GLOBAL INPUTS (MOVED FROM SIDEBAR) ---
st.markdown("### 🌍 Global Demand & Financial Parameters")
g_col1, g_col2, g_col3, g_col4 = st.columns(4)

with g_col1:
    mu = st.number_input("Daily Demand (Mean)", value=50.0)
with g_col2:
    sigma = st.number_input("Daily Demand (Std Dev)", value=15.0)
with g_col3:
    sim_days = st.number_input("Simulation Horizon (Days)", value=365)
with g_col4:
    holding_rate = st.number_input("Annual Holding Cost (%)", value=20.0, help="Used as a % of Unit Cost") / 100.0

demand_arr = generate_adaptive_demand(mu, sigma, sim_days, 42)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🐢 Primary Supplier (Slow & Cheap)")
    slow_uc = st.number_input("Unit Cost ($)", value=10.0, key="s_uc")
    slow_oc = st.number_input("Cost per Order ($)", value=500.0, key="s_oc")
    slow_lt = st.number_input("Lead Time (Days)", value=45, key="s_lt")
    
    st.markdown("#### Dual Strategy: Standing Order Setup")
    slow_freq = st.number_input("Order Frequency (Days)", min_value=1, value=30, key="s_freq")
    rec_base_qty = int(mu * slow_freq * 0.8)
    st.caption(f"💡 Recommended Base Qty (~80% of mean): {rec_base_qty}")
    slow_qty = st.number_input("Fixed Order Quantity", min_value=0, value=rec_base_qty, key="s_qty")

with col2:
    st.markdown("### 🐇 Secondary Supplier (Fast & Expensive)")
    fast_uc = st.number_input("Unit Cost ($)", value=15.0, key="f_uc")
    fast_oc = st.number_input("Cost per Order ($)", value=100.0, key="f_oc")
    fast_lt = st.number_input("Lead Time (Days)", value=5, key="f_lt")
    
    st.markdown("#### Surge Policy & Service Level Targets")
    target_sl = st.slider("Target Service Level (%)", 50.0, 99.9, 95.0, 0.1) / 100.0
    fast_policy = st.selectbox("Agile Policy Type", ["Continuous Review (s, Q)", "Periodic Review (R, S)"])
    
    opt_p1, opt_p2 = get_optimal_params(mu, sigma, fast_lt, target_sl, holding_rate, fast_uc, fast_oc, fast_policy)
    
    if fast_policy == "Continuous Review (s, Q)":
        st.caption(f"💡 Target SL Recommended ROP: **{opt_p1}**, EOQ: **{opt_p2}**")
        f_p1 = st.number_input("Reorder Point (s)", value=opt_p1)
        f_p2 = st.number_input("Order Quantity (Q)", value=opt_p2)
    else:
        st.caption(f"💡 Target SL Recommended Target Level (S): **{opt_p2}**")
        f_p1 = st.number_input("Review Period (R)", min_value=1, value=opt_p1)
        f_p2 = st.number_input("Target Level (S)", value=opt_p2)

st.divider()

if st.button("🚀 Run Triple-Scenario Cost Comparison", type="primary", use_container_width=True):
    with st.spinner("Simulating network..."):
        
        init_inv = int(mu * (fast_lt + 5))
        
        # 1. SLOW SUPPLIER ONLY (Optimized dynamically based on Target SL)
        slow_opt_p1, slow_opt_p2 = get_optimal_params(mu, sigma, slow_lt, target_sl, holding_rate, slow_uc, slow_oc, fast_policy)
        res_slow_only = simulate_single_sourcing(
            demand_arr, sim_days, slow_lt, fast_policy, slow_opt_p1, slow_opt_p2, 
            slow_uc, slow_oc, holding_rate, init_inv
        )
        
        # 2. FAST SUPPLIER ONLY (Optimized dynamically based on Target SL)
        res_fast_only = simulate_single_sourcing(
            demand_arr, sim_days, fast_lt, fast_policy, f_p1, f_p2, 
            fast_uc, fast_oc, holding_rate, init_inv
        )
        
        # 3. DUAL SOURCING (Base-Surge)
        res_dual = simulate_dual_sourcing(
            demand_arr, sim_days,
            slow_lt, slow_freq, slow_qty, slow_uc, slow_oc,
            fast_lt, fast_policy, f_p1, f_p2, fast_uc, fast_oc,
            holding_rate, init_inv
        )
        
        # --- EXECUTIVE COMPARISON ---
        st.markdown("### 🏆 Total Cost Scenario Breakdown")
        
        comp_data = {
            "Scenario": ["1. 100% Slow Vendor", "2. 100% Fast Vendor", "3. Dual Base-Surge"],
            "System Fill Rate": [f"{res_slow_only['fill_rate']:.2f}%", f"{res_fast_only['fill_rate']:.2f}%", f"{res_dual['fill_rate']:.2f}%"],
            "Purchase Cost": [res_slow_only['total_purchase_cost'], res_fast_only['total_purchase_cost'], res_dual['total_purchase_cost']],
            "Order Cost": [res_slow_only['total_order_cost'], res_fast_only['total_order_cost'], res_dual['total_order_cost']],
            "Holding Cost": [res_slow_only['total_holding_cost'], res_fast_only['total_holding_cost'], res_dual['total_holding_cost']],
            "Total System Cost": [res_slow_only['total_system_cost'], res_fast_only['total_system_cost'], res_dual['total_system_cost']]
        }
        df_comp = pd.DataFrame(comp_data)
        
        # Plotly Stacked Bar Chart
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(x=df_comp["Scenario"], y=df_comp["Purchase Cost"], name="Purchase Cost", marker_color="#1f77b4"))
        fig_comp.add_trace(go.Bar(x=df_comp["Scenario"], y=df_comp["Order Cost"], name="Order Cost", marker_color="#ff7f0e"))
        fig_comp.add_trace(go.Bar(x=df_comp["Scenario"], y=df_comp["Holding Cost"], name="Holding Cost", marker_color="#2ca02c"))
        
        fig_comp.update_layout(barmode='stack', yaxis_title="Cost ($)", title="Total System Cost Composition")
        fig_comp = style_plotly_fig(fig_comp)
        
        # Render Matrix and Chart
        col_t1, col_t2 = st.columns([1.2, 1])
        with col_t1:
            st.plotly_chart(fig_comp, use_container_width=True)
        with col_t2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.dataframe(df_comp.style.format({
                "Purchase Cost": "${:,.0f}",
                "Order Cost": "${:,.0f}",
                "Holding Cost": "${:,.0f}",
                "Total System Cost": "${:,.0f}"
            }), use_container_width=True, hide_index=True)
        
        st.divider()

        # --- DUAL SOURCING DEEP DIVE ---
        st.markdown("### 🔍 Scenario 3: Dual Sourcing Deep-Dive")
        
        df = res_dual["df"]
        k1, k2, k3 = st.columns(3)
        k1.metric("Blended Unit Cost", f"${res_dual['blended_unit_cost']:,.2f}")
        k2.metric("Slow Volume Split", f"{(res_dual['slow_units'] / (res_dual['slow_units'] + res_dual['fast_units']))*100 if (res_dual['slow_units'] + res_dual['fast_units']) > 0 else 0:.1f}%")
        k3.metric("Avg Physical Inv", f"{int(df['Physical Inventory'].mean()):,} units")
        
        tab1, tab2 = st.tabs(["Inventory Behavior", "Delivery Patterns"])
        
        with tab1:
            fig_inv = go.Figure()
            fig_inv.add_trace(go.Scatter(x=df["Day"], y=df["Physical Inventory"], name="Physical Inventory", line=dict(color='#1f77b4', width=2)))
            fig_inv.add_trace(go.Scatter(x=df["Day"], y=df["Inventory Position"], name="Inventory Position", line=dict(color='gray', width=1, dash='dot')))
            
            fast_triggers = df[df["Fast Orders Placed"] > 0]
            fig_inv.add_trace(go.Scatter(x=fast_triggers["Day"], y=fast_triggers["Physical Inventory"], mode="markers", name="Fast Order Triggered", marker=dict(color="#ff7f0e", symbol="triangle-up", size=10)))
            
            fig_inv = style_plotly_fig(fig_inv)
            st.plotly_chart(fig_inv, use_container_width=True)
            
        with tab2:
            fig_arr = go.Figure()
            fig_arr.add_trace(go.Bar(x=df["Day"], y=df["Slow Arrivals"], name="🐢 Slow Deliveries", marker_color="#2ca02c"))
            fig_arr.add_trace(go.Bar(x=df["Day"], y=df["Fast Arrivals"], name="🐇 Fast Deliveries", marker_color="#d62728"))
            
            fig_arr.update_layout(barmode='stack', yaxis_title="Units Received")
            fig_arr = style_plotly_fig(fig_arr)
            st.plotly_chart(fig_arr, use_container_width=True)

        with st.expander("🔍 View Simulation Data Table"):
            st.dataframe(df.style.format({
                "Physical Inventory": "{:.0f}",
                "Inventory Position": "{:.0f}",
                "Slow Arrivals": "{:.0f}",
                "Fast Arrivals": "{:.0f}",
                "Slow Orders Placed": "{:.0f}",
                "Fast Orders Placed": "{:.0f}",
                "Lost Sales": "{:.0f}"
            }), use_container_width=True, hide_index=True)
