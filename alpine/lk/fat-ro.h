// SPDX-License-Identifier: BSD-3-Clause
#ifndef LUMIA_FAT_RO_H
#define LUMIA_FAT_RO_H
#include <stddef.h>
#include <stdint.h>

typedef int (*fat_ro_read_fn)(void *, uint64_t, void *, size_t);

struct fat_ro {
	fat_ro_read_fn read;
	void *context;
	uint64_t bytes;
	uint32_t fat, fat_sectors, data, root, root_entries;
	uint32_t clusters, sectors_per_cluster;
	unsigned bits;
};

int fat_ro_mount(struct fat_ro *, fat_ro_read_fn, void *, uint64_t);
int fat_ro_load(struct fat_ro *, const char *, void *, size_t, size_t *);
#endif
