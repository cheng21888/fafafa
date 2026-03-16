#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股集合竞价数据获取演示程序 - Streamlit版本
整合AKShare和BaoStock，展示完整的竞价数据分析流程
"""

import streamlit as st
import akshare as ak
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
        padding: 15px;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    .signal-buy {
        color: #00C853;
        font-weight: bold;
    }
    .signal-sell {
        color: #D32F2F;
        font-weight: bold;
    }
    .signal-hold {
        color: #FFB300;
        font-weight: bold;
    }
    .info-text {
        font-size: 0.9rem;
        color: #616161;
    }
</style>
""", unsafe_allow_html=True)

class AuctionDataAnalyzer:
    """集合竞价数据分析器"""
    
    def __init__(self):
        self.name = "A股集合竞价数据分析器"
        self.baostock_logged_in = False
        
    def login_baostock(self):
        """登录BaoStock"""
        try:
            lg = bs.login()
            if lg.error_code == '0':
                self.baostock_logged_in = True
                return True
            else:
                st.error(f"BaoStock登录失败: {lg.error_msg}")
                return False
        except Exception as e:
            st.error(f"BaoStock连接错误: {e}")
            return False
    
    def logout_baostock(self):
        """登出BaoStock"""
        if self.baostock_logged_in:
            try:
                bs.logout()
                self.baostock_logged_in = False
            except:
                pass
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算RSI指标"""
        try:
            if len(df) < period + 1:
                return 50.0
            
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1]
        except Exception:
            return 50.0
    
    def _calculate_volume_ratio(self, df: pd.DataFrame, period: int = 20) -> float:
        """计算成交量比率"""
        try:
            if len(df) < period:
                return 1.0
            
            avg_volume = df['volume'].tail(period).mean()
            current_volume = df['volume'].iloc[-1]
            
            if avg_volume > 0:
                return current_volume / avg_volume
            return 1.0
        except Exception:
            return 1.0
    
    def _calculate_tech_indicators(self, df: pd.DataFrame) -> dict:
        """计算技术指标评分"""
        score = 0.5
        details = {}
        
        try:
            # 均线系统评分
            ma_score = 0
            if len(df) >= 20:
                ma5 = df['close'].rolling(5).mean().iloc[-1]
                ma10 = df['close'].rolling(10).mean().iloc[-1] 
                ma20 = df['close'].rolling(20).mean().iloc[-1]
                current = df['close'].iloc[-1]
                
                if current > ma5 > ma10 > ma20:
                    ma_score = 0.30
                    ma_desc = "多头排列"
                elif current > ma5 > ma10:
                    ma_score = 0.20
                    ma_desc = "短期多头"
                elif current > ma20:
                    ma_score = 0.10
                    ma_desc = "站上20日线"
                elif current < ma5 < ma10 < ma20:
                    ma_score = -0.20
                    ma_desc = "空头排列"
                elif current < ma20:
                    ma_score = -0.10
                    ma_desc = "跌破20日线"
                else:
                    ma_desc = "均线纠结"
                
                score += ma_score
                details['ma'] = {'score': ma_score, 'desc': ma_desc}
            
            # RSI评分
            rsi = self._calculate_rsi(df)
            rsi_score = 0
            if 40 <= rsi <= 60:
                rsi_score = 0.15
                rsi_desc = "中性"
            elif 60 < rsi <= 70:
                rsi_score = 0.10
                rsi_desc = "强势"
            elif rsi > 70:
                rsi_score = -0.10
                rsi_desc = "超买"
            elif 30 <= rsi < 40:
                rsi_score = 0.05
                rsi_desc = "弱势可能反弹"
            elif rsi < 30:
                rsi_score = 0.10
                rsi_desc = "超卖"
            
            score += rsi_score
            details['rsi'] = {'score': rsi_score, 'value': round(rsi, 2), 'desc': rsi_desc}
            
            # 成交量评分
            vol_ratio = self._calculate_volume_ratio(df)
            vol_score = 0
            if vol_ratio > 2.0:
                vol_score = 0.20
                vol_desc = "显著放量"
            elif vol_ratio > 1.5:
                vol_score = 0.15
                vol_desc = "放量"
            elif vol_ratio > 1.2:
                vol_score = 0.10
                vol_desc = "温和放量"
            elif vol_ratio < 0.5:
                vol_score = -0.10
                vol_desc = "显著缩量"
            else:
                vol_desc = "量能正常"
            
            score += vol_score
            details['volume'] = {'score': vol_score, 'ratio': round(vol_ratio, 2), 'desc': vol_desc}
            
        except Exception as e:
            details['error'] = str(e)
        
        return {
            'total_score': max(0.0, min(1.0, score)),
            'details': details
        }
    
    def get_akshare_auction_data(self, symbol):
        """使用AKShare获取集合竞价数据"""
        try:
            with st.spinner(f'正在获取 {symbol} 的AKShare数据...'):
                pre_market_df = ak.stock_zh_a_hist_pre_min_em(
                    symbol=symbol,
                    start_time="09:00:00",
                    end_time="09:30:00"
                )
                
                if pre_market_df.empty:
                    return None
                
                auction_df = pre_market_df[
                    pre_market_df['时间'].str.contains('09:1[5-9]|09:2[0-5]', na=False)
                ].copy()
                
                if auction_df.empty:
                    return None
                
                opening_price = auction_df['收盘'].iloc[-1] if len(auction_df) > 0 else None
                total_volume = auction_df['成交量'].sum()
                total_amount = auction_df['成交额'].sum()
                price_high = auction_df['最高'].max()
                price_low = auction_df['最低'].min()
                
                if len(auction_df) >= 2:
                    first_price = auction_df['收盘'].iloc[0]
                    last_price = auction_df['收盘'].iloc[-1]
                    trend_pct = (last_price - first_price) / first_price * 100
                else:
                    trend_pct = 0
                
                result = {
                    'symbol': symbol,
                    'data_source': 'AKShare',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'opening_price': float(opening_price) if opening_price else None,
                    'auction_high': float(price_high),
                    'auction_low': float(price_low),
                    'total_volume': int(total_volume),
                    'total_amount': float(total_amount),
                    'trend_pct': round(trend_pct, 2),
                    'data_points': len(auction_df),
                    'raw_data': auction_df
                }
                
                return result
                
        except Exception as e:
            st.error(f"获取{symbol} AKShare数据失败: {e}")
            return None
    
    def get_baostock_opening_data(self, symbol, days=20):
        """使用BaoStock获取开盘价数据"""
        if not self.baostock_logged_in:
            return None
        
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y-%m-%d')
            
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
            
            if not data_list:
                return None
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            numeric_cols = ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'pctChg']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna().tail(days)
            
            if df.empty:
                return None
            
            tech_analysis = self._calculate_tech_indicators(df)
            
            latest = df.iloc[-1]
            result = {
                'symbol': symbol,
                'data_source': 'BaoStock',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'latest_date': latest['date'],
                'latest_open': float(latest['open']),
                'latest_close': float(latest['close']),
                'latest_volume': int(latest['volume']),
                'latest_pct_change': float(latest['pctChg']),
                'technical_score': tech_analysis['total_score'],
                'technical_details': tech_analysis['details'],
                'historical_data': df
            }
            
            return result
            
        except Exception as e:
            st.error(f"获取{symbol} BaoStock数据失败: {e}")
            return None
    
    def analyze_auction_signals(self, akshare_data, baostock_data=None):
        """分析集合竞价信号"""
        if not akshare_data:
            return None
        
        analysis = {
            'symbol': akshare_data['symbol'],
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_quality': 'good' if akshare_data['data_points'] >= 5 else 'limited',
            'signals': {}
        }
        
        # 价格趋势信号
        trend_pct = akshare_data['trend_pct']
        if trend_pct > 1:
            price_signal = 'strong_bullish'
            price_desc = "强势看涨"
        elif trend_pct > 0.2:
            price_signal = 'bullish'
            price_desc = "看涨"
        elif trend_pct < -1:
            price_signal = 'strong_bearish'
            price_desc = "强势看跌"
        elif trend_pct < -0.2:
            price_signal = 'bearish'
            price_desc = "看跌"
        else:
            price_signal = 'neutral'
            price_desc = "中性"
        
        analysis['signals']['price_trend'] = {
            'signal': price_signal,
            'desc': price_desc,
            'trend_pct': trend_pct,
            'strength': 'strong' if abs(trend_pct) > 1 else 'weak'
        }
        
        # 成交量信号
        volume = akshare_data['total_volume']
        if volume > 10000:
            volume_signal = 'high_volume'
            volume_desc = "高成交量"
        elif volume > 5000:
            volume_signal = 'medium_volume'
            volume_desc = "中等成交量"
        else:
            volume_signal = 'low_volume'
            volume_desc = "低成交量"
        
        analysis['signals']['volume'] = {
            'signal': volume_signal,
            'desc': volume_desc,
            'total_volume': volume,
            'volume_level': 'active' if volume > 5000 else 'quiet'
        }
        
        # 价格波动率信号
        if akshare_data['opening_price']:
            volatility_pct = (akshare_data['auction_high'] - akshare_data['auction_low']) / akshare_data['opening_price'] * 100
            
            if volatility_pct > 2:
                volatility_desc = "高波动"
            elif volatility_pct > 1:
                volatility_desc = "中等波动"
            else:
                volatility_desc = "低波动"
            
            analysis['signals']['volatility'] = {
                'desc': volatility_desc,
                'volatility_pct': round(volatility_pct, 2),
                'price_range': f"{akshare_data['auction_low']:.2f} - {akshare_data['auction_high']:.2f}"
            }
        
        # 综合交易建议
        bullish_signals = sum([
            price_signal in ['bullish', 'strong_bullish'],
            volume > 5000,
            trend_pct > 0.5
        ])
        
        bearish_signals = sum([
            price_signal in ['bearish', 'strong_bearish'],
            trend_pct < -0.5,
            volume > 10000 and trend_pct < 0
        ])
        
        if baostock_data and 'technical_score' in baostock_data:
            tech_score = baostock_data['technical_score']
            if tech_score > 0.7:
                bullish_signals += 1
            elif tech_score < 0.3:
                bearish_signals += 1
        
        if bullish_signals >= 2:
            recommendation = 'BUY'
            rec_desc = "买入"
            rec_class = "signal-buy"
        elif bearish_signals >= 2:
            recommendation = 'SELL'
            rec_desc = "卖出"
            rec_class = "signal-sell"
        else:
            recommendation = 'HOLD'
            rec_desc = "持有"
            rec_class = "signal-hold"
        
        analysis['recommendation'] = {
            'action': recommendation,
            'desc': rec_desc,
            'class': rec_class,
            'confidence': '高' if max(bullish_signals, bearish_signals) >= 2 else '低',
            'bullish_signals': bullish_signals,
            'bearish_signals': bearish_signals
        }
        
        return analysis

def create_auction_chart(akshare_data):
    """创建集合竞价图表"""
    if not akshare_data or 'raw_data' not in akshare_data:
        return None
    
    df = akshare_data['raw_data']
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3]
    )
    
    # K线图
    fig.add_trace(
        go.Candlestick(
            x=df['时间'],
            open=df['开盘'],
            high=df['最高'],
            low=df['最低'],
            close=df['收盘'],
            name='价格',
            increasing_line_color='#FF4B4B',
            decreasing_line_color='#4B9EFF'
        ),
        row=1, col=1
    )
    
    # 成交量图
    colors = ['#FF4B4B' if row['收盘'] >= row['开盘'] else '#4B9EFF' 
              for _, row in df.iterrows()]
    
    fig.add_trace(
        go.Bar(
            x=df['时间'],
            y=df['成交量'],
            name='成交量',
            marker_color=colors
        ),
        row=2, col=1
    )
    
    # 更新布局
    fig.update_layout(
        title=f"{akshare_data['symbol']} 集合竞价走势",
        xaxis_title="时间",
        height=600,
        showlegend=False,
        template='plotly_white'
    )
    
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    
    return fig

def display_stock_table(results):
    """显示股票数据表格"""
    if not results:
        return
    
    table_data = []
    for result in results:
        if result['analysis']:
            row = {
                '股票代码': result['symbol'],
                '开盘价': f"¥{result['akshare_data']['opening_price']:.2f}" if result['akshare_data']['opening_price'] else 'N/A',
                '竞价趋势': f"{result['akshare_data']['trend_pct']:+.2f}%",
                '成交量(手)': f"{result['akshare_data']['total_volume']:,}",
                '价格波动': f"{result['analysis']['signals']['volatility']['volatility_pct']:.2f}%" if 'volatility' in result['analysis']['signals'] else 'N/A',
                '趋势信号': result['analysis']['signals']['price_trend']['desc'],
                '量能信号': result['analysis']['signals']['volume']['desc'],
                '技术评分': f"{result['baostock_data']['technical_score']:.3f}" if result.get('baostock_data') else 'N/A',
                '交易建议': result['analysis']['recommendation']['desc'],
                '置信度': result['analysis']['recommendation']['confidence']
            }
            table_data.append(row)
    
    if table_data:
        df_display = pd.DataFrame(table_data)
        
        # 使用st.dataframe显示表格
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                '股票代码': st.column_config.TextColumn('股票代码', width='small'),
                '开盘价': st.column_config.TextColumn('开盘价', width='small'),
                '竞价趋势': st.column_config.TextColumn('竞价趋势', width='small'),
                '成交量(手)': st.column_config.TextColumn('成交量(手)', width='medium'),
                '价格波动': st.column_config.TextColumn('价格波动', width='small'),
                '趋势信号': st.column_config.TextColumn('趋势信号', width='small'),
                '量能信号': st.column_config.TextColumn('量能信号', width='small'),
                '技术评分': st.column_config.TextColumn('技术评分', width='small'),
                '交易建议': st.column_config.TextColumn('交易建议', width='small'),
                '置信度': st.column_config.TextColumn('置信度', width='small')
            }
        )
        
        return df_display
    return None

def display_technical_details(baostock_data):
    """显示技术指标详情"""
    if not baostock_data or 'technical_details' not in baostock_data:
        return
    
    details = baostock_data['technical_details']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if 'ma' in details:
            st.metric(
                "均线系统",
                details['ma']['desc'],
                f"评分: {details['ma']['score']:+.2f}"
            )
    
    with col2:
        if 'rsi' in details:
            st.metric(
                "RSI指标",
                details['rsi']['desc'],
                f"值: {details['rsi']['value']}"
            )
    
    with col3:
        if 'volume' in details:
            st.metric(
                "成交量",
                details['volume']['desc'],
                f"比率: {details['volume']['ratio']}"
            )

def main():
    """主函数"""
    st.markdown('<h1 class="main-header">📊 A股集合竞价分析系统</h1>', unsafe_allow_html=True)
    
    # 侧边栏配置
    with st.sidebar:
        st.markdown('<h2 class="sub-header">⚙️ 配置面板</h2>', unsafe_allow_html=True)
        
        # 股票选择方式
        input_method = st.radio(
            "选择输入方式",
            ["示例股票列表", "手动输入股票代码", "上传股票列表"]
        )
        
        stocks = []
        
        if input_method == "示例股票列表":
            stocks = st.multiselect(
                "选择要分析的股票",
                [
                    "000001 (平安银行)",
                    "000002 (万科A)",
                    "600000 (浦发银行)",
                    "600036 (招商银行)",
                    "300015 (爱尔眼科)",
                    "600519 (贵州茅台)",
                    "000858 (五粮液)"
                ],
                default=["000001 (平安银行)", "000002 (万科A)"]
            )
            stocks = [s.split(' ')[0] for s in stocks]
            
        elif input_method == "手动输入股票代码":
            stock_input = st.text_input(
                "输入股票代码（多个用逗号分隔）",
                placeholder="例如: 000001,000002,600000"
            )
            if stock_input:
                stocks = [s.strip() for s in stock_input.split(',')]
        
        else:  # 上传文件
            uploaded_file = st.file_uploader(
                "上传股票列表文件（每行一个代码）",
                type=['txt', 'csv']
            )
            if uploaded_file:
                content = uploaded_file.read().decode()
                stocks = [line.strip() for line in content.split('\n') if line.strip()]
        
        # 分析按钮
        analyze_button = st.button("🚀 开始分析", type="primary", use_container_width=True)
        
        st.markdown("---")
        st.markdown("### ℹ️ 关于")
        st.markdown("""
        本系统整合AKShare和BaoStock数据源，提供：
        - 集合竞价实时数据
        - 技术指标分析
        - 交易信号识别
        - 综合评分系统
        """)
    
    # 主内容区
    if analyze_button and stocks:
        # 初始化分析器
        analyzer = AuctionDataAnalyzer()
        
        # 登录BaoStock
        with st.spinner('正在连接数据源...'):
            if not analyzer.login_baostock():
                st.error("BaoStock连接失败，部分功能可能不可用")
        
        # 进度条
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 存储结果
        results = []
        
        # 创建结果显示区域
        results_container = st.container()
        
        for i, symbol in enumerate(stocks):
            status_text.text(f"正在分析 {symbol}... ({i+1}/{len(stocks)})")
            
            # 转换股票代码格式
            akshare_symbol = symbol
            baostock_symbol = f"sh.{symbol}" if symbol.startswith('6') else f"sz.{symbol}"
            
            # 获取数据
            akshare_data = analyzer.get_akshare_auction_data(akshare_symbol)
            baostock_data = analyzer.get_baostock_opening_data(baostock_symbol, days=20)
            
            # 分析信号
            if akshare_data:
                analysis = analyzer.analyze_auction_signals(akshare_data, baostock_data)
                
                results.append({
                    'symbol': symbol,
                    'akshare_data': akshare_data,
                    'baostock_data': baostock_data,
                    'analysis': analysis
                })
            
            # 更新进度
            progress_bar.progress((i + 1) / len(stocks))
        
        # 清除进度显示
        progress_bar.empty()
        status_text.empty()
        
        # 显示结果
        with results_container:
            st.markdown('<h2 class="sub-header">📈 分析结果汇总</h2>', unsafe_allow_html=True)
            
            # 显示数据表格
            df_display = display_stock_table(results)
            
            if df_display is not None:
                # 统计信息
                st.markdown('<h2 class="sub-header">📊 统计概览</h2>', unsafe_allow_html=True)
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    buy_count = len(df_display[df_display['交易建议'] == '买入'])
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>买入建议</h3>
                        <h2 class="signal-buy">{buy_count}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    sell_count = len(df_display[df_display['交易建议'] == '卖出'])
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>卖出建议</h3>
                        <h2 class="signal-sell">{sell_count}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col3:
                    hold_count = len(df_display[df_display['交易建议'] == '持有'])
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>持有建议</h3>
                        <h2 class="signal-hold">{hold_count}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col4:
                    avg_score = pd.to_numeric(df_display['技术评分'].replace('N/A', np.nan)).mean()
                    st.markdown(f"""
                    <div class="metric-card">
                        <h3>平均技术评分</h3>
                        <h2>{avg_score:.3f}</h2>
                    </div>
                    """, unsafe_allow_html=True)
                
                # 详细分析标签页
                st.markdown('<h2 class="sub-header">🔍 详细分析</h2>', unsafe_allow_html=True)
                
                tabs = st.tabs([f"{r['symbol']}" for r in results])
                
                for idx, (tab, result) in enumerate(zip(tabs, results)):
                    with tab:
                        if result['analysis']:
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                # 竞价图表
                                fig = create_auction_chart(result['akshare_data'])
                                if fig:
                                    st.plotly_chart(fig, use_container_width=True)
                            
                            with col2:
                                # 关键信息卡片
                                st.markdown("### 📋 关键信息")
                                
                                rec = result['analysis']['recommendation']
                                st.markdown(f"""
                                <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px;">
                                    <h3 style="color: #1E88E5;">交易建议</h3>
                                    <h2 class="{rec['class']}" style="font-size: 2rem;">{rec['desc']}</h2>
                                    <p>置信度: {rec['confidence']}</p>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                st.markdown("### 📊 技术指标详情")
                                if result.get('baostock_data'):
                                    display_technical_details(result['baostock_data'])
                                
                                st.markdown("### 📈 竞价信号")
                                signals = result['analysis']['signals']
                                for key, value in signals.items():
                                    if key != 'volatility' or 'desc' in value:
                                        st.write(f"**{key.replace('_', ' ').title()}**: {value.get('desc', 'N/A')}")
                            
                            # 原始数据
                            with st.expander("查看原始数据"):
                                st.dataframe(result['akshare_data']['raw_data'])
        
        # 登出BaoStock
        analyzer.logout_baostock()
        
    else:
        # 欢迎界面
        st.markdown("""
        <div style="text-align: center; padding: 50px;">
            <h2>👈 请在侧边栏配置分析参数</h2>
            <p class="info-text">选择要分析的股票，点击"开始分析"按钮获取数据</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 功能介绍
        st.markdown('<h2 class="sub-header">✨ 功能介绍</h2>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            ### 🎯 集合竞价分析
            - 实时获取9:15-9:25竞价数据
            - 价格趋势识别
            - 成交量分析
            - 波动率评估
            """)
        
        with col2:
            st.markdown("""
            ### 📊 技术指标系统
            - 均线系统分析
            - RSI指标计算
            - 成交量比率
            - 综合技术评分
            """)
        
        with col3:
            st.markdown("""
            ### 💡 智能交易建议
            - 多信号综合判断
            - 置信度评估
            - 买入/卖出/持有建议
            - 实时风险提示
            """)

if __name__ == "__main__":
    main()
