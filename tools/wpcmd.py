import os
import socket
import sys

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240


class TelnetParser:
    def __init__(self, sock):
        self.sock = sock
        self.state = 'data'
        self.command = None

    def feed(self, data):
        out = bytearray()
        for byte in data:
            if self.state == 'data':
                if byte == IAC:
                    self.state = 'iac'
                else:
                    out.append(byte)
            elif self.state == 'iac':
                if byte == IAC:
                    out.append(IAC)
                    self.state = 'data'
                elif byte in (DO, DONT, WILL, WONT):
                    self.command = byte
                    self.state = 'option'
                elif byte == SB:
                    self.state = 'subnegotiation'
                else:
                    self.state = 'data'
            elif self.state == 'option':
                if self.command in (DO, WILL):
                    reply = WONT if self.command == DO else DONT
                    self.sock.sendall(bytes((IAC, reply, byte)))
                self.command = None
                self.state = 'data'
            elif self.state == 'subnegotiation':
                if byte == IAC:
                    self.state = 'subnegotiation-iac'
            elif self.state == 'subnegotiation-iac':
                self.state = 'data' if byte == SE else 'subnegotiation'
        return bytes(out)


def read(sock, wait, parser):
    sock.settimeout(wait)
    buf = bytearray()
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buf.extend(parser.feed(data))
    except socket.timeout:
        pass
    return bytes(buf)


def main():
    host, cmds = sys.argv[1], sys.argv[2:]
    with socket.create_connection((host, 23), timeout=8) as sock:
        parser = TelnetParser(sock)
        print(read(sock, 2, parser).decode('utf-8', 'replace'), end='')
        for cmd in cmds:
            sock.sendall(cmd.encode() + b'\r\n')
            data = read(sock, float(os.environ.get('WPWAIT', '3')), parser)
            print(data.decode('utf-8', 'replace'), end='')


if __name__ == '__main__':
    main()
