import ast

path = 'scripts/market_sentiment.py'
with open(path, 'r') as f:
    content = f.read()

content = content.replace('import json, sys, argparse, time', 'import json, sys, argparse, time, threading')

NL = chr(10)
LB = chr(91)
RB = chr(93)
DQ = chr(34)

helper = NL + NL
helper += 'def _futu_connect(func_name, *args, timeout=3):' + NL
helper += '    result = [None]' + NL
helper += '    error = [None]' + NL
helper += '    def _run():' + NL
helper += '        try:' + NL
helper += '            from futu import OpenQuoteContext, RET_OK' + NL
helper += '            ctx = OpenQuoteContext()' + NL
helper += '            ctx.open()' + NL
helper += '            func = getattr(ctx, func_name)' + NL
helper += '            ret, data = func(*args)' + NL
helper += '            result[0] = (ret, data)' + NL
helper += '        except Exception as e:' + NL
helper += '            error[0] = e' + NL
helper += '    t = threading.Thread(target=_run, daemon=True)' + NL
helper += '    t.start()' + NL
helper += '    t.join(timeout=timeout)' + NL
helper += '    if t.is_alive():' + NL
helper += '        return None' + NL
helper += '    if error[0]:' + NL
helper += '        return None' + NL
helper += '    return result[0]' + NL + NL

insert_pos = content.find(NL, content.find('from cache_util import retry_call')) + 1
content = content[:insert_pos] + helper + content[insert_pos:]

# Build the three replacements using chr() for brackets
def make_replace(old_ctx, old_call, new_ctx, new_call):
    return content.replace(old_ctx, new_ctx).replace(old_call, new_call)

# Pattern 1
old1a = 'with OpenQuoteContext() as ctx:' + NL
old1b = '            ret, data = ctx.get_stock_quote(' + LB + DQ + 'US.VIX' + DQ + RB + ')'
new1a = '_result = _futu_connect(' + DQ + 'get_stock_quote' + DQ + ', ' + LB + DQ + 'US.VIX' + DQ + RB + ', timeout=3)' + NL
new1b = '            if _result is not None:' + NL
new1c = '                ret, data = _result'
content = content.replace(old1a + old1b, new1a + new1b + NL + ' ' * 12 + new1c)

# Pattern 2
old2b = '            ret, data = ctx.get_stock_quote(' + LB + DQ + 'US.DJI' + DQ + ', ' + DQ + 'US.IXIC' + DQ + ', ' + DQ + 'US.SPX' + DQ + RB + ')'
new2a = '_result = _futu_connect(' + DQ + 'get_stock_quote' + DQ + ', ' + LB + DQ + 'US.DJI' + DQ + ', ' + DQ + 'US.IXIC' + DQ + ', ' + DQ + 'US.SPX' + DQ + RB + ', timeout=3)' + NL
content = content.replace(old1a + old2b, new2a + new1b + NL + ' ' * 12 + new1c)

# Pattern 3
old3b = '            ret, data = ctx.get_stock_quote(symbols)'
new3a = '_result = _futu_connect(' + DQ + 'get_stock_quote' + DQ + ', symbols, timeout=3)' + NL
content = content.replace(old1a + old3b, new3a + new1b + NL + ' ' * 12 + new1c)

with open(path, 'w') as f:
    f.write(content)

ast.parse(content)
print('OK')
print('threading:', 'import threading' in content)
print('_futu_connect:', content.count('_futu_connect('))
print('OpenQuoteContext remaining:', content.count('OpenQuoteContext'))
