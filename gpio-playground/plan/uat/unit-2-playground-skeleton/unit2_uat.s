; Manual UAT program for emma65-peripherals Unit 2 (new peripheral skeleton,
; emma65-via-playground). Not part of any package -- assembled standalone via
; ca65/ld65 into a ROM image; see README.md alongside this file for build/run
; instructions.
;
; This unit only proves the peripheral's connection plumbing, not any VIA
; pin traffic, so the program does nothing but keep the CPU running.

.setcpu "w65c02"

.segment "CODE"

.global main
main:
loop:
    bra loop

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused)
