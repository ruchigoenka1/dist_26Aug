import streamlit as st
import pandas as pd
import io

# ------------------------------------------------
# Page Configuration
# ------------------------------------------------
st.title("🔄 Inventory Format Converter")
st.write("Upload your raw ERP export to automatically clean and convert it into the **Standard Inventory Ledger Format** required for the simulation tools.")

# ------------------------------------------------
# File Upload
# ------------------------------------------------
uploaded_file = st.file_uploader("Upload Raw Inventory File (.xlsx or .csv)", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    try:
        with st.spinner("Processing file..."):
            # 1. Load the data
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
                
            # 2. Clean completely empty dates
            df = df.dropna(subset=['Date'])
            
            # 3. Extract purely numeric values, coercing text (like 'Beginning Stock') to 0
            df['Purchase Quantity'] = pd.to_numeric(df['Purchase Quantity'], errors='coerce').fillna(0)
            df['Sale Quantity'] = pd.to_numeric(df['Sale Quantity'], errors='coerce').fillna(0)
            
            # Handle adjustment column if it exists in the raw data
            if 'Adjustment Quantity' in df.columns:
                df['Adjustment Quantity'] = pd.to_numeric(df['Adjustment Quantity'], errors='coerce').fillna(0)
            else:
                df['Adjustment Quantity'] = 0
                
            # 4. Standardise Date formats and sort chronically
            try:
                # Attempt strict European date parsing first (DD/MM/YYYY) as seen in your file
                df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='raise')
            except ValueError:
                # Fallback for generic parsing
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce', dayfirst=True)
                
            # Drop any parsing failures and sort 
            df = df.dropna(subset=['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            
            # 5. Aggregate by Day (Resolves issues where a single day has multiple rows)
            df_daily = df.groupby('Date').agg(
                Demand=('Sale Quantity', 'sum'),
                Orders_Received=('Purchase Quantity', 'sum'),
                Adjustment=('Adjustment Quantity', 'sum'),
                Closing_Balance=('Closing Quantity', 'last') # Takes the final closing balance of the day
            ).reset_index()
            
            # 6. Calculate Opening Balance dynamically 
            # (Opening Balance = Previous day's Closing Balance)
            df_daily['Opening Balance'] = df_daily['Closing_Balance'].shift(1)
            
            # For the very first day, backtrack the Opening Balance based on the day's activity
            first_idx = df_daily.index[0]
            df_daily.loc[first_idx, 'Opening Balance'] = (
                df_daily.loc[first_idx, 'Closing_Balance'] + 
                df_daily.loc[first_idx, 'Demand'] - 
                df_daily.loc[first_idx, 'Orders_Received'] - 
                df_daily.loc[first_idx, 'Adjustment']
            )
            
            # 7. Map to Final Standard Format
            df_daily['Order Placed (PO)'] = 0 # Default placeholder for the standard format
            
            standard_df = pd.DataFrame({
                'Date': df_daily['Date'].dt.strftime('%Y-%m-%d'),
                'Opening Balance': df_daily['Opening Balance'].round(0),
                'Demand (Order Received)': df_daily['Demand'].round(0),
                'Order Placed (PO)': df_daily['Order Placed (PO)'],
                'Orders Received': df_daily['Orders_Received'].round(0),
                'Closing Balance': df_daily['Closing_Balance'].round(0)
            })
            
        st.success("✅ File processed and mapped successfully!")
        
        # ------------------------------------------------
        # Preview & Download Output
        # ------------------------------------------------
        st.subheader("Data Preview (Standard Format)")
        st.dataframe(standard_df.head(15), use_container_width=True)
        
        # Create Excel file in memory for download
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            standard_df.to_excel(writer, index=False, sheet_name='Standard_Ledger')
            
            # Optional: auto-adjust column widths for the generated Excel file
            worksheet = writer.sheets['Standard_Ledger']
            for i, col in enumerate(standard_df.columns):
                max_len = max(standard_df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
                
        st.download_button(
            label="📥 Download Standardized File (.xlsx)",
            data=buffer.getvalue(),
            file_name="Converted_Standard_Inventory_Ledger.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        
    except Exception as e:
        st.error(f"⚠️ Error processing the file: {e}")
