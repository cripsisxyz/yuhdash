import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, Tuple
import re
from price_api import get_current_price as api_get_price, get_ticker_info as api_get_info, get_historical_data

st.set_page_config(page_title="Yuhdash", page_icon=":material/finance_mode:", layout="wide")

st.markdown("""
<style>
[data-testid="metric-container"] {
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 14px 16px;
    background-color: rgba(255,255,255,0.025);
}
[data-testid="stMetricDelta"] {
    font-size: 0.82rem !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_ticker_info(ticker: str) -> Dict:
    """Get ticker information using multi-source API"""
    return api_get_info(ticker)

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_current_price(ticker: str) -> Tuple[float, str]:
    """Get current price using multi-source API with fallback"""
    price, source = api_get_price(ticker)
    return (price if price else 0.0), source

@st.cache_data(ttl=3600)
def get_historical_prices(ticker: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Get historical prices"""
    data = get_historical_data(ticker, start_date, end_date)
    return data if data is not None else pd.DataFrame()

def extract_asset_description(activity_name: str) -> str:
    """Extract asset description from ACTIVITY NAME column"""
    # Example: "7.2737x Silver (Swisscanto Silver)" -> "Silver (Swisscanto Silver)"
    if pd.isna(activity_name) or activity_name == '':
        return ''

    # Remove the quantity prefix (e.g., "7.2737x ")
    match = re.search(r'[\d.]+x\s+(.+)', str(activity_name))
    if match:
        extracted = match.group(1)
        # Remove leading/trailing quotes and whitespace
        extracted = extracted.strip().strip('"').strip("'")
        return extracted

    # Fallback: clean up the activity name
    cleaned = str(activity_name).strip().strip('"').strip("'")
    return cleaned

def detect_csv_format(df):
    """Detect which CSV format is being used"""
    columns = df.columns.tolist()
    if 'Transaction type' in columns or 'Transaction ID' in columns:
        return 'crypto'
    elif 'ACTIVITY TYPE' in columns:
        return 'standard'
    else:
        return 'unknown'

def normalize_crypto_format(df):
    """Normalize crypto format to standard format"""
    normalized = pd.DataFrame()
    try:
        transaction_type_col = 'Transaction type' if 'Transaction type' in df.columns else None
        asset_col = 'Asset' if 'Asset' in df.columns else None
        amount_col = 'Eur (amount)' if 'Eur (amount)' in df.columns else None
        currency_col = 'Currency' if 'Currency' in df.columns else None
        fee_col = 'Fee' if 'Fee' in df.columns else None
        asset_amount_col = 'Asset (amount)' if 'Asset (amount)' in df.columns else None
        market_price_col = 'Asset (market price)' if 'Asset (market price)' in df.columns else None
        date_col = 'Date (UTC - Coordinated Universal Time)' if 'Date (UTC - Coordinated Universal Time)' in df.columns else None

        if not all([transaction_type_col, asset_col, amount_col]):
            raise ValueError(f"Required columns not found. Available columns: {df.columns.tolist()}")

        def safe_float(series):
            return pd.to_numeric(
                series.astype(str).str.replace(',', '.').str.strip().replace('', '0'),
                errors='coerce'
            ).fillna(0).abs()

        normalized['ACTIVITY TYPE'] = df[transaction_type_col].apply(
            lambda x: 'INVEST_ORDER_EXECUTED' if x == 'Buy' else ('INVEST_SELL_EXECUTED' if x == 'Sell' else x)
        )
        normalized['ACTIVITY NAME'] = df[transaction_type_col].astype(str) + ' ' + df[asset_col].astype(str)
        normalized['DEBIT'] = safe_float(df[amount_col])
        normalized['DEBIT CURRENCY'] = df[currency_col] if currency_col else 'EUR'
        normalized['CREDIT'] = 0
        normalized['CREDIT CURRENCY'] = ''
        normalized['FEES/COMMISSION'] = safe_float(df[fee_col]) if fee_col else 0
        normalized['BUY/SELL'] = df[transaction_type_col].apply(
            lambda x: 'BUY' if x == 'Buy' else 'SELL' if x == 'Sell' else ''
        )
        normalized['QUANTITY'] = safe_float(df[asset_amount_col]) if asset_amount_col else 0
        normalized['ASSET'] = df[asset_col].astype(str).str.strip()
        normalized['PRICE PER UNIT'] = safe_float(df[market_price_col]) if market_price_col else 0
        if date_col:
            normalized['DATE'] = pd.to_datetime(df[date_col], errors='coerce')
        return normalized
    except Exception as e:
        st.error(f"Error normalizing crypto format: {str(e)}")
        st.write("Available columns:", df.columns.tolist())
        st.write("First rows:", df.head())
        raise

def calculate_portfolio_timeline(investments_df: pd.DataFrame, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Calculate portfolio value over time"""
    # Create date range
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')

    # Get unique assets
    assets = investments_df['ASSET'].unique()

    timeline_data = []

    for date in date_range:
        daily_value = 0
        for asset in assets:
            # Get all transactions up to this date
            asset_txs = investments_df[
                (investments_df['ASSET'] == asset) &
                (investments_df['DATE'] <= date)
            ].copy()

            if len(asset_txs) == 0:
                continue

            # Calculate position
            quantity = 0
            for _, tx in asset_txs.iterrows():
                if tx['BUY/SELL'] == 'BUY':
                    quantity += tx['QUANTITY']
                elif tx['BUY/SELL'] == 'SELL':
                    quantity -= tx['QUANTITY']

            if quantity > 0:
                # Get historical price
                hist_prices = get_historical_prices(asset, date, date + timedelta(days=1))
                if not hist_prices.empty:
                    price = hist_prices['Close'].iloc[-1]
                    daily_value += quantity * price

        timeline_data.append({
            'Date': date,
            'Portfolio Value': daily_value
        })

    return pd.DataFrame(timeline_data)

# Title and description
st.title("Yuhdash")
st.markdown("Portfolio analytics for your Yuh transactions")

# File uploader
uploaded_file = st.file_uploader("Upload your Yuh CSV file", type=['csv'])

if uploaded_file is not None:
    # Try to read CSV with different separators
    try:
        df = pd.read_csv(uploaded_file, sep=',')
        if len(df.columns) == 1:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=';')
        if len(df.columns) == 1:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file)
    except:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file)

    # Clean column names
    df.columns = df.columns.str.strip()

    st.success(f"File loaded: {len(df)} transactions found")

    # Detect format
    csv_format = detect_csv_format(df)

    if csv_format == 'crypto':
        st.info("Format detected: Crypto Transactions")
        df = normalize_crypto_format(df)
    elif csv_format == 'standard':
        st.info("Format detected: Standard Yuh format")
    else:
        st.error("CSV format not recognized.")
        st.stop()

    # Show raw data
    with st.expander(":material/table: Raw Data"):
        st.dataframe(df)

    # Add DATE column if not present
    if 'DATE' not in df.columns:
        if 'DATE' in df.columns:
            df['DATE'] = pd.to_datetime(df['DATE'], errors='coerce')
        else:
            df['DATE'] = pd.to_datetime('today')

    # Calculate total fees
    if 'FEES/COMMISSION' in df.columns:
        df['FEES/COMMISSION'] = pd.to_numeric(df['FEES/COMMISSION'], errors='coerce').fillna(0)
        total_fees = df['FEES/COMMISSION'].sum()
    else:
        total_fees = 0

    # Filter investment transactions
    investment_activities = ['INVEST_ORDER_EXECUTED', 'INVEST_RECURRING_ORDER_EXECUTED', 'INVEST_SELL_EXECUTED']

    if 'ACTIVITY TYPE' in df.columns:
        investments_df = df[df['ACTIVITY TYPE'].isin(investment_activities)].copy()
    else:
        investments_df = pd.DataFrame()

    if len(investments_df) > 0:
        # Process investment data
        investments_df['QUANTITY'] = pd.to_numeric(investments_df['QUANTITY'], errors='coerce').fillna(0)
        investments_df['PRICE PER UNIT'] = pd.to_numeric(investments_df['PRICE PER UNIT'], errors='coerce').fillna(0)
        investments_df['DEBIT'] = pd.to_numeric(investments_df['DEBIT'], errors='coerce').fillna(0).abs()
        investments_df['DATE'] = pd.to_datetime(investments_df['DATE'], errors='coerce', dayfirst=True)

        if 'CREDIT' in investments_df.columns:
            investments_df['CREDIT'] = pd.to_numeric(investments_df['CREDIT'], errors='coerce').fillna(0)
        else:
            investments_df['CREDIT'] = 0

        # Extract asset descriptions from ACTIVITY NAME
        if 'ACTIVITY NAME' in investments_df.columns:
            investments_df['ASSET_DESCRIPTION'] = investments_df['ACTIVITY NAME'].apply(extract_asset_description)
        else:
            investments_df['ASSET_DESCRIPTION'] = ''

        # Time Range Selector
        st.header(":material/date_range: Time Range")
        col1, col2 = st.columns(2)

        min_date = investments_df['DATE'].min().date()
        max_date = investments_df['DATE'].max().date()

        with col1:
            start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
        with col2:
            end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date)

        # Filter by date range
        mask = (investments_df['DATE'].dt.date >= start_date) & (investments_df['DATE'].dt.date <= end_date)
        filtered_investments = investments_df[mask].copy()

        # Calculate portfolio by asset
        portfolio = {}
        asset_transactions = {}
        asset_descriptions = {}  # Store asset descriptions from ACTIVITY NAME
        realized_pnl = {}  # Realized profits (closed positions)
        asset_fees = {}  # Track fees per asset

        for _, row in filtered_investments.iterrows():
            asset = row['ASSET']
            if pd.notna(asset) and asset != '':
                if asset not in portfolio:
                    portfolio[asset] = {
                        'quantity': 0,
                        'total_cost': 0,
                        'transactions': [],
                        'buy_transactions': [],
                        'sell_transactions': []
                    }
                    asset_transactions[asset] = []
                    asset_descriptions[asset] = row.get('ASSET_DESCRIPTION', '')
                    realized_pnl[asset] = 0
                    asset_fees[asset] = 0

                quantity = row['QUANTITY']
                price_per_unit = row['PRICE PER UNIT']
                buy_sell = row['BUY/SELL']
                debit = row['DEBIT']
                credit = row['CREDIT']
                date = row['DATE']
                fee = row.get('FEES/COMMISSION', 0) if 'FEES/COMMISSION' in row else 0

                # Accumulate fees for this asset
                asset_fees[asset] += fee

                # Record transaction
                asset_transactions[asset].append({
                    'date': date,
                    'type': buy_sell,
                    'quantity': quantity,
                    'price': price_per_unit,
                    'total': debit,
                    'fee': fee,
                    'activity': row['ACTIVITY NAME'] if 'ACTIVITY NAME' in row else ''
                })

                if buy_sell == 'BUY':
                    portfolio[asset]['quantity'] += quantity
                    portfolio[asset]['total_cost'] += debit
                    portfolio[asset]['buy_transactions'].append({
                        'date': date,
                        'quantity': quantity,
                        'price': price_per_unit,
                        'cost': debit
                    })
                elif buy_sell == 'SELL':
                    # Calculate realized P&L
                    avg_cost_per_unit = portfolio[asset]['total_cost'] / portfolio[asset]['quantity'] if portfolio[asset]['quantity'] > 0 else 0
                    realized_gain = (price_per_unit - avg_cost_per_unit) * quantity
                    realized_pnl[asset] += realized_gain

                    portfolio[asset]['quantity'] -= quantity
                    if portfolio[asset]['quantity'] > 0:
                        avg_cost = portfolio[asset]['total_cost'] / (portfolio[asset]['quantity'] + quantity)
                        portfolio[asset]['total_cost'] -= avg_cost * quantity
                    else:
                        portfolio[asset]['total_cost'] = 0

                    portfolio[asset]['sell_transactions'].append({
                        'date': date,
                        'quantity': quantity,
                        'price': price_per_unit,
                        'proceeds': credit if credit > 0 else quantity * price_per_unit
                    })

        # Calculate current prices from CSV data (last known price per unit)
        current_prices = {}
        for asset in portfolio.keys():
            if portfolio[asset]['quantity'] > 0.0001:
                # Get the last transaction for this asset to use as current price
                asset_txs = filtered_investments[filtered_investments['ASSET'] == asset].sort_values('DATE', ascending=False)
                if len(asset_txs) > 0:
                    last_price = asset_txs.iloc[0]['PRICE PER UNIT']
                    current_prices[asset] = last_price if last_price > 0 else (abs(portfolio[asset]['total_cost'] / portfolio[asset]['quantity']) if portfolio[asset]['quantity'] > 0 else 0)
                else:
                    # Fallback to average cost
                    current_prices[asset] = abs(portfolio[asset]['total_cost'] / portfolio[asset]['quantity']) if portfolio[asset]['quantity'] > 0 else 0

        # Pre-compute all metrics before display
        total_invested = sum([abs(p['total_cost']) for p in portfolio.values() if p['quantity'] > 0.0001])
        unique_assets = len([k for k, v in portfolio.items() if v['quantity'] > 0.0001])
        total_realized = sum(realized_pnl.values())

        portfolio_data = []
        total_current_value = 0
        total_cost = 0
        total_unrealized = 0

        for asset, data in portfolio.items():
            if data['quantity'] > 0.0001:
                current_price = current_prices.get(asset, 0)
                current_value = data['quantity'] * current_price
                cost = abs(data['total_cost'])
                unrealized_pnl = current_value - cost
                unrealized_pnl_pct = (unrealized_pnl / cost * 100) if cost > 0.01 else 0

                realized = realized_pnl.get(asset, 0)
                total_pnl = realized + unrealized_pnl
                total_pnl_pct = (total_pnl / cost * 100) if cost > 0.01 else 0

                info = get_ticker_info(asset)

                asset_desc = asset_descriptions.get(asset, '')
                if not asset_desc:
                    asset_desc = info['name']

                asset_type = info.get('asset_type', 'N/A')
                type_icon = {
                    'ETF': '📊', 'Stock': '📈', 'Crypto': '₿',
                    'Mutual Fund': '📊', 'Index': '📉', 'Future': '📈',
                    'Option': '📈', 'Currency': '💱', 'N/A': '—'
                }.get(asset_type, '—')

                portfolio_data.append({
                    'Type': f"{type_icon} {asset_type}",
                    'Asset': asset,
                    'Name': asset_desc,
                    'Quantity': data['quantity'],
                    'Avg Price': cost / data['quantity'] if data['quantity'] > 0 else 0,
                    'Current Price': current_price,
                    'Total Cost': cost,
                    'Current Value': current_value,
                    'Fees Paid': asset_fees.get(asset, 0),
                    'Realized PnL': realized,
                    'Unrealized PnL': unrealized_pnl,
                    'Total PnL': total_pnl,
                    'PnL %': total_pnl_pct,
                    'Description': info['description'][:100] + '...' if len(info['description']) > 100 else info['description']
                })

                total_current_value += current_value
                total_cost += cost
                total_unrealized += unrealized_pnl

        portfolio_df = pd.DataFrame(portfolio_data)

        total_profit_loss = total_unrealized + total_realized
        net_profit_loss = total_profit_loss - total_fees
        total_profit_loss_pct = (total_profit_loss / total_cost * 100) if total_cost > 0 else 0
        roi_pct = (net_profit_loss / total_cost * 100) if total_cost > 0 else 0

        # Primary performance KPIs
        st.header(":material/analytics: Portfolio Overview")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Portfolio Value", f"{total_current_value:.2f} CHF")

        with col2:
            st.metric(
                "Unrealized P&L",
                f"{total_unrealized:.2f} CHF",
                delta=f"{(total_unrealized/total_cost*100):+.2f}%" if total_cost > 0 else None,
                delta_color="normal" if total_unrealized >= 0 else "inverse",
                help="Open positions, excluding fees"
            )

        with col3:
            st.metric(
                "Gross P&L",
                f"{total_profit_loss:.2f} CHF",
                delta=f"{total_profit_loss_pct:+.2f}%",
                delta_color="normal" if total_profit_loss >= 0 else "inverse",
                help="Before deducting fees"
            )

        with col4:
            st.metric(
                "NET P&L",
                f"{net_profit_loss:.2f} CHF",
                delta=f"{roi_pct:+.2f}%",
                delta_color="normal" if net_profit_loss >= 0 else "inverse",
                help=f"After deducting {total_fees:.2f} CHF in fees"
            )

        # Secondary stats
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Invested", f"{total_invested:.2f} CHF")

        with col2:
            st.metric("Assets Held", unique_assets)

        with col3:
            st.metric(
                "Realized P&L",
                f"{total_realized:.2f} CHF",
                delta=f"{(total_realized/total_invested*100):+.2f}%" if total_invested > 0 and total_realized != 0 else None,
                delta_color="normal" if total_realized >= 0 else "inverse"
            )

        with col4:
            st.metric("Fees Paid", f"{total_fees:.2f} CHF")

        st.divider()

        # Portfolio breakdown table
        st.subheader(":material/table_view: Breakdown by Asset")

        # Format for display
        portfolio_display = portfolio_df.copy()
        portfolio_display['Quantity'] = portfolio_display['Quantity'].apply(lambda x: f"{x:.4f}")
        portfolio_display['Avg Price'] = portfolio_display['Avg Price'].apply(lambda x: f"{x:.2f} CHF")
        portfolio_display['Current Price'] = portfolio_display['Current Price'].apply(lambda x: f"{x:.2f} CHF")
        portfolio_display['Total Cost'] = portfolio_display['Total Cost'].apply(lambda x: f"{x:.2f} CHF")
        portfolio_display['Current Value'] = portfolio_display['Current Value'].apply(lambda x: f"{x:.2f} CHF")
        portfolio_display['Fees Paid'] = portfolio_display['Fees Paid'].apply(lambda x: f"{x:.2f} CHF")
        portfolio_display['Realized PnL'] = portfolio_display['Realized PnL'].apply(lambda x: f"{'+' if x >= 0 else ''}{x:.2f} CHF")
        portfolio_display['Unrealized PnL'] = portfolio_display['Unrealized PnL'].apply(lambda x: f"{'+' if x >= 0 else ''}{x:.2f} CHF")
        portfolio_display['Total PnL'] = portfolio_display['Total PnL'].apply(lambda x: f"{'+' if x >= 0 else ''}{x:.2f} CHF")
        portfolio_display['PnL %'] = portfolio_display['PnL %'].apply(lambda x: f"{'+' if x >= 0 else ''}{x:.2f}%")

        _GREEN = 'background-color: rgba(0,200,83,0.15); color: #00c853'
        _RED   = 'background-color: rgba(255,82,82,0.15); color: #ff5252'
        _pnl_cols = ['Realized PnL', 'Unrealized PnL', 'Total PnL', 'PnL %']
        _display_cols = ['Type', 'Asset', 'Name', 'Quantity', 'Avg Price', 'Current Price',
                         'Current Value', 'Fees Paid', 'Realized PnL', 'Unrealized PnL', 'Total PnL', 'PnL %']

        def _highlight_pnl(val):
            v = str(val)
            if v.startswith('+'):
                return _GREEN
            elif v.startswith('-'):
                return _RED
            return ''

        try:
            _styled = portfolio_display[_display_cols].style.map(_highlight_pnl, subset=_pnl_cols)
        except AttributeError:
            _styled = portfolio_display[_display_cols].style.applymap(_highlight_pnl, subset=_pnl_cols)

        st.dataframe(_styled, use_container_width=True)

        # Clarification note
        st.info("The P&L shown does not include fees. The NET P&L in the summary deducts all fees paid.")

        # Asset Details Expander
        st.subheader(":material/info: Asset Details")
        for _, row in portfolio_df.iterrows():
            with st.expander(f"{row['Type']} {row['Asset']} - {row['Name']}"):
                # First row - Key metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Quantity", f"{row['Quantity']:.4f}")
                with col2:
                    st.metric("Avg Buy Price", f"{row['Avg Price']:.2f} CHF")
                with col3:
                    st.metric("Current Price", f"{row['Current Price']:.2f} CHF")
                with col4:
                    st.metric("Total Cost", f"{row['Total Cost']:.2f} CHF")

                # Second row - Performance metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    gain_pct = ((row['Current Value'] - row['Total Cost']) / row['Total Cost'] * 100) if row['Total Cost'] > 0 else 0
                    st.metric(
                        "Current Value",
                        f"{row['Current Value']:.2f} CHF",
                        delta=f"{gain_pct:+.2f}%",
                        delta_color="normal" if gain_pct >= 0 else "inverse"
                    )
                with col2:
                    realized_pct = (row['Realized PnL'] / row['Total Cost'] * 100) if row['Total Cost'] > 0 else 0
                    st.metric(
                        "Realized P&L",
                        f"{row['Realized PnL']:.2f} CHF",
                        delta=f"{realized_pct:+.2f}%",
                        delta_color="normal" if row['Realized PnL'] >= 0 else "inverse"
                    )
                with col3:
                    unrealized_pct = (row['Unrealized PnL'] / row['Total Cost'] * 100) if row['Total Cost'] > 0 else 0
                    st.metric(
                        "Unrealized P&L",
                        f"{row['Unrealized PnL']:.2f} CHF",
                        delta=f"{unrealized_pct:+.2f}%",
                        delta_color="normal" if row['Unrealized PnL'] >= 0 else "inverse"
                    )
                with col4:
                    st.metric(
                        "Total P&L",
                        f"{row['Total PnL']:.2f} CHF",
                        delta=f"{row['PnL %']:+.2f}%",
                        delta_color="normal" if row['Total PnL'] >= 0 else "inverse"
                    )

                # Description section
                st.markdown("---")
                st.markdown(f"**Description:** {row['Description']}")

        # Visualizations
        st.header(":material/bar_chart: Charts")

        tab1, tab2, tab3, tab4 = st.tabs([
            ":material/donut_large: Composition",
            ":material/trending_up: Performance",
            ":material/timeline: Timeline",
            ":material/receipt_long: Transactions"
        ])

        with tab1:
            # Portfolio composition pie chart
            fig_pie = px.pie(
                portfolio_df,
                values='Current Value',
                names='Asset',
                title='Portfolio Composition',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Vivid
            )
            fig_pie.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with tab2:
            # PnL bar chart
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                name='Realized P&L',
                x=portfolio_df['Asset'],
                y=portfolio_df['Realized PnL'],
                marker_color=['#00c853' if v >= 0 else '#ff5252' for v in portfolio_df['Realized PnL']]
            ))
            fig_bar.add_trace(go.Bar(
                name='Unrealized P&L',
                x=portfolio_df['Asset'],
                y=portfolio_df['Unrealized PnL'],
                marker_color=['rgba(0,200,83,0.45)' if v >= 0 else 'rgba(255,82,82,0.45)' for v in portfolio_df['Unrealized PnL']]
            ))
            fig_bar.update_layout(
                title='P&L by Asset',
                barmode='stack',
                xaxis_title='Asset',
                yaxis_title='P&L (CHF)',
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # PnL % chart
            fig_pct = px.bar(
                portfolio_df,
                x='Asset',
                y='PnL %',
                title='Performance % by Asset',
                color='PnL %',
                color_continuous_scale=[[0, '#ff5252'], [0.5, '#ffeb3b'], [1, '#00c853']],
                labels={'PnL %': 'Performance (%)'}
            )
            fig_pct.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_pct, use_container_width=True)

        with tab3:
            # Timeline chart - Evolution by asset
            st.subheader("Portfolio Evolution")

            selected_assets = st.multiselect(
                "Select assets to view their evolution",
                options=list(portfolio.keys()),
                default=list(portfolio.keys())[:3] if len(portfolio) >= 3 else list(portfolio.keys())
            )

            if selected_assets:
                fig_timeline = go.Figure()

                for asset in selected_assets:
                    asset_hist = filtered_investments[filtered_investments['ASSET'] == asset].sort_values('DATE')

                    if len(asset_hist) > 0:
                        # Calculate cumulative position
                        cumulative_qty = 0
                        cumulative_cost = 0
                        timeline_data = []

                        for _, tx in asset_hist.iterrows():
                            if tx['BUY/SELL'] == 'BUY':
                                cumulative_qty += tx['QUANTITY']
                                cumulative_cost += tx['DEBIT']
                            elif tx['BUY/SELL'] == 'SELL':
                                cumulative_qty -= tx['QUANTITY']
                                if cumulative_qty > 0:
                                    avg_cost = cumulative_cost / (cumulative_qty + tx['QUANTITY'])
                                    cumulative_cost -= avg_cost * tx['QUANTITY']
                                else:
                                    cumulative_cost = 0

                            avg_price = cumulative_cost / cumulative_qty if cumulative_qty > 0 else 0
                            current_price = current_prices.get(asset, tx['PRICE PER UNIT'])
                            value = cumulative_qty * current_price

                            timeline_data.append({
                                'date': tx['DATE'],
                                'value': value,
                                'quantity': cumulative_qty
                            })

                        if timeline_data:
                            timeline_df = pd.DataFrame(timeline_data)
                            fig_timeline.add_trace(go.Scatter(
                                x=timeline_df['date'],
                                y=timeline_df['value'],
                                name=asset,
                                mode='lines+markers'
                            ))

                fig_timeline.update_layout(
                    title='Value Evolution by Asset',
                    xaxis_title='Date',
                    yaxis_title='Value (CHF)',
                    hovermode='x unified',
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_timeline, use_container_width=True)

        with tab4:
            # Transaction history
            st.subheader("Transaction History")
            selected_asset = st.selectbox("Select an asset", list(asset_transactions.keys()))

            if selected_asset:
                transactions = asset_transactions[selected_asset]
                transactions_df = pd.DataFrame(transactions)
                transactions_df = transactions_df.sort_values('date', ascending=False)
                st.dataframe(transactions_df, use_container_width=True)

        # Additional stats
        st.header(":material/query_stats: Statistics")

        col1, col2 = st.columns(2)

        with col1:
            # Activity type distribution
            if 'ACTIVITY TYPE' in df.columns:
                activity_counts = df['ACTIVITY TYPE'].value_counts()
                fig_activities = px.bar(
                    x=activity_counts.index,
                    y=activity_counts.values,
                    title='Activity Type Distribution',
                    labels={'x': 'Activity Type', 'y': 'Count'}
                )
                fig_activities.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_activities, use_container_width=True)

        with col2:
            # Fees breakdown
            if 'FEES/COMMISSION' in df.columns:
                fees_df = df[df['FEES/COMMISSION'] > 0]
                if len(fees_df) > 0 and 'ACTIVITY TYPE' in fees_df.columns:
                    fees_by_activity = fees_df.groupby('ACTIVITY TYPE')['FEES/COMMISSION'].sum().sort_values(ascending=False)
                    fig_fees = px.bar(
                        x=fees_by_activity.index,
                        y=fees_by_activity.values,
                        title='Fees by Activity Type',
                        labels={'x': 'Activity Type', 'y': 'Fees (CHF)'}
                    )
                    fig_fees.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_fees, use_container_width=True)
                else:
                    st.info("No fees recorded in this period")

    else:
        st.warning("No investment transactions found in the file.")

else:
    st.info("Upload your Yuh CSV file to start the analysis.")

    st.markdown("""
    ### Instructions

    1. **Download your CSV** from the Yuh app
    2. **Upload the file** using the button above
    3. **Select the date range** you want to analyze

    ### Features

    - **Historical prices** from your CSV data
    - **Portfolio evolution timeline**
    - **Realized vs Unrealized P&L** — closed vs open positions
    - **Detailed analysis by asset** with descriptions
    - **Customizable date range**
    - **Net ROI** after fees
    """)
