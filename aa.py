#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股集合竞价数据获取演示程序
整合AKShare和BaoStock，展示完整的竞价数据分析流程
"""

import os
import akshare as ak
import baostock as bs
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
import warnings
warnings.filterwarnings('ignore')

class AuctionDataAnalyzer:
    """集合竞价数据分析器"""
    
    def __init__(self):
        self.name = "A股集合竞价数据分析器"
        self.baostock_logged_in = False
        print(f"🚀 初始化 {self.name}")
        self._login_baostock()
    
    def _login_baostock(self):
        """登录BaoStock"""
        try:
            lg = bs.login()
            if lg.error_code == '0':
                self.baostock_logged_in = True
                print("✅ BaoStock登录成功")
            else:
                print(f"❌ BaoStock登录失败: {lg.error_msg}")
        except Exception as e:
            print(f"❌ BaoStock连接错误: {e}")
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算RSI指标"""
        try:
            if len(df) < period + 1:
                return 50.0
            
            # 计算价格变化
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            # 计算RSI
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
    
    def _calculate_tech_indicators(self, df: pd.DataFrame) -> float:
        """计算技术指标评分"""
        score = 0.5  # 基础分
        
        try:
            # 均线系统评分 (30%)
            if len(df) >= 20:
                ma5 = df['close'].rolling(5).mean().iloc[-1]
                ma10 = df['close'].rolling(10).mean().iloc[-1] 
                ma20 = df['close'].rolling(20).mean().iloc[-1]
                current = df['close'].iloc[-1]
                
                # 多头排列加分
                if current > ma5 > ma10 > ma20:
                    score += 0.30
                # 短期多头加分
                elif current > ma5 > ma10:
                    score += 0.20
                # 站上20日线加分
                elif current > ma20:
                    score += 0.10
                # 均线空头排列减分
                elif current < ma5 < ma10 < ma20:
                    score -= 0.20
                # 跌破20日线减分
                elif current < ma20:
                    score -= 0.10
            
            # RSI指标评分 (20%)
            rsi = self._calculate_rsi(df)
            if 40 <= rsi <= 60:
                score += 0.15  # 中性区域
            elif 60 < rsi <= 70:
                score += 0.10  # 强势区域
            elif rsi > 70:
                score -= 0.10  # 超买区域
            elif 30 <= rsi < 40:
                score += 0.05  # 弱势区域但可能反弹
            elif rsi < 30:
                score += 0.10  # 超卖区域
            
            # 成交量评分 (20%)
            vol_ratio = self._calculate_volume_ratio(df)
            if vol_ratio > 2.0:
                score += 0.20  # 显著放量
            elif vol_ratio > 1.5:
                score += 0.15  # 放量
            elif vol_ratio > 1.2:
                score += 0.10  # 温和放量
            elif vol_ratio < 0.5:
                score -= 0.10  # 显著缩量
            
            # MACD趋势评分 (15%)
            if len(df) >= 26:
                exp1 = df['close'].ewm(span=12, adjust=False).mean()
                exp2 = df['close'].ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()
                
                current_macd = macd.iloc[-1]
                current_signal = signal.iloc[-1]
                prev_macd = macd.iloc[-2]
                
                # MACD金叉
                if prev_macd <= current_signal and current_macd > current_signal:
                    score += 0.15
                # MACD多头
                elif current_macd > 0 and current_macd > current_signal:
                    score += 0.10
                # MACD死叉
                elif prev_macd >= current_signal and current_macd < current_signal:
                    score -= 0.15
                # MACD空头
                elif current_macd < 0 and current_macd < current_signal:
                    score -= 0.10
            
            # 布林带评分 (15%)
            if len(df) >= 20:
                # 计算布林带
                sma = df['close'].rolling(20).mean()
                std = df['close'].rolling(20).std()
                upper = sma + 2 * std
                lower = sma - 2 * std
                
                current = df['close'].iloc[-1]
                
                # 价格位置评分
                if current < lower:
                    score += 0.15  # 下轨支撑
                elif current > upper:
                    score -= 0.10  # 上轨压力
                elif lower < current < sma:
                    score += 0.05  # 中下轨之间
                elif sma < current < upper:
                    score += 0.10  # 中上轨之间
                
                # 带宽评分 (波动率)
                band_width = (upper - lower) / sma
                if band_width < 0.05:
                    # 窄带，可能变盘
                    if current > sma:
                        score += 0.10  # 向上变盘可能
                    else:
                        score -= 0.05  # 向下变盘可能
                elif band_width > 0.15:
                    # 宽带，波动剧烈
                    if current > upper:
                        score -= 0.10  # 可能回落
                    elif current < lower:
                        score += 0.05  # 可能反弹
            
        except Exception as e:
            print(f"⚠️ 技术指标计算异常: {e}")
        
        # 确保评分在0-1之间
        return max(0.0, min(1.0, score))
    
    def _calculate_volume_profile_score(self, df: pd.DataFrame) -> dict:
        """计算成交量分布评分"""
        try:
            if len(df) < 20:
                return {'score': 0.5, 'details': '数据不足'}
            
            # 价格区间分布
            current_price = df['close'].iloc[-1]
            price_min = df['low'].min()
            price_max = df['high'].max()
            
            if price_max - price_min < 0.01:
                return {'score': 0.5, 'details': '价格区间过小'}
            
            # 创建价格区间
            bins = 10
            price_ranges = np.linspace(price_min, price_max, bins + 1)
            
            volume_profile = {}
            max_volume = 0
            value_area_low = price_min
            value_area_high = price_max
            
            for i in range(bins):
                lower = price_ranges[i]
                upper = price_ranges[i + 1]
                
                # 计算该价格区间的成交量
                mask = (df['low'] >= lower) & (df['high'] < upper)
                if mask.any():
                    volume = df.loc[mask, 'volume'].sum()
                    volume_profile[f"{lower:.2f}-{upper:.2f}"] = volume
                    
                    if volume > max_volume:
                        max_volume = volume
                        value_area_low = lower
                        value_area_high = upper
            
            # 判断当前价格位置
            if value_area_low <= current_price <= value_area_high:
                position_score = 0.15  # 在价值区内
            elif current_price < value_area_low:
                position_score = 0.10  # 在价值区下方
            else:
                position_score = -0.05  # 在价值区上方
            
            score = 0.5 + position_score
            
            return {
                'score': score,
                'value_area': f"{value_area_low:.2f}-{value_area_high:.2f}",
                'current_price_position': 'in_area' if value_area_low <= current_price <= value_area_high else ('below' if current_price < value_area_low else 'above'),
                'volume_distribution': volume_profile
            }
            
        except Exception as e:
            return {'score': 0.5, 'details': f'计算异常: {e}'}
    
    def get_akshare_auction_data(self, symbol):
        """
        使用AKShare获取集合竞价数据
        
        Args:
            symbol (str): 股票代码，如 "000001"
        
        Returns:
            dict: 竞价数据结果
        """
        print(f"📊 正在获取 {symbol} 的AKShare集合竞价数据...")
        
        try:
            # 获取盘前分钟数据
            pre_market_df = ak.stock_zh_a_hist_pre_min_em(
                symbol=symbol,
                start_time="09:00:00",
                end_time="09:30:00"
            )
            
            if pre_market_df.empty:
                print(f"⚠️ {symbol} 暂无盘前数据")
                return None
            
            # 筛选集合竞价时间段 (9:15-9:25)
            auction_df = pre_market_df[
                pre_market_df['时间'].str.contains('09:1[5-9]|09:2[0-5]', na=False)
            ].copy()
            
            if auction_df.empty:
                print(f"⚠️ {symbol} 暂无集合竞价数据")
                return None
            
            # 解析竞价数据
            opening_price = auction_df['收盘'].iloc[-1] if len(auction_df) > 0 else None
            total_volume = auction_df['成交量'].sum()
            total_amount = auction_df['成交额'].sum()
            price_high = auction_df['最高'].max()
            price_low = auction_df['最低'].min()
            
            # 计算竞价趋势
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
                'raw_data': auction_df.to_dict('records')
            }
            
            print(f"✅ {symbol} AKShare数据获取成功")
            return result
            
        except Exception as e:
            print(f"❌ 获取{symbol} AKShare数据失败: {e}")
            return None
    
    def get_baostock_opening_data(self, symbol, days=5):
        """
        使用BaoStock获取开盘价数据
        
        Args:
            symbol (str): 股票代码，如 "sh.600000"
            days (int): 获取天数
        
        Returns:
            dict: 开盘价数据结果
        """
        if not self.baostock_logged_in:
            print("❌ BaoStock未登录，无法获取数据")
            return None
        
        print(f"📈 正在获取 {symbol} 的BaoStock开盘价数据...")
        
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y-%m-%d')
            
            # 获取日K线数据
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
                print(f"⚠️ {symbol} BaoStock暂无数据")
                return None
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # 数据类型转换
            numeric_cols = ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'pctChg']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna().tail(days)
            
            if df.empty:
                print(f"⚠️ {symbol} BaoStock数据为空")
                return None
            
            # 计算技术指标评分
            tech_score = self._calculate_tech_indicators(df)
            
            # 计算成交量分布评分
            volume_profile = self._calculate_volume_profile_score(df)
            
            # 计算开盘缺口
            gaps = []
            for i in range(1, len(df)):
                prev_close = df.iloc[i-1]['close']
                current_open = df.iloc[i]['open']
                gap_pct = (current_open - prev_close) / prev_close * 100
                
                gaps.append({
                    'date': df.iloc[i]['date'],
                    'gap_pct': round(gap_pct, 2),
                    'prev_close': prev_close,
                    'open_price': current_open
                })
            
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
                'gap_analysis': gaps,
                'technical_score': round(tech_score, 3),
                'volume_profile': volume_profile,
                'historical_data': df.to_dict('records')
            }
            
            print(f"✅ {symbol} BaoStock数据获取成功")
            return result
            
        except Exception as e:
            print(f"❌ 获取{symbol} BaoStock数据失败: {e}")
            return None
    
    def analyze_auction_signals(self, akshare_data, baostock_data=None):
        """
        分析集合竞价信号
        
        Args:
            akshare_data (dict): AKShare竞价数据
            baostock_data (dict): BaoStock开盘价数据
        
        Returns:
            dict: 分析结果
        """
        if not akshare_data:
            return None
        
        print(f"🔍 正在分析 {akshare_data['symbol']} 的竞价信号...")
        
        analysis = {
            'symbol': akshare_data['symbol'],
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_quality': 'good' if akshare_data['data_points'] >= 5 else 'limited',
            'signals': {}
        }
        
        # 1. 价格趋势信号
        trend_pct = akshare_data['trend_pct']
        if trend_pct > 1:
            price_signal = 'strong_bullish'
        elif trend_pct > 0.2:
            price_signal = 'bullish'
        elif trend_pct < -1:
            price_signal = 'strong_bearish'
        elif trend_pct < -0.2:
            price_signal = 'bearish'
        else:
            price_signal = 'neutral'
        
        analysis['signals']['price_trend'] = {
            'signal': price_signal,
            'trend_pct': trend_pct,
            'strength': 'strong' if abs(trend_pct) > 1 else 'weak'
        }
        
        # 2. 成交量信号
        volume = akshare_data['total_volume']
        if volume > 10000:  # 成交量大于1万手
            volume_signal = 'high_volume'
        elif volume > 5000:
            volume_signal = 'medium_volume'
        else:
            volume_signal = 'low_volume'
        
        analysis['signals']['volume'] = {
            'signal': volume_signal,
            'total_volume': volume,
            'volume_level': 'active' if volume > 5000 else 'quiet'
        }
        
        # 3. 价格波动率信号
        if akshare_data['opening_price']:
            volatility_pct = (akshare_data['auction_high'] - akshare_data['auction_low']) / akshare_data['opening_price'] * 100
            
            if volatility_pct > 2:
                volatility_signal = 'high_volatility'
            elif volatility_pct > 1:
                volatility_signal = 'medium_volatility'
            else:
                volatility_signal = 'low_volatility'
            
            analysis['signals']['volatility'] = {
                'signal': volatility_signal,
                'volatility_pct': round(volatility_pct, 2),
                'price_range': f"{akshare_data['auction_low']:.2f} - {akshare_data['auction_high']:.2f}"
            }
        
        # 4. 技术指标评分
        if baostock_data and 'technical_score' in baostock_data:
            tech_score = baostock_data['technical_score']
            analysis['technical_analysis'] = {
                'overall_score': tech_score,
                'score_level': '优秀' if tech_score >= 0.8 else '良好' if tech_score >= 0.6 else '一般' if tech_score >= 0.4 else '较差',
                'volume_profile': baostock_data.get('volume_profile', {})
            }
        
        # 5. 综合交易建议
        bullish_signals = sum([
            price_signal in ['bullish', 'strong_bullish'],
            volume_signal in ['high_volume', 'medium_volume'],
            trend_pct > 0.5
        ])
        
        bearish_signals = sum([
            price_signal in ['bearish', 'strong_bearish'],
            trend_pct < -0.5,
            volume > 10000 and trend_pct < 0  # 高成交量下跌
        ])
        
        # 结合技术指标评分调整建议
        if baostock_data and 'technical_score' in baostock_data:
            tech_score = baostock_data['technical_score']
            if tech_score > 0.7:
                bullish_signals += 1
            elif tech_score < 0.3:
                bearish_signals += 1
        
        if bullish_signals >= 2:
            recommendation = 'BUY'
        elif bearish_signals >= 2:
            recommendation = 'SELL'
        else:
            recommendation = 'HOLD'
        
        analysis['recommendation'] = {
            'action': recommendation,
            'confidence': 'high' if max(bullish_signals, bearish_signals) >= 2 else 'low',
            'bullish_signals': bullish_signals,
            'bearish_signals': bearish_signals
        }
        
        # 6. 如果有BaoStock数据，进行交叉验证
        if baostock_data and baostock_data.get('gap_analysis'):
            latest_gap = baostock_data['gap_analysis'][-1] if baostock_data['gap_analysis'] else None
            if latest_gap:
                analysis['gap_validation'] = {
                    'gap_pct': latest_gap['gap_pct'],
                    'consistent_with_auction': abs(latest_gap['gap_pct'] - trend_pct) < 1,
                    'data_source': 'BaoStock'
                }
        
        print(f"✅ {akshare_data['symbol']} 信号分析完成")
        return analysis
    
    def run_comprehensive_analysis(self, stock_symbols):
        """
        运行综合分析
        
        Args:
            stock_symbols (list): 股票代码列表，支持两种格式
                - AKShare格式: ["000001", "000002"]
                - BaoStock格式: ["sh.600000", "sz.000001"]
        """
        print(f"\n🎯 开始综合分析 {len(stock_symbols)} 只股票...")
        print("=" * 60)
        
        results = []
        
        for i, symbol in enumerate(stock_symbols, 1):
            print(f"\n📍 [{i}/{len(stock_symbols)}] 分析股票: {symbol}")
            print("-" * 40)
            
            # 转换股票代码格式
            akshare_symbol = self._convert_to_akshare_format(symbol)
            baostock_symbol = self._convert_to_baostock_format(symbol)
            
            # 获取AKShare数据
            akshare_data = self.get_akshare_auction_data(akshare_symbol)
            
            # 获取BaoStock数据
            baostock_data = None
            if baostock_symbol:
                baostock_data = self.get_baostock_opening_data(baostock_symbol, days=20)  # 增加天数用于技术指标计算
            
            # 分析信号
            if akshare_data:
                analysis = self.analyze_auction_signals(akshare_data, baostock_data)
                
                result = {
                    'symbol': symbol,
                    'akshare_data': akshare_data,
                    'baostock_data': baostock_data,
                    'analysis': analysis
                }
                results.append(result)
                
                # 打印关键信息
                self._print_analysis_summary(result)
            
            # 避免请求过于频繁
            if i < len(stock_symbols):
                time.sleep(1)
        
        # 保存结果
        self._save_results(results)
        
        # 生成总结报告
        self._generate_summary_report(results)
        
        return results
    
    def _convert_to_akshare_format(self, symbol):
        """转换为AKShare格式"""
        if symbol.startswith(('sh.', 'sz.')):
            return symbol.split('.')[1]
        return symbol
    
    def _convert_to_baostock_format(self, symbol):
        """转换为BaoStock格式"""
        if not symbol.startswith(('sh.', 'sz.')):
            if symbol.startswith('6'):
                return f'sh.{symbol}'
            elif symbol.startswith(('0', '3')):
                return f'sz.{symbol}'
        return symbol
    
    def _print_analysis_summary(self, result):
        """打印分析摘要"""
        if not result['analysis']:
            return
        
        analysis = result['analysis']
        akshare_data = result['akshare_data']
        
        print(f"💰 开盘价: {akshare_data['opening_price']:.2f}")
        print(f"📈 竞价趋势: {analysis['signals']['price_trend']['trend_pct']:+.2f}%")
        print(f"📊 成交量: {akshare_data['total_volume']:,} 手")
        
        # 打印技术指标评分
        if 'technical_analysis' in analysis:
            tech = analysis['technical_analysis']
            print(f"📐 技术评分: {tech['overall_score']:.3f} ({tech['score_level']})")
            
            if 'volume_profile' in tech and 'value_area' in tech['volume_profile']:
                print(f"📊 价值区: {tech['volume_profile']['value_area']}")
        
        print(f"🎯 交易建议: {analysis['recommendation']['action']} "
              f"(置信度: {analysis['recommendation']['confidence']})")
        
        if 'gap_validation' in analysis:
            print(f"🔄 缺口验证: {analysis['gap_validation']['gap_pct']:+.2f}% "
                  f"({'一致' if analysis['gap_validation']['consistent_with_auction'] else '不一致'})")
    
    def _save_results(self, results):
        """保存分析结果"""
        filename = f"/Users/yang/auction_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # 转换为可序列化的格式
        serializable_results = []
        for result in results:
            serializable_result = {
                'symbol': result['symbol'],
                'analysis_summary': result['analysis']['recommendation'] if result['analysis'] else None,
                'opening_price': float(result['akshare_data']['opening_price']) if result['akshare_data'] and result['akshare_data']['opening_price'] else None,
                'trend_pct': float(result['akshare_data']['trend_pct']) if result['akshare_data'] else None,
                'total_volume': int(result['akshare_data']['total_volume']) if result['akshare_data'] else None,
                'technical_score': float(result['baostock_data']['technical_score']) if result['baostock_data'] and 'technical_score' in result['baostock_data'] else None
            }
            serializable_results.append(serializable_result)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 分析结果已保存到: {filename}")
    
    def _generate_summary_report(self, results):
        """生成总结报告"""
        print("\n" + "=" * 60)
        print("📋 集合竞价分析总结报告")
        print("=" * 60)
        
        total_stocks = len(results)
        successful_analysis = len([r for r in results if r['analysis']])
        
        print(f"📊 分析股票总数: {total_stocks}")
        print(f"✅ 成功分析数量: {successful_analysis}")
        
        if successful_analysis > 0:
            # 统计交易建议
            recommendations = [r['analysis']['recommendation']['action'] 
                             for r in results if r['analysis']]
            
            buy_count = recommendations.count('BUY')
            sell_count = recommendations.count('SELL')
            hold_count = recommendations.count('HOLD')
            
            print(f"\n🎯 交易建议分布:")
            print(f"  📈 买入建议: {buy_count} 只")
            print(f"  📉 卖出建议: {sell_count} 只")
            print(f"  📊 持有建议: {hold_count} 只")
            
            # 统计技术指标评分
            tech_scores = []
            for r in results:
                if r.get('baostock_data') and 'technical_score' in r['baostock_data']:
                    tech_scores.append(r['baostock_data']['technical_score'])
            
            if tech_scores:
                avg_tech_score = sum(tech_scores) / len(tech_scores)
                print(f"\n📐 平均技术评分: {avg_tech_score:.3f}")
                
                # 技术评分分布
                excellent = len([s for s in tech_scores if s >= 0.8])
                good = len([s for s in tech_scores if 0.6 <= s < 0.8])
                fair = len([s for s in tech_scores if 0.4 <= s < 0.6])
                poor = len([s for s in tech_scores if s < 0.4])
                
                print(f"  优秀(≥0.8): {excellent} 只")
                print(f"  良好(0.6-0.8): {good} 只")
                print(f"  一般(0.4-0.6): {fair} 只")
                print(f"  较差(<0.4): {poor} 只")
            
            # 推荐关注的股票
            high_confidence_buys = [
                r for r in results 
                if r['analysis'] and 
                r['analysis']['recommendation']['action'] == 'BUY' and
                r['analysis']['recommendation']['confidence'] == 'high'
            ]
            
            if high_confidence_buys:
                print(f"\n⭐ 高信心买入建议 ({len(high_confidence_buys)} 只):")
                for result in high_confidence_buys:
                    symbol = result['symbol']
                    opening_price = result['akshare_data']['opening_price']
                    trend = result['akshare_data']['trend_pct']
                    volume = result['akshare_data']['total_volume']
                    tech_score = result['baostock_data']['technical_score'] if result.get('baostock_data') else 'N/A'
                    print(f"  • {symbol}: 开盘{opening_price:.2f}, 趋势{trend:+.2f}%, 量{volume:,}手, 技术评分{tech_score}")
        
        print("\n" + "=" * 60)
        print(f"🔚 分析完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    def __del__(self):
        """析构函数"""
        if self.baostock_logged_in:
            try:
                bs.logout()
                print("👋 BaoStock已登出")
            except:
                pass

def main():
    """主函数 - 演示完整的集合竞价数据分析流程"""
    print("🚀 A股集合竞价数据获取与分析演示")
    print("=" * 60)
    
    # 创建分析器
    analyzer = AuctionDataAnalyzer()
    
    # 测试股票列表（包含不同市场的股票）
    test_stocks = [
        "000001",  # 平安银行 (深交所主板)
        "000002",  # 万科A (深交所主板)
        "600000",  # 浦发银行 (上交所主板)
        "600036",  # 招商银行 (上交所主板)
        "300015",  # 爱尔眼科 (创业板)
    ]
    
    # 运行综合分析
    results = analyzer.run_comprehensive_analysis(test_stocks)
    
    print("\n🎉 演示程序执行完成！")
    print("\n📝 使用说明:")
    print("1. AKShare提供详细的集合竞价过程数据")
    print("2. BaoStock提供稳定的开盘价和历史数据")
    print("3. 程序自动分析竞价信号、计算技术指标并给出交易建议")
    print("4. 技术指标评分综合了均线、RSI、成交量、MACD和布林带等多个维度")
    print("5. 结果已保存为JSON文件供后续分析")
    
    return results

if __name__ == "__main__":
    # 运行演示程序
    main()
