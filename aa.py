#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CChanTrader-AI 交易日报生成器 - Streamlit版本
在每个交易日9:25-9:29自动分析并生成日报，使用Streamlit显示
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import baostock as bs
import akshare as ak
from tqdm import tqdm
import warnings
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

warnings.filterwarnings('ignore')

# 设置页面配置
st.set_page_config(
    page_title="CChanTrader-AI 交易日报",
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
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .stock-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .very-high {
        color: #2e7d32;
        font-weight: bold;
    }
    .high {
        color: #1976d2;
        font-weight: bold;
    }
    .medium {
        color: #ed6c02;
        font-weight: bold;
    }
    .low {
        color: #d32f2f;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


class DailyReportGenerator:
    """交易日报生成器"""
    
    def __init__(self):
        """初始化日报生成器"""
        self.analysis_results = {}
        self.report_data = {}
        
    def is_trading_day(self, date=None) -> bool:
        """判断是否为交易日"""
        if date is None:
            date = datetime.now()
        
        # 简化版：排除周末
        weekday = date.weekday()
        if weekday >= 5:
            return False
        
        return True
    
    def get_stock_data_quick(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """快速获取股票数据"""
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            rs = bs.query_history_k_data_plus(symbol,
                'date,code,open,high,low,close,volume',
                start_date=start_date,
                end_date=end_date,
                frequency='d')
            df = rs.get_data()
            
            if df.empty:
                return pd.DataFrame()
            
            # 数据转换
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.split().str[0]
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df.dropna()
            
        except Exception:
            return pd.DataFrame()
    
    def get_auction_data_quick(self, symbol: str) -> dict:
        """快速获取竞价数据"""
        try:
            # 使用AKShare获取竞价数据
            pre_market_df = ak.stock_zh_a_hist_pre_min_em(
                symbol=symbol,
                start_time="09:00:00",
                end_time="09:30:00"
            )
            
            if pre_market_df.empty:
                return self._get_default_auction()
            
            # 筛选竞价时间
            auction_df = pre_market_df[
                pre_market_df['时间'].str.contains('09:1[5-9]|09:2[0-5]')
            ]
            
            if auction_df.empty:
                return self._get_default_auction()
            
            final_price = float(auction_df.iloc[-1]['开盘'])
            total_volume = auction_df['成交量'].sum()
            
            return {
                'final_price': final_price,
                'total_volume': total_volume,
                'data_points': len(auction_df),
                'status': 'success'
            }
            
        except Exception:
            return self._get_default_auction()
    
    def _get_default_auction(self) -> dict:
        """默认竞价数据"""
        return {
            'final_price': 0,
            'total_volume': 0,
            'data_points': 0,
            'status': 'no_data'
        }
    
    def analyze_single_stock(self, symbol: str, stock_name: str) -> dict:
        """分析单只股票"""
        try:
            # 获取历史数据
            df = self.get_stock_data_quick(symbol, 30)
            if len(df) < 20:
                return None
            
            current_price = float(df['close'].iloc[-1])
            prev_close = float(df['close'].iloc[-2])
            
            # 基础过滤
            if not (2 <= current_price <= 300):
                return None
            
            # 技术指标计算
            tech_score = self._calculate_tech_indicators(df)
            
            # 竞价数据分析
            auction_data = self.get_auction_data_quick(symbol)
            auction_score = self._analyze_auction_signals(auction_data, prev_close)
            
            # 综合评分
            total_score = tech_score * 0.65 + auction_score['strength'] * 0.35
            
            # 竞价加分
            if auction_score['ratio'] > 0.5 and auction_score['strength'] > 0.6:
                total_score += 0.1
            
            # 筛选条件
            if total_score < 0.65:
                return None
            
            return {
                'symbol': symbol,
                'stock_name': stock_name,
                'market': self._get_market_type(symbol),
                'current_price': current_price,
                'total_score': round(total_score, 3),
                'tech_score': round(tech_score, 3),
                'auction_score': round(auction_score['strength'], 3),
                'auction_ratio': auction_score['ratio'],
                'gap_type': auction_score['gap_type'],
                'capital_bias': auction_score.get('capital_bias', 0),
                'rsi': self._calculate_rsi(df),
                'volume_ratio': self._calculate_volume_ratio(df),
                'entry_price': current_price,
                'stop_loss': round(current_price * 0.92, 2),
                'target_price': round(current_price * 1.15, 2),
                'confidence': self._determine_confidence(total_score, auction_score),
                'strategy': self._generate_strategy(auction_score)
            }
            
        except Exception:
            return None
    
    def _calculate_tech_indicators(self, df: pd.DataFrame) -> float:
        """计算技术指标评分"""
        score = 0.5
        
        try:
            # 均线
            if len(df) >= 20:
                ma5 = df['close'].rolling(5).mean().iloc[-1]
                ma10 = df['close'].rolling(10).mean().iloc[-1]
                ma20 = df['close'].rolling(20).mean().iloc[-1]
                current = df['close'].iloc[-1]
                
                if current > ma5 > ma10 > ma20:
                    score += 0.25
                elif current > ma5 > ma10:
                    score += 0.15
            
            # RSI
            rsi = self._calculate_rsi(df)
            if 30 <= rsi <= 70:
                score += 0.15
            
            # 成交量
            vol_ratio = self._calculate_volume_ratio(df)
            if vol_ratio > 0.8:
                score += 0.1
            
        except Exception:
            pass
        
        return min(1.0, score)
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算RSI"""
        try:
            if len(df) < period + 1:
                return 50.0
            
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = -delta.where(delta < 0, 0).rolling(period).mean()
            rs = gain / (loss + 1e-10)
            rsi = 100 - (100 / (1 + rs))
            return float(rsi.iloc[-1])
        except Exception:
            return 50.0
    
    def _calculate_volume_ratio(self, df: pd.DataFrame) -> float:
        """计算量比"""
        try:
            if len(df) < 10:
                return 1.0
            
            vol_ma = df['volume'].rolling(10).mean().iloc[-1]
            current_vol = df['volume'].iloc[-1]
            return float(current_vol / (vol_ma + 1e-10))
        except Exception:
            return 1.0
    
    def _analyze_auction_signals(self, auction_data: dict, prev_close: float) -> dict:
        """分析竞价信号"""
        if auction_data['status'] != 'success' or auction_data['final_price'] == 0:
            return {
                'strength': 0.3,
                'ratio': 0,
                'gap_type': 'no_data',
                'capital_bias': 0
            }
        
        final_price = auction_data['final_price']
        ratio = (final_price - prev_close) / prev_close * 100
        
        # 缺口类型
        if ratio > 3:
            gap_type = 'high_gap_up'
        elif ratio > 1:
            gap_type = 'gap_up'
        elif ratio > -1:
            gap_type = 'flat'
        elif ratio > -3:
            gap_type = 'gap_down'
        else:
            gap_type = 'low_gap_down'
        
        # 信号强度
        strength = 0.5
        if 0.5 <= ratio <= 3:
            strength += 0.3
        elif ratio > 3:
            strength -= 0.1
        
        if auction_data['total_volume'] > 0:
            strength += 0.1
        
        if auction_data['data_points'] >= 8:
            strength += 0.1
        
        return {
            'strength': max(0, min(1, strength)),
            'ratio': round(ratio, 2),
            'gap_type': gap_type,
            'capital_bias': min(auction_data['data_points'] / 10, 1.0)
        }
    
    def _get_market_type(self, symbol: str) -> str:
        """获取市场类型"""
        if symbol.startswith('sh.6'):
            return '上海主板'
        elif symbol.startswith('sz.000'):
            return '深圳主板'
        elif symbol.startswith('sz.002'):
            return '中小板'
        elif symbol.startswith('sz.30'):
            return '创业板'
        return '其他'
    
    def _determine_confidence(self, total_score: float, auction_score: dict) -> str:
        """确定置信度"""
        if total_score > 0.85 and auction_score['strength'] > 0.7:
            return 'very_high'
        elif total_score > 0.75:
            return 'high'
        elif total_score > 0.65:
            return 'medium'
        return 'low'
    
    def _generate_strategy(self, auction_score: dict) -> str:
        """生成策略建议"""
        gap_type = auction_score['gap_type']
        ratio = auction_score['ratio']
        
        if gap_type == 'high_gap_up':
            return "高开过度，建议等待回踩"
        elif gap_type == 'gap_up' and auction_score['strength'] > 0.6:
            return "温和高开，开盘可买"
        elif gap_type == 'flat' and auction_score['strength'] > 0.6:
            return "平开强势，关注买入"
        elif gap_type == 'gap_down' and ratio > -2:
            return "小幅低开，可逢低买入"
        else:
            return "竞价信号一般，建议观望"
    
    def generate_daily_report(self) -> dict:
        """生成每日报告"""
        st.info("🔄 开始生成交易日报...")
        
        if not self.is_trading_day():
            st.warning("📅 今日非交易日，跳过报告生成")
            return {}
        
        # 连接数据源
        lg = bs.login()
        st.info(f"📊 BaoStock连接: {lg.error_code}")
        
        try:
            # 获取股票列表
            st.info("🔍 获取股票列表...")
            stock_rs = bs.query_all_stock(day=datetime.now().strftime('%Y-%m-%d'))
            all_stocks = stock_rs.get_data()
            
            if all_stocks.empty:
                st.error("❌ 无法获取股票列表")
                return {}
            
            # 快速采样分析 (限制数量以提高速度)
            markets = {
                '上海主板': all_stocks[all_stocks['code'].str.startswith('sh.6')],
                '深圳主板': all_stocks[all_stocks['code'].str.startswith('sz.000')],
                '中小板': all_stocks[all_stocks['code'].str.startswith('sz.002')],
                '创业板': all_stocks[all_stocks['code'].str.startswith('sz.30')]
            }
            
            sample_stocks = []
            for market_name, market_stocks in markets.items():
                if len(market_stocks) > 0:
                    sample_size = min(15, len(market_stocks))
                    sampled = market_stocks.sample(n=sample_size, random_state=42)
                    sample_stocks.append(sampled)
            
            final_sample = pd.concat(sample_stocks, ignore_index=True)
            st.info(f"📋 快速分析样本: {len(final_sample)}只股票")
            
            # 执行分析
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            recommendations = []
            auction_stats = {
                'gap_up_count': 0,
                'flat_count': 0,
                'gap_down_count': 0,
                'total_auction_ratio': 0,
                'analyzed_count': 0
            }
            
            for idx, (_, stock) in enumerate(final_sample.iterrows()):
                status_text.text(f"正在分析: {stock['code_name']} ({idx+1}/{len(final_sample)})")
                result = self.analyze_single_stock(stock['code'], stock['code_name'])
                if result:
                    recommendations.append(result)
                    
                    auction_stats['analyzed_count'] += 1
                    auction_stats['total_auction_ratio'] += result['auction_ratio']
                    
                    gap_type = result['gap_type']
                    if 'gap_up' in gap_type:
                        auction_stats['gap_up_count'] += 1
                    elif gap_type == 'flat':
                        auction_stats['flat_count'] += 1
                    elif 'gap_down' in gap_type:
                        auction_stats['gap_down_count'] += 1
                
                progress_bar.progress((idx + 1) / len(final_sample))
            
            progress_bar.empty()
            status_text.empty()
            
            # 排序推荐结果
            recommendations.sort(key=lambda x: x['total_score'], reverse=True)
            
            # 计算汇总统计
            avg_auction_ratio = (auction_stats['total_auction_ratio'] / 
                               max(auction_stats['analyzed_count'], 1))
            
            avg_score = (sum(r['total_score'] for r in recommendations) / 
                        max(len(recommendations), 1))
            
            # 生成报告数据
            report_data = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'analysis_time': datetime.now().strftime('%H:%M:%S'),
                'recommendations': recommendations[:15],
                'market_summary': {
                    'total_analyzed': len(final_sample),
                    'total_recommended': len(recommendations),
                    'avg_score': round(avg_score, 3)
                },
                'auction_analysis': {
                    'avg_auction_ratio': round(avg_auction_ratio, 2),
                    'gap_up_count': auction_stats['gap_up_count'],
                    'flat_count': auction_stats['flat_count'],
                    'gap_down_count': auction_stats['gap_down_count']
                }
            }
            
            # 保存详细结果
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)
            json_file = os.path.join(data_dir, f'daily_report_{timestamp}.json')
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            report_data['json_file'] = json_file
            
            return report_data
            
        except Exception as e:
            st.error(f"❌ 报告生成失败: {e}")
            return {}
        
        finally:
            bs.logout()


def display_dashboard(report_data):
    """显示Streamlit仪表板"""
    
    # 头部
    st.markdown("<h1 class='main-header'>📊 CChanTrader-AI 交易日报</h1>", unsafe_allow_html=True)
    
    # 日期时间信息
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("报告日期", report_data.get('date', 'N/A'))
    with col2:
        st.metric("生成时间", report_data.get('analysis_time', 'N/A'))
    with col3:
        st.metric("推荐股票", len(report_data.get('recommendations', [])))
    
    st.markdown("---")
    
    # 市场概况
    st.markdown("<h2 class='sub-header'>📈 市场概况</h2>", unsafe_allow_html=True)
    
    market_summary = report_data.get('market_summary', {})
    auction_analysis = report_data.get('auction_analysis', {})
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("分析股票数", market_summary.get('total_analyzed', 0))
    with col2:
        st.metric("推荐股票数", market_summary.get('total_recommended', 0))
    with col3:
        st.metric("平均评分", f"{market_summary.get('avg_score', 0):.3f}")
    with col4:
        st.metric("平均竞价涨幅", f"{auction_analysis.get('avg_auction_ratio', 0):.2f}%")
    
    # 竞价分析图表
    col1, col2 = st.columns(2)
    
    with col1:
        # 缺口类型分布饼图
        gap_data = {
            '类型': ['高开', '平开', '低开'],
            '数量': [
                auction_analysis.get('gap_up_count', 0),
                auction_analysis.get('flat_count', 0),
                auction_analysis.get('gap_down_count', 0)
            ]
        }
        fig_gap = px.pie(
            gap_data, 
            values='数量', 
            names='类型',
            title='竞价缺口类型分布',
            color_discrete_sequence=['#4caf50', '#ff9800', '#f44336']
        )
        st.plotly_chart(fig_gap, use_container_width=True)
    
    with col2:
        # 评分分布直方图
        if report_data.get('recommendations'):
            scores = [r['total_score'] for r in report_data['recommendations']]
            fig_scores = px.histogram(
                x=scores,
                nbins=10,
                title='推荐股票评分分布',
                labels={'x': '综合评分', 'y': '数量'}
            )
            st.plotly_chart(fig_scores, use_container_width=True)
    
    st.markdown("---")
    
    # 推荐股票表格
    st.markdown("<h2 class='sub-header'>🎯 今日推荐股票</h2>", unsafe_allow_html=True)
    
    recommendations = report_data.get('recommendations', [])
    
    if recommendations:
        # 转换为DataFrame以便显示
        df_recommendations = pd.DataFrame(recommendations)
        
        # 重命名列
        df_display = df_recommendations[[
            'symbol', 'stock_name', 'market', 'current_price', 'total_score',
            'auction_ratio', 'gap_type', 'confidence', 'strategy', 'entry_price',
            'stop_loss', 'target_price', 'rsi', 'volume_ratio'
        ]].copy()
        
        df_display.columns = [
            '代码', '名称', '市场', '现价', '综合评分',
            '竞价涨幅%', '缺口类型', '置信度', '策略', '入场价',
            '止损价', '目标价', 'RSI', '量比'
        ]
        
        # 格式化数值
        df_display['综合评分'] = df_display['综合评分'].apply(lambda x: f"{x:.3f}")
        df_display['竞价涨幅%'] = df_display['竞价涨幅%'].apply(lambda x: f"{x:.2f}%")
        df_display['RSI'] = df_display['RSI'].apply(lambda x: f"{x:.1f}")
        df_display['量比'] = df_display['量比'].apply(lambda x: f"{x:.2f}")
        
        # 设置置信度样式
        def color_confidence(val):
            if val == 'very_high':
                return 'background-color: #c8e6c9; color: #2e7d32'
            elif val == 'high':
                return 'background-color: #bbdefb; color: #1976d2'
            elif val == 'medium':
                return 'background-color: #fff3e0; color: #ed6c02'
            else:
                return 'background-color: #ffcdd2; color: #d32f2f'
        
        # 显示表格
        st.dataframe(
            df_display.style.applymap(color_confidence, subset=['置信度']),
            use_container_width=True,
            height=400
        )
        
        # 详细股票卡片（可展开）
        with st.expander("查看详细股票分析"):
            for idx, stock in enumerate(recommendations[:5]):  # 只显示前5只详细分析
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"**{stock['stock_name']} ({stock['symbol']})**")
                    st.markdown(f"市场: {stock['market']}")
                    st.markdown(f"现价: ¥{stock['current_price']:.2f}")
                
                with col2:
                    confidence_class = {
                        'very_high': 'very-high',
                        'high': 'high',
                        'medium': 'medium',
                        'low': 'low'
                    }.get(stock['confidence'], '')
                    
                    st.markdown(f"综合评分: {stock['total_score']:.3f}")
                    st.markdown(f"置信度: <span class='{confidence_class}'>{stock['confidence']}</span>", unsafe_allow_html=True)
                    st.markdown(f"策略: {stock['strategy']}")
                
                with col3:
                    st.markdown(f"止损价: ¥{stock['stop_loss']:.2f}")
                    st.markdown(f"目标价: ¥{stock['target_price']:.2f}")
                    st.markdown(f"盈亏比: {((stock['target_price'] - stock['current_price'])/(stock['current_price'] - stock['stop_loss'])):.2f}")
                
                st.markdown("---")
    else:
        st.info("暂无推荐股票")
    
    # 保存信息
    st.markdown("---")
    st.markdown(f"📁 详细数据已保存至: `{report_data.get('json_file', 'N/A')}`")


def quick_test_report():
    """快速测试报告生成"""
    st.info("🧪 快速测试日报生成...")
    
    # 模拟报告数据
    mock_data = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'analysis_time': datetime.now().strftime('%H:%M:%S'),
        'recommendations': [
            {
                'symbol': 'sh.600000',
                'stock_name': '浦发银行',
                'market': '上海主板',
                'current_price': 13.65,
                'total_score': 0.856,
                'tech_score': 0.750,
                'auction_score': 0.720,
                'auction_ratio': 1.2,
                'gap_type': 'gap_up',
                'capital_bias': 0.68,
                'rsi': 65.2,
                'volume_ratio': 1.3,
                'entry_price': 13.65,
                'stop_loss': 12.56,
                'target_price': 15.70,
                'confidence': 'very_high',
                'strategy': '温和高开，开盘可买'
            },
            {
                'symbol': 'sz.000001',
                'stock_name': '平安银行',
                'market': '深圳主板',
                'current_price': 12.38,
                'total_score': 0.789,
                'tech_score': 0.680,
                'auction_score': 0.650,
                'auction_ratio': 0.8,
                'gap_type': 'flat',
                'capital_bias': 0.55,
                'rsi': 58.1,
                'volume_ratio': 1.1,
                'entry_price': 12.38,
                'stop_loss': 11.39,
                'target_price': 14.24,
                'confidence': 'high',
                'strategy': '平开强势，关注买入'
            },
            {
                'symbol': 'sz.002142',
                'stock_name': '宁波银行',
                'market': '中小板',
                'current_price': 25.67,
                'total_score': 0.823,
                'tech_score': 0.710,
                'auction_score': 0.680,
                'auction_ratio': 0.5,
                'gap_type': 'flat',
                'capital_bias': 0.62,
                'rsi': 55.8,
                'volume_ratio': 0.95,
                'entry_price': 25.67,
                'stop_loss': 23.62,
                'target_price': 29.52,
                'confidence': 'high',
                'strategy': '平开强势，关注买入'
            }
        ],
        'market_summary': {
            'total_analyzed': 60,
            'total_recommended': 3,
            'avg_score': 0.823
        },
        'auction_analysis': {
            'avg_auction_ratio': 1.0,
            'gap_up_count': 25,
            'flat_count': 20,
            'gap_down_count': 15
        }
    }
    
    return mock_data


def main():
    """主函数"""
    
    # 侧边栏
    with st.sidebar:
        st.image("https://via.placeholder.com/300x100/1E88E5/ffffff?text=CChanTrader-AI", use_column_width=True)
        st.markdown("## 控制面板")
        
        # 模式选择
        mode = st.radio(
            "选择模式",
            ["实时分析", "测试模式", "加载历史报告"]
        )
        
        if mode == "加载历史报告":
            # 列出历史报告文件
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
            if os.path.exists(data_dir):
                report_files = [f for f in os.listdir(data_dir) if f.startswith('daily_report_') and f.endswith('.json')]
                if report_files:
                    selected_file = st.selectbox("选择历史报告", report_files)
                    if selected_file:
                        file_path = os.path.join(data_dir, selected_file)
                        with open(file_path, 'r', encoding='utf-8') as f:
                            report_data = json.load(f)
                        st.session_state['report_data'] = report_data
                        st.success(f"已加载: {selected_file}")
                else:
                    st.info("暂无历史报告")
        
        st.markdown("---")
        st.markdown("### 关于")
        st.markdown("CChanTrader-AI 交易日报生成器")
        st.markdown("在每个交易日9:25-9:29自动分析")
        
        # 生成报告按钮
        if st.button("🚀 生成新报告", type="primary", use_container_width=True):
            with st.spinner("正在生成报告..."):
                generator = DailyReportGenerator()
                report_data = generator.generate_daily_report()
                if report_data:
                    st.session_state['report_data'] = report_data
                    st.success("报告生成成功!")
                else:
                    st.error("报告生成失败")
        
        if st.button("🧪 测试模式", use_container_width=True):
            mock_data = quick_test_report()
            st.session_state['report_data'] = mock_data
            st.success("测试数据已加载")
    
    # 主内容区域
    if 'report_data' in st.session_state and st.session_state['report_data']:
        display_dashboard(st.session_state['report_data'])
    else:
        # 欢迎页面
        st.markdown("<h1 class='main-header'>欢迎使用 CChanTrader-AI</h1>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            <div class='info-box'>
                <h3>📊 实时分析</h3>
                <p>点击左侧"生成新报告"开始实时分析</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class='info-box'>
                <h3>🧪 测试模式</h3>
                <p>使用测试数据预览报告效果</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class='info-box'>
                <h3>📁 历史报告</h3>
                <p>加载之前生成的报告</p>
            </div>
            """, unsafe_allow_html=True)
        
        # 功能介绍
        st.markdown("---")
        st.markdown("""
        ### ✨ 功能特点
        
        - **自动分析**：每个交易日9:25-9:29自动分析股票
        - **竞价分析**：结合竞价数据判断开盘强弱
        - **技术指标**：综合RSI、均线、成交量等技术指标
        - **智能评分**：基于多维度数据给出综合评分
        - **策略建议**：根据竞价情况给出具体操作建议
        """)


if __name__ == "__main__":
    main()
