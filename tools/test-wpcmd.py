#!/usr/bin/env python3
import socket
import unittest

from wpcmd import DONT, DO, IAC, SB, SE, WILL, WONT, TelnetParser, read


class Socket:
    def __init__(self, chunks=()):
        self.sent = bytearray()
        self.chunks = iter(chunks)

    def sendall(self, data):
        self.sent.extend(data)

    def settimeout(self, timeout):
        pass

    def recv(self, size):
        chunk = next(self.chunks, b'')
        if chunk is None:
            raise socket.timeout
        return chunk


class ParserTests(unittest.TestCase):
    wire = (b'hello' + bytes((IAC, DO, 1)) + b'/' + bytes((IAC, WILL, 3, IAC, DONT, 4, IAC, WONT, 5)) +
            bytes((IAC, SB, 24)) + b'private subnegotiation' + bytes((IAC, IAC)) + b'tail' +
            bytes((IAC, SE, IAC, 241, IAC, IAC)) + b'done')
    expected = b'hello/\xffdone'
    replies = bytes((IAC, WONT, 1, IAC, DONT, 3))

    def check_chunks(self, chunks):
        sock = Socket()
        parser = TelnetParser(sock)
        output = b''.join(parser.feed(chunk) for chunk in chunks)
        self.assertEqual(output, self.expected)
        self.assertEqual(sock.sent, self.replies)
        self.assertEqual(parser.state, 'data')

    def test_every_two_and_three_part_split(self):
        for first in range(len(self.wire) + 1):
            for second in range(first, len(self.wire) + 1):
                with self.subTest(first=first, second=second):
                    self.check_chunks((self.wire[:first], self.wire[first:second], self.wire[second:]))

    def test_one_byte_at_a_time(self):
        self.check_chunks(bytes((byte,)) for byte in self.wire)

    def test_state_survives_read_timeout(self):
        sock = Socket((b'one' + bytes((IAC,)), None, bytes((DO,)), None,
                       bytes((1, IAC, SB, 24)) + b'hidden', None,
                       bytes((IAC,)), None, bytes((SE,)) + b'two', b''))
        parser = TelnetParser(sock)
        outputs = [read(sock, 0.01, parser) for _ in range(5)]
        self.assertEqual(b''.join(outputs), b'onetwo')
        self.assertEqual(sock.sent, bytes((IAC, WONT, 1)))

    def test_incomplete_sequence_does_not_leak(self):
        for tail in (bytes((IAC,)), bytes((IAC, DO)), bytes((IAC, SB, 24)) + b'hidden'):
            parser = TelnetParser(Socket())
            self.assertEqual(parser.feed(b'visible' + tail), b'visible')

    def test_connections_do_not_share_state(self):
        first, second = TelnetParser(Socket()), TelnetParser(Socket())
        self.assertEqual(first.feed(bytes((IAC,))), b'')
        self.assertEqual(second.feed(b'plain'), b'plain')
        self.assertEqual(first.feed(bytes((IAC,))), bytes((IAC,)))

    def test_negative_negotiation_does_not_loop(self):
        sock = Socket()
        parser = TelnetParser(sock)
        for byte in bytes((IAC, DONT, 1, IAC, WONT, 3)) * 10:
            self.assertEqual(parser.feed(bytes((byte,))), b'')
        self.assertEqual(sock.sent, b'')


if __name__ == '__main__':
    unittest.main()
