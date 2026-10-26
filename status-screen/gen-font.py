import re, sys

src = open(sys.argv[1]).read()
body = src.split("FONTDATAMAX, 0 }, {", 1)[1]
body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
vals = re.findall(r"0x[0-9a-fA-F]{2}", body)[:4096]
assert len(vals) == 4096, len(vals)
print("static const unsigned char font8x16[4096] = {")
for i in range(0, 4096, 16):
    print("\t" + ", ".join(vals[i:i + 16]) + ",")
print("};")
