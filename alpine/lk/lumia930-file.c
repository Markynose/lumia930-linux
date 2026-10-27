// SPDX-License-Identifier: BSD-3-Clause
#include <debug.h>
#include <fastboot.h>
#include <libfdt.h>
#include <mmc.h>
#include <partition_parser.h>
#include <stdlib.h>
#include <string.h>
#include <target.h>

#include "fat-ro.h"
#include "image-valid.h"
#include "lumia930-file.h"

struct esp_reader {
	uint64_t start, bytes, cached;
	uint8_t *sector;
};

static int esp_read(void *context, uint64_t offset, void *buffer, size_t len)
{
	struct esp_reader *reader = context;
	uint8_t *out = buffer;

	if (offset > reader->bytes || len > reader->bytes - offset)
		return -1;
	while (len) {
		size_t chunk;
		uint64_t sector = offset & ~(uint64_t)511;

		if (!(offset & 511) && !((uintptr_t)out & (CACHE_LINE - 1)) && len >= 512) {
			chunk = len & ~(size_t)511;
			if (chunk > 65536)
				chunk = 65536;
			if (mmc_read(reader->start + offset, (uint32_t *)out, (uint32_t)chunk))
				return -1;
		} else {
			if (reader->cached != sector) {
				if (mmc_read(reader->start + sector, (uint32_t *)reader->sector, 512))
					return -1;
				reader->cached = sector;
			}
			chunk = 512 - (size_t)(offset & 511);
			if (chunk > len)
				chunk = len;
			memcpy(out, reader->sector + (offset & 511), chunk);
		}
		offset += chunk;
		out += chunk;
		len -= chunk;
	}
	return 0;
}

static int load_alpine(void **image, size_t *size)
{
	struct esp_reader reader;
	struct fat_ro fs;
	const void *dtb;
	size_t capacity = target_get_max_flash_size();
	int index = partition_get_index("EFIESP"), result = -1;

	if (index < 0 || mmc_get_device_blocksize() != 512) {
		dprintf(CRITICAL, "alpine: EFIESP or 512-byte MMC blocks unavailable\n");
		return -1;
	}
	reader.start = partition_get_offset(index);
	reader.bytes = partition_get_size(index);
	reader.cached = ~(uint64_t)0;
	if (!reader.bytes || (reader.start & 511) || (reader.bytes & 511) ||
	    reader.start > ~(uint64_t)0 - reader.bytes)
		return -1;
	reader.sector = memalign(CACHE_LINE, 512);
	if (!reader.sector)
		return -1;
	*image = target_get_scratch_address();
	if (capacity > 32U * 1024 * 1024)
		capacity = 32U * 1024 * 1024;
	if (!*image || !capacity || fat_ro_mount(&fs, esp_read, &reader, reader.bytes)) {
		dprintf(CRITICAL, "alpine: unsupported or damaged EFIESP FAT volume\n");
		goto done;
	}
	if (fat_ro_load(&fs, "/alpine/boot.img", *image, capacity, size)) {
		dprintf(CRITICAL, "alpine: cannot read complete /alpine/boot.img\n");
		goto done;
	}
	dtb = lumia930_image_fdt(*image, *size);
	if (!dtb || fdt_check_header(dtb) || fdt_node_check_compatible(dtb, 0, "nokia,martini")) {
		dprintf(CRITICAL, "alpine: invalid image, addresses or martini DTB\n");
		goto done;
	}
	dprintf(ALWAYS, "alpine: FAT%u, validated %u-byte RAM image\n", fs.bits, (unsigned)*size);
	result = 0;
done:
	free(reader.sector);
	return result;
}

void lumia930_alpine_boot(void)
{
	extern void cmd_boot(const char *, void *, unsigned);
	void *image;
	size_t size;

	if (!load_alpine(&image, &size))
		cmd_boot("", image, (unsigned)size);
}

static void cmd_alpine_check(const char *arg, void *data, unsigned sz)
{
	void *image;
	size_t size;

	if (load_alpine(&image, &size))
		fastboot_fail("alpine image validation failed; phone storage unchanged");
	else
		fastboot_okay("alpine image valid; phone storage unchanged");
}
FASTBOOT_REGISTER("oem alpine-check", cmd_alpine_check);
