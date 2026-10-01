"""
Run Backtest & Pattern Memory Compiler
Usage: python run_backtest.py
Generates 3-year historical datasets, tests all patterns, and builds the pattern memory storage.
"""
import asyncio
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtesting.generate_backtested_data import run_full_3year_generation
from backtesting.backtest_engine import BacktestEngine
from backtesting.backtest_config import backtest_config


async def main():
    print("="*75)
    print("  CRYPTOINTEL 3-YEAR BACKTEST & PATTERN MEMORY SYSTEM")
    print("="*75)
    
    # 1. Generate historical data & evaluate patterns
    summary = await run_full_3year_generation()
    
    # 2. Run Backtest Analytics
    engine = BacktestEngine(backtest_config.BACKTEST_DB_PATH, backtest_config.PATTERN_MEMORY_DB_PATH)
    overall = engine.get_overall_summary()
    session_stats = engine.get_session_analytics()
    top_patterns = engine.get_pattern_leaderboard(limit=12)
    
    # 3. Print Comprehensive Report
    print("\n" + "="*75)
    print("  3-YEAR BACKTEST PERFORMANCE SUMMARY (1:3 RISK-TO-REWARD)")
    print("="*75)
    print(f"  Historical Range:       {overall['years_tested']} Years ({overall['timeframe']} timeframe)")
    print(f"  Total Bars Analyzed:    {overall['total_candles_analyzed']:,} hourly candles")
    print(f"  Total Trades Tested:    {overall['total_trades']:,}")
    print(f"  Winning Trades:         {overall['winning_trades']:,} ({overall['win_rate_pct']} Win Rate)")
    print(f"  Losing Trades:          {overall['losing_trades']:,}")
    print(f"  Risk:Reward Ratio:      {overall['risk_reward_ratio']} (Stop: {overall['stop_loss_pct']}, TP: {overall['take_profit_pct']})")
    print(f"  Profit Factor:          {overall['profit_factor']}")
    print(f"  Total Realized P&L:     +{overall['total_pnl_pct']}%")
    print(f"  Max Strategy Drawdown:  {overall['max_drawdown_pct']}%")
    print(f"  Sharpe Ratio:           {overall['sharpe_ratio']}")
    
    print("\n" + "-"*75)
    print("  MARKET SESSION BREAKDOWN")
    print("-"*75)
    print(f"  {'Session':<24} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL':<10} | {'Total PnL'}")
    print("  " + "-"*70)
    for s in session_stats:
        print(f"  {s['session']:<24} | {s['total_trades']:<8} | {s['win_rate']*100:>6.1f}%   | {s['avg_pnl_pct']:>7.2f}%  | +{s['total_pnl_pct']}%")
        
    print("\n" + "-"*75)
    print("  TOP PATTERNS LEADERBOARD & PATTERN MEMORY AUTO-APPLY RULES")
    print("-"*75)
    print(f"  {'Pattern':<22} | {'Session':<20} | {'Samples':<8} | {'Win Rate':<10} | {'Action'}")
    print("  " + "-"*70)
    for p in top_patterns:
        rec = p.get('recommendation', 'CONFIRMATION_REQUIRED')
        status_tag = "[AUTO-APPLY]" if rec == 'AUTO_APPLY' else ("[FILTER]" if rec == 'FILTER_OUT' else "[CONFIRM]")
        print(f"  {p['pattern_name']:<22} | {p['session']:<20} | {p['total_occurrences']:<8} | {p['win_rate']*100:>6.1f}%   | {status_tag}")

    print("\n" + "="*75)
    print("  [SUCCESS] 3-Year Backtest Data & Pattern Memory Storage Ready!")
    print(f"  Database Files:")
    print(f"    Raw Data:       {backtest_config.BACKTEST_DB_PATH}")
    print(f"    Pattern Memory: {backtest_config.PATTERN_MEMORY_DB_PATH}")
    print("="*75 + "\n")


if __name__ == '__main__':
    asyncio.run(main())
