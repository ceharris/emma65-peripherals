; Manual UAT program for emma65-peripherals Unit 6 (Port A control-cell
; interactivity, emma65-via-playground). Not part of any package --
; assembled standalone via ca65/ld65 into a ROM image; see README.md
; alongside this file for build/run instructions.
;
; Leaves PCR at its reset default ($00): CA1 is a negative-edge-sensitive
; interrupt input, and CA2 is a negative-edge-sensitive interrupt input in
; non-independent mode (so reading ORA would also clear its flag, though
; this program clears IFR directly instead and never touches ORA).
;
; With PCR fixed to negative-edge detection, only a high-to-low transition
; on CA1/CA2 sets that pin's IFR flag -- of the two transitions in a single
; press+release (or a pulse-mode press), exactly one of them is always a
; high-to-low edge regardless of which polarity the panel's momentary is
; set to, so every interaction produces at least one detectable edge:
;   - rising polarity (idle low, active high): the *release* (or pulse's
;     auto-revert) is the high-to-low edge that gets caught.
;   - falling polarity (idle high, active low): the *press* is the
;     high-to-low edge that gets caught.
; This program polls IFR bits 0 (CA2) and 1 (CA1), prints the masked byte
; as two hex digits whenever either goes high, then clears just those bits
; by writing them back to IFR (the documented way to clear IFR flags,
; independent of PCR's auto-clear-on-ORA-read behavior).

.setcpu "w65c02"

VIA_BASE     = $9000
VIA_DDRA     = VIA_BASE + $3
VIA_PCR      = VIA_BASE + $C
VIA_IFR      = VIA_BASE + $D
VIA_ACR      = VIA_BASE + $B

CONSOLE_DATA = $9010

.segment "CODE"

.global main
main:
    stz VIA_ACR              ; no timer needed here -- this program just polls
    stz VIA_DDRA              ; PA0-7 unused by this UAT; leave as inputs
    stz VIA_PCR               ; reset default: CA1/CA2 both negative-edge inputs
    lda VIA_IFR
    sta VIA_IFR                ; clear any flags already latched at reset

poll_loop:
    lda VIA_IFR
    and #$03                  ; bit0 = CA2, bit1 = CA1
    beq poll_loop
    sta pending_flags
    jsr print_hex_byte
    lda pending_flags
    sta VIA_IFR                ; write 1s back to the bits we just saw -- clears them
    bra poll_loop

; Prints A as two upper-case hex digits followed by CRLF, via the console
; device's data register (raw byte writes -- no transport framing).
print_hex_byte:
    pha
    lsr a
    lsr a
    lsr a
    lsr a
    and #$0F
    tax
    lda hex_digits, x
    sta CONSOLE_DATA
    pla
    and #$0F
    tax
    lda hex_digits, x
    sta CONSOLE_DATA
    lda #$0D
    sta CONSOLE_DATA
    lda #$0A
    sta CONSOLE_DATA
    rts

.segment "RODATA"
hex_digits: .byte "0123456789ABCDEF"

.segment "DATA"
pending_flags: .res 1

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
