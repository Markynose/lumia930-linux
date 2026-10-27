// SPDX-License-Identifier: BSD-3-Clause
#define _POSIX_C_SOURCE 200809L
#include "fat-ro.h"
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

struct image {
	uint8_t *data;
	size_t size, reads;
	long fail_after;
};

static int read_image(void *context, uint64_t offset, void *buf, size_t len)
{
	struct image *image = context;

	assert(offset <= image->size && len <= image->size - offset);
	assert(++image->reads < 200000);
	if (image->fail_after >= 0 && image->reads > (size_t)image->fail_after)
		return -1;
	memcpy(buf, image->data + offset, len);
	return 0;
}

int main(int argc, char **argv)
{
	struct stat st;
	struct image image;
	struct fat_ro fs;
	int fd, expected, result;
	FILE *reference;
	long length;
	size_t loaded = 123;
	uint8_t *golden, *output;

	assert(argc >= 5);
	fd = open(argv[1], O_RDONLY);
	assert(fd >= 0 && fstat(fd, &st) == 0 && st.st_size > 0);
	image.size = (size_t)st.st_size;
	image.data = mmap(NULL, image.size, PROT_READ | PROT_WRITE, MAP_PRIVATE, fd, 0);
	assert(image.data != MAP_FAILED);
	image.reads = 0;
	image.fail_after = -1;
	for (int i = 5; i < argc; i++) {
		unsigned long long offset;
		unsigned value;

		if (!strncmp(argv[i], "io=", 3)) {
			image.fail_after = strtol(argv[i] + 3, NULL, 10);
			continue;
		}
		assert(sscanf(argv[i], "%llx:%x", &offset, &value) == 2);
		assert(offset < image.size && value < 256);
		image.data[(size_t)offset] = (uint8_t)value;
	}
	reference = fopen(argv[2], "rb");
	assert(reference && fseek(reference, 0, SEEK_END) == 0);
	length = ftell(reference);
	assert(length > 0 && fseek(reference, 0, SEEK_SET) == 0);
	golden = malloc((size_t)length);
	output = malloc((size_t)length);
	assert(golden && output);
	assert(fread(golden, 1, (size_t)length, reference) == (size_t)length);
	assert(fclose(reference) == 0);
	expected = !strcmp(argv[4], "pass");
	result = fat_ro_mount(&fs, read_image, &image, image.size);
	if (!result)
		result = fat_ro_load(&fs, argv[3], output, (size_t)length, &loaded);
	if (expected) {
		assert(result == 0 && loaded == (size_t)length);
		assert(!memcmp(output, golden, loaded));
	} else {
		assert(result != 0);
	}
	free(output);
	free(golden);
	assert(munmap(image.data, image.size) == 0);
	assert(close(fd) == 0);
	return 0;
}
