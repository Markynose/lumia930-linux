#!/usr/bin/env python3
"""Side-effect-free host helper regression tests: all privileged/remote tools mocked."""
import os
from pathlib import Path
import pty
import select
import signal
import time
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class HostUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.trace = self.base / "trace"
        self.sys = self.base / "net" / "usb0"
        self.sys.mkdir(parents=True)
        (self.sys / "address").write_text("02:93:00:00:00:02\n")
        self.usb = self.base / "lumia-usb"
        # Substitute only the sysfs fixture path, never the real host interface.
        source = (ROOT / "alpine/host/lumia-usb").read_text()
        self.usb.write_text(source.replace("/sys/class/net", str(self.base / "net")))
        self.usb.chmod(0o755)
        self.save = ROOT / "alpine/persistence/host-save"
        self.env = dict(os.environ, PATH=str(self.bin), TERM="xterm", MOCK_UID="0",
                        TRACE=str(self.trace), TMPDIR=str(self.base))
        for name in ("awk", "cat", "rm", "dirname", "basename", "sleep"):
            os.symlink(shutil.which(name), self.bin / name)
        mock = self.bin / "mock"
        mock.write_text("""#!/bin/sh
name=${0##*/}
printf '%s %s\\n' "$name" "$*" >> "$TRACE"
case "$name" in
 id) echo "$MOCK_UID";;
 date) echo '2026-10-27 12:00:00';;
 ip) case "$*" in '-4 route get 1.1.1.1') echo '1.1.1.1 dev eth0';; esac;;
 sysctl) case "$1" in -n) echo 1;; esac;;
 mktemp) printf '%s/rules\\n' "$TMPDIR"; : > "$TMPDIR/rules";;
 nmcli|dhcpcd) sleep "${MOCK_DELAY:-0.25}";;
 ssh) printf 'remote output\\n'; printf 'remote diagnostic\\n' >&2;;
esac
if [ "${FAIL:-}" = "$name" ]; then
 printf 'mock %s failure\\n' "$name" >&2
 exit 37
fi
exit 0
""")
        mock.chmod(0o755)
        for name in ("id", "date", "ip", "sysctl", "mktemp", "nmcli", "dhcpcd", "ssh", "nft", "doas", "sudo"):
            os.symlink(mock, self.bin / name)

    def run_helper(self, save=False, args=(), **env):
        return subprocess.run(["/bin/sh", str(self.save if save else self.usb), *args],
                              env=dict(self.env, **env), capture_output=True, timeout=5)

    def test_network_plain(self):
        result = self.run_helper(args=("--network",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"temporary sharing: usb0 -> eth0", result.stdout)
        self.assertIn(b"releasing usb0", result.stderr)
        self.assertNotIn(b"\r", result.stderr)
        self.assertNotIn(b"\x1b", result.stderr)
        self.assertFalse((self.base / "rules").exists())
        trace = self.trace.read_text()
        self.assertIn("nft -c -f ", trace)
        self.assertIn("ip addr replace 172.16.42.2/24 dev usb0", trace)

    def test_missing_phone_stays_immediate(self):
        (self.sys / "address").write_text("not-the-phone\n")
        result = self.run_helper(args=("--network",))
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"phone USB network not found", result.stderr)
        self.assertNotIn("ip ", self.trace.read_text())

    def test_network_failure_keeps_exit_and_cleanup(self):
        result = self.run_helper(args=("--network",), FAIL="nft")
        self.assertEqual(result.returncode, 37)
        self.assertIn(b"mock nft failure", result.stderr)
        self.assertFalse((self.base / "rules").exists())
        self.assertNotIn("ip addr", self.trace.read_text())

    def test_disconnect_remains_best_effort(self):
        result = self.run_helper(args=("--network",), FAIL="nmcli")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"temporary sharing:", result.stdout)

    def test_dhcpcd_fallback(self):
        (self.bin / "nmcli").unlink()
        result = self.run_helper(args=("--network",))
        self.assertEqual(result.returncode, 0)
        self.assertIn("dhcpcd -x usb0", self.trace.read_text())

    def test_interruption_cleans_rules_and_spinner(self):
        master, slave = pty.openpty()
        proc = subprocess.Popen(["/bin/sh", str(self.usb), "--network"],
                                env=dict(self.env, MOCK_DELAY="2"),
                                stdout=subprocess.DEVNULL, stderr=slave,
                                start_new_session=True)
        os.close(slave)
        data = b""
        try:
            deadline = time.monotonic() + 5
            while b"releasing usb0" not in data and time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    data += os.read(master, 4096)
            self.assertIn(b"releasing usb0", data)
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=3)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse((self.base / "rules").exists())
            # All writers close the PTY when the animation has been reaped.
            while select.select([master], [], [], 1)[0]:
                try:
                    if not os.read(master, 4096):
                        break
                except OSError:
                    break
            else:
                self.fail("animation still holds terminal open after cancellation")
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            os.close(master)

    def test_normal_user_and_sudo_fallback(self):
        for escalator in ("doas", "sudo"):
            if escalator == "sudo":
                (self.bin / "doas").unlink()
            result = self.run_helper(MOCK_UID="1000")
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"remote diagnostic", result.stderr)
            self.assertIn(b"USB network and clock ready", result.stdout)
            self.assertIn(escalator + " -n ", self.trace.read_text())

    def test_escalation_failure_stops_before_ssh(self):
        result = self.run_helper(MOCK_UID="1000", FAIL="doas")
        self.assertEqual(result.returncode, 37)
        self.assertNotIn("ssh ", self.trace.read_text())

    def test_clock_failure_does_not_claim_ready(self):
        result = self.run_helper(MOCK_UID="1000", FAIL="ssh")
        self.assertEqual(result.returncode, 37)
        self.assertNotIn(b"clock ready", result.stdout)

    def test_save_streams_output_and_status(self):
        for failure, code in (("", 0), ("ssh", 37)):
            result = self.run_helper(save=True, FAIL=failure)
            self.assertEqual(result.returncode, code)
            self.assertIn(b"remote output", result.stdout)
            self.assertIn(b"remote diagnostic", result.stderr)
            self.assertIn(b"requesting a phone save", result.stderr)
            self.assertNotIn(b"\r", result.stderr)

    def test_save_usage_and_root_guard(self):
        result = self.run_helper(save=True, args=("extra",))
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"usage:", result.stderr)
        result = self.run_helper()
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"normal user", result.stderr)

    def test_tty_animation_and_dumb_fallback(self):
        for term in ("xterm", "dumb"):
            master, slave = pty.openpty()
            # Disable terminal newline translation so CR means spinner, not ONLCR.
            import termios
            attrs = termios.tcgetattr(slave)
            attrs[1] &= ~termios.ONLCR
            termios.tcsetattr(slave, termios.TCSANOW, attrs)
            proc = subprocess.Popen(["/bin/sh", str(self.usb), "--network"],
                                    env=dict(self.env, TERM=term), stdout=subprocess.PIPE,
                                    stderr=slave)
            os.close(slave)
            data = b""
            try:
                while True:
                    if select.select([master], [], [], 5)[0]:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        data += chunk
                    else:
                        self.fail("TTY helper timed out")
                stdout, _ = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, data)
                self.assertIn(b"temporary sharing:", stdout)
                self.assertEqual(b"\r" in data, term != "dumb")
                if term != "dumb":
                    self.assertIn(b"\r  - releasing usb0", data)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                os.close(master)

if __name__ == "__main__":
    unittest.main()
