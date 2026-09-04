#!/usr/bin/env python3
import json,sys,argparse
from datetime import datetime

def load_positions(json_input):
    json_input = json_input.strip()
    if json_input.startswith("[") or json_input.startswith("{"):
        return json.loads(json_input)
    with open(json_input, encoding="utf-8") as f:
        return json.load(f)

def diagnose_portfolio(positions,total_capital=100000):
    if not isinstance(positions,list): positions=positions.get('positions',[positions])
    total_value=0; positions_detail=[]; sector_map={}
    for p in positions:
        symbol=p.get('symbol','')
        shares=p.get('shares',0)
        entry_price=p.get('entry_price',0)
        current_price=p.get('current_price',entry_price)
        sector=p.get('sector','unknown')
        stop_loss=p.get('stop_loss')
        target_1=p.get('target_1')
        value=shares*current_price
        cost=shares*entry_price
        pnl=value-cost
        pnl_pct=(pnl/cost*100) if cost>0 else 0
        position_pct=(value/total_capital*100) if total_capital>0 else 0
        risk_flags=[]
        if position_pct>20: risk_flags.append('仓位过重')
        if stop_loss and current_price<stop_loss: risk_flags.append('已跌破止损')
        if pnl_pct<-10: risk_flags.append('亏损超10%')
        if pnl_pct>30: risk_flags.append('盈利超30%，考虑移动止损')
        positions_detail.append({'symbol':symbol,'shares':shares,'entry_price':entry_price,'current_price':current_price,'value':round(value,2),'cost':round(cost,2),'pnl':round(pnl,2),'pnl_pct':round(pnl_pct,2),'position_pct':round(position_pct,2),'sector':sector,'stop_loss':stop_loss,'target_1':target_1,'risk_flags':risk_flags})
        total_value+=value
        sector_map[sector]=sector_map.get(sector,0)+value
    total_cost=sum(x['cost'] for x in positions_detail)
    total_pnl=total_value-total_cost
    total_pnl_pct=(total_pnl/total_cost*100) if total_cost>0 else 0
    cash=total_capital-total_value
    cash_pct=(cash/total_capital*100) if total_capital>0 else 0
    sector_summary=[]
    for sec,val in sorted(sector_map.items(),key=lambda x:-x[1]):
        pct=(val/total_value*100) if total_value>0 else 0
        sector_summary.append({'sector':sec,'value':round(val,2),'pct':round(pct,1)})
    risk_score=50
    if cash_pct<10: risk_score-=15
    elif cash_pct<20: risk_score-=5
    max_sector_pct=max((s['pct'] for s in sector_summary),default=0)
    if max_sector_pct>40: risk_score-=15
    elif max_sector_pct>30: risk_score-=5
    max_single_pct=max((x['position_pct'] for x in positions_detail),default=0)
    if max_single_pct>20: risk_score-=10
    broken_stops=sum(1 for x in positions_detail if x['stop_loss'] and x['current_price']<x['stop_loss'])
    risk_score-=broken_stops*15
    big_losses=sum(1 for x in positions_detail if x['pnl_pct']<-10)
    risk_score-=big_losses*5
    risk_score=max(0,min(100,risk_score))
    risk_level='低' if risk_score>=70 else ('中' if risk_score>=40 else '高')
    suggestions=[]
    if cash_pct<10: suggestions.append('现金不足，建议减仓或暂停新开仓')
    if max_sector_pct>40: suggestions.append('行业集中度过高，建议分散')
    if max_single_pct>20: suggestions.append('单股仓位过重，建议降低')
    if broken_stops>0: suggestions.append('有 '+str(broken_stops)+' 只持仓已跌破止损，建议止损或加仓摊薄')
    if big_losses>0: suggestions.append('有 '+str(big_losses)+' 只持仓亏损超10%，需重新评估')
    for x in positions_detail:
        if x['pnl_pct']>20 and x['stop_loss']:
            suggestions.append(x['symbol']+' 盈利'+str(round(x['pnl_pct'],1))+'%，建议上移止损至成本价')
    return {'total_capital':total_capital,'total_value':round(total_value,2),'total_cost':round(total_cost,2),'total_pnl':round(total_pnl,2),'total_pnl_pct':round(total_pnl_pct,2),'cash':round(cash,2),'cash_pct':round(cash_pct,1),'position_count':len(positions_detail),'risk_score':risk_score,'risk_level':risk_level,'sector_summary':sector_summary,'positions':positions_detail,'suggestions':suggestions}

def main():
    p=argparse.ArgumentParser(description='Portfolio Diagnose')
    p.add_argument('--positions-json',required=True)
    p.add_argument('--capital',type=float,default=100000.0)
    p.add_argument('--output',default=None)
    a=p.parse_args()
    positions=load_positions(a.positions_json)
    result=diagnose_portfolio(positions,a.capital)
    out=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:
        with open(a.output,'w',encoding='utf-8') as f: f.write(out)
        print('已保存: '+a.output,file=sys.stderr)
    else: print(out)

if __name__=='__main__': main()
