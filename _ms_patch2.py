import ast
path = chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)+chr(47)+chr(109)+chr(97)+chr(114)+chr(107)+chr(101)+chr(116)+chr(95)+chr(115)+chr(101)+chr(110)+chr(116)+chr(105)+chr(109)+chr(101)+chr(110)+chr(46)+chr(112)+chr(121))
with open(path) as f:
    c = f.read()
NL=chr(10); DQ=chr(34)
# The patterns have blank lines between with and ret
# Pattern 1: US.DJI
c=c.replace('        with OpenQuoteContext() as ctx:'+NL+NL+'            ret, data = ctx.get_stock_quote(['+DQ+'US.DJI'+DQ+', '+DQ+'US.IXIC'+DQ+', '+DQ+'US.SPX'+DQ+'])', '_result=_futu_connect('+DQ+'get_stock_quote'+DQ+', ['+DQ+'US.DJI'+DQ+', '+DQ+'US.IXIC'+DQ+', '+DQ+'US.SPX'+DQ+'],timeout=3)'+NL+NL+'            if _result is not None:'+NL+'                ret, data = _result')
# Pattern 2: US.VIX
c=c.replace('        with OpenQuoteContext() as ctx:'+NL+NL+'            ret, data = ctx.get_stock_quote(['+DQ+'US.VIX'+DQ+'])', '_result=_futu_connect('+DQ+'get_stock_quote'+DQ+', ['+DQ+'US.VIX'+DQ+'],timeout=3)'+NL+NL+'            if _result is not None:'+NL+'                ret, data = _result')
# Pattern 3: symbols
c=c.replace('        with OpenQuoteContext() as ctx:'+NL+NL+'            ret, data = ctx.get_stock_quote(symbols)', '_result=_futu_connect('+DQ+'get_stock_quote'+DQ+', symbols,timeout=3)'+NL+NL+'            if _result is not None:'+NL+'                ret, data = _result')
with open(path,'w') as f:
    f.write(c)
ast.parse(c)
print('OK')
print('OQC remaining:', c.count('OpenQuoteContext() as ctx'))
print('_futu_connect calls:', c.count('_futu_connect('))
