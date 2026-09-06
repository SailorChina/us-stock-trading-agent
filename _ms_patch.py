import ast
path = 'scripts/market_sentiment.py'
with open(path) as f:
    c = f.read()
# Add threading
c = c.replace('import json, sys, argparse, urllib.request, time, logging', 'import json, sys, argparse, urllib.request, time, logging, threading')
NL=chr(10); DQ=chr(34); ST=chr(42); LB=chr(91); RB=chr(93)
h=NL+NL
h+='def _futu_connect(fn,'+ST+'args,timeout=3):'+NL
h+='    r=[None];e=[None]'+NL
h+='    def _run():'+NL
h+='        try:'+NL
h+='            from futu import OpenQuoteContext,RET_OK'+NL
h+='            ctx=OpenQuoteContext();ctx.open();f2=getattr(ctx,fn);r[0]=f2(*args)'+NL
h+='        except Exception as ex:e[0]=ex'+NL
h+='    t=threading.Thread(target=_run,daemon=True);t.start();t.join(timeout=timeout)'+NL
h+='    if t.is_alive():return None'+NL
h+='    if e[0]:return None'+NL
h+='    return r[0]'+NL+NL
ip=c.find(NL,c.find('from cache_util import retry_call'))+1
c=c[:ip]+h+c[ip:]
# Replace patterns - use LB/RB for brackets
c=c.replace('with OpenQuoteContext() as ctx:'+NL+'            ret, data = ctx.get_stock_quote(['+DQ+'US.VIX'+DQ+'])', '_result=_futu_connect('+DQ+'get_stock_quote'+DQ+', ['+DQ+'US.VIX'+DQ+'],timeout=3)'+NL+'            if _result is not None:'+NL+'                ret, data = _result')
c=c.replace('with OpenQuoteContext() as ctx:'+NL+'            ret, data = ctx.get_stock_quote(['+DQ+'US.DJI'+DQ+', '+DQ+'US.IXIC'+DQ+', '+DQ+'US.SPX'+DQ+'])', '_result=_futu_connect('+DQ+'get_stock_quote'+DQ+', ['+DQ+'US.DJI'+DQ+', '+DQ+'US.IXIC'+DQ+', '+DQ+'US.SPX'+DQ+'],timeout=3)'+NL+'            if _result is not None:'+NL+'                ret, data = _result')
c=c.replace('with OpenQuoteContext() as ctx:'+NL+'            ret, data = ctx.get_stock_quote(symbols)', '_result=_futu_connect('+DQ+'get_stock_quote'+DQ+', symbols,timeout=3)'+NL+'            if _result is not None:'+NL+'                ret, data = _result')
with open(path,'w') as f:
    f.write(c)
ast.parse(c)
print('OK')
print('threading:', 'import threading' in c)
print('_futu_connect:', c.count('_futu_connect('))
print('OQC remaining:', c.count('OpenQuoteContext'))
