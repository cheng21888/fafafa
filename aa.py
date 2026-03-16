#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CChanTrader-AI 交易日报生成器 - Streamlit版本
支持选择日期进行分析
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
import time

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
    .stDateInput {
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


class DailyReportGenerator:
    """交易日报生成器"""
    
    def __init__(self, analysis_date=None):
        """
        初始化日报生成器
        Args:
            analysis_date: 分析日期，datetime对象，默认为当前日期
        """
        self.analysis_results = {}
        self.report_data = {}
        self.analysis_date = analysis_date or datetime.now()
        
    def is_trading_day(self, date=None) -> bool:
        """判断是否为交易日"""
        if date is None:
            date = self.analysis_date
        
        # 简化版：排除周末
        weekday = date.weekday()
        if weekday >= 5:
            return False
        
        return True
    
    def get_stock_list_from_akshare(self, date=None) -> pd.DataFrame:
        """
        使用akshare获取A股股票列表
        """
        try:
            if date is None:
                date = self.analysis_date
            
            # 获取所有A股股票列表
            stock_info = ak.stock_info_a_code_name()
            
            # 转换股票代码格式以匹配baostock的格式
            stock_list = []
            for _, row in stock_info.iterrows():
                code = row['code']
                name = row['name']
                
                # 转换代码格式为 baostock 兼容格式
                if code.startswith('6'):
                    bs_code = f"sh.{code}"
                elif code.startswith('0') or code.startswith('3') or code.startswith('2'):
                    bs_code = f"sz.{code}"
                else:
                    bs_code = code
                
                stock_list.append({
                    'code': bs_code,
                    'code_name': name,
                    'status': '1'  # 假设所有股票都是正常交易状态
                })
            
            df = pd.DataFrame(stock_list)
            
            # 过滤掉B股、北交所等
            df = df[
                ~df['code'].str.contains('.200') &  # 深圳B股
                ~df['code'].str.contains('.900') &  # 上海B股
                ~df['code'].str.contains('.8') &    # 北交所/三板
                ~df['code'].str.contains('.4')       # 老三板
            ]
            
            return df
            
        except Exception as e:
            st.error(f"获取股票列表失败: {e}")
            # 返回一个小的示例列表作为备选
            return pd.DataFrame([
                {'code': 'sh.600000', 'code_name': '浦发银行', 'status': '1'},
                {'code': 'sh.600004', 'code_name': '白云机场', 'status': '1'},
                {'code': 'sh.600009', 'code_name': '上海机场', 'status': '1'},
                {'code': 'sz.000001', 'code_name': '平安银行', 'status': '1'},
                {'code': 'sz.000002', 'code_name': '万科A', 'status': '1'},
                {'code': 'sz.000333', 'code_name': '美的集团', 'status': '1'},
                {'code': 'sz.002142', 'code_name': '宁波银行', 'status': '1'},
                {'code': 'sz.300059', 'code_name': '东方财富', 'status': '1'}
            ])
    
    def get_stock_data_for_date(self, symbol: str, target_date: datetime, days: int = 60) -> pd.DataFrame:
        """
        获取指定日期附近的股票数据（仍使用baostock，因为akshare历史数据获取可能更复杂）
        Args:
            symbol: 股票代码
            target_date: 目标日期
            days: 获取数据的天数范围
        """
        try:
            end_date = target_date.strftime('%Y-%m-%d')
            start_date = (target_date - timedelta(days=days)).strftime('%Y-%m-%d')
            
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
            
            # 确保日期列是日期类型并排序
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            return df.dropna()
            
        except Exception as e:
            st.error(f"获取股票数据失败 {symbol}: {e}")
            return pd.DataFrame()
    
    def get_auction_data_for_date(self, symbol: str, target_date: datetime) -> dict:
        """
        获取指定日期的竞价数据
        使用akshare获取实时或历史分时数据
        """
        try:
            # 转换代码格式为akshare格式（去掉前缀）
            ak_code = symbol.replace('sh.', '').replace('sz.', '')
            
            # 如果是当前日期，尝试获取实时数据
            if target_date.date() == datetime.now().date():
                try:
                    # 获取当日分时数据
                    intraday = ak.stock_zh_a_tick_tx(ak_code, trade_date=target_date.strftime('%Y%m%d'))
                    
                    if not intraday.empty:
                        # 筛选竞价时间（9:15-9:25）
                        intraday['时间'] = pd.to_datetime(intraday['时间']).dt.time
                        auction_data = intraday[
                            (intraday['时间'] >= pd.to_datetime('09:15').time()) & 
                            (intraday['时间'] <= pd.to_datetime('09:25').time())
                        ]
                        
                        if not auction_data.empty:
                            final_price = float(auction_data.iloc[-1]['成交价'])
                            total_volume = auction_data['成交量'].sum()
                            
                            return {
                                'final_price': final_price,
                                'total_volume': total_volume,
                                'data_points': len(auction_data),
                                'status': 'success'
                            }
                except:
                    pass
            
            # 尝试获取历史分时数据
            try:
                # 获取历史分时数据（可能需要特殊处理）
                hist_data = ak.stock_zh_a_hist_pre_min_em(
                    symbol=ak_code,
                    start_time="09:00:00",
                    end_time="09:30:00"
                )
                
                if not hist_data.empty:
                    # 筛选竞价时间
                    auction_df = hist_data[
                        hist_data['时间'].str.contains('09:1[5-9]|09:2[0-5]')
                    ]
                    
                    if not auction_df.empty:
                        final_price = float(auction_df.iloc[-1]['开盘'])
                        total_volume = auction_df['成交量'].sum()
                        
                        return {
                            'final_price': final_price,
                            'total_volume': total_volume,
                            'data_points': len(auction_df),
                            'status': 'success'
                        }
            except:
                pass
            
            # 方案3：使用历史日线数据估算竞价情况
            historical_data = self.get_stock_data_for_date(symbol, target_date, 5)
            if not historical_data.empty and len(historical_data) >= 2:
                # 使用前一日收盘价作为竞价基准
                prev_close = float(historical_data['close'].iloc[-2]) if len(historical_data) >= 2 else float(historical_data['close'].iloc[-1])
                current_open = float(historical_data['open'].iloc[-1])
                
                # 估算竞价数据
                return {
                    'final_price': current_open,
                    'total_volume': float(historical_data['volume'].iloc[-1]) * 0.1,  # 估算竞价量
                    'data_points': 10,  # 估算数据点
                    'status': 'estimated'
                }
            
            return self._get_default_auction()
            
        except Exception as e:
            st.warning(f"获取竞价数据失败 {symbol}: {e}")
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
            df = self.get_stock_data_for_date(symbol, self.analysis_date, 60)
            if len(df) < 20:
                return None
            
            # 找到目标日期在数据中的位置
            target_date_str = self.analysis_date.strftime('%Y-%m-%d')
            if target_date_str in df['date'].astype(str).values:
                # 目标日期有数据
                target_idx = df[df['date'].astype(str) == target_date_str].index[0]
                if target_idx > 0:
                    current_price = float(df.loc[target_idx, 'close'])
                    prev_close = float(df.loc[target_idx - 1, 'close'])
                    analysis_df = df.loc[:target_idx].copy()  # 使用截止到目标日期的数据
                else:
                    return None
            else:
                # 目标日期无数据，使用最近的数据
                st.warning(f"目标日期 {target_date_str} 无数据，使用最近数据")
                current_price = float(df['close'].iloc[-1])
                prev_close = float(df['close'].iloc[-2]) if len(df) >= 2 else current_price
                analysis_df = df.copy()
            
            # 基础过滤
            if not (2 <= current_price <= 300):
                return None
            
            # 技术指标计算
            tech_score = self._calculate_tech_indicators(analysis_df)
            
            # 竞价数据分析
            auction_data = self.get_auction_data_for_date(symbol, self.analysis_date)
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
                'rsi': self._calculate_rsi(analysis_df),
                'volume_ratio': self._calculate_volume_ratio(analysis_df),
                'entry_price': current_price,
                'stop_loss': round(current_price * 0.92, 2),
                'target_price': round(current_price * 1.15, 2),
                'confidence': self._determine_confidence(total_score, auction_score),
                'strategy': self._generate_strategy(auction_score),
                'analysis_date': self.analysis_date.strftime('%Y-%m-%d')
            }
            
        except Exception as e:
            st.error(f"分析股票失败 {symbol}: {e}")
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
        if auction_data['status'] == 'no_data' or auction_data['final_price'] == 0:
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
        
        # 如果是估算数据，适当调整强度
        if auction_data['status'] == 'estimated':
            strength *= 0.9
        
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
        elif symbol.startswith('sh.688'):
            return '科创板'
        elif symbol.startswith('sz.000'):
            return '深圳主板'
        elif symbol.startswith('sz.002'):
            return '中小板'
        elif symbol.startswith('sz.30'):
            return '创业板'
        elif symbol.startswith('sz.00'):
            return '深圳主板'
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
    
    def get_trading_dates(self, year: int) -> list:
        """获取指定年份的交易日列表（使用akshare）"""
        try:
            # 使用akshare获取交易日历
            calendar = ak.tool_trade_date_hist_sina()
            # 过滤指定年份的交易日
            year_dates = calendar[
                (pd.to_datetime(calendar['trade_date']).dt.year == year) &
                (calendar['is_open'] == 1)
            ]['trade_date'].tolist()
            
            return [date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else date for date in year_dates]
        except Exception as e:
            st.warning(f"获取交易日历失败: {e}")
            # 返回一个简单的备选列表（仅限工作日）
            dates = []
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31)
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() < 5:  # 周一到周五
                    dates.append(current_date.strftime('%Y-%m-%d'))
                current_date += timedelta(days=1)
            return dates
    
    def generate_daily_report(self) -> dict:
        """生成每日报告"""
        st.info(f"🔄 开始生成 {self.analysis_date.strftime('%Y-%m-%d')} 交易日报...")
        
        if not self.is_trading_day():
            st.warning(f"📅 {self.analysis_date.strftime('%Y-%m-%d')} 非交易日，跳过报告生成")
            return {}
        
        # 连接数据源 (baostock仍用于历史数据)
        lg = bs.login()
        st.info(f"📊 BaoStock连接: {lg.error_code}")
        
        try:
            # 使用akshare获取股票列表
            st.info("🔍 使用akshare获取股票列表...")
            all_stocks = self.get_stock_list_from_akshare()
            
            if all_stocks.empty:
                st.error("❌ 无法获取股票列表")
                return {}
            
            st.info(f"📋 获取到 {len(all_stocks)} 只A股")
            
            # 按市场分类
            markets = {
                '上海主板': all_stocks[all_stocks['code'].str.startswith('sh.6') & ~all_stocks['code'].str.startswith('sh.688')],
                '科创板': all_stocks[all_stocks['code'].str.startswith('sh.688')],
                '深圳主板': all_stocks[all_stocks['code'].str.startswith('sz.000')],
                '中小板': all_stocks[all_stocks['code'].str.startswith('sz.002')],
                '创业板': all_stocks[all_stocks['code'].str.startswith('sz.30')]
            }
            
            # 显示各市场股票数量
            market_counts = {name: len(df) for name, df in markets.items()}
            st.info(f"📊 市场分布: {market_counts}")
            
            # 采样分析 (限制数量以提高速度)
            sample_stocks = []
            sample_size_per_market = min(30, 500 // len(markets))  # 每个市场采样约30只，总样本约150只
            
            for market_name, market_stocks in markets.items():
                if len(market_stocks) > 0:
                    sample_size = min(sample_size_per_market, len(market_stocks))
                    sampled = market_stocks.sample(n=sample_size, random_state=42)
                    sample_stocks.append(sampled)
                    st.info(f"  {market_name}: 采样 {sample_size} 只")
            
            final_sample = pd.concat(sample_stocks, ignore_index=True)
            st.info(f"📋 最终分析样本: {len(final_sample)}只股票")
            
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
                time.sleep(0.05)  # 稍微延迟，避免请求过快
            
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
                'date': self.analysis_date.strftime('%Y-%m-%d'),
                'analysis_time': datetime.now().strftime('%H:%M:%S'),
                'recommendations': recommendations[:30],  # 限制推荐数量为前30只
                'market_summary': {
                    'total_analyzed': len(final_sample),
                    'total_recommended': len(recommendations),
                    'avg_score': round(avg_score, 3),
                    'market_distribution': market_counts
                },
                'auction_analysis': {
                    'avg_auction_ratio': round(avg_auction_ratio, 2),
                    'gap_up_count': auction_stats['gap_up_count'],
                    'flat_count': auction_stats['flat_count'],
                    'gap_down_count': auction_stats['gap_down_count']
                }
            }
            
            # 保存详细结果
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)
            
            filename = f"daily_report_{self.analysis_date.strftime('%Y%m%d')}_{datetime.now().strftime('%H%M%S')}.json"
            json_file = os.path.join(data_dir, filename)
            
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            report_data['json_file'] = json_file
            
            st.success(f"✅ 日报生成完成!")
            st.info(f"   📊 分析股票: {len(final_sample)}只")
            st.info(f"   🎯 推荐股票: {len(recommendations)}只")
            st.info(f"   📈 平均评分: {avg_score:.3f}")
            st.info(f"   💾 详细数据: {json_file}")
            
            return report_data
            
        except Exception as e:
            st.error(f"❌ 报告生成失败: {e}")
            import traceback
            st.error(traceback.format_exc())
            return {}
        
        finally:
            bs.logout()


