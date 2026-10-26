/* init for the lumia 930 status screen. static, no libc, armv7. */
#include "font8x16.h"

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

#define SYS_read	3
#define SYS_write	4
#define SYS_open	5
#define SYS_close	6
#define SYS_mount	21
#define SYS_ioctl	54
#define SYS_mkdir	39
#define SYS_symlink	83
#define SYS_clock_gettime 263
#define SYS_nanosleep	162
#define SYS_poll	168
#define SYS_mmap2	192
#define SYS_getdents64	217
#define SYS_socket	281
#define SYS_bind	282
#define SYS_listen	284
#define SYS_accept	285
#define SYS_setsockopt	294

#define O_RDONLY	0
#define O_WRONLY	1
#define O_DIRECTORY	040000

#define BG	0x101010
#define FG	0xc8c8c8
#define ACCENT	0xff79c6
#define DIM	0x707070

#define SCALE	3
#define CW	(8 * SCALE)
#define CH	(16 * SCALE)
#define COLS	45
#define LOGTOP	8
#define LOGROWS	5
#define DASHROWS 27
#define PORT	7000

static long sys(long n, long a, long b, long c, long d, long e, long f)
{
	register long r7 __asm__("r7") = n;
	register long r0 __asm__("r0") = a;
	register long r1 __asm__("r1") = b;
	register long r2 __asm__("r2") = c;
	register long r3 __asm__("r3") = d;
	register long r4 __asm__("r4") = e;
	register long r5 __asm__("r5") = f;

	__asm__ volatile("svc #0"
			 : "+r"(r0)
			 : "r"(r7), "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5)
			 : "memory");
	return r0;
}

void *memset(void *s, int c, unsigned long n)
{
	volatile u8 *p = s;

	while (n--)
		*p++ = c;
	return s;
}

void *memcpy(void *d, const void *s, unsigned long n)
{
	volatile u8 *dp = d;
	const u8 *sp = s;

	while (n--)
		*dp++ = *sp++;
	return d;
}

void *memmove(void *d, const void *s, unsigned long n)
{
	u8 *dp = d;
	const u8 *sp = s;

	if (dp < sp) {
		while (n--)
			*dp++ = *sp++;
	} else {
		dp += n;
		sp += n;
		while (n--)
			*--dp = *--sp;
	}
	return d;
}

static unsigned long slen(const char *s)
{
	unsigned long n = 0;

	while (s[n])
		n++;
	return n;
}

static void sleep_ms(long ms)
{
	long ts[2] = { ms / 1000, (ms % 1000) * 1000000 };

	sys(SYS_nanosleep, (long)ts, 0, 0, 0, 0, 0);
}

static int xopen(const char *p, int flags)
{
	return sys(SYS_open, (long)p, flags, 0, 0, 0, 0);
}

static void xwrite(int fd, const char *s)
{
	sys(SYS_write, fd, (long)s, slen(s), 0, 0, 0);
}

static void put_file(const char *path, const char *val)
{
	int fd = xopen(path, O_WRONLY);

	if (fd < 0)
		return;
	xwrite(fd, val);
	sys(SYS_close, fd, 0, 0, 0, 0, 0);
}

static void xmkdir(const char *p)
{
	sys(SYS_mkdir, (long)p, 0755, 0, 0, 0, 0);
}

/* framebuffer */
static u32 *fb;
static u32 fbw, fbh, fbstride;
static u32 sh_r, sh_g, sh_b, sh_t;

static u32 rgb(u32 c)
{
	return (((c >> 16) & 0xff) << sh_r) | (((c >> 8) & 0xff) << sh_g) |
	       ((c & 0xff) << sh_b) | (0xffu << sh_t);
}

static void fill(u32 x, u32 y, u32 w, u32 h, u32 color)
{
	u32 c = rgb(color);

	for (u32 j = y; j < y + h && j < fbh; j++)
		for (u32 i = x; i < x + w && i < fbw; i++)
			fb[j * fbstride + i] = c;
}

