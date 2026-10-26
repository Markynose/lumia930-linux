.syntax unified
.arch armv7-a
.arm
.section .text
.global _start
_start:
	ldr r0, =0x7cc4c000
	mrc p15, 0, r1, c0, c0, 5
	str r1, [r0]
	ldr r0, =0xf9002000
	ldr r1, [r0, #0x0c]
	ubfx r2, r1, #0, #10
	cmp r2, #1
	streq r1, [r0, #0x10]
	ldr r0, =0x304000
	mvn r1, #0
	str r1, [r0]
	dsb sy
	ldr r0, =0x7cc82de0
	ldr r1, =0x930c0003
	str r1, [r0]
	dsb sy
	ldr r0, =0x304800
	bx r0
	.ltorg