def display_dashboard(report_data):
    """显示Streamlit仪表板"""
    
    # 头部
    st.markdown("<h1 class='main-header'>📊 CChanTrader-AI 交易日报</h1>", unsafe_allow_html=True)
    
    # 日期时间信息
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("分析日期", report_data.get('date', 'N/A'))
    with col2:
        st.metric("生成时间", report_data.get('analysis_time', 'N/A'))
    with col3:
        st.metric("推荐股票", len(report_data.get('recommendations', [])))
    with col4:
        # 计算平均评分
        recommendations = report_data.get('recommendations', [])
        avg_score = sum(r.get('total_score', 0) for r in recommendations) / max(len(recommendations), 1)
        st.metric("平均评分", f"{avg_score:.3f}")
    
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
    
    # 市场分布
    market_dist = market_summary.get('market_distribution', {})
    if market_dist:
        st.markdown("##### 市场分布")
        cols = st.columns(len(market_dist))
        for i, (market, count) in enumerate(market_dist.items()):
            with cols[i]:
                st.metric(market, count)
    
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
        if sum(gap_data['数量']) > 0:
            fig_gap = px.pie(
                gap_data, 
                values='数量', 
                names='类型',
                title='竞价缺口类型分布',
                color_discrete_sequence=['#4caf50', '#ff9800', '#f44336']
            )
            st.plotly_chart(fig_gap, use_container_width=True)
        else:
            st.info("无竞价数据")
    
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
        
        # 导出数据按钮
        csv = df_display.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下载推荐列表 (CSV)",
            data=csv,
            file_name=f"recommendations_{report_data.get('date', 'unknown')}.csv",
            mime="text/csv"
        )
        
        # 详细股票卡片（可展开）
        with st.expander("查看详细股票分析"):
            for idx, stock in enumerate(recommendations[:10]):  # 只显示前10只详细分析
                col1, col2, col3, col4 = st.columns(4)
                
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
                    st.markdown(f"技术评分: {stock['tech_score']:.3f}")
                    st.markdown(f"竞价评分: {stock['auction_score']:.3f}")
                    st.markdown(f"竞价涨幅: {stock['auction_ratio']:.2f}%")
                
                with col4:
                    st.markdown(f"止损价: ¥{stock['stop_loss']:.2f}")
                    st.markdown(f"目标价: ¥{stock['target_price']:.2f}")
                    profit_ratio = ((stock['target_price'] - stock['current_price']) / stock['current_price']) * 100
                    loss_ratio = ((stock['current_price'] - stock['stop_loss']) / stock['current_price']) * 100
                    st.markdown(f"预期收益: +{profit_ratio:.1f}% / -{loss_ratio:.1f}%")
                
                st.markdown("---")
    else:
        st.info("暂无推荐股票")
    
    # 保存信息
    st.markdown("---")
    st.markdown(f"📁 详细数据已保存至: `{report_data.get('json_file', 'N/A')}`")


