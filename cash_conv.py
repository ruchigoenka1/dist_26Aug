import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm, gamma

st.set_page_config(page_title="Cash Conversion Cycle", layout="wide")

# =====================================================================
# STYLING
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

# =====================================================================
# PAGE HEADER & INPUTS
# =====================================================================
st.header("Inventory & Cash Flow Simulation & Scenario Analysis")
st.markdown("Simulate daily operations and track the true **Cost of Capital** based on a strict **Cash Flow** approach, alongside multi-scenario optimization.")

# --- 1. BASE SIMULATION & FINANCIAL PARAMETERS ---
st.subheader("1. Base Simulation & Financial Parameters")

col_p1, col_p2, col_p3, col_p4 = st.columns(4)
with col_p1:
    avg_demand = st.number_input("Average Daily Demand", min_value=1.0, value=50.0)
    variation = st.number_input("Demand Variation (Std Dev)", min_value=0.0, value=10.0)
with col_p2:
    lead_time = st.number_input("Lead Time (Days)", min_value=1, value=60)
    unit_value = st.number_input("Value of Product (Unit Cost $)", min_value=0.1, value=100.0)
with col_p3:
    physical_holding_cost = st.number_input("Physical Holding Cost/Unit/Year ($)", min_value=0.0, value=10.0)
    cost_of_capital_pct = st.number_input("Cost of Capital (Annual %)", min_value=0.0, value=12.0) / 100.0
with col_p4:
    ordering_cost = st.number_input("Ordering Cost per Order ($)", min_value=1.0, value=250.0)
    sim_days = st.number_input("Simulation Duration (Days)", min_value=30, value=365, step=30)
    warmup_days = st.number_input("Warm-up Period (Days)", min_value=0, max_value=int(sim_days)-1, value=60)

col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    opening_capital = st.number_input("Initial Cash Balance ($)", value=100000.0, step=5000.0)
    credit_rx = st.number_input("Supplier Credit (Days)", min_value=0, value=30)
with col_c2:
    credit_given = st.number_input("Buyer Credit (Days)", min_value=0, value=15)
    service_level = st.slider("Target Service Level (%)", min_value=50.0, max_value=99.99, value=95.0, step=0.1)
with col_c3:
    price_modifier = st.number_input("Price Premium / Discount (%)", value=0.0, step=1.0, help="Positive for price markup, negative for discount.")