static void glyph(u32 col, u32 row, u8 ch, u32 color)
{
	const u8 *g = &font8x16[ch * 16];
	u32 c = rgb(color), b = rgb(BG);
	u32 x0 = col * CW, y0 = row * CH;

	for (u32 j = 0; j < 16; j++)
		for (u32 i = 0; i < 8; i++) {
			u32 v = (g[j] >> (7 - i)) & 1 ? c : b;

			for (u32 sj = 0; sj < SCALE; sj++)
				for (u32 si = 0; si < SCALE; si++) {
					u32 x = x0 + i * SCALE + si;
					u32 y = y0 + j * SCALE + sj;

					if (x < fbw && y < fbh)
						fb[y * fbstride + x] = v;
				}
		}
}

static void text(u32 col, u32 row, const char *s, u32 color)
{
	while (*s && col < COLS)
		glyph(col++, row, (u8)*s++, color);
}

static u32 logrow = LOGTOP;

static void note(const char *s, u32 color)
{
	if (!fb)
		return;
	if (logrow >= LOGTOP + LOGROWS)
		logrow = LOGTOP;
	fill(0, logrow * CH, fbw, CH, BG);
	text(0, logrow, s, color);
	logrow++;
}

static int fb_init(void)
{
	long v[40], f[17];
	int fd = -1;

	for (int i = 0; i < 50 && fd < 0; i++) {
		fd = xopen("/dev/fb0", 2);
		if (fd < 0)
			sleep_ms(100);
	}
	if (fd < 0)
		return -1;
	if (sys(SYS_ioctl, fd, 0x4600, (long)v, 0, 0, 0) < 0 ||
	    sys(SYS_ioctl, fd, 0x4602, (long)f, 0, 0, 0) < 0)
		return -2;
	/* fb_var_screeninfo: xres, yres at 0 and 4, bpp at 24, colour fields from 32 */
	fbw = v[0];
	fbh = v[1];
	if (v[6] != 32)
		return -3;
	sh_r = v[8];
	sh_g = v[11];
	sh_b = v[14];
	sh_t = v[18] ? v[17] : 24;
	/* fb_fix_screeninfo: smem_len at 20, line_length at 44 */
	fbstride = ((u32 *)f)[11] >> 2;
	long len = ((u32 *)f)[5];
	long p = sys(SYS_mmap2, 0, len, 3, 1, fd, 0);

	if (p < 0 && p > -4096)
		return -4;
	fb = (u32 *)p;
	{
		int tty = xopen("/dev/tty0", 2);

		if (tty >= 0)
			sys(SYS_ioctl, tty, 0x4b3a, 1, 0, 0, 0);
	}
	fill(0, 0, fbw, fbh, BG);
	return 0;
}

static int read_file(const char *path, char *buf, u32 size)
{
	int fd = xopen(path, O_RDONLY);
	long n;

	if (fd < 0)
		return -1;
	n = sys(SYS_read, fd, (long)buf, size - 1, 0, 0, 0);
	sys(SYS_close, fd, 0, 0, 0, 0, 0);
	buf[n > 0 ? n : 0] = 0;
	return n;
}

static char *decimal(char *p, u32 n)
{
	char digits[10];
	u32 len = 0;

	do {
		digits[len++] = '0' + n % 10;
		n /= 10;
	} while (n);
	while (len)
		*p++ = digits[--len];
	*p = 0;
	return p;
}

