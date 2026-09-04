#!/usr/bin/env python3
import json,sys,argparse,os,subprocess,re
from datetime import datetime
try:
    from futu import OpenQuoteContext, RET_OK, OpenSecTradeContext, TrdEnv, OrderType, TrdSide
    FUTU_OK=True
except ImportError:
    FUTU_OK=False

AUDIT_LOG=os.path.expanduser('~/.futu_trade_audit.jsonl')

def log_trade(action,symbol,shares,price,status='simulated'):
    entry={'timestamp':datetime.now().isoformat(),'action':action,'symbol':symbol,'shares':shares,'price':price,'status':status}
    with open(AUDIT_LOG,'a',encoding='utf-8') as f: f.write(json.dumps(entry,ensure_ascii=False)+chr(10))
    return entry

def place_order(symbol,direction,shares,price,trd_env='SIMULATE',dry_run=False):
    if dry_run:
        return {'status':'dry_run','symbol':symbol,'direction':direction,'shares':shares,'price':price,'note':'Paper trading - no order placed'}
    if not FUTU_OK: return {'status':'error','error':'futu-api not available'}
    try:
        env=TrdEnv.SIMULATE if trd_env.upper()=='SIMULATE' else TrdEnv.REAL
        with OpenSecTradeContext() as ctx:
            ret,data=ctx.place_order(price=price,qty=shares,code=symbol,trd_side=TrdSide.BUY if direction.lower()=="buy" else TrdSide.SELL,order_type=OrderType.LIMIT_IF_TOUCHED,trd_env=env)
            if ret==RET_OK:
                oid=data.get('order_id','') if data else ''
                log_trade(direction,symbol,shares,price,oid,'placed')
                return {'status':'ok','order_id':oid,'data':data}
            log_trade(direction,symbol,shares,price,status='failed')
            return {'status':'error','error':str(data)}
    except Exception as e:
        log_trade(direction,symbol,shares,price,status='error')
        return {'status':'error','error':str(e)}

def auto_trade_from_signal(signal_file,trd_env='SIMULATE'):
    with open(signal_file,encoding='utf-8') as f: signal=json.load(f)
    results=[]
    for item in signal.get('signals',[]):
        action=item.get('action'); symbol=item.get('symbol'); shares=item.get('shares',100); price=item.get('price',0)
        if not symbol or not action: continue
        print('执行: '+action+' '+str(shares)+'x '+symbol+' @ '+str(price),file=sys.stderr)
        results.append({'signal':item,'result':place_order(symbol,action.lower(),shares,price,trd_env=trd_env)})
    return {'results':results,'executed_at':datetime.now().isoformat()}

def generate_signal_from_analysis(analysis_result, max_position_pct=0.15):
    """Generate trade signals from structured analysis result (v2 format)."""
    signals = []
    tech = analysis_result.get('modules', {}).get('tech', {})
    if tech.get('status') != 'ok':
        return signals
    # Try structured data first
    data = tech.get('data', {})
    if data and isinstance(data, dict):
        rating = data.get('rating', '')
        trade_plan = data.get('trade_plan', {})
        resonance = data.get('resonance', {})
        if rating in ('Overweight', 'Buy', 'Strong Buy') or '买入' in rating:
            signals.append({
                'action': 'BUY',
                'symbol': analysis_result.get('symbol', ''),
                'entry_price': trade_plan.get('entry_zone', 0),
                'stop_loss': trade_plan.get('stop_loss', 0),
                'target_1': trade_plan.get('target_1', 0),
                'target_2': trade_plan.get('target_2', 0),
                'risk_reward': trade_plan.get('risk_reward', 0),
                'position_pct': min(trade_plan.get('position_size_pct', max_position_pct), max_position_pct),
                'entry_type': 'VWAP回调' if trade_plan.get('entry_zone') else '现价',
                'reason': f"{rating} 得分{data.get('score', '')} 共振{resonance.get('alignment', '')}"
            })
        elif rating in ('Underweight', 'Sell', 'Strong Sell') or '卖出' in rating:
            signals.append({
                'action': 'SELL',
                'symbol': analysis_result.get('symbol', ''),
                'reason': f"{rating} 技术面卖出信号"
            })
    else:
        # Fallback: parse raw text (v1 format)
        import re
        raw = tech.get('raw', '')
        if 'Overweight' in raw or '买入' in raw:
            m = re.search(r'建议入场[:：]\s*([\d.]+)', raw)
            entry = float(m.group(1)) if m else 0
            m2 = re.search(r'止损位[:：]\s*([\d.]+)', raw)
            stop = float(m2.group(1)) if m2 else 0
            signals.append({'action': 'BUY', 'symbol': analysis_result.get('symbol', ''),
                           'entry_price': entry, 'stop_loss': stop,
                           'reason': '技术面买入信号', 'max_position_pct': max_position_pct})
        elif '卖出' in raw or 'Underweight' in raw:
            signals.append({'action': 'SELL', 'symbol': analysis_result.get('symbol', ''),
                           'reason': '技术面卖出信号'})
    return signals

def main():
    p=argparse.ArgumentParser(description='Auto Trader')
    p.add_argument('--action',default='analyze',choices=['analyze','order','signal-to-order','audit'])
    p.add_argument('--symbol')
    p.add_argument('--entry',type=float)
    p.add_argument('--shares',type=int,default=100)
    p.add_argument('--trd-env',default='SIMULATE',choices=['SIMULATE','REAL'])
    p.add_argument('--dry-run',action='store_true',help='Paper trading mode')
    p.add_argument('--signal-file')
    p.add_argument('--analysis-file')
    p.add_argument('--output',default=None)
    a=p.parse_args()
    if a.action=='order':
        if not a.symbol or not a.entry: print('需要 --symbol 和 --entry',file=sys.stderr); sys.exit(1)
        r=place_order(a.symbol,'buy',a.shares,a.entry,trd_env=a.trd_env,dry_run=a.dry_run)
        print(json.dumps(r,ensure_ascii=False,indent=2))
    elif a.action=='analyze':
        if not a.analysis_file: print('需要 --analysis-file',file=sys.stderr); sys.exit(1)
        with open(os.path.abspath(a.analysis_file),encoding='utf-8') as f: analysis=json.load(f)
        signals=generate_signal_from_analysis(analysis)
        out={'signals':signals,'generated_at':datetime.now().isoformat()}
        if a.output:
            with open(a.output,'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
        else: print(json.dumps(out,ensure_ascii=False,indent=2))
    elif a.action=='signal-to-order':
        if not a.signal_file: print('需要 --signal-file',file=sys.stderr); sys.exit(1)
        r=auto_trade_from_signal(a.signal_file,trd_env=a.trd_env,dry_run=a.dry_run)
        print(json.dumps(r,ensure_ascii=False,indent=2))
    elif a.action=='audit':
        if os.path.exists(AUDIT_LOG):
            with open(AUDIT_LOG,encoding='utf-8') as f: lines=f.readlines()
            print(json.dumps({'count':len(lines),'trades':[json.loads(l) for l in lines[-20:]]},ensure_ascii=False,indent=2))
        else: print(json.dumps({'count':0,'trades':[]}))

if __name__=='__main__': main()
