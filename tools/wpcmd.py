import os, socket, sys, time

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

def strip(s, data):
    out, i = bytearray(), 0
    while i < len(data):
        b = data[i]
        if b == IAC and i + 1 < len(data):
            c = data[i + 1]
            if c in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                s.sendall(bytes([IAC, WONT if c == DO else DONT, data[i + 2]]))
                i += 3
                continue
            i += 2
            continue
        out.append(b)
        i += 1
    return bytes(out)

def read(s, wait):
    s.settimeout(wait)
    buf = b""
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
            buf += strip(s, d)
            s.settimeout(wait)
    except socket.timeout:
        pass
    return buf

host, cmds = sys.argv[1], sys.argv[2:]
s = socket.create_connection((host, 23), timeout=8)
print(read(s, 2).decode("utf-8", "replace"), end="")
for c in cmds:
    s.sendall(c.encode() + b"\r\n")
    print(read(s, float(os.environ.get("WPWAIT", "3"))).decode("utf-8", "replace"), end="")
s.close()