static void cpu_panel(void)
{
	static u32 previous_total[4], previous_idle[4], seen[4];
	u32 total[4] = {0}, idle[4] = {0}, online[4] = {0}, count = 0;
	char buf[2048], line[COLS + 1];
	int n = read_file("/proc/stat", buf, sizeof(buf));
	char *p = buf;

	if (!fb)
		return;
	while (n > 0 && *p) {
		char *end = p;

		while (*end && *end != '\n')
			end++;
		if (end - p > 4 && p[0] == 'c' && p[1] == 'p' &&
		    p[2] == 'u' && p[3] >= '0' && p[3] <= '3' && p[4] == ' ') {
			u32 cpu = p[3] - '0', fields = 0;
			char *q = p + 4;

			while (fields < 8 && q < end) {
				u32 value = 0;

				while (q < end && *q == ' ')
					q++;
				if (q == end || *q < '0' || *q > '9')
					break;
				while (q < end && *q >= '0' && *q <= '9')
					value = value * 10 + *q++ - '0';
				total[cpu] += value;
				if (fields == 3 || fields == 4)
					idle[cpu] += value;
				fields++;
			}
			if (fields == 8)
				online[cpu] = 1, count++;
		}
		p = *end ? end + 1 : end;
	}
	fill(0, 2 * CH, fbw, 5 * CH, BG);
	memcpy(line, "phone cpus: ", 12);
	p = decimal(line + 12, count);
	memcpy(p, "/4 online", 10);
	text(0, 2, count ? line : "phone cpu stats unavailable", count ? ACCENT : DIM);
	for (u32 cpu = 0; cpu < 4; cpu++) {
		u32 dt = total[cpu] - previous_total[cpu];
		u32 di = idle[cpu] - previous_idle[cpu];

		memcpy(line, "cpu0  ", 7);
		line[3] += cpu;
		p = line + 6;
		if (!online[cpu]) {
			memcpy(p, n > 0 ? "offline" : "unknown", 8);
			seen[cpu] = 0;
		} else if (!seen[cpu] || !dt) {
			memcpy(p, "sampling", 9);
		} else {
			/* iowait can decrease; bound it before unsigned subtraction. */
			u32 busy = di <= dt ? dt - di : 0;

			p = decimal(p, busy * 100 / dt);
			memcpy(p, "% busy", 7);
		}
		text(0, 3 + cpu, line, online[cpu] ? FG : DIM);
		previous_total[cpu] = total[cpu];
		previous_idle[cpu] = idle[cpu];
		seen[cpu] = online[cpu];
	}
}

#ifdef SMP_TEST
#include "smp-test.h"
#endif

static void gadget(void)
{
	const char *g = "/sys/kernel/config/usb_gadget/g1";
	char buf[512];
	int fd, n, ok = 0;

	xmkdir("/sys/kernel/config/usb_gadget");
	xmkdir(g);
	put_file("/sys/kernel/config/usb_gadget/g1/idVendor", "0x1d6b");
	put_file("/sys/kernel/config/usb_gadget/g1/idProduct", "0x0104");
	xmkdir("/sys/kernel/config/usb_gadget/g1/strings/0x409");
	put_file("/sys/kernel/config/usb_gadget/g1/strings/0x409/serialnumber", "930");
	put_file("/sys/kernel/config/usb_gadget/g1/strings/0x409/manufacturer", "lumia");
	put_file("/sys/kernel/config/usb_gadget/g1/strings/0x409/product", "lumia 930 status");
	xmkdir("/sys/kernel/config/usb_gadget/g1/configs/c.1");
	xmkdir("/sys/kernel/config/usb_gadget/g1/configs/c.1/strings/0x409");
	put_file("/sys/kernel/config/usb_gadget/g1/configs/c.1/strings/0x409/configuration", "ncm");
	xmkdir("/sys/kernel/config/usb_gadget/g1/functions/ncm.usb0");
	sys(SYS_symlink, (long)"/sys/kernel/config/usb_gadget/g1/functions/ncm.usb0",
	    (long)"/sys/kernel/config/usb_gadget/g1/configs/c.1/ncm.usb0", 0, 0, 0, 0);

	for (int i = 0; i < 100 && !ok; i++) {
		fd = xopen("/sys/class/udc", O_RDONLY | O_DIRECTORY);
		if (fd >= 0) {
			n = sys(SYS_getdents64, fd, (long)buf, sizeof(buf), 0, 0, 0);
			sys(SYS_close, fd, 0, 0, 0, 0, 0);
			for (int o = 0; n > 0 && o < n;) {
				u16 reclen = *(u16 *)(buf + o + 16);
				const char *name = buf + o + 19;

				if (name[0] != '.') {
					put_file("/sys/kernel/config/usb_gadget/g1/UDC", name);
					ok = 1;
					break;
				}
				o += reclen;
			}
		}
		if (!ok)
			sleep_ms(100);
	}
	note(ok ? "usb gadget bound" : "no udc found", ok ? FG : ACCENT);
}

