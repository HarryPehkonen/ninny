; A reference implementation of the nasm-sum task -- the answer key.
;
; It exists for one reason: to prove the acceptance corpus can pass. An oracle that only
; ever fails is not evidence of anything, so `ninny verify-task` runs the corpus against
; this.
;
;   build/sum <a> <b>   exit (a + b) & 0xFF, for a, b decimal in 0..=127
;   anything else       exit 2
;   no output, ever
;
; No libc: ld links this without -lc, and the only kernel service used is exit_group.
;
; Leading zeros are fine, so they are skipped before the accumulator starts and before the
; digit count: "007" is 7 and "0128" is rejected for being 128, not for being long. All
; zeros is zero. The three-digit cap applies to SIGNIFICANT digits only, which is why a
; value above 127 cannot wrap the accumulator.

global _start

section .text
_start:
    mov  rax, [rsp]             ; argc
    cmp  rax, 3                 ; program, a, b
    jne  .reject

    mov  rdi, [rsp + 16]        ; argv[1]
    call parse
    test edx, edx
    jnz  .reject
    mov  r8d, eax               ; keep the first value

    mov  rdi, [rsp + 24]        ; argv[2]
    call parse
    test edx, edx
    jnz  .reject

    add  eax, r8d
    and  eax, 0xFF              ; exit statuses are a byte
    mov  edi, eax
    jmp  .exit

.reject:
    mov  edi, 2

.exit:
    mov  eax, 60                ; exit_group
    syscall

; parse: rdi -> NUL-terminated string
;   out: eax = value, edx = 0 when it is a decimal in 0..=127, 1 otherwise
; clobbers: rax, rcx, rdx, rsi, rdi, r9
parse:
    xor  eax, eax               ; the value
    xor  ecx, ecx               ; significant digits accumulated
    xor  r9d, r9d               ; how many digits were seen at all
.digit:
    movzx esi, byte [rdi]
    test esi, esi
    jz   .end                   ; NUL
    sub  esi, '0'
    cmp  esi, 9
    ja   .bad                   ; not an ASCII digit
    inc  r9d
    inc  rdi
    test ecx, ecx
    jnz  .accumulate
    test esi, esi
    jz   .digit                 ; a leading zero: true, but not significant
.accumulate:
    imul eax, eax, 10
    add  eax, esi
    inc  ecx
    cmp  ecx, 3
    ja   .bad                   ; four significant digits is beyond 127 for certain
    jmp  .digit
.end:
    test r9d, r9d
    jz   .bad                   ; the empty string is not a number
    cmp  eax, 127
    ja   .bad                   ; in range, or rejected: never truncated
    xor  edx, edx
    ret
.bad:
    mov  edx, 1
    ret