# =====================================================================
# SIMULATION ENGINE
# =====================================================================
def run_cash_flow_simulation(ad, var, lt, uv, phc, coc, oc, crx, cgiv, sl, op_cap, s_days, p_mod, warm_up=0, custom_rop=None, custom_o_qty=None):
    # Adaptive logic for target service level (Normal vs Gamma)
    cov = var / ad if ad > 0 else 0
    if cov <= 0.5:
        z_s = norm.ppf(sl / 100.0)
        s_stock = z_s * var * np.sqrt(lt)
        rec_rop = (ad * lt) + s_stock
    else:
        shape = (ad / var) ** 2
        scale = (var ** 2) / ad
        rec_rop = gamma.ppf(sl / 100.0, a=shape * lt, scale=scale)
    
    effective_uv = uv * (1 + (p_mod / 100.0))
    base_cap_cost = effective_uv * coc
    eoq_hc = phc + base_cap_cost
    ann_dem = ad * 365
    eoq_val = np.sqrt((2 * ann_dem * oc) / max(0.01, eoq_hc))
    
    rop_val = int(custom_rop) if custom_rop is not None else int(rec_rop)
    o_qty = max(1, int(custom_o_qty)) if custom_o_qty is not None else max(1, int(eoq_val))
    
    init_inv = rop_val + o_qty
    init_inv_val = init_inv * effective_uv
    eff_op_cash = op_cap - init_inv_val
    
    np.random.seed(42)
    # Adaptive Demand Generation
    if cov <= 0.5:
        d_demands = np.maximum(0, np.random.normal(ad, var, s_days)).round()
    else:
        shape = (ad / var) ** 2
        scale = (var ** 2) / ad
        d_demands = np.random.gamma(shape, scale, s_days).round()
    
    max_buf = int(s_days + max(crx, cgiv, lt) + 100)
    deliveries = np.zeros(max_buf)
    cash_out = np.zeros(max_buf)
    cash_in = np.zeros(max_buf)
    
    inv = init_inv
    on_ord = 0
    
    inv_arr = np.zeros(s_days)
    inv_pos_arr = np.zeros(s_days)
    sales_arr = np.zeros(s_days)
    orders_arr = np.zeros(s_days)
    
    for d in range(s_days):
        arrived = deliveries[d]
        inv += arrived
        on_ord -= arrived
        
        demand_today = d_demands[d]
        sold = min(inv, demand_today)
        inv -= sold
        sales_arr[d] = sold
        
        cash_in[d + int(cgiv)] += sold * effective_uv
        
        inv_pos = inv + on_ord
        placed_today = 0
        while inv_pos <= rop_val:
            deliveries[d + int(lt)] += o_qty
            on_ord += o_qty
            inv_pos += o_qty
            placed_today += 1
            cash_out[d + int(crx)] += o_qty * effective_uv
            
        inv_arr[d] = inv
        inv_pos_arr[d] = inv_pos
        orders_arr[d] = placed_today
        
    df_sim = pd.DataFrame({
        "Day": np.arange(1, s_days + 1),
        "Demand": d_demands,
        "Sales": sales_arr,
        "Inventory Units": inv_arr,
        "Orders Placed": orders_arr,
        "Inventory Position": inv_pos_arr
    })
    
    df_sim["Cash Inflow ($)"] = cash_in[:s_days]
    df_sim["Cash Outflow ($)"] = cash_out[:s_days]
    df_sim["Net Cash Flow ($)"] = df_sim["Cash Inflow ($)"] - df_sim["Cash Outflow ($)"]
    df_sim["Running Cash"] = eff_op_cash + df_sim["Net Cash Flow ($)"].cumsum()
    df_sim["Capital Deficit"] = np.maximum(0, -df_sim["Running Cash"])
    
    df_sim["Phys Holding Cost"] = df_sim["Inventory Units"] * (phc / 365.0)
    df_sim["Capital Cost"] = df_sim["Capital Deficit"] * (coc / 365.0)
    
    # --- APPLY WARM-UP SLICE ---
    df_kpi = df_sim.iloc[warm_up:].copy() if warm_up < s_days else df_sim.copy()
    
    avg_inventory = df_kpi["Inventory Units"].mean()
    min_inventory = df_kpi["Inventory Units"].min()
    max_inventory = df_kpi["Inventory Units"].max()
    tot_demand = df_kpi["Demand"].sum()
    tot_sales = df_kpi["Sales"].sum()
    fill_rate_val = (tot_sales / tot_demand) * 100 if tot_demand > 0 else 0
    stockout_days_val = len(df_kpi[df_kpi["Demand"] > df_kpi["Sales"]])
    
    tot_holding = df_kpi["Phys Holding Cost"].sum()
    tot_capital = df_kpi["Capital Cost"].sum()
    tot_orders = df_kpi["Orders Placed"].sum()
    tot_ordering = tot_orders * oc
    
    total_inv_cost = tot_holding + tot_capital + tot_ordering
    total_product_cost = tot_sales * effective_uv
    total_system_cost = total_inv_cost + total_product_cost
    
    return {
        "avg_inventory": avg_inventory,
        "min_inventory": min_inventory,
        "max_inventory": max_inventory,
        "fill_rate": fill_rate_val,
        "stockout_days": stockout_days_val,
        "holding_cost": tot_holding + tot_capital,
        "ordering_cost": tot_ordering,
        "product_cost": total_product_cost,
        "total_inventory_cost": total_inv_cost,
        "total_cost": total_system_cost,
        "df": df_sim 
    }

