import streamlit as st
import akshare as ak
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import plotly.graph_objects as go
import plotly.express as px
warnings.filterwarnings('ignore')

# 设置页面配置
st.set_page_config(
    page_title="A股集合竞价分析系统",
    page_icon="📊",
    layout="wide"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #0D47A1;
        margin-top: 1rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .signal-positive {
        color: #00C853;
        font-weight: bold;
    }
    .signal-negative {
        color: #D32F2F;
        font-weight: bold;
    }
    .signal-neutral {
        color: #FFC107;
        font-weight: bold;
    }
    .stock-search {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 0.5rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# 缓存股票列表数据
@st.cache_data(ttl=3600)  # 缓存1小时
def get_stock_list():
    """获取A股股票列表"""
    try:
        # 获取A股股票列表
        stock_info_df = ak.stock_info_a_code_name()
        return stock_info_df
    except Exception as e:
        st.error(f"获取股票列表失败: {e}")
        # 返回默认股票列表作为备选
        default_stocks = pd.DataFrame({
            'code': ['000001', '600000', '300015', '600519', '002594', '300750'],
            'name': ['平安银行', '浦发银行', '爱尔眼科', '贵州茅台', '比亚迪', '宁德时代']
        })
        return default_stocks

def search_stocks(search_term, stock_list):
    """搜索股票"""
    if not search_term:
        return stock_list.head(10)  # 返回前10个作为推荐
    
    # 搜索股票代码或名称
    mask = (
        stock_list['code'].str.contains(search_term, na=False) |
        stock_list['name'].str.contains(search_term, na=False)
    )
    return stock_list[mask].head(10)  # 限制返回10条结果

def get_stock_info(stock_code, stock_list):
    """获取股票名称"""
    try:
        stock_info = stock_list[stock_list['code'] == stock_code]
        if not stock_info.empty:
            return stock_info.iloc[0]['name']
        return f"股票{stock_code}"
    except:
        return f"股票{stock_code}"

def get_auction_data_akshare(symbol):
    """获取AKShare集合竞价数据"""
    try:
        pre_market_df = ak.stock_zh_a_hist_pre_min_em(
            symbol=symbol,
            start_time="09:00:00",
            end_time="09:30:00"
        )
        
        if not pre_market_df.empty:
            # 筛选集合竞价时间段 (9:15-9:25)
            auction_df = pre_market_df[
                pre_market_df['时间'].str.contains('09:1[5-9]|09:2[0-5]', na=False)
            ].copy()
            
            if not auction_df.empty:
                # 添加时间列（仅保留时间部分）
                auction_df['竞价时间'] = auction_df['时间'].str.split().str[1]
                auction_df['竞价时间'] = pd.to_datetime(auction_df['竞价时间']).dt.strftime('%H:%M:%S')
                
                # 重命名列
                auction_df = auction_df.rename(columns={
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume'
                })
                
                return auction_df[['竞价时间', 'close', 'volume', 'high', 'low']]
    except Exception as e:
        st.error(f"获取{symbol}数据失败: {e}")
    return None

def get_baostock_data(symbol, days=10):
    """获取BaoStock开盘价数据"""
    try:
        lg = bs.login()
        if lg.error_code == '0':
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            rs = bs.query_history_k_data_plus(
                symbol,
                "date,code,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            bs.logout()
            
            if data_list:
                df = pd.DataFrame(data_list, columns=rs.fields)
                
                # 数据类型转换
                numeric_cols = ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'pctChg']
                for col in numeric_cols:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # 计算开盘缺口
                df['gap'] = ((df['open'] - df['preclose']) / df['preclose'] * 100).round(2)
                df['gap'] = df['gap'].apply(lambda x: f"{x:+.2f}%")
                
                # 格式化数据
                df['open'] = df['open'].round(2)
                df['close'] = df['close'].round(2)
                df['high'] = df['high'].round(2)
                df['low'] = df['low'].round(2)
                df['volume'] = (df['volume'] / 10000).round(2)  # 转换为万股
                df['pctChg'] = df['pctChg'].round(2)
                
                return df.dropna()
    except Exception as e:
        st.error(f"获取{symbol}数据失败: {e}")
    return None

def analyze_auction_signals(auction_df):
    """分析集合竞价信号"""
    if auction_df is None or auction_df.empty:
        return None
    
    opening_price = auction_df['close'].iloc[-1]
    first_price = auction_df['close'].iloc[0]
    total_volume = auction_df['volume'].sum()
    price_high = auction_df['high'].max()
    price_low = auction_df['low'].min()
    trend_pct = (opening_price - first_price) / first_price * 100
    volatility_pct = (price_high - price_low) / opening_price * 100
    
    # 生成信号
    signals = {}
    
    # 趋势信号
    if trend_pct > 1:
        signals['trend'] = ('强烈看涨', 'positive')
    elif trend_pct > 0.2:
        signals['trend'] = ('看涨', 'positive')
    elif trend_pct < -1:
        signals['trend'] = ('强烈看跌', 'negative')
    elif trend_pct < -0.2:
        signals['trend'] = ('看跌', 'negative')
    else:
        signals['trend'] = ('中性', 'neutral')
    
    # 成交量信号
    if total_volume > 10000:
        signals['volume'] = ('高成交量', 'positive')
    elif total_volume > 5000:
        signals['volume'] = ('中等成交量', 'neutral')
    else:
        signals['volume'] = ('低成交量', 'neutral')
    
    # 波动率信号
    if volatility_pct > 2:
        signals['volatility'] = ('高波动', 'negative')
    elif volatility_pct > 1:
        signals['volatility'] = ('中等波动', 'neutral')
    else:
        signals['volatility'] = ('低波动', 'positive')
    
    # 综合建议
    bullish_count = sum([
        trend_pct > 0.5,
        total_volume > 5000,
        volatility_pct < 3
    ])
    
    if bullish_count >= 2:
        signals['recommendation'] = ('建议关注 (偏多)', 'positive')
    elif trend_pct < -0.5:
        signals['recommendation'] = ('谨慎观望 (偏空)', 'negative')
    else:
        signals['recommendation'] = ('中性持有', 'neutral')
    
    return {
        'opening_price': opening_price,
        'trend_pct': trend_pct,
        'volatility_pct': volatility_pct,
        'total_volume': total_volume,
        'price_high': price_high,
        'price_low': price_low,
        'signals': signals
    }

def plot_auction_chart(auction_df, symbol):
    """绘制集合竞价走势图"""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=auction_df['竞价时间'],
        y=auction_df['close'],
        mode='lines+markers',
        name='价格',
        line=dict(color='#1E88E5', width=2),
        marker=dict(size=6)
    ))
    
    fig.add_trace(go.Bar(
        x=auction_df['竞价时间'],
        y=auction_df['volume'],
        name='成交量',
        yaxis='y2',
        marker_color='rgba(255, 193, 7, 0.5)'
    ))
    
    fig.update_layout(
        title=f'{symbol} 集合竞价走势',
        xaxis_title='竞价时间',
        yaxis_title='价格',
        yaxis2=dict(
            title='成交量',
            overlaying='y',
            side='right'
        ),
        height=400,
        hovermode='x unified'
    )
    
    return fig

