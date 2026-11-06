import streamlit as st
import pandas as pd
import io

# ------------------------------------------------
# Page Configuration
# ------------------------------------------------
st.title("🔄 Inventory Format Converter")
st.write("Upload your raw ERP export to automatically clean and convert it into the **Inventory Simulation App Format**.")

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
                # Attempt strict European date parsing first (DD/MM/YYYY)
                df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='raise')
            except ValueError:
                # Fallback for generic parsing
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce', dayfirst=True)
                
            # Drop any parsing failures and sort 
            df = df.dropna(subset=['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            
            # 5. Aggregate by Day (Resolves issues where a single day has multiple rows)
            df_daily = df.groupby('Date').agg(
                Demand_Sales=('Sale Quantity', 'sum'),
                Receiving=('Purchase Quantity', 'sum'),
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
                df_daily.loc[first_idx, 'Demand_Sales'] - 
                df_daily.loc[first_idx, 'Receiving'] - 
                df_daily.loc[first_idx, 'Adjustment']
            )
            
            # 7. Map to Final Target Format (inventory_simulation_app_format.xlsx)
            standard_df = pd.DataFrame({
                'Date': df_daily['Date'].dt.strftime('%Y-%m-%d'),
                'Opening Balance': df_daily['Opening Balance'].round(0),
                'Demand/Sales': df_daily['Demand_Sales'].round(0),
                'Receiving': df_daily['Receiving'].round(0),
                'Closing Balance': df_daily['Closing_Balance'].round(0)
            })
            
        st.success("✅ File processed and mapped to the Simulation App format successfully!")
        
        # ------------------------------------------------
        # Preview & Download Output
        # ------------------------------------------------
        st.subheader("Data Preview (App Format)")
        st.dataframe(standard_df.head(15), use_container_width=True)
        
        # Create Excel file in memory for download
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            standard_df.to_excel(writer, index=False, sheet_name='Simulation_Data')
            
            # Auto-adjust column widths for the generated Excel file
            worksheet = writer.sheets['Simulation_Data']
            for i, col in enumerate(standard_df.columns):
                max_len = max(standard_df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
                
        st.download_button(
            label="📥 Download Converted App File (.xlsx)",
            data=buffer.getvalue(),
            file_name="Converted_Simulation_App_Format.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        
    except Exception as e:
        st.error(f"⚠️ Error processing the file: {e}")