# Run Baseline
base_res = run_cash_flow_simulation(
    avg_demand, variation, lead_time, unit_value, 
    physical_holding_cost, cost_of_capital_pct, ordering_cost, 
    credit_rx, credit_given, service_level, opening_capital, 
    int(sim_days), price_modifier, warm_up=int(warmup_days)
)

# =====================================================================
# BASELINE VISUALIZATION
# =====================================================================
st.markdown("---")
st.subheader("2. Baseline Simulation Deep-Dive")

# --- Operational Inventory KPIs ---
st.markdown("#### Operational Performance")
b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
b_col1.metric("Fill Rate", f"{base_res['fill_rate']:.2f}%")
b_col2.metric("Stockout Days", f"{int(base_res['stockout_days'])}")
b_col3.metric("Min Physical Inv.", f"{int(base_res['min_inventory']):,} Units")
b_col4.metric("Max Physical Inv.", f"{int(base_res['max_inventory']):,} Units")
b_col5.metric("Avg Physical Inv.", f"{int(base_res['avg_inventory']):,} Units")

st.write("<br>", unsafe_allow_html=True)

# --- CCC Breakdown Matrix ---
st.markdown("#### Cash Conversion Cycle (CCC) Breakdown")

avg_transit_inv = avg_demand * lead_time
total_owned_inv = base_res['avg_inventory'] + avg_transit_inv

daily_cogs = avg_demand * unit_value
dio = total_owned_inv / avg_demand if avg_demand > 0 else 0
dso = credit_given
dpo = credit_rx 
ccc = dio + dso - dpo

avg_transit_val = avg_transit_inv * unit_value
avg_inv_val = total_owned_inv * unit_value
avg_rec_val = daily_cogs * dso
avg_pay_val = daily_cogs * dpo
net_cap_tied_up = avg_inv_val + avg_rec_val - avg_pay_val

ccc_c1, ccc_c2, ccc_c3, ccc_c4, ccc_c5 = st.columns(5)
ccc_c1.metric("Transit Inventory Days", f"{lead_time:.1f} Days", f"Value: ${avg_transit_val:,.0f}", delta_color="off")
ccc_c2.metric("Days Inventory Out (DIO)", f"{dio:.1f} Days", f"Total Inv: ${avg_inv_val:,.0f}", delta_color="off")
ccc_c3.metric("Days Sales Out (DSO)", f"{dso:.1f} Days", f"Receivables: ${avg_rec_val:,.0f}", delta_color="off")
ccc_c4.metric("Days Payable Out (DPO)", f"{dpo:.1f} Days", f"Payables: ${avg_pay_val:,.0f}", delta_color="off")
ccc_c5.metric("Cash Conversion Cycle", f"{ccc:.1f} Days", f"Capital Tied: ${net_cap_tied_up:,.0f}", delta_color="inverse")

st.write("<br>", unsafe_allow_html=True)

# --- Graphs ---
wu_days = int(warmup_days)
s_days = int(sim_days)
df_b = base_res['df'].iloc[wu_days:].copy() if wu_days < s_days else base_res['df'].copy()

st.markdown("#### 📉 Baseline Inventory Movement (Post Warm-up)")
fig_b_inv = go.Figure()
fig_b_inv.add_trace(go.Scatter(x=df_b["Day"], y=df_b["Inventory Units"], mode='lines', name='Inventory Level', line=dict(color='#1f77b4', width=2)))
fig_b_inv.add_trace(go.Scatter(x=df_b["Day"], y=df_b["Inventory Position"], mode='lines', name='Inventory Position', line=dict(color='#9467bd', dash='dot', width=2)))
fig_b_inv.update_layout(xaxis_title="Days", yaxis_title="Units", hovermode="x unified", height=450)
st.plotly_chart(style_plotly_fig(fig_b_inv), use_container_width=True)

