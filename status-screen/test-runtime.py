#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root / 'init.c')
parser.add_argument('--case', choices=('framebuffer', 'reconnect'))
args = parser.parse_args()
source = args.source.read_text()
defines = '\n'.join(line for line in source.splitlines() if line.startswith('#define '))
common = '#include <assert.h>\n#include <string.h>\n#include <stdio.h>\ntypedef unsigned char u8;\ntypedef unsigned int u32;\n' + defines
framebuffer = r'''
static const u8 font8x16[4096];
static u32 pixels[8];
static int mode, closes, tty_closes;
static long map_result;
static long sys(long n, long a, long b, long c, long d, long e, long f) {
    if (n == SYS_ioctl && b == 0x4600) {
        if (mode == 1) return -1;
        long *v = (long *)c;
        memset(v, 0, 40 * sizeof(*v));
        v[0] = 2; v[1] = 2; v[6] = mode == 3 ? 16 : 32;
        v[8] = mode == 8 ? 32 : 16; v[11] = 8; v[14] = 0;
        if (mode == 4) v[0] = 0;
        return 0;
    }
    if (n == SYS_ioctl && b == 0x4602) {
        if (mode == 2) return -1;
        memset((void *)c, 0, 17 * sizeof(long));
        u32 *v = (u32 *)c;
        v[5] = sizeof(pixels); v[11] = mode == 5 ? 4 : 16;
        return 0;
    }
    if (n == SYS_mmap2) return map_result;
    if (n == SYS_close) {
        if (a == 31) closes++;
        if (a == 32) tty_closes++;
    }
    return 0;
}
static int xopen(const char *path, int flags) {
    if (!strcmp(path, "/dev/fb0")) return mode == 9 ? -1 : 31;
    assert(!strcmp(path, "/dev/tty0"));
    return 32;
}
static void sleep_ms(long ms) {}
'''
fb_tests = r'''
int main(void) {
    const int modes[] = {3, 6, 1, 2, 4, 5, 7, 8, 9};
    for (unsigned test = 0; test < sizeof(modes) / sizeof(modes[0]); test++) {
        mode = modes[test];
        fb = NULL; fbw = fbh = fbstride = sh_r = sh_g = sh_b = sh_t = 0;
        closes = tty_closes = 0;
        map_result = mode == 6 ? -12 : mode == 7 ? 0 : (long)pixels;
        assert(fb_init() < 0);
        assert(!fb && !fbw && !fbh && !fbstride);
        assert(closes == (mode == 9 ? 0 : 1) && !tty_closes);
        fill(fbw - 40, 8, 24, 24, ACCENT);
        glyph(0, 0, 'a', FG);
        note("no framebuffer", FG);
    }
    fb = NULL; fbw = fbh = fbstride = 4; sh_r = sh_g = sh_b = sh_t = 32;
    fill(0, 0, 4, 4, FG);
    glyph(0, 0, 'a', FG);
    fbw = fbh = fbstride = sh_r = sh_g = sh_b = sh_t = 0;
    mode = closes = tty_closes = 0;
    map_result = (long)pixels;
    for (unsigned i = 0; i < 8; i++) pixels[i] = 0x12345678;
    assert(fb_init() == 0 && fb == pixels && fbw == 2 && fbh == 2 && fbstride == 4);
    assert(closes == 1 && tty_closes == 1);
    assert(pixels[0] == 0xff101010 && pixels[1] == 0xff101010);
    assert(pixels[4] == 0xff101010 && pixels[5] == 0xff101010);
    assert(pixels[2] == 0x12345678 && pixels[3] == 0x12345678);
    assert(pixels[6] == 0x12345678 && pixels[7] == 0x12345678);
    puts("framebuffer failures, draw guards and padded-stride tests passed");
}
'''
network = r'''
#include <setjmp.h>
static jmp_buf done;
static int polls, accepts, reads, closes, beats, refreshes, feeds;
static u32 fbw = 1080;
static long sys(long n, long a, long b, long c, long d, long e, long f) {
    if (n == SYS_socket) return 10;
    if (n == SYS_clock_gettime) { ((long *)b)[0] = polls; return 0; }
    if (n == SYS_poll) {
        struct pollfd { int fd; short ev, rev; } *p = (void *)a;
        polls++;
        if (polls == 9) longjmp(done, 1);
        assert(p[0].fd == 10 && p[0].ev == 1);
        assert(b == ((polls == 1 || polls == 7) ? 1 : 2));
        if (b == 2) {
            int expected = polls <= 3 ? 100 : polls == 4 ? 101 : polls <= 6 ? 102 : 100;
            assert(p[1].fd == expected && p[1].ev == 1);
            p[1].rev = polls == 6 ? 0x10 : (polls == 2 || polls == 3 || polls == 8) ? 1 : 0;
        }
        p[0].rev = polls == 1 || polls == 3 || polls == 4 || polls == 7 ? 1 : 0;
        return polls == 5 ? 0 : 1;
    }
    if (n == SYS_accept) {
        const int fds[] = {100,101,102,100};
        assert(accepts < 4);
        return fds[accepts++];
    }
    if (n == SYS_close) { assert(a >= 100 && a <= 102); closes++; return 0; }
    if (n == SYS_read) {
        assert((polls == 2 && a == 100) || (polls == 6 && a == 102) || (polls == 8 && a == 100));
        reads++;
        if (polls == 6) return 0;
        memcpy((void *)b, "x\n", 2);
        return 2;
    }
    return 0;
}
static void note(const char *s, u32 c) {}
static void add_line(const char *s, u32 c) {}
static void cpu_panel(void) { refreshes++; }
static void fill(u32 x, u32 y, u32 w, u32 h, u32 c) { beats++; }
static void feed(char *in, long n, char *cur, u32 *len) { assert(n == 2); feeds++; }
'''
net_tests = r'''
int main(void) {
    if (!setjmp(done)) { serve(); assert(0); }
    assert(accepts == 4 && reads == 3 && closes == 3 && feeds == 2);
    assert(beats == 8 && refreshes == 9);
    puts("reconnect, silent replacement, fd reuse, EOF and heartbeat tests passed");
}
'''
cases = {
    'framebuffer': framebuffer + source[source.index('/* framebuffer */'):source.index('static int read_file(')] + fb_tests,
    'reconnect': network + source[source.index('static void serve('):source.index('void _start(')] + net_tests,
}
with tempfile.TemporaryDirectory(prefix='lumia930-runtime-') as tmp:
    work = Path(tmp)
    for name, body in cases.items():
        if args.case and args.case != name:
            continue
        path = work / name
        path.with_suffix('.c').write_text(common + body)
        subprocess.run([os.environ.get('CC', 'clang'), '-Wall', '-Wextra', '-Wno-unused-parameter',
                        '-fsanitize=address,undefined', '-g', str(path.with_suffix('.c')), '-o', str(path)], check=True)
        subprocess.run([str(path)], check=True, timeout=10)
