; Manual UAT program for emma65-peripherals Unit 3 (reusable cell-rendering
; architecture + static Port A row, emma65-via-playground). Not part of any
; package -- assembled standalone via ca65/ld65 into a ROM image; see
; README.md alongside this file for build/run instructions.
;
; This unit renders a static placeholder Port A row -- no live VIA pin
; traffic or interactivity yet -- so the program does nothing but keep the
; CPU running while the via/6522 device's socket stays up, same as Unit 2.

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