def main():
    st.markdown('<h1 class="main-header">📈 A股集合竞价分析系统</h1>', unsafe_allow_html=True)
    
    # 获取股票列表
    stock_list = get_stock_list()
    
    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 配置选项")
        
        # 股票搜索框
        st.markdown('<div class="stock-search">', unsafe_allow_html=True)
        st.mark("### 🔍 股票搜索")
        
        # 初始化session state
        if 'selected_stock' not in st.session_state:
            st.session_state.selected_stock = '000001'
        if 'search_term' not in st.session_state:
            st.session_state.search_term = ''
        
        # 搜索输入框
        search_term = st.text_input(
            "输入股票代码或名称",
            value=st.session_state.search_term,
            placeholder="例如: 000001 或 平安银行",
            key="search_input"
        )
        
        # 更新搜索词
        if search_term != st.session_state.search_term:
            st.session_state.search_term = search_term
        
        # 搜索结果显示
        search_results = search_stocks(search_term, stock_list)
        
        if not search_results.empty:
            # 创建选择选项
            options = []
            for _, row in search_results.iterrows():
                options.append(f"{row['code']} - {row['name']}")
            
            # 默认选中000001
            default_index = 0
            for i, opt in enumerate(options):
                if opt.startswith('000001'):
                    default_index = i
                    break
            
            selected_option = st.selectbox(
                "选择股票",
                options=options,
                index=default_index,
                key="stock_selector"
            )
            
            # 解析选择的股票代码
            if selected_option:
                st.session_state.selected_stock = selected_option.split(' - ')[0]
        else:
            st.warning("未找到匹配的股票")
            st.session_state.selected_stock = '000001'
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 数据源选择
        data_source = st.radio(
            "选择数据源",
            ["AKShare (集合竞价)", "BaoStock (历史开盘)"]
        )
        
        if data_source == "BaoStock (历史开盘)":
            days_back = st.slider("回溯天数", 5, 30, 10)
        
        refresh_button = st.button("🔄 刷新数据")
    
    # 获取当前选择的股票代码和名称
    selected_stock = st.session_state.selected_stock
    stock_name = get_stock_info(selected_stock, stock_list)
    
    # 主内容区域
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f'<h2 class="sub-header">📊 {stock_name} ({selected_stock}) 数据</h2>', 
                   unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"<p style='text-align: right; color: #666;'>更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>", 
                   unsafe_allow_html=True)
    
    # 根据数据源显示不同内容
    if data_source == "AKShare (集合竞价)":
        with st.spinner('正在获取集合竞价数据...'):
            auction_data = get_auction_data_akshare(selected_stock)
            
            if auction_data is not None and not auction_data.empty:
                # 显示数据表格
                st.markdown("### 📋 集合竞价数据表")
                
                # 格式化显示
                display_df = auction_data.copy()
                display_df['close'] = display_df['close'].round(2)
                display_df['high'] = display_df['high'].round(2)
                display_df['low'] = display_df['low'].round(2)
                display_df['volume'] = display_df['volume'].apply(lambda x: f"{x:,.0f}")
                
                # 使用st.dataframe显示表格
                st.dataframe(
                    display_df,
                    column_config={
                        "竞价时间": "时间",
                        "close": "价格",
                        "volume": "成交量(手)",
                        "high": "最高",
                        "low": "最低"
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                # 绘制走势图
                st.markdown("### 📈 竞价走势图")
                fig = plot_auction_chart(auction_data, stock_name)
                st.plotly_chart(fig, use_container_width=True)
                
                # 信号分析
                st.markdown("### 🚦 信号分析")
                analysis = analyze_auction_signals(auction_data)
                
                if analysis:
                    # 关键指标
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("开盘价", f"¥{analysis['opening_price']:.2f}")
                    with col2:
                        st.metric("竞价趋势", f"{analysis['trend_pct']:+.2f}%")
                    with col3:
                        st.metric("波动率", f"{analysis['volatility_pct']:.2f}%")
                    with col4:
                        st.metric("总成交量", f"{analysis['total_volume']:,.0f}")
                    
                    # 信号卡片
                    st.markdown("#### 信号解读")
                    cols = st.columns(4)
                    signal_names = {'trend': '趋势', 'volume': '成交量', 
                                   'volatility': '波动率', 'recommendation': '建议'}
                    
                    for i, (key, (signal, signal_type)) in enumerate(analysis['signals'].items()):
                        with cols[i]:
                            css_class = f"signal-{signal_type}"
                            st.markdown(f"**{signal_names[key]}**")
                            st.markdown(f'<span class="{css_class}">{signal}</span>', 
                                      unsafe_allow_html=True)
            else:
                st.warning("当前非交易时间或无集合竞价数据")
    
    else:  # BaoStock数据
        with st.spinner('正在获取历史开盘数据...'):
            bs_symbol = selected_stock
            if selected_stock.startswith('6'):
                bs_symbol = f"sh.{selected_stock}"
            else:
                bs_symbol = f"sz.{selected_stock}"
            
            bs_data = get_baostock_data(bs_symbol, days_back)
            
            if bs_data is not None and not bs_data.empty:
                st.markdown("### 📋 历史开盘数据表")
                
                # 选择要显示的列
                display_cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'pctChg', 'gap']
                display_df = bs_data[display_cols].copy()
                
                # 重命名列
                display_df.columns = ['日期', '开盘', '收盘', '最高', '最低', '成交量(万股)', '涨跌幅%', '开盘缺口']
                
                # 使用st.dataframe显示表格
                st.dataframe(
                    display_df,
                    hide_index=True,
                    use_container_width=True
                )
                
                # 绘制K线图简化版
                st.markdown("### 📈 价格走势图")
                fig = go.Figure()
                
                fig.add_trace(go.Candlestick(
                    x=bs_data['date'],
                    open=bs_data['open'],
                    high=bs_data['high'],
                    low=bs_data['low'],
                    close=bs_data['close'],
                    name='K线'
                ))
                
                fig.update_layout(
                    title=f'{stock_name} 最近{days_back}天走势',
                    xaxis_title='日期',
                    yaxis_title='价格',
                    height=400,
                    xaxis_rangeslider_visible=False
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # 统计信息
                st.markdown("### 📊 统计信息")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    avg_gap = bs_data['gap'].str.replace('%', '').astype(float).mean()
                    st.metric("平均开盘缺口", f"{avg_gap:+.2f}%")
                
                with col2:
                    positive_days = (bs_data['pctChg'] > 0).sum()
                    st.metric("上涨天数", f"{positive_days}/{len(bs_data)}")
                
                with col3:
                    avg_volume = bs_data['volume'].mean()
                    st.metric("平均成交量", f"{avg_volume:.0f}万股")
            else:
                st.warning("未获取到历史数据")
    
    # 底部说明
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9rem;'>
        <p>数据来源: AKShare & BaoStock | 分析仅供参考，不构成投资建议</p>
        <p>集合竞价时间: 9:15-9:25 | 数据更新频率: 实时</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
