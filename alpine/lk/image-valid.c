// SPDX-License-Identifier: BSD-3-Clause
#include "image-valid.h"
#include <stdint.h>
#include <string.h>

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
	       (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint32_t be32(const uint8_t *p)
{
	return (uint32_t)p[3] | (uint32_t)p[2] << 8 |
	       (uint32_t)p[1] << 16 | (uint32_t)p[0] << 24;
}

int lumia930_image_valid(const void *image, size_t size)
{
	const uint8_t *b = image, *kernel, *dtb;
	uint32_t kernel_size, ramdisk_size, start, end, zsize;
	uint64_t kernel_padded, ramdisk_padded;

	if (!b || size < 2048 || size > 32U * 1024 * 1024 || memcmp(b, "ANDROID!", 8))
		return 0;
	kernel_size = le32(b + 8);
	ramdisk_size = le32(b + 16);
	if (le32(b + 12) != 0x10008000 || le32(b + 20) != 0x14000000 ||
	    le32(b + 32) != 0x13e00000 || le32(b + 36) != 2048 ||
	    le32(b + 40) || le32(b + 24) || kernel_size < 48 || !ramdisk_size ||
	    !memchr(b + 64, 0, 512))
		return 0;
	kernel_padded = ((uint64_t)kernel_size + 2047) & ~(uint64_t)2047;
	ramdisk_padded = ((uint64_t)ramdisk_size + 2047) & ~(uint64_t)2047;
	if (2048 + kernel_padded + ramdisk_padded != size)
		return 0;
	kernel = b + 2048;
	if (le32(kernel + 0x24) != 0x016f2818)
		return 0;
	start = le32(kernel + 0x28);
	end = le32(kernel + 0x2c);
	if (end < start)
		return 0;
	zsize = end - start;
	if (zsize < 48 || kernel_size < 40 || zsize > kernel_size - 40)
		return 0;
	dtb = kernel + zsize;
	if (be32(dtb) != 0xd00dfeed || be32(dtb + 4) != kernel_size - zsize)
		return 0;
	return 1;
}

const void *lumia930_image_fdt(const void *image, size_t size)
{
	const uint8_t *b = image;

	if (!lumia930_image_valid(image, size))
		return NULL;
	return b + 2048 + le32(b + 2048 + 0x2c) - le32(b + 2048 + 0x28);
}
