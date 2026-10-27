#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if len(sys.argv) != 2:
    raise SystemExit('usage: test-data-policy.py /path/to/guarded-linux')
src = Path(sys.argv[1]).resolve()
policy = (src / 'drivers/mmc/core/lumia930-audit.h').read_text()
constants = (src / 'include/linux/mmc/mmc.h').read_text()
names = set(re.findall(r'\b(?:MMC|EXT_CSD)_[A-Z0-9_]+\b', policy + (src / 'drivers/mmc/core/lumia930-data-range.h').read_text()))
names.add('EXT_CSD_PART_CONFIG_ACC_MASK')
defines = []
for name in sorted(names):
    match = re.search(r'^#define\s+' + name + r'\s+(.+)$', constants, re.M)
    assert match, name
    defines.append('#define ' + name + ' ' + match.group(1))
core = (src / 'drivers/mmc/core/core.c').read_text()
start = core.index('static void __mmc_start_request(')
end = core.index('\n\t/* Assumes host controller', start)
guard = core[start:end] + '\n    (void)err;\n    sent++;\n}\n'
body = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include "lumia930-audit.h"
#include "lumia930-data-range.h"
struct mmc_card { bool mmc, blockaddr; struct { unsigned cache_ctrl, part_config; } ext_csd; };
struct mmc_host { struct mmc_card *card; };
static bool mmc_card_mmc(struct mmc_card *c) { return c->mmc; }
static bool mmc_card_blockaddr(struct mmc_card *c) { return c->blockaddr; }
struct mmc_command { unsigned opcode, arg; int error; };
struct mmc_data { unsigned flags, blksz, blocks; };
struct mmc_request { struct mmc_command *cmd, *sbc, *stop; struct mmc_data *data; };
#define MMC_DATA_WRITE 256
#define pr_warn_ratelimited(...) ((void)0)
static unsigned sent, completed;
static void mmc_request_done(struct mmc_host *host, struct mmc_request *mrq) {
    (void)host;
    assert(mrq->cmd->error < 0);
    completed++;
}
'''
body += guard
body += r'''
int main(void) {
    unsigned cases = 0;
    const unsigned reads[] = {0,1,2,3,7,8,9,10,12,13,16,17,18,21,23};
    for (unsigned opcode=0; opcode<256; opcode++) {
        bool expected=false;
        for (unsigned n=0; n<sizeof(reads)/sizeof(reads[0]); n++)
            expected |= opcode == reads[n];
        assert(lumia930_mmc_audit_allowed(opcode, 0, false) == expected);
        assert(!lumia930_mmc_audit_allowed(opcode, UINT32_MAX, true));
        cases += 2;
    }
    for (unsigned access=0; access<4; access++)
    for (unsigned index=0; index<256; index++)
    for (unsigned value=0; value<256; value++)
    for (unsigned set=0; set<8; set++) {
        unsigned arg=(access<<24)|(index<<16)|(value<<8)|set;
        bool expected=access==3 && set==1 &&
            ((index==183 && value<=2) || (index==185 && value<=1) ||
             (index==187 && value<=15) || (index==33 && value==0) ||
             ((index==175 || index==34 || index==161) && value==1));
        assert(lumia930_mmc_audit_allowed(6, arg, false) == expected);
        assert(!lumia930_mmc_audit_allowed(6, arg, true));
        cases += 2;
    }
    for (unsigned bit=26; bit<32; bit++)
        assert(!lumia930_mmc_audit_allowed(6, (1u<<bit)|0x03b70001, false));
    struct mmc_host host={0};
    struct mmc_command cmd={17,0,0}, sbc={23,1,0}, stop={12,0,0};
    struct mmc_data data={0};
    struct mmc_request mrq={&cmd,&sbc,&stop,&data};
    __mmc_start_request(&host, &mrq);
    assert(sent==1 && completed==0);
    data.flags=MMC_DATA_WRITE;
    __mmc_start_request(&host, &mrq);
    assert(sent==1 && completed==1 && cmd.error==-EROFS);
    data.flags=0; cmd.error=0; sbc.opcode=24;
    __mmc_start_request(&host, &mrq);
    assert(sent==1 && completed==2);
    sbc.opcode=23; stop.opcode=38;
    __mmc_start_request(&host, &mrq);
    assert(sent==1 && completed==3);
    stop.opcode=12; cmd.opcode=6; cmd.arg=0x03a50101;
    __mmc_start_request(&host, &mrq);
    assert(sent==1 && completed==4 && cmd.error==-EBADMSG);
    struct mmc_card card={true,true,{0,0}};
    host.card=&card; cmd.opcode=25; cmd.arg=LUMIA930_DATA_FIRST;
    data.flags=MMC_DATA_WRITE; data.blksz=512; data.blocks=2; cmd.error=0;
    __mmc_start_request(&host,&mrq); assert(sent==2 && completed==4);
    cmd.arg=LUMIA930_DATA_END-1;
    __mmc_start_request(&host,&mrq); assert(sent==2 && completed==5);
    data.blocks=1; cmd.error=0;
    __mmc_start_request(&host,&mrq); assert(sent==3 && completed==5);
    card.ext_csd.cache_ctrl=1;
    __mmc_start_request(&host,&mrq); assert(sent==3 && completed==6);
    card.ext_csd.cache_ctrl=0; card.blockaddr=false;
    __mmc_start_request(&host,&mrq); assert(sent==3 && completed==7);
    card.blockaddr=true; card.ext_csd.part_config=1;
    __mmc_start_request(&host,&mrq); assert(sent==3 && completed==8);
    card.ext_csd.part_config=0; data.flags|=512;
    __mmc_start_request(&host,&mrq); assert(sent==3 && completed==9);
    unsigned positions[]={0,LUMIA930_DATA_FIRST-1,LUMIA930_DATA_FIRST,
        LUMIA930_DATA_FIRST+1,LUMIA930_DATA_END-2,LUMIA930_DATA_END-1,
        LUMIA930_DATA_END,UINT32_MAX};
    unsigned counts[]={0,1,2,511,65535,UINT32_MAX};
    for(unsigned op=0;op<256;op++)
    for(unsigned p=0;p<8;p++)
    for(unsigned c=0;c<6;c++)
    for(unsigned mask=0;mask<8;mask++) {
        unsigned sector=positions[p],n=counts[c];
        bool expected=(op==24||op==25)&&mask==7&&n&&
            (op!=24||n==1)&&sector>=5308416ULL&&
            (uint64_t)sector+n<=61071327ULL;
        assert(lumia930_mmc_data_write_allowed(op,sector,512,n,
            mask&1,mask&2,mask&4)==expected);
        assert(!lumia930_mmc_data_write_allowed(op,sector,4096,n,true,true,true));
        cases+=2;
    }
    puts("bounded submission, cache/partition/address mode, boundary/overflow checks passed");
    printf("%u total policy cases passed\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='lumia930-mmc-policy-') as tmp:
    work = Path(tmp)
    stub = work / 'linux/mmc'
    stub.mkdir(parents=True)
    (stub / 'mmc.h').write_text('\n'.join(defines) + '\n')
    (work / 'test.c').write_text(body)
    subprocess.run([os.environ.get('CC', 'clang'), '-std=c11', '-O1', '-Wall', '-Wextra',
                    '-Werror', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I', str(work), '-I', str(src / 'drivers/mmc/core'),
                    str(work / 'test.c'), '-o', str(work / 'test')], check=True)
    subprocess.run([str(work / 'test')], check=True, timeout=20)
block = (src / 'drivers/mmc/core/block.c').read_text()
assert 'md->read_only = mmc_blk_readonly(card);' in block
assert 'features = 0;' in block
assert 'BLK_FEAT_WRITE_CACHE' not in block[block.index('static struct mmc_blk_data *mmc_blk_alloc_req'):block.index('static struct mmc_blk_data *mmc_blk_alloc_req')+5000]
assert block.index('set_disk_ro(md->disk') < block.index('ret = add_disk_fwnode(')
assert 'req_op(req) != REQ_OP_WRITE' in block
assert 'MMC_DRV_OP_GET_EXT_CSD' in block
assert 'unsigned int cmd, unsigned long arg)\n{\n\treturn -EROFS;' in block
assert '/* no hardware partitions or RPMB in this build. */\n\treturn 0;' in block
assert 'int mmc_cqe_start_req(struct mmc_host *host, struct mmc_request *mrq)\n{\n\treturn -EROFS;' in core
print('no write-cache advertisement, raw ioctl/CQE denial and hardware-partition exclusion source checks passed')
