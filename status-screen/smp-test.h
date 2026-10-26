/* test-only pinned workers and a read-only TCP boot report. */
struct smp_result {
	u32 pid, state, before, after, checksum;
	long affinity;
};

static volatile struct smp_result *smp_results;
static u32 smp_reported[4];

static void smp_test_start(void)
{
	char online[64];
	u32 mask = 0;
	long addr = sys(SYS_mmap2, 0, 4096, 3, 0x21, -1, 0);

	if (addr < 0 && addr > -4096)
		return;
	smp_results = (volatile struct smp_result *)addr;
	if (read_file("/sys/devices/system/cpu/online", online, sizeof(online)) <= 0)
		return;
	for (char *p = online; *p;) {
		u32 first = 0, last;

		if (*p < '0' || *p > '9') {
			p++;
			continue;
		}
		while (*p >= '0' && *p <= '9')
			first = first * 10 + *p++ - '0';
		last = first;
		if (*p == '-') {
			p++;
			last = 0;
			while (*p >= '0' && *p <= '9')
				last = last * 10 + *p++ - '0';
		}
		for (u32 cpu = first; cpu <= last && cpu < 4; cpu++)
			mask |= 1u << cpu;
	}
	for (u32 cpu = 0; cpu < 4; cpu++) {
		long pid;

		if (!(mask & (1u << cpu)))
			continue;
		smp_results[cpu].state = 1;
		pid = sys(2, 0, 0, 0, 0, 0, 0);
		if (pid < 0) {
			smp_results[cpu].state = 5;
			continue;
		}
		if (!pid) {
			u32 affinity = 1u << cpu, before = ~0u, after = ~0u;
			u32 value = 0x930c0000u | cpu;
			long ret = sys(241, 0, sizeof(affinity), (long)&affinity, 0, 0, 0);

			smp_results[cpu].affinity = ret;
			if (ret >= 0) {
				sys(345, (long)&before, 0, 0, 0, 0, 0);
				for (u32 i = 0; i < 30000000; i++) {
					value ^= value << 13;
					value ^= value >> 17;
					value ^= value << 5;
				}
				sys(345, (long)&after, 0, 0, 0, 0, 0);
			}
			smp_results[cpu].before = before;
			smp_results[cpu].after = after;
			smp_results[cpu].checksum = value;
			__asm__ volatile("dmb ish" ::: "memory");
			smp_results[cpu].state = ret < 0 ? 3 :
				(before == cpu && after == cpu ? 2 : 4);
			for (;;)
				sys(1, 0, 0, 0, 0, 0, 0);
		}
		smp_results[cpu].pid = pid;
	}
}

static void smp_test_reap(void)
{
	while (sys(114, -1, 0, 1, 0, 0, 0) > 0)
		;
	if (!smp_results)
		return;
	for (u32 cpu = 0; cpu < 4; cpu++) {
		u32 state = smp_results[cpu].state;
		char line[COLS + 1] = "cpu0 pinned work: ";

		if (state < 2 || smp_reported[cpu])
			continue;
		__asm__ volatile("dmb ish" ::: "memory");
		smp_reported[cpu] = 1;
		line[3] += cpu;
		memcpy(line + 18, state == 2 ? "pass" : "fail", 5);
		note(line, state == 2 ? FG : ACCENT);
	}
}

static void smp_send(int fd, const char *p, u32 size)
{
	while (size) {
		long n = sys(SYS_write, fd, (long)p, size, 0, 0, 0);

		if (n <= 0)
			break;
		p += n;
		size -= n;
	}
}

static void smp_report_file(int sock, const char *path)
{
	char buf[8192];
	int fd = xopen(path, O_RDONLY | 04000);
	u32 count = 0;
	long n;

	xwrite(sock, "\n--- ");
	xwrite(sock, path);
	xwrite(sock, " ---\n");
	if (fd < 0)
		return;
	while (count < 262144 && (n = sys(SYS_read, fd, (long)buf, sizeof(buf), 0, 0, 0)) > 0) {
		smp_send(sock, buf, n);
		count += n;
	}
	sys(SYS_close, fd, 0, 0, 0, 0, 0);
}

static void smp_test_report(int fd)
{
	char value[16];

	xwrite(fd, "lumia930 SMP validation\n");
	if (smp_results) {
		__asm__ volatile("dmb ish" ::: "memory");
		for (u32 cpu = 0; cpu < 4; cpu++) {
			const volatile struct smp_result *r = &smp_results[cpu];

			decimal(value, cpu);
			xwrite(fd, "cpu="); xwrite(fd, value);
			decimal(value, r->state);
			xwrite(fd, " state="); xwrite(fd, value);
			decimal(value, r->before);
			xwrite(fd, " before="); xwrite(fd, value);
			decimal(value, r->after);
			xwrite(fd, " after="); xwrite(fd, value);
			decimal(value, r->checksum);
			xwrite(fd, " checksum="); xwrite(fd, value);
			decimal(value, r->affinity);
			xwrite(fd, " affinity="); xwrite(fd, value);
			xwrite(fd, "\n");
		}
	}
	smp_report_file(fd, "/sys/devices/system/cpu/online");
	smp_report_file(fd, "/sys/devices/system/cpu/possible");
	smp_report_file(fd, "/proc/cmdline");
	smp_report_file(fd, "/proc/stat");
	smp_report_file(fd, "/proc/interrupts");
	smp_report_file(fd, "/proc/cpuinfo");
	smp_report_file(fd, "/proc/iomem");
	smp_report_file(fd, "/dev/kmsg");
	xwrite(fd, "\n--- report complete ---\n");
}