static u32 htonl32(u32 v)
{
	return (v >> 24) | ((v >> 8) & 0xff00) | ((v << 8) & 0xff0000) | (v << 24);
}

static void ifreq_addr(u8 *r, u32 ip)
{
	memset(r + 16, 0, 24);
	r[16] = 2;
	*(u32 *)(r + 20) = htonl32(ip);
}

static int netup(void)
{
	u8 r[40];
	int s = sys(SYS_socket, 2, 2, 0, 0, 0, 0);

	if (s < 0)
		return -1;
	for (int i = 0; i < 100; i++) {
		memset(r, 0, sizeof(r));
		memcpy(r, "usb0", 5);
		if (sys(SYS_ioctl, s, 0x8913, (long)r, 0, 0, 0) >= 0)
			break;
		sleep_ms(100);
		if (i == 99)
			return -2;
	}
	memset(r, 0, sizeof(r));
	memcpy(r, "usb0", 5);
	ifreq_addr(r, 0xac102a01);	/* 172.16.42.1 */
	sys(SYS_ioctl, s, 0x8916, (long)r, 0, 0, 0);
	memset(r, 0, sizeof(r));
	memcpy(r, "usb0", 5);
	ifreq_addr(r, 0xffffff00);
	sys(SYS_ioctl, s, 0x891c, (long)r, 0, 0, 0);
	memset(r, 0, sizeof(r));
	memcpy(r, "usb0", 5);
	sys(SYS_ioctl, s, 0x8913, (long)r, 0, 0, 0);
	*(u16 *)(r + 16) |= 0x41;	/* up, running */
	sys(SYS_ioctl, s, 0x8914, (long)r, 0, 0, 0);
	sys(SYS_close, s, 0, 0, 0, 0, 0);
	return 0;
}

static char lines[DASHROWS][COLS + 1];
static u32 lcolor[DASHROWS];
static u32 nlines;

static void redraw(void)
{
	u32 top = LOGTOP + LOGROWS + 1;

	fill(0, top * CH, fbw, DASHROWS * CH, BG);
	for (u32 i = 0; i < nlines; i++)
		text(0, top + i, lines[i], lcolor[i]);
}

static void add_line(const char *s, u32 color)
{
	u32 n = 0;

	if (nlines == DASHROWS) {
		memmove(lines[0], lines[1], (DASHROWS - 1) * (COLS + 1));
		memmove(lcolor, lcolor + 1, (DASHROWS - 1) * sizeof(u32));
		nlines--;
	}
	while (s[n] && n < COLS) {
		lines[nlines][n] = s[n];
		n++;
	}
	lines[nlines][n] = 0;
	lcolor[nlines] = color;
	nlines++;
	redraw();
}

static void feed(char *in, long n, char *cur, u32 *len)
{
	for (long i = 0; i < n; i++) {
		char c = in[i];

		if (c == '\r')
			continue;
		if (c == '\n') {
			cur[*len] = 0;
			if (cur[0] == '#' && cur[1] == ' ')
				add_line(cur + 2, ACCENT);
			else if (cur[0] == '!' && cur[1] == 'c')
				nlines = 0, redraw();
			else
				add_line(cur, FG);
			*len = 0;
		} else if (*len < COLS) {
			cur[(*len)++] = c == '\t' ? ' ' : c;
		}
	}
}

