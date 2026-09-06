import base64,sys
data=open(sys.argv[1]).read()
print(base64.b64encode(data.encode()).decode())
