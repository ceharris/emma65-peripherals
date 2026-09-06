; Manual UAT program for emma65-peripherals Unit 7 (Port B joins the panel;
; combined two-port window, emma65-via-playground). Not part of any package
; -- assembled standalone via ca65/ld65 into a ROM image; see README.md
; alongside this file for build/run instructions.
;
; Configures DDRA/DDRB to match the panel's own --pa-direction/--pb-direction
; defaults ($F0, $38), so PA3-PA0 and PB2-PB0 are VIA inputs (the panel's
; toggle/momentary drive them directly, no contention) while PA7-PA4 and
; PB5-PB3 stay VIA-driven outputs this program never touches (they read back
; 0 regardless of the panel's toggle -- expected contention, not a bug; see
; README.md). Leaves PCR at its reset default ($00), making CA1/CA2/CB1/CB2
; all negative-edge-sensitive interrupt inputs, same as Unit 6.
;
; Polls IFR for CA1/CA2/CB1/CB2 edges and ORA/ORB for changes, printing to
; the console whenever any of them fires:
;   Cxx  - IFR & $1B just went nonzero (bit0=CA2 bit1=CA1 bit3=CB2 bit4=CB1)
;   Axx  - Port A's live level (ORA) changed to xx
;   Bxx  - Port B's live level (ORB) changed to xx
;
; IFR is checked *before* ORA/ORB each iteration, and must stay that way:
; with PCR left at $00, CA1/CB1's flags are unconditionally cleared by any
; ORA/ORB access, and CA2/CB2's are cleared too since PCR's independent-mode
; bits (bit3 for CA2, bit7 for CB2) are also 0. Reading ORA/ORB before
; checking IFR would silently wipe a control-pin edge before it's ever seen.

.setcpu "w65c02"

VIA_BASE     = $9000
VIA_ORB      = VIA_BASE + $0
VIA_ORA      = VIA_BASE + $1
VIA_DDRB     = VIA_BASE + $2
VIA_DDRA     = VIA_BASE + $3
VIA_PCR      = VIA_BASE + $C
VIA_IFR      = VIA_BASE + $D
VIA_ACR      = VIA_BASE + $B

CONSOLE_DATA = $9010

.segment "CODE"

.global main
main:
    stz VIA_ACR               ; no timer needed here -- this program just polls
    lda #$F0
    sta VIA_DDRA               ; PA7-PA4 out, PA3-PA0 in (matches --pa-direction default)
    lda #$38
    sta VIA_DDRB               ; PB5-PB3 out, PB2-PB0 in (matches --pb-direction default)
    stz VIA_PCR                ; reset default: CA1/CA2/CB1/CB2 all negative-edge inputs
    lda VIA_IFR
    sta VIA_IFR                 ; clear any flags already latched at reset
    lda #$FF
    sta last_a
    sta last_b                  ; force the first poll to print both ports' levels

; Order matters here: with PCR left at $00, CA1/CB1's IFR flags are
; unconditionally cleared by any ORA/ORB access, and CA2/CB2's are cleared
; too since PCR's independent-mode bits (bit3 for CA2, bit7 for CB2) are
; also 0 -- so IFR must be checked (and any set bits printed+cleared)
; *before* this same iteration touches ORA/ORB, or a control-pin edge that
; landed since the last iteration gets silently wiped by the ORA/ORB read
; below before ever being seen.
poll_loop:
    lda VIA_IFR
    and #$1B                   ; bit0=CA2 bit1=CA1 bit3=CB2 bit4=CB1
    beq check_a
    sta pending_flags
    lda #'C'
    sta CONSOLE_DATA
    lda pending_flags
    jsr print_hex_byte
    lda pending_flags
    sta VIA_IFR                 ; write 1s back to the bits we just saw -- clears them
check_a:
    lda VIA_ORA
    cmp last_a
    beq check_b
    sta last_a
    lda #'A'
    sta CONSOLE_DATA
    lda last_a
    jsr print_hex_byte
check_b:
    lda VIA_ORB
    cmp last_b
    beq poll_loop
    sta last_b
    lda #'B'
    sta CONSOLE_DATA
    lda last_b
    jsr print_hex_byte
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
last_a: .res 1
last_b: .res 1
pending_flags: .res 1

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
