with open("scripts/tech_engine.py", "r") as f: content = f.read()
content = content.replace("import json, sys, os, time", "import json, sys, os, time, threading")
NL = chr(10)
helper = NL+NL+"def _with_futu_context(func, *args, timeout=5):"+NL+"    result = [None]"+NL+"    error = [None]"+NL+"    def _run():"+NL+"        try:"+NL+"            result[0] = func(*args)"+NL+"        except Exception as e:"+NL+"            error[0] = e"+NL+"    t = threading.Thread(target=_run, daemon=True)"+NL+"    t.start()"+NL+"    t.join(timeout=timeout)"+NL+"    if t.is_alive():"+NL+"        print(f\"[tech_engine] timeout\", file=sys.stderr)"+NL+"        return None"+NL+"    if error[0]:"+NL+"        raise error[0]"+NL+"    return result[0]"+NL+NL
content = content.replace("from cache_util import retry_call", "from cache_util import retry_call" + helper)
