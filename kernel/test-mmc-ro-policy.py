#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import os
from pathlib import Path
import re
import subprocess
import tempfile
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: test-mmc-ro-policy.py /path/to/read-only-linux')
src = Path(sys.argv[1]).resolve()
policy = (src / 'drivers/mmc/core/lumia930-audit.h').read_text()
constants = (src / 'include/linux/mmc/mmc.h').read_text()
names = set(re.findall(r'\b(?:MMC|EXT_CSD)_[A-Z0-9_]+\b', policy))
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
struct mmc_host { int unused; };
struct mmc_command { unsigned opcode, arg; int error; };
struct mmc_data { unsigned flags; };
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
             (index==187 && value<=15) ||
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
    printf("%u policy cases plus request-path rejection tests passed\n",cases);
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
assert 'md->read_only = true;' in block
assert block.index('set_disk_ro(md->disk') < block.index('ret = add_disk_fwnode(')
assert 'if (req_op(req) != REQ_OP_READ)\n\t\treturn MMC_REQ_FAILED_TO_START;' in block
assert 'unsigned int cmd, unsigned long arg)\n{\n\treturn -EROFS;' in block
assert 'if (md->read_only)\n\t\treturn 0;' in block
assert 'int mmc_cqe_start_req(struct mmc_host *host, struct mmc_request *mrq)\n{\n\treturn -EROFS;' in core
print('block read-only publication, queue guard, raw ioctl/CQE denial and hardware-partition exclusion checks passed')