st.markdown("#### 💰 Baseline Cash Statement (Post Warm-up)")
fig_b_cash = go.Figure()
fig_b_cash.add_trace(go.Scatter(x=df_b["Day"], y=df_b["Running Cash"], mode='lines', name='Running Cash Balance', line=dict(color='#2ca02c', width=3)))
fig_b_cash.add_trace(go.Scatter(x=[df_b["Day"].min(), df_b["Day"].max()], y=[0, 0], mode='lines', name='Zero Line', line=dict(color='white', dash='solid')))
fig_b_cash.add_trace(go.Scatter(x=df_b["Day"], y=-df_b["Capital Deficit"], mode='none', fill='tozeroy', name='Capital Deficit (Borrowing)', fillcolor='rgba(214, 39, 40, 0.3)'))
fig_b_cash.update_layout(xaxis_title="Days", yaxis_title="Available Cash ($)", hovermode="x unified", height=450)
st.plotly_chart(style_plotly_fig(fig_b_cash), use_container_width=True)

# =====================================================================
# MULTI-SCENARIO BUILDER
# =====================================================================
st.markdown("---")
st.subheader("3. Multi-Scenario Configuration Matrix")
st.markdown("Define alternative supply chain parameters using the input columns below to compare performance against your baseline configuration.")

num_scenarios = st.slider("Select Number of Scenarios to Compare:", min_value=1, max_value=4, value=3)

scenario_cols = st.columns(num_scenarios)
scenario_inputs = []

default_names = ["Baseline", "Aggressive Credit", "Lean Lead Time", "Price Discount"]
default_crx = [credit_rx, 60, credit_rx, credit_rx]
default_lt = [lead_time, lead_time, 30, lead_time]
default_sl = [service_level, service_level, service_level, service_level]
default_pm = [price_modifier, 0.0, 0.0, -5.0]

global_cov = variation / avg_demand if avg_demand > 0 else 0

for i, col in enumerate(scenario_cols):
    with col:
        st.markdown(f"##### Scenario {i+1}")
        s_name = st.text_input("Scenario Name", value=default_names[i], key=f"name_{i}")
        s_crx = st.number_input("Supplier Credit (Days)", min_value=0, value=int(default_crx[i]), key=f"crx_{i}")
        s_lt = st.number_input("Supplier Lead Time", min_value=1, value=int(default_lt[i]), key=f"lt_{i}")
        s_sl = st.number_input("Target Service Level (%)", min_value=50.0, max_value=99.99, value=float(default_sl[i]), step=0.1, key=f"sl_{i}")
        s_pm = st.number_input("Price Modifier (%)", value=float(default_pm[i]), step=1.0, key=f"pm_{i}")
        
        # Adaptive Recommendation math
        if global_cov <= 0.5:
            z_score_val = norm.ppf(s_sl / 100.0)
            safety_stock_val = z_score_val * variation * np.sqrt(s_lt)
            def_rop = int((avg_demand * s_lt) + safety_stock_val)
        else:
            shape = (avg_demand / variation) ** 2
            scale = (variation ** 2) / avg_demand
            def_rop = int(gamma.ppf(s_sl / 100.0, a=shape * s_lt, scale=scale))
        
        eff_uv = unit_value * (1 + (s_pm / 100.0))
        def_hc = physical_holding_cost + (eff_uv * cost_of_capital_pct)
        def_eoq = max(1, int(np.sqrt((2 * (avg_demand * 365) * ordering_cost) / max(0.01, def_hc))))
        
        s_rop = st.number_input("Reorder Point (ROP)", min_value=0, value=def_rop, key=f"rop_{i}")
        st.caption(f"💡 Recommended ROP: {def_rop:,}")
        
        s_o_qty = st.number_input("Order Quantity", min_value=1, value=def_eoq, key=f"oqty_{i}")
        st.caption(f"💡 Recommended EOQ: {def_eoq:,}")
        
        scenario_inputs.append({
            "Name": s_name, "Crx": s_crx, "Lt": s_lt, "Sl": s_sl, "Pm": s_pm, "Rop": s_rop, "OQty": s_o_qty
        })

