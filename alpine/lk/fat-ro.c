// SPDX-License-Identifier: BSD-3-Clause
#include "fat-ro.h"
#include <string.h>

static uint16_t le16(const uint8_t *p)
{
	return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}

static uint32_t le32(const uint8_t *p)
{
	return le16(p) | (uint32_t)le16(p + 2) << 16;
}

static int read_at(struct fat_ro *fs, uint64_t offset, void *buf, size_t len)
{
	if (offset > fs->bytes || len > fs->bytes - offset)
		return -1;
	return fs->read(fs->context, offset, buf, len);
}

int fat_ro_mount(struct fat_ro *fs, fat_ro_read_fn read, void *context,
		 uint64_t bytes)
{
	uint8_t b[512];
	uint32_t total, reserved, fats, root_sectors, sectors;
	uint64_t data;

	memset(fs, 0, sizeof(*fs));
	fs->read = read;
	fs->context = context;
	fs->bytes = bytes;
	if (!read || bytes < 512 || bytes % 512 || read_at(fs, 0, b, sizeof(b)))
		return -1;
	if (le16(b + 510) != 0xaa55 || le16(b + 11) != 512)
		return -1;
	sectors = b[13];
	reserved = le16(b + 14);
	fats = b[16];
	total = le16(b + 19);
	if (!total)
		total = le32(b + 32);
	fs->fat_sectors = le16(b + 22);
	if (!fs->fat_sectors)
		fs->fat_sectors = le32(b + 36);
	fs->root_entries = le16(b + 17);
	root_sectors = (fs->root_entries * 32 + 511) / 512;
	data = (uint64_t)reserved + (uint64_t)fats * fs->fat_sectors + root_sectors;
	if (!sectors || sectors > 128 || (sectors & (sectors - 1)) ||
	    !reserved || !fats || fats > 2 || !fs->fat_sectors ||
	    !total || (uint64_t)total * 512 > bytes || data >= total)
		return -1;
	fs->clusters = (uint32_t)((total - data) / sectors);
	fs->bits = fs->clusters < 65525 ? 16 : 32;
	if (fs->clusters < 4085 || fs->clusters >= 0x0ffffff0 - 2)
		return -1;
	if ((uint64_t)(fs->clusters + 2) * (fs->bits / 8) > (uint64_t)fs->fat_sectors * 512)
		return -1;
	fs->fat = reserved;
	fs->data = (uint32_t)data;
	fs->sectors_per_cluster = sectors;
	fs->bytes = (uint64_t)total * 512;
	if (fs->bits == 16) {
		if (!fs->root_entries || !le16(b + 22))
			return -1;
		fs->root = reserved + fats * fs->fat_sectors;
	} else {
		uint32_t flags = le16(b + 40);

		if (fs->root_entries || le16(b + 22) || le16(b + 42))
			return -1;
		if (flags & 0x80) {
			unsigned active = flags & 15;

			if (active >= fats)
				return -1;
			fs->fat += active * fs->fat_sectors;
		}
		fs->root = le32(b + 44);
		if (fs->root < 2 || fs->root - 2 >= fs->clusters)
			return -1;
	}
	return 0;
}

static int cluster_valid(struct fat_ro *fs, uint32_t cluster)
{
	return cluster >= 2 && cluster - 2 < fs->clusters &&
	       cluster < (fs->bits == 16 ? 0xfff0U : 0x0ffffff0U);
}

static uint64_t cluster_offset(struct fat_ro *fs, uint32_t cluster)
{
	return ((uint64_t)fs->data + (uint64_t)(cluster - 2) * fs->sectors_per_cluster) * 512;
}

static int next_cluster(struct fat_ro *fs, uint32_t cluster, uint32_t *next)
{
	uint8_t b[4];
	uint32_t value, end = fs->bits == 16 ? 0xfff8 : 0x0ffffff8;
	unsigned width = fs->bits / 8;

	if (!cluster_valid(fs, cluster) ||
	    read_at(fs, (uint64_t)fs->fat * 512 + (uint64_t)cluster * width, b, width))
		return -1;
	value = fs->bits == 16 ? le16(b) : le32(b) & 0x0fffffff;
	if (value >= end)
		return 1;
	if (value >= end - 8 || !cluster_valid(fs, value))
		return -1;
	*next = value;
	return 0;
}

