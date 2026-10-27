// SPDX-License-Identifier: BSD-3-Clause
#include "image-valid.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t le32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
	       (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void field(uint8_t *image, size_t size, size_t offset, uint32_t value)
{
	uint8_t original[4];

	memcpy(original, image + offset, 4);
	for (unsigned i = 0; i < 4; i++)
		image[offset + i] = (uint8_t)(value >> (i * 8));
	assert(!lumia930_image_valid(image, size));
	memcpy(image + offset, original, 4);
}

int main(int argc, char **argv)
{
	FILE *file;
	uint8_t *image, saved[512];
	long length;
	size_t size, dtb;

	assert(argc == 2);
	file = fopen(argv[1], "rb");
	assert(file && fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0 && fseek(file, 0, SEEK_SET) == 0);
	size = (size_t)length;
	image = malloc(size);
	assert(image && fread(image, 1, size, file) == size);
	assert(fclose(file) == 0);
	assert(lumia930_image_valid(image, size));
	assert(!lumia930_image_valid(NULL, size));
	for (size_t i = 0; i < 2048; i++)
		assert(!lumia930_image_valid(image, i));
	assert(!lumia930_image_valid(image, size - 1));
	assert(!lumia930_image_valid(image, size + 1));
	assert(!lumia930_image_valid(image, 33U * 1024 * 1024));
	for (unsigned i = 0; i < 8; i++) {
		image[i] ^= 0x80;
		assert(!lumia930_image_valid(image, size));
		image[i] ^= 0x80;
	}
	field(image, size, 8, 0);
	field(image, size, 8, 47);
	field(image, size, 8, UINT32_MAX);
	field(image, size, 12, 0x8000);
	field(image, size, 16, 0);
	field(image, size, 16, UINT32_MAX);
	field(image, size, 20, 0x1000000);
	field(image, size, 24, 1);
	field(image, size, 32, 0x100);
	field(image, size, 36, 0);
	field(image, size, 36, 512);
	field(image, size, 36, 4096);
	field(image, size, 40, 1);
	field(image, size, 2048 + 0x24, 0);
	field(image, size, 2048 + 0x28, UINT32_MAX);
	field(image, size, 2048 + 0x2c, UINT32_MAX);
	field(image, size, 2048 + 0x2c, 0);
	dtb = 2048U + le32(image + 2048 + 0x2c) - le32(image + 2048 + 0x28);
	field(image, size, dtb, 0);
	field(image, size, dtb + 4, 0);
	memcpy(saved, image + 64, sizeof(saved));
	memset(image + 64, 'x', sizeof(saved));
	assert(!lumia930_image_valid(image, size));
	memcpy(image + 64, saved, sizeof(saved));
	assert(lumia930_image_valid(image, size));
	free(image);
	puts("Android v0 address, size, truncation and appended-DTB checks passed");
	return 0;
}
