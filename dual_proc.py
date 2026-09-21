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

# =====================================================================
# SIMULATION ENGINE
# =====================================================================
def simulate_dual_sourcing(
    demand, sim_days, 
    slow_lt, slow_freq, slow_qty, slow_unit_cost, slow_order_cost,
    fast_lt, fast_policy, fast_p1, fast_p2, fast_unit_cost, fast_order_cost,
    holding_rate, initial_inv
):
    inv = initial_inv
    
    # Active pipeline trackers
    slow_pipeline = []
    fast_pipeline = []
    
    # Data trackers for the dataframe
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
        # 1. Receive Shipments
        slow_received = sum([qty for arr_day, qty in slow_pipeline if arr_day == day])
        fast_received = sum([qty for arr_day, qty in fast_pipeline if arr_day == day])
        
        slow_pipeline = [(arr_day, qty) for arr_day, qty in slow_pipeline if arr_day != day]
        fast_pipeline = [(arr_day, qty) for arr_day, qty in fast_pipeline if arr_day != day]
        
        inv += (slow_received + fast_received)
        hist_slow_arrivals[day] = slow_received
        hist_fast_arrivals[day] = fast_received
        
        # 2. Fulfill Demand
        demand_today = demand[day]
        sold = min(inv, demand_today)
        lost = demand_today - sold
        inv -= sold
        
        hist_lost_sales[day] = lost
        hist_inv[day] = inv
        
        # Calculate holding cost (blended proxy based on end of day inventory)
        total_holding_cost += (inv * slow_unit_cost * daily_holding_pct)
        
        # 3. Calculate Inventory Position (Phys + Fast Pipeline + Slow Pipeline)
        in_transit = sum([q for d, q in slow_pipeline]) + sum([q for d, q in fast_pipeline])
        inv_pos = inv + in_transit
        
        # 4. Trigger Slow Supplier (Standing Base Load)
        if day % slow_freq == 0:
            slow_pipeline.append((day + slow_lt, slow_qty))
            hist_slow_orders[day] = slow_qty
            inv_pos += slow_qty # Update pos immediately for fast supplier logic
            
        # 5. Trigger Fast Supplier (Agile Surge Load)
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
        
    # Aggregate KPIs
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
        "blended_unit_cost": blended_unit_cost,
        "total_holding_cost": total_holding_cost,
        "slow_units": total_slow_units,
        "fast_units": total_fast_units,
        "slow_order_cost": total_slow_order_cost,
        "fast_order_cost": total_fast_order_cost,
        "lost_sales_total": hist_lost_sales.sum(),
        "fill_rate": 100 * (1 - (hist_lost_sales.sum() / demand.sum())) if demand.sum() > 0 else 100
    }

# =====================================================================
# UI LAYOUT
# =====================================================================
st.title("⚖️ Dual Procurement Policy (Base-Surge Strategy)")
st.markdown("Optimize a multi-vendor strategy by ordering a fixed base load from a slow, cheap supplier while covering demand volatility with an agile, fast supplier.")

# --- GLOBAL INPUTS ---
st.sidebar.header("Demand & Financials")
mu = st.sidebar.number_input("Daily Demand (Mean)", value=50.0)
sigma = st.sidebar.number_input("Daily Demand (Std Dev)", value=15.0)
sim_days = st.sidebar.number_input("Simulation Horizon (Days)", value=365)
holding_rate = st.sidebar.number_input("Annual Holding Rate (%)", value=20.0) / 100.0

demand_arr = generate_adaptive_demand(mu, sigma, sim_days, 42)

# --- VENDOR CONFIGURATION ---
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🐢 Primary Supplier (Slow & Cheap)")
    st.caption("Policy: Fixed Quantity Standing Order")
    
    slow_uc = st.number_input("Unit Cost ($)", value=10.0, key="s_uc")
    slow_oc = st.number_input("Cost per Order ($)", value=500.0, key="s_oc")
    slow_lt = st.number_input("Lead Time (Days)", value=45, key="s_lt")
    
    st.markdown("#### Standing Order Setup")
    slow_freq = st.number_input("Order Frequency (Days)", min_value=1, value=30, key="s_freq")
    
    # Recommendation logic for base load
    rec_base_qty = int(mu * slow_freq * 0.8) # Cover 80% of mean demand with cheap supplier
    st.caption(f"💡 Recommended Base Qty (~80% of mean): {rec_base_qty}")
    slow_qty = st.number_input("Fixed Order Quantity", min_value=0, value=rec_base_qty, key="s_qty")

