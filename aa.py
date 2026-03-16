#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股集合竞价数据获取演示程序 - Streamlit版本
整合AKShare和BaoStock，展示完整的竞价数据分析流程
支持全市场A股批量分析
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
warnings.filterwarnings('ignore')

# 设置页面配置
st.set_page_config(
    page_title="A股集合竞价分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
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
    .stProgress > div > div > div > div {
        background-color: #1E88E5;
    }
    .success-box {
        background-color: #00C85320;
        padding: 10px;
        border-radius: 5px;
        border-left: 3px solid #00C853;
    }
    .warning-box {
        background-color: #FFB30020;
        padding: 10px;
        border-radius: 5px;
        border-left: 3px solid #FFB300;
    }
</style>
""", unsafe_allow_html=True)

# 全局线程锁
data_lock = threading.Lock()

# 缓存函数，避免重复请求
@st.cache_data(ttl=3600)  # 缓存1小时
def get_all_stock_list():
    """获取所有A股股票列表"""
    try:
        with st.spinner('正在获取全市场A股股票列表...'):
            # 获取所有A股股票信息
            stock_info = ak.stock_info_a_code_name()
            
            # 添加市场标识
            stock_info['market'] = stock_info['code'].apply(
                lambda x: 'sh' if x.startswith('6') else 'sz'
            )
            stock_info['baostock_code'] = stock_info['market'] + '.' + stock_info['code']
            stock_info['display_name'] = stock_info['code'] + ' - ' + stock_info['name']
            
            # 添加板块信息
            stock_info['sector'] = stock_info['code'].apply(
                lambda x: '科创板' if x.startswith('688') 
                else ('创业板' if x.startswith('30') 
                      else ('上证主板' if x.startswith('6') 
                            else '深证主板'))
            )
            
            return stock_info
    except Exception as e:
        st.error(f"获取股票列表失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=1800)  # 缓存30分钟
def get_stock_list_by_sector(sector_type):
    """按板块获取股票列表"""
    try:
        all_stocks = get_all_stock_list()
        
        if sector_type == "全部A股":
            return all_stocks
        elif sector_type == "沪深300":
            df = ak.stock_zh_index_cons_csindex("000300")
            result = pd.DataFrame({
                'code': df['成分券代码'],
                'name': df['成分券名称']
            })
            return result
        elif sector_type == "中证500":
            df = ak.stock_zh_index_cons_csindex("000905")
            result = pd.DataFrame({
                'code': df['成分券代码'],
                'name': df['成分券名称']
            })
            return result
        elif sector_type == "科创板":
            return all_stocks[all_stocks['sector'] == '科创板']
        elif sector_type == "创业板":
            return all_stocks[all_stocks['sector'] == '创业板']
        elif sector_type == "上证主板":
            return all_stocks[all_stocks['sector'] == '上证主板']
        elif sector_type == "深证主板":
            return all_stocks[all_stocks['sector'] == '深证主板']
        else:
            return all_stocks
    except Exception as e:
        st.error(f"获取{sector_type}股票列表失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)  # 缓存5分钟
def get_hot_stocks(top_n=50):
    """获取热门股票（基于成交额）"""
    try:
        # 获取实时行情数据
        stock_zh_a_spot = ak.stock_zh_a_spot_em()
        # 按成交额排序
        hot_stocks = stock_zh_a_spot.nlargest(top_n, '成交额')[['代码', '名称']]
        hot_stocks.columns = ['code', 'name']
        return hot_stocks
    except Exception as e:
        st.warning(f"获取热门股票失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)  # 缓存5分钟
def get_limit_up_stocks():
    """获取涨停股票"""
    try:
        stock_zt_pool_em = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
        if not stock_zt_pool_em.empty:
            result = pd.DataFrame({
                'code': stock_zt_pool_em['代码'],
                'name': stock_zt_pool_em['名称']
            })
            return result
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"获取涨停股票失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_limit_down_stocks():
    """获取跌停股票"""
    try:
        stock_zt_pool_dtgc_em = ak.stock_zt_pool_dtgc_em(date=datetime.now().strftime('%Y%m%d'))
        if not stock_zt_pool_dtgc_em.empty:
            result = pd.DataFrame({
                'code': stock_zt_pool_dtgc_em['代码'],
                'name': stock_zt_pool_dtgc_em['名称']
            })
            return result
        return pd.DataFrame()
    except Exception as e:
        st.warning(f"获取跌停股票失败: {e}")
        return pd.DataFrame()

class AuctionDataAnalyzer:
    """集合竞价数据分析器"""
    
    def __init__(self):
        self.name = "A股集合竞价数据分析器"
        self.baostock_logged_in = False
        self.results_cache = {}
        self.analysis_stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'buy': 0,
            'sell': 0,
            'hold': 0
        }
        
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
                details['ma'] = {'score': ma_score, 'desc': ma_desc, 'value': f"{ma5:.2f}/{ma10:.2f}/{ma20:.2f}"}
            
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
    
    def analyze_stock(self, symbol, stock_name=""):
        """分析单只股票"""
        cache_key = f"{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
        
        if cache_key in self.results_cache:
            return self.results_cache[cache_key]
        
        # 转换股票代码格式
        baostock_symbol = f"sh.{symbol}" if symbol.startswith('6') else f"sz.{symbol}"
        
        # 获取数据
        akshare_data = self.get_akshare_auction_data(symbol)
        baostock_data = self.get_baostock_opening_data(baostock_symbol, days=20)
        
        # 分析信号
        if akshare_data:
            analysis = self.analyze_auction_signals(akshare_data, baostock_data)
            
            result = {
                'symbol': symbol,
                'name': stock_name,
                'akshare_data': akshare_data,
                'baostock_data': baostock_data,
                'analysis': analysis
            }
            
            self.results_cache[cache_key] = result
            
            # 更新统计
            with data_lock:
                self.analysis_stats['total'] += 1
                self.analysis_stats['success'] += 1
                if analysis and 'recommendation' in analysis:
                    if analysis['recommendation']['action'] == 'BUY':
                        self.analysis_stats['buy'] += 1
                    elif analysis['recommendation']['action'] == 'SELL':
                        self.analysis_stats['sell'] += 1
                    else:
                        self.analysis_stats['hold'] += 1
            
            return result
        else:
            with data_lock:
                self.analysis_stats['total'] += 1
                self.analysis_stats['failed'] += 1
            return None
    
    def analyze_stocks_batch(self, stocks_df, max_workers=5):
        """批量分析股票"""
        results = []
        
        # 创建进度条
        progress_bar = st.progress(0)
        status_text = st.empty()
        stats_text = st.empty()
        
        total_stocks = len(stocks_df)
        
        # 使用线程池进行并行分析
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_stock = {
                executor.submit(self.analyze_stock, row['code'], row['name']): (row['code'], row['name'])
                for _, row in stocks_df.iterrows()
            }
            
            # 收集结果
            for i, future in enumerate(as_completed(future_to_stock)):
                stock_code, stock_name = future_to_stock[future]
                
                try:
                    result = future.result(timeout=10)
                    if result:
                        results.append(result)
                    
                    # 更新进度
                    progress = (i + 1) / total_stocks
                    progress_bar.progress(progress)
                    
                    # 更新状态显示
                    status_text.text(f"正在分析: {stock_code} {stock_name} ({i+1}/{total_stocks})")
                    
                    # 显示统计信息
                    stats_text.markdown(f"""
                    <div class="success-box">
                        📊 当前统计: 成功 {self.analysis_stats['success']} | 
                        失败 {self.analysis_stats['failed']} | 
                        买入 {self.analysis_stats['buy']} | 
                        卖出 {self.analysis_stats['sell']} | 
                        持有 {self.analysis_stats['hold']}
                    </div>
                    """, unsafe_allow_html=True)
                    
                except Exception as e:
                    st.warning(f"分析 {stock_code} 失败: {e}")
                    with data_lock:
                        self.analysis_stats['failed'] += 1
        
        # 清除进度显示
        progress_bar.empty()
        status_text.empty()
        stats_text.empty()
        
        return results

def create_auction_chart(akshare_data, stock_name=""):
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
    title = f"{akshare_data['symbol']} {stock_name} 集合竞价走势" if stock_name else f"{akshare_data['symbol']} 集合竞价走势"
    
    fig.update_layout(
        title=title,
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
        return None
    
    table_data = []
    for result in results:
        if result and result['analysis']:
            row = {
                '股票代码': result['symbol'],
                '股票名称': result.get('name', ''),
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
                '股票名称': st.column_config.TextColumn('股票名称', width='small'),
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
            st.caption(f"MA5/MA10/MA20: {details['ma']['value']}")
    
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
    st.markdown('<h1 class="main-header">📊 A股集合竞价分析系统 - 全市场版</h1>', unsafe_allow_html=True)
    
    # 侧边栏配置
    with st.sidebar:
        st.markdown('<h2 class="sub-header">⚙️ 配置面板</h2>', unsafe_allow_html=True)
        
        # 获取所有股票列表
        all_stocks_df = get_all_stock_list()
        
        if all_stocks_df.empty:
            st.error("无法获取股票列表，请检查网络连接")
            return
        
        # 股票选择方式
        selection_method = st.radio(
            "选择股票方式",
            ["按板块筛选", "特殊股票池", "搜索股票", "自定义列表"]
        )
        
        selected_stocks_df = pd.DataFrame()
        
        if selection_method == "按板块筛选":
            sector = st.selectbox(
                "选择板块",
                ["全部A股", "沪深300", "中证500", "上证主板", "深证主板", "创业板", "科创板"]
            )
            
            selected_stocks_df = get_stock_list_by_sector(sector)
            
            if not selected_stocks_df.empty:
                st.success(f"📊 {sector}: 共 {len(selected_stocks_df)} 只股票")
                
                # 显示板块分布
                if sector == "全部A股":
                    sector_dist = selected_stocks_df['sector'].value_counts()
                    st.caption(f"分布: {dict(sector_dist)}")
        
        elif selection_method == "特殊股票池":
            special_type = st.selectbox(
                "选择股票池",
                ["热门股票(成交额TOP50)", "涨停股票", "跌停股票"]
            )
            
            if special_type == "热门股票(成交额TOP50)":
                selected_stocks_df = get_hot_stocks(50)
            elif special_type == "涨停股票":
                selected_stocks_df = get_limit_up_stocks()
            else:
                selected_stocks_df = get_limit_down_stocks()
            
            if not selected_stocks_df.empty:
                st.success(f"📈 {special_type}: 共 {len(selected_stocks_df)} 只股票")
        
        elif selection_method == "搜索股票":
            search_term = st.text_input("输入股票代码或名称", placeholder="例如: 000001 或 平安银行")
            
            if search_term:
                # 搜索匹配的股票
                mask = (
                    all_stocks_df['code'].str.contains(search_term) | 
                    all_stocks_df['name'].str.contains(search_term)
                )
                search_results = all_stocks_df[mask]
                
                if not search_results.empty:
                    st.success(f"找到 {len(search_results)} 只匹配股票")
                    
                    # 多选
                    selected_options = st.multiselect(
                        "选择要分析的股票",
                        options=search_results['display_name'].tolist()
                    )
                    
                    if selected_options:
                        codes = [opt.split(' - ')[0] for opt in selected_options]
                        names = [opt.split(' - ')[1] for opt in selected_options]
                        selected_stocks_df = pd.DataFrame({
                            'code': codes,
                            'name': names
                        })
        
        else:  # 自定义列表
            custom_input = st.text_area(
                "输入股票代码（每行一个）",
                placeholder="例如:\n000001\n000002\n600000",
                height=150
            )
            
            if custom_input:
                custom_stocks = [line.strip() for line in custom_input.split('\n') if line.strip()]
                
                # 验证股票代码
                valid_stocks = []
                valid_names = []
                invalid_stocks = []
                
                for code in custom_stocks:
                    if code in all_stocks_df['code'].values:
                        valid_stocks.append(code)
                        name = all_stocks_df[all_stocks_df['code'] == code]['name'].iloc[0]
                        valid_names.append(name)
                    else:
                        invalid_stocks.append(code)
                
                if valid_stocks:
                    selected_stocks_df = pd.DataFrame({
                        'code': valid_stocks,
                        'name': valid_names
                    })
                    st.success(f"✅ 有效股票: {len(valid_stocks)} 只")
                
                if invalid_stocks:
                    st.warning(f"❌ 无效股票: {', '.join(invalid_stocks)}")
        
        # 分析选项
        st.markdown("---")
        st.markdown("### ⚡ 分析选项")
        
        col1, col2 = st.columns(2)
        with col1:
            use_technical = st.checkbox("技术指标", value=True)
            parallel_mode = st.checkbox("并行分析", value=True, help="使用多线程加快分析速度")
        
        with col2:
            show_charts = st.checkbox("显示图表", value=True)
            max_workers = st.number_input("并行线程数", min_value=1, max_value=10, value=5)
        
        # 分析按钮
        analyze_button = st.button("🚀 开始全市场分析", type="primary", use_container_width=True)
        
        st.markdown("---")
        st.markdown("### ℹ️ 系统信息")
        st.markdown(f"""
        **市场概况:**
        - 总股票数: {len(all_stocks_df)}
        - 上证主板: {len(all_stocks_df[all_stocks_df['sector']=='上证主板'])}
        - 深证主板: {len(all_stocks_df[all_stocks_df['sector']=='深证主板'])}
        - 创业板: {len(all_stocks_df[all_stocks_df['sector']=='创业板'])}
        - 科创板: {len(all_stocks_df[all_stocks_df['sector']=='科创板'])}
        """)
    
    # 主内容区
    if analyze_button and not selected_stocks_df.empty:
        # 初始化分析器
        analyzer = AuctionDataAnalyzer()
        
        # 登录BaoStock
        with st.spinner('正在连接数据源...'):
            if use_technical:
                if not analyzer.login_baostock():
                    st.warning("BaoStock连接失败，将仅使用AKShare数据分析")
        
        # 显示分析开始信息
        st.markdown(f"""
        <div class="warning-box">
            🚀 开始分析 {len(selected_stocks_df)} 只股票，请耐心等待...
        </div>
        """, unsafe_allow_html=True)
        
        # 批量分析
        if parallel_mode:
            results = analyzer.analyze_stocks_batch(selected_stocks_df, max_workers=max_workers)
        else:
            # 串行分析
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, (_, row) in enumerate(selected_stocks_df.iterrows()):
                status_text.text(f"正在分析 {row['code']} {row['name']}... ({i+1}/{len(selected_stocks_df)})")
                
                result = analyzer.analyze_stock(row['code'], row['name'])
                if result:
                    results.append(result)
                
                progress_bar.progress((i + 1) / len(selected_stocks_df))
                time.sleep(0.5)  # 避免请求过于频繁
            
            progress_bar.empty()
            status_text.empty()
        
        # 显示最终统计
        st.markdown(f"""
        <div class="success-box">
            📊 分析完成统计:
            - 总计: {analyzer.analysis_stats['total']} 只
            - 成功: {analyzer.analysis_stats['success']} 只
            - 失败: {analyzer.analysis_stats['failed']} 只
            - 买入建议: {analyzer.analysis_stats['buy']} 只
            - 卖出建议: {analyzer.analysis_stats['sell']} 只
            - 持有建议: {analyzer.analysis_stats['hold']} 只
        </div>
        """, unsafe_allow_html=True)
        
        # 显示结果
        if results:
            st.markdown('<h2 class="sub-header">📈 分析结果汇总</h2>', unsafe_allow_html=True)
            
            # 显示数据表格
            df_display = display_stock_table(results)
            
            if df_display is not None:
                # 统计图表
                col1, col2 = st.columns(2)
                
                with col1:
                    # 交易建议分布
                    rec_counts = df_display['交易建议'].value_counts()
                    st.bar_chart(rec_counts)
                
                with col2:
                    # 技术评分分布
                    tech_scores = pd.to_numeric(df_display['技术评分'].replace('N/A', np.nan))
                    if not tech_scores.isna().all():
                        st.line_chart(tech_scores.value_counts().sort_index())
                
                # 详细分析标签页
                if show_charts and len(results) <= 20:  # 限制图表显示数量避免页面过长
                    st.markdown('<h2 class="sub-header">🔍 详细分析</h2>', unsafe_allow_html=True)
                    
                    # 创建标签页
                    tabs = st.tabs([f"{r['symbol']} {r.get('name', '')}" for r in results[:10]])  # 最多显示10个标签
                    
                    for idx, (tab, result) in enumerate(zip(tabs, results[:10])):
                        with tab:
                            if result['analysis']:
                                col1, col2 = st.columns([2, 1])
                                
                                with col1:
                                    # 竞价图表
                                    fig = create_auction_chart(
                                        result['akshare_data'], 
                                        result.get('name', '')
                                    )
                                    if fig:
                                        st.plotly_chart(fig, use_container_width=True)
                                
                                with col2:
                                    # 关键信息卡片
                                    st.markdown("### 📋 关键信息")
                                    
                                    rec = result['analysis']['recommendation']
                                    st.markdown(f"""
                                    <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 15px;">
                                        <h3 style="color: #1E88E5;">交易建议</h3>
                                        <h2 class="{rec['class']}" style="font-size: 2rem;">{rec['desc']}</h2>
                                        <p>置信度: {rec['confidence']}</p>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    # 竞价信号
                                    st.markdown("### 📈 竞价信号")
                                    signals = result['analysis']['signals']
                                    
                                    signal_data = {
                                        '指标': ['价格趋势', '成交量', '波动率'],
                                        '数值': [
                                            f"{signals['price_trend']['trend_pct']:+.2f}%",
                                            f"{signals['volume']['total_volume']:,}手",
                                            f"{signals['volatility']['volatility_pct']:.2f}%"
                                        ],
                                        '状态': [
                                            signals['price_trend']['desc'],
                                            signals['volume']['desc'],
                                            signals['volatility']['desc']
                                        ]
                                    }
                                    st.dataframe(pd.DataFrame(signal_data), hide_index=True, use_container_width=True)
                                    
                                    # 技术指标详情
                                    if use_technical and result.get('baostock_data'):
                                        st.markdown("### 📊 技术指标")
                                        display_technical_details(result['baostock_data'])
                else:
                    st.info("图表显示已限制，可通过导出功能获取完整数据")
                
                # 导出功能
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    # 导出为CSV
                    csv = df_display.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 CSV导出",
                        data=csv,
                        file_name=f"auction_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                with col2:
                    # 导出为Excel
                    try:
                        output = pd.ExcelWriter(f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", engine='openpyxl')
                        df_display.to_excel(output, index=False, sheet_name='分析结果')
                        output.close()
                        
                        with open(output.path, 'rb') as f:
                            excel_data = f.read()
                        
                        st.download_button(
                            label="📊 Excel导出",
                            data=excel_data,
                            file_name=f"auction_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except:
                        st.button("Excel导出不可用", disabled=True, use_container_width=True)
                
                with col3:
                    # 导出买入建议
                    buy_df = df_display[df_display['交易建议'] == '买入']
                    if not buy_df.empty:
                        buy_csv = buy_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="💰 买入清单",
                            data=buy_csv,
                            file_name=f"buy_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    else:
                        st.button("💰 无买入信号", disabled=True, use_container_width=True)
                
                with col4:
                    # 刷新按钮
                    if st.button("🔄 刷新数据", use_container_width=True):
                        st.cache_data.clear()
                        st.rerun()
        
        else:
            st.warning("没有获取到任何有效数据")
        
        # 登出BaoStock
        analyzer.logout_baostock()
        
    elif analyze_button and selected_stocks_df.empty:
        st.warning("请先选择要分析的股票")
    else:
        # 欢迎界面
        st.markdown("""
        <div style="text-align: center; padding: 30px;">
            <h2>👈 请在侧边栏选择要分析的股票</h2>
            <p class="info-text">支持全市场A股分析，可选择全部股票或按板块筛选</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 显示市场概览
        all_stocks = get_all_stock_list()
        
        if not all_stocks.empty:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                sh_count = len(all_stocks[all_stocks['sector'] == '上证主板'])
                st.markdown(f"""
                <div class="metric-card">
                    <h3>上证主板</h3>
                    <h2>{sh_count}</h2>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                sz_count = len(all_stocks[all_stocks['sector'] == '深证主板'])
                st.markdown(f"""
                <div class="metric-card">
                    <h3>深证主板</h3>
                    <h2>{sz_count}</h2>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                cyb_count = len(all_stocks[all_stocks['sector'] == '创业板'])
                st.markdown(f"""
                <div class="metric-card">
                    <h3>创业板</h3>
                    <h2>{cyb_count}</h2>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                kcb_count = len(all_stocks[all_stocks['sector'] == '科创板'])
                st.markdown(f"""
                <div class="metric-card">
                    <h3>科创板</h3>
                    <h2>{kcb_count}</h2>
                </div>
                """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
