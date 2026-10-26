#!/usr/bin/env python3
# sends dashboard lines to the lumia status screen. lines starting with "# " are drawn in the accent colour.
import socket
import sys
import time

HOST, PORT = "172.16.42.1", 7000


def meminfo():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        m[k] = int(v.split()[0])
    return m


def frame():
    up = float(open("/proc/uptime").read().split()[0])
    load = open("/proc/loadavg").read().split()[:3]
    m = meminfo()
    used = (m["MemTotal"] - m["MemAvailable"]) // 1024
    return [
        "!c",
        "# " + time.strftime("%H:%M:%S"),
        time.strftime("%a %d %b %Y"),
        "",
        "uptime %dh %02dm" % (up // 3600, up % 3600 // 60),
        "load   " + " ".join(load),
        "mem    %d / %d mib" % (used, m["MemTotal"] // 1024),
    ]


def main():
    s = socket.create_connection((HOST, PORT), timeout=5)
    if len(sys.argv) > 1:
        s.sendall(("\n".join(sys.argv[1:]) + "\n").encode())
        return
    while True:
        s.sendall(("\n".join(frame()) + "\n").encode())
        time.sleep(2)


if __name__ == "__main__":
    main()