st.markdown("---")
if st.button("🚀 Run Multi-Scenario Analysis", type="primary", use_container_width=True):
    
    ops_cost_data = {
        "Metric": [
            "Reorder Point (ROP)", "Order Quantity (Q)", "Fill Rate (%)", 
            "Stockout Days", "Min Physical Inv. (Units)", "Max Physical Inv. (Units)", 
            "Avg Physical Inv. (Units)", "Holding Cost ($)", "Ordering Cost ($)", 
            "Product Cost ($)", "Total System Cost ($)"
        ]
    }
    
    ccc_data = {
        "Metric": [
            "Transit Inventory (Days)", "Days Inventory Out (DIO)", 
            "Days Sales Out (DSO)", "Days Payable Out (DPO)", "Cash Conversion Cycle (Days)"
        ]
    }
    
    wc_data = {
        "Metric": [
            "Avg Owned Inventory (Transit + Physical) ($)", 
            "Accounts Receivable ($)", "Accounts Payable ($)", "Net Working Capital Tied Up ($)"
        ]
    }
    
    for sc in scenario_inputs:
        res = run_cash_flow_simulation(
            avg_demand, variation, sc["Lt"], unit_value, 
            physical_holding_cost, cost_of_capital_pct, ordering_cost, 
            sc["Crx"], credit_given, sc["Sl"], opening_capital, 
            int(sim_days), sc["Pm"], warm_up=int(warmup_days), custom_rop=sc["Rop"], custom_o_qty=sc["OQty"]
        )
        
        eff_uv = unit_value * (1 + (sc["Pm"] / 100.0))
        daily_cogs = avg_demand * eff_uv
        
        avg_transit_inv = avg_demand * sc["Lt"]
        total_owned_inv = res['avg_inventory'] + avg_transit_inv
        
        dio = total_owned_inv / avg_demand if avg_demand > 0 else 0
        dso = credit_given
        dpo = sc["Crx"] 
        ccc = dio + dso - dpo
        
        avg_inv_val = total_owned_inv * eff_uv
        avg_rec_val = daily_cogs * dso
        avg_pay_val = daily_cogs * dpo
        net_cap_tied_up = avg_inv_val + avg_rec_val - avg_pay_val
        
        ops_cost_data[sc["Name"]] = [
            f"{int(sc['Rop']):,}", f"{int(sc['OQty']):,}", f"{res['fill_rate']:.2f}%", 
            f"{int(res['stockout_days']):,}", f"{int(res['min_inventory']):,}", 
            f"{int(res['max_inventory']):,}", f"{int(res['avg_inventory']):,}", 
            f"${res['holding_cost']:,.0f}", f"${res['ordering_cost']:,.0f}", 
            f"${res['product_cost']:,.0f}", f"${res['total_cost']:,.0f}"
        ]
        
        ccc_data[sc["Name"]] = [
            f"{float(sc['Lt']):.1f}", f"{dio:.1f}", f"{dso:.1f}", f"{dpo:.1f}", f"{ccc:.1f}"
        ]
        
        wc_data[sc["Name"]] = [
            f"${avg_inv_val:,.0f}", f"${avg_rec_val:,.0f}", f"${avg_pay_val:,.0f}", f"${net_cap_tied_up:,.0f}"
        ]
        
    st.markdown("### 🏆 Executive Scenario Scorecard")
    
    st.markdown("#### 1. Operational & Cost Performance")
    st.dataframe(pd.DataFrame(ops_cost_data), use_container_width=True, hide_index=True)
    
    st.markdown("#### 2. Cash Conversion Cycle (Days)")
    st.dataframe(pd.DataFrame(ccc_data), use_container_width=True, hide_index=True)
    
    st.markdown("#### 3. Average Working Capital ($)")
    st.dataframe(pd.DataFrame(wc_data), use_container_width=True, hide_index=True)