with col2:
    st.markdown("### 🐇 Secondary Supplier (Fast & Expensive)")
    st.caption("Policy: Dynamic Review to catch stockouts")
    
    fast_uc = st.number_input("Unit Cost ($)", value=15.0, key="f_uc")
    fast_oc = st.number_input("Cost per Order ($)", value=100.0, key="f_oc")
    fast_lt = st.number_input("Lead Time (Days)", value=5, key="f_lt")
    
    st.markdown("#### Surge Policy Setup")
    fast_policy = st.selectbox("Agile Policy Type", ["Continuous Review (s, Q)", "Periodic Review (R, S)"])
    
    if fast_policy == "Continuous Review (s, Q)":
        f_p1 = st.number_input("Reorder Point (s)", value=int(mu * fast_lt * 1.5))
        f_p2 = st.number_input("Order Quantity (Q)", value=int(mu * 10))
    else:
        f_p1 = st.number_input("Review Period (R)", min_value=1, value=7)
        f_p2 = st.number_input("Target Level (S)", value=int(mu * (fast_lt + f_p1) * 1.5))

st.divider()

if st.button("🚀 Run Dual Sourcing Simulation", type="primary", use_container_width=True):
    with st.spinner("Simulating network..."):
        
        # Calculate initial inventory default to avoid day 1 stockouts
        init_inv = int(mu * (fast_lt + 5))
        
        res = simulate_dual_sourcing(
            demand_arr, sim_days,
            slow_lt, slow_freq, slow_qty, slow_uc, slow_oc,
            fast_lt, fast_policy, f_p1, f_p2, fast_uc, fast_oc,
            holding_rate, init_inv
        )
        
        df = res["df"]
        
        # --- EXECUTIVE SCORECARD ---
        st.subheader("🏆 Executive Scorecard")
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("System Fill Rate", f"{res['fill_rate']:.2f}%", f"Lost Sales: {int(res['lost_sales_total'])} units", delta_color="off")
        k2.metric("Total System Cost", f"${res['total_system_cost']:,.0f}")
        k3.metric("Blended Unit Cost", f"${res['blended_unit_cost']:,.2f}")
        k4.metric("Avg Physical Inv", f"{int(df['Physical Inventory'].mean()):,} units")
        
        st.write("<br>", unsafe_allow_html=True)
        
        # Sourcing Split Matrix
        st.markdown("#### Sourcing Volume Split")
        s_col1, s_col2 = st.columns(2)
        total_vol = res['slow_units'] + res['fast_units']
        
        with s_col1:
            st.info(f"**🐢 Slow Vendor:** {int(res['slow_units']):,} units ({(res['slow_units']/total_vol)*100 if total_vol>0 else 0:.1f}%)")
            st.write(f"- Procurement Cost: ${res['slow_units'] * slow_uc:,.0f}")
            st.write(f"- Total Order Costs: ${res['slow_order_cost']:,.0f}")
        with s_col2:
            st.warning(f"**🐇 Fast Vendor:** {int(res['fast_units']):,} units ({(res['fast_units']/total_vol)*100 if total_vol>0 else 0:.1f}%)")
            st.write(f"- Procurement Cost: ${res['fast_units'] * fast_uc:,.0f}")
            st.write(f"- Total Order Costs: ${res['fast_order_cost']:,.0f}")

        st.divider()

        # --- VISUALIZATIONS ---
        st.subheader("📊 Operational Trajectory")
        
        tab1, tab2 = st.tabs(["Inventory Behavior", "Delivery Patterns"])
        
        with tab1:
            fig_inv = go.Figure()
            fig_inv.add_trace(go.Scatter(x=df["Day"], y=df["Physical Inventory"], name="Physical Inventory", line=dict(color='#1f77b4', width=2)))
            fig_inv.add_trace(go.Scatter(x=df["Day"], y=df["Inventory Position"], name="Inventory Position", line=dict(color='gray', width=1, dash='dot')))
            
            # Mark fast orders
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

        # --- RAW DATA ---
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
