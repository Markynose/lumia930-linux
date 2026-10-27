# Host helper output

These are the PC-side helpers:

- `alpine/host/lumia-usb`: temporary USB internet sharing and an SSH clock sync.
- `alpine/persistence/host-save`: the host `lumia-save` SSH wrapper.

Install them as described in [the Alpine README](../README.md). Each remains a
standalone POSIX shell script; there is no extra UI dependency to install.

Progress labels go to stderr, leaving command stdout intact. Redirected stderr
and `TERM=dumb` receive ordinary lines with no animation or escape sequences.
Other terminals show an ASCII spinner only while the already-silent
NetworkManager/dhcpcd disconnect command is running. No colour is required.
The ending dash means the best-effort attempt finished, not that it succeeded.

SSH output (including save progress and errors) is streamed unchanged. It is
not animated or captured, so diagnostics stay readable. Save uses `exec ssh`
as before: the SSH exit status and signal behaviour remain intact. There are
no new connection retries, phone polling loops, artificial progress percentages,
or added readiness claims. The existing dhcpcd one-second pause is unchanged.

## Safe output regressions

From the repository root:

```sh
sh -n alpine/host/lumia-usb
sh -n alpine/persistence/host-save
python3 alpine/tests/test-host-ui.py
```

The Python tests substitute a temporary sysfs fixture in a temporary script
copy and mock all network, privilege, SSH and forwarding commands. They never
connect to a phone or change the machine's network/firewall configuration.
They cover redirected/TTY output, cancellation cleanup, doas/sudo and
NetworkManager/dhcpcd paths, missing hardware, save usage and failed commands.
They are not a real-device or real-network validation.