static void serve(void)
{
	int one = 1, lfd = sys(SYS_socket, 2, 1, 0, 0, 0, 0), cfd = -1;
	u8 sa[16];
	char cur[COLS + 2], in[256];
	u32 len = 0, beat = 0, last_tick = ~0u;
	struct { int fd; short ev, rev; } p[2];

	if (lfd < 0) {
		note("tcp socket failed", ACCENT);
		return;
	}
	sys(SYS_setsockopt, lfd, 1, 2, (long)&one, 4, 0);
	memset(sa, 0, sizeof(sa));
	sa[0] = 2;
	sa[2] = PORT >> 8;
	sa[3] = PORT & 0xff;
	if (sys(SYS_bind, lfd, (long)sa, 16, 0, 0, 0) < 0 ||
	    sys(SYS_listen, lfd, 1, 0, 0, 0, 0) < 0) {
		note("tcp bind failed", ACCENT);
		return;
	}
	note("listening on 172.16.42.1:7000", FG);

	for (;;) {
		int n = 1;
		long now[2] = {0};

		sys(SYS_clock_gettime, 1, (long)now, 0, 0, 0, 0);
		if ((u32)now[0] != last_tick) {
			cpu_panel();
			last_tick = now[0];
#ifdef SMP_TEST
			smp_test_reap();
#endif
		}
		p[0].fd = lfd, p[0].ev = 1, p[0].rev = 0;
		if (cfd >= 0)
			p[1].fd = cfd, p[1].ev = 1, p[1].rev = 0, n = 2;
		long r = sys(SYS_poll, (long)p, n, 1000, 0, 0, 0);

		fill(fbw - 40, 8, 24, 24, (beat++ & 1) ? ACCENT : BG);
		if (r <= 0)
			continue;
		if (p[0].rev & 1) {
			int c = sys(SYS_accept, lfd, 0, 0, 0, 0, 0);

			if (c >= 0) {
				if (cfd >= 0)
					sys(SYS_close, cfd, 0, 0, 0, 0, 0);
				cfd = c;
				len = 0;
				add_line("-- connected", DIM);
#ifdef SMP_TEST
				smp_test_report(cfd);
#endif
			}
		}
		if (cfd >= 0 && n == 2 && (p[1].rev & 0x19)) {
			long k = sys(SYS_read, cfd, (long)in, sizeof(in), 0, 0, 0);

			if (k <= 0) {
				sys(SYS_close, cfd, 0, 0, 0, 0, 0);
				cfd = -1;
				add_line("-- disconnected", DIM);
			} else {
				feed(in, k, cur, &len);
			}
		}
	}
}

void _start(void)
{
	int rc;

	xmkdir("/dev");
	xmkdir("/proc");
	xmkdir("/sys");
	sys(SYS_mount, (long)"devtmpfs", (long)"/dev", (long)"devtmpfs", 0, 0, 0);
	sys(SYS_mount, (long)"proc", (long)"/proc", (long)"proc", 0, 0, 0);
	sys(SYS_mount, (long)"sysfs", (long)"/sys", (long)"sysfs", 0, 0, 0);
	sys(SYS_mount, (long)"configfs", (long)"/sys/kernel/config", (long)"configfs", 0, 0, 0);

	rc = fb_init();
	if (rc == 0) {
		text(0, 0, "lumia 930", ACCENT);
		text(0, 1, "linux status screen", DIM);
		note("framebuffer ok", FG);
	}
	cpu_panel();
#ifdef SMP_TEST
	smp_test_start();
#endif
	gadget();
	rc = netup();
	note(rc == 0 ? "usb0 up 172.16.42.1/24" : "usb0 failed", rc == 0 ? FG : ACCENT);
	if (rc == 0)
		serve();
	for (;;)
		sleep_ms(1000);
}
