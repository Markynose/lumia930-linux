# status-screen regression tests

run from the repository root:

```sh
python3 status-screen/test-cpu-panel.py
python3 status-screen/test-runtime.py
python3 tools/test-wpcmd.py
python3 status-screen/test-build.py /path/to/linux-source-tree
```

the native C tests need clang and ASan/UBSan. they exercise the actual C
functions with mocked syscalls, not a second implementation. coverage:

- CPU sampling, offline/missing/malformed input and counter wrap.
- framebuffer open/ioctl/format/geometry/mmap failures, unpublished state on
  failure, safe drawing without a mapping, successful padded-stride drawing.
- simultaneous client readiness and replacement, a silent replacement,
  later accepts, descriptor reuse, EOF and continued heartbeat/CPU refresh.

the framebuffer and reconnect tests reject the original `d82cc45` source.
these are host regressions, not reproductions on phone hardware.

`tools/test-wpcmd.py` covers every two- and three-part split of a mixed
TELNET stream, byte-at-a-time delivery, escaped IAC, option negotiation,
subnegotiation, incomplete packets and state surviving read timeouts.
negative option replies are consumed without starting negotiation loops.

the parallel-build test needs the normal ARM build dependencies. it launches
four real builds with mixed normal/`SMP_TEST=1` settings and separate output
directories. it checks each packed init against its own binary, verifies the
correct diagnostic setting, and checks that shared source artifacts stay
unchanged. this does not test parallel kernel builds in one kernel checkout.

## output isolation

```sh
sh status-screen/build.sh /path/to/linux-source-tree /path/to/private-output
```

omitting the second argument keeps the original default output directory,
`status-screen/`. generation and compilation always use a temporary private
workspace; published artifact files are replaced only after a successful
build. simultaneous callers must still use distinct output directories if
they need distinct results. do not share a kernel checkout between parallel
`tools/build-image.sh` runs either.

these source fixes do not rebuild or deploy any phone image. the tested
alpine setup uses OpenRC/BusyBox instead of this tiny PID1.