static int short_name(const char *name, size_t len, uint8_t out[11])
{
	unsigned base = 0, ext = 0, dot = 0;

	memset(out, ' ', 11);
	for (size_t i = 0; i < len; i++) {
		unsigned char c = (unsigned char)name[i];

		if (c == '.') {
			if (dot || !base)
				return -1;
			dot = 1;
			continue;
		}
		if (c >= 'a' && c <= 'z')
			c -= 'a' - 'A';
		if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
		      c == '_' || c == '-' || c == '~'))
			return -1;
		if (dot) {
			if (ext == 3)
				return -1;
			out[8 + ext++] = c;
		} else {
			if (base == 8)
				return -1;
			out[base++] = c;
		}
	}
	return base && (!dot || ext) ? 0 : -1;
}

static int find_entry(struct fat_ro *fs, uint32_t dir, const uint8_t name[11],
		      uint8_t entry[32])
{
	uint8_t b[512];
	uint32_t hops = 0, scanned = 0, entries = 0;
	unsigned count = dir ? fs->sectors_per_cluster : (fs->root_entries + 15) / 16;

	do {
		uint64_t offset;

		if (dir && !cluster_valid(fs, dir))
			return -1;
		offset = dir ? cluster_offset(fs, dir) : (uint64_t)fs->root * 512;
		for (unsigned sector = 0; sector < count; sector++) {
			if (++scanned > 1024 || read_at(fs, offset + sector * 512, b, sizeof(b)))
				return -1;
			for (unsigned i = 0; i < 512; i += 32) {
				if (!dir && entries++ == fs->root_entries)
					return -1;
				if (!b[i])
					return -1;
				if (b[i] == 0xe5 || (b[i + 11] & 8))
					continue;
				if (!memcmp(b + i, name, 11)) {
					memcpy(entry, b + i, 32);
					return 0;
				}
			}
		}
		if (!dir || ++hops >= fs->clusters)
			return -1;
	} while (next_cluster(fs, dir, &dir) == 0);
	return -1;
}

int fat_ro_load(struct fat_ro *fs, const char *path, void *buffer, size_t capacity,
		size_t *size)
{
	uint8_t name[11], entry[32];
	uint32_t dir = fs->bits == 16 ? 0 : fs->root, cluster, bytes;
	size_t left, position = 0;
	unsigned depth = 0;

	if (!path || !buffer || !size)
		return -1;
	*size = 0;
	if (*path == '/')
		path++;
	for (;;) {
		const char *end = strchr(path, '/');
		size_t len = end ? (size_t)(end - path) : strlen(path);

		if (++depth > 8 || short_name(path, len, name) || find_entry(fs, dir, name, entry))
			return -1;
		cluster = le16(entry + 26);
		if (fs->bits == 32)
			cluster |= (uint32_t)le16(entry + 20) << 16;
		if (!end) {
			if (entry[11] & 0x10)
				return -1;
			break;
		}
		if (!(entry[11] & 0x10) || !cluster_valid(fs, cluster))
			return -1;
		dir = cluster;
		path = end + 1;
	}
	bytes = le32(entry + 28);
	if (bytes > capacity)
		return -1;
	left = bytes;
	for (uint32_t hop = 0; left; hop++) {
		size_t chunk = (size_t)fs->sectors_per_cluster * 512;
		int next;

		if (hop >= fs->clusters || !cluster_valid(fs, cluster))
			return -1;
		if (chunk > left)
			chunk = left;
		if (read_at(fs, cluster_offset(fs, cluster), (uint8_t *)buffer + position, chunk))
			return -1;
		position += chunk;
		left -= chunk;
		next = next_cluster(fs, cluster, &cluster);
		if ((left && next != 0) || (!left && next != 1))
			return -1;
	}
	*size = bytes;
	return 0;
}
