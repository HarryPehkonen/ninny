; Implement this file.
;
; Makefile, tools/ and tests/own/README.md are frozen. Everything you write goes here and
; in tests/own/.
;
; This stub assembles as it stands and exits 0 -- a stub that builds, not a build error --
; so your first own-test run is a test that ran and failed, which is what a RED observation
; is supposed to be.
;
; On entry, rsp points at argc, and argv[1] is at [rsp+16]. Leave the exit status in edi
; and call syscall 60.

global _start

section .text
_start:
    mov edi, 0
    mov eax, 60
    syscall
