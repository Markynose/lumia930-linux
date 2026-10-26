#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent
source = (root / 'init.c').read_text()
functions = source[source.index('static char *decimal('):source.index('\n#ifdef SMP_TEST')]
harness = r'''
#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef unsigned int u32;
#define COLS 45
#define CH 48
#define BG 0
#define ACCENT 1
#define DIM 2
#define FG 3
static u32 fake_fb, *fb = &fake_fb, fbw = 1080;
static const char *fixture;
static char rows[7][46];
static int read_file(const char *path, char *buf, u32 size) {
    if (!fixture) { buf[0] = 0; return -1; }
    size_t n = strlen(fixture);
    assert(n < size);
    memcpy(buf, fixture, n + 1);
    return n;
}
static void fill(u32 x, u32 y, u32 w, u32 h, u32 c) {}
static void text(u32 col, u32 row, const char *s, u32 color) {
    assert(strlen(s) <= 45);
    strcpy(rows[row], s);
}
'''
tests = r'''
int main(void) {
    fixture = "cpu 30 0 0 170 0 0 0 0\ncpu0 10 0 0 90 0 0 0 0 999 999\ncpu1 20 0 0 80 0 0 0 0\n";
    cpu_panel();
    assert(!strcmp(rows[2], "phone cpus: 2/4 online"));
    assert(!strcmp(rows[3], "cpu0  sampling"));
    assert(!strcmp(rows[5], "cpu2  offline"));
    fixture = "cpu0 20 0 0 180 0 0 0 0\ncpu1 40 0 0 160 0 0 0 0\ncpu2 1 0 0 99 0 0 0 0\ncpu3 1 0 0 99 0 0 0 0\n";
    cpu_panel();
    assert(!strcmp(rows[2], "phone cpus: 4/4 online"));
    assert(!strcmp(rows[3], "cpu0  10% busy"));
    assert(!strcmp(rows[4], "cpu1  20% busy"));
    assert(!strcmp(rows[6], "cpu3  sampling"));
    fixture = "cpu0 30 0 0 270 0 0 0 0\ncpu1 60 0 0 240 0 0 0 0\ncpu2 2 0 0 198 0 0 0 0\ncpu3 101 0 0 99 0 0 0 0\n";
    cpu_panel();
    assert(!strcmp(rows[5], "cpu2  1% busy"));
    assert(!strcmp(rows[6], "cpu3  100% busy"));
    fixture = NULL;
    cpu_panel();
    assert(!strcmp(rows[2], "phone cpu stats unavailable"));
    assert(!strcmp(rows[6], "cpu3  unknown"));
    fixture = "cpu0 4294967290 0 0 0 0 0 0 0\n";
    cpu_panel();
    fixture = "cpu0 4 0 0 0 0 0 0 0\n";
    cpu_panel();
    assert(!strcmp(rows[3], "cpu0  100% busy"));
    fixture = "cpu10 1 2 3 4 5 6 7 8\ncpu0 1 2 3\n";
    cpu_panel();
    assert(!strcmp(rows[2], "phone cpu stats unavailable"));
    puts("phone CPU panel tests passed");
}
'''
with tempfile.TemporaryDirectory(prefix='lumia930-cpu-panel-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(harness + functions + tests)
    subprocess.run([os.environ.get('CC', 'clang'), '-Wall', '-Wextra',
                    '-Wno-unused-parameter', '-fsanitize=address,undefined',
                    '-g', str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