def load_historical_reports():
    """加载历史报告列表"""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    if os.path.exists(data_dir):
        report_files = [f for f in os.listdir(data_dir) 
                       if f.startswith('daily_report_') and f.endswith('.json')]
        return sorted(report_files, reverse=True)
    return []


def main():
    """主函数"""
    
    # 初始化session state
    if 'report_data' not in st.session_state:
        st.session_state['report_data'] = None
    if 'analysis_date' not in st.session_state:
        st.session_state['analysis_date'] = datetime.now()
    
    # 侧边栏
    with st.sidebar:
        st.image("https://via.placeholder.com/300x100/1E88E5/ffffff?text=CChanTrader-AI", use_column_width=True)
        st.markdown("## 控制面板")
        
        # 日期选择
        st.markdown("### 📅 选择分析日期")
        
        # 预设常用日期选项
        date_option = st.radio(
            "日期选择",
            ["今天", "昨天", "指定日期", "选择交易日"]
        )
        
        if date_option == "今天":
            selected_date = datetime.now()
        elif date_option == "昨天":
            selected_date = datetime.now() - timedelta(days=1)
        elif date_option == "指定日期":
            selected_date = st.date_input(
                "选择日期",
                value=datetime.now(),
                min_value=datetime(2020, 1, 1),
                max_value=datetime.now()
            )
            selected_date = datetime.combine(selected_date, datetime.min.time())
        else:  # 选择交易日
            # 这里可以添加交易日选择逻辑
            year = st.selectbox("选择年份", range(2020, datetime.now().year + 1))
            
            # 获取交易日列表
            generator = DailyReportGenerator()
            trading_dates = generator.get_trading_dates(year)
            
            if trading_dates:
                selected_trading_date = st.selectbox("选择交易日", trading_dates)
                selected_date = datetime.strptime(selected_trading_date, '%Y-%m-%d')
            else:
                st.warning("无法获取交易日列表，使用今天")
                selected_date = datetime.now()
        
        st.session_state['analysis_date'] = selected_date
        st.info(f"当前选择: {selected_date.strftime('%Y-%m-%d')}")
        
        st.markdown("---")
        
        # 模式选择
        st.markdown("### 🎯 操作")
        
        # 生成报告按钮
        if st.button("🚀 生成报告", type="primary", use_container_width=True):
            with st.spinner(f"正在生成 {selected_date.strftime('%Y-%m-%d')} 报告..."):
                generator = DailyReportGenerator(analysis_date=selected_date)
                report_data = generator.generate_daily_report()
                if report_data:
                    st.session_state['report_data'] = report_data
                    st.success("报告生成成功!")
                    st.rerun()
                else:
                    st.error("报告生成失败")
        
        if st.button("🧪 测试模式", use_container_width=True):
            mock_data = quick_test_report(selected_date)
            st.session_state['report_data'] = mock_data
            st.success("测试数据已加载")
            st.rerun()
        
        st.markdown("---")
        
        # 历史报告
        st.markdown("### 📚 历史报告")
        report_files = load_historical_reports()
        
        if report_files:
            selected_file = st.selectbox("选择历史报告", report_files)
            if selected_file and st.button("📂 加载报告", use_container_width=True):
                data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
                file_path = os.path.join(data_dir, selected_file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        report_data = json.load(f)
                    st.session_state['report_data'] = report_data
                    st.success(f"已加载: {selected_file}")
                    st.rerun()
                except Exception as e:
                    st.error(f"加载失败: {e}")
        else:
            st.info("暂无历史报告")
        
        st.markdown("---")
        
        # 关于信息
        with st.expander("ℹ️ 关于"):
            st.markdown("""
            **CChanTrader-AI 交易日报生成器**
            
            - 支持选择任意日期分析
            - 每个交易日9:25-9:29自动分析
            - 结合竞价数据和技术指标
            - 智能评分和策略建议
            - 使用AKShare获取股票列表
            - 使用BaoStock获取历史K线数据
            """)
    
    # 主内容区域
    if st.session_state['report_data']:
        display_dashboard(st.session_state['report_data'])
    else:
        # 欢迎页面
        st.markdown("<h1 class='main-header'>欢迎使用 CChanTrader-AI</h1>", unsafe_allow_html=True)
        
        # 当前选择日期显示
        st.markdown(f"<h3 style='text-align: center;'>当前选择: {st.session_state['analysis_date'].strftime('%Y-%m-%d')}</h3>", 
                   unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("""
            <div class='info-box'>
                <h3>📊 实时分析</h3>
                <p>选择日期后点击"生成报告"开始分析</p>
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
        
        - **📅 日期选择**：支持任意历史日期分析
        - **🔍 竞价分析**：结合竞价数据判断开盘强弱
        - **📊 技术指标**：综合RSI、均线、成交量等技术指标
        - **🎯 智能评分**：基于多维度数据给出综合评分
        - **💡 策略建议**：根据竞价情况给出具体操作建议
        """)


def quick_test_report(analysis_date=None):
    """快速测试报告生成"""
    if analysis_date is None:
        analysis_date = datetime.now()
    
    # 模拟报告数据
    mock_data = {
        'date': analysis_date.strftime('%Y-%m-%d'),
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
                'strategy': '温和高开，开盘可买',
                'analysis_date': analysis_date.strftime('%Y-%m-%d')
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
                'strategy': '平开强势，关注买入',
                'analysis_date': analysis_date.strftime('%Y-%m-%d')
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
                'strategy': '平开强势，关注买入',
                'analysis_date': analysis_date.strftime('%Y-%m-%d')
            },
            {
                'symbol': 'sh.600036',
                'stock_name': '招商银行',
                'market': '上海主板',
                'current_price': 36.42,
                'total_score': 0.791,
                'tech_score': 0.690,
                'auction_score': 0.630,
                'auction_ratio': 0.3,
                'gap_type': 'flat',
                'capital_bias': 0.58,
                'rsi': 52.3,
                'volume_ratio': 0.88,
                'entry_price': 36.42,
                'stop_loss': 33.51,
                'target_price': 41.88,
                'confidence': 'medium',
                'strategy': '竞价信号一般，建议观望',
                'analysis_date': analysis_date.strftime('%Y-%m-%d')
            }
        ],
        'market_summary': {
            'total_analyzed': 150,
            'total_recommended': 4,
            'avg_score': 0.815,
            'market_distribution': {
                '上海主板': 50,
                '科创板': 20,
                '深圳主板': 30,
                '中小板': 30,
                '创业板': 20
            }
        },
        'auction_analysis': {
            'avg_auction_ratio': 0.7,
            'gap_up_count': 18,
            'flat_count': 15,
            'gap_down_count': 12
        }
    }
    
    return mock_data


if __name__ == "__main__":
    main()
