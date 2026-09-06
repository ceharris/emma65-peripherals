; Manual UAT program for emma65-peripherals Unit 7 (Port B joins the panel;
; combined two-port window, emma65-via-playground). Not part of any package
; -- assembled standalone via ca65/ld65 into a ROM image; see README.md
; alongside this file for build/run instructions.
;
; Configures DDRA=$00 and DDRB=$00 -- ALL of PA0-PA7 and PB0-PB5 are declared
; VIA *inputs* for this UAT (see README.md for why: it keeps every data-pin
; write from the panel fully visible in ORA/ORB, which the CA1/CB1 filtering
; below depends on). Run the peripheral with --pa-direction 00 --pb-direction
; 00 to match. This intentionally sidesteps VIA-output/contention scenarios
; (Unit 10's territory, and the subject of a separate bug report against
; emma65 itself: PortState broadcasts don't yet compose DDR correctly when a
; peripheral, rather than the 6502 program, changes port data).
;
; Leaves PCR at its reset default ($00), making CA1/CA2/CB1/CB2 all
; negative-edge-sensitive interrupt inputs, same as Unit 6.
;
; Polls IFR for CA1/CA2/CB1/CB2 edges and ORA/ORB for changes, printing to
; the console whenever any of them fires:
;   Cxx  - a genuine CA1/CA2/CB1/CB2 edge (bit0=CA2 bit1=CA1 bit3=CB2 bit4=CB1)
;   Axx  - Port A's live level (ORA) changed to xx
;   Bxx  - Port B's live level (ORB) changed to xx
;
; Two emulator quirks this program has to work around, both confirmed by
; reading emma65's via6522.rs directly rather than assuming datasheet
; behavior:
;
; 1. Reading ORA/ORB clears IFR flags as a side effect: ORA always clears
;    CA1, and clears CA2 too since PCR's independent-mode bit is 0
;    (dependent mode); ORB does the same for CB1/CB2. IFR must be read
;    *before* ORA/ORB each iteration, or a control-pin edge gets silently
;    wiped before this program ever sees it.
;
; 2. emma65 deliberately sets IRQ_CA1 on *any* Port A data change (and
;    IRQ_CB1 on any Port B data change) -- "data + strobe bundled in one
;    message", documented as intentional in emma65's own
;    plan/6522-via-edge-cases.md, not something to work around upstream.
;    That means an ordinary PAx/PBx toggle/momentary click also flags
;    CA1/CB1, even though it has nothing to do with the CA1/CB1 control
;    lines. This program filters that out: a genuine CA1/CB1 edge (sent as
;    its own SC/RC message) never coincides with an ORA/ORB change in the
;    same poll iteration, since those are separate wire messages -- so if
;    ORA changed this iteration, the CA1 bit in this iteration's IFR read is
;    presumed to be that data write's side effect and is not printed (same
;    for ORB/CB1). This is why DDRA/DDRB are $00 above: a data bit declared
;    a VIA *output* would still flip IRQ_CA1/CB1 on a panel click without
;    ever showing up in ORA/ORB (DDR masks it out of the read), defeating
;    this filter.

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
    stz VIA_ACR                ; no timer needed here -- this program just polls
    stz VIA_DDRA                ; PA0-PA7 all VIA inputs -- see header comment
    stz VIA_DDRB                ; PB0-PB5 all VIA inputs -- see header comment
    stz VIA_PCR                 ; reset default: CA1/CA2/CB1/CB2 all negative-edge inputs
    lda VIA_IFR
    sta VIA_IFR                  ; clear any flags already latched at reset
    lda #$FF
    sta last_a
    sta last_b                   ; force the first poll to print both ports' levels

poll_loop:
    lda VIA_IFR
    and #$1B                    ; bit0=CA2 bit1=CA1 bit3=CB2 bit4=CB1 -- snapshot
    sta pending_flags            ; *before* the ORA/ORB reads below, which auto-clear
                                  ; all four flags (see header comment, point 1)
    lda VIA_ORA
    sta cur_a
    lda VIA_ORB
    sta cur_b

    ; Strip CA1/CB1 out of pending_flags if this iteration's data read also
    ; changed -- that means the emulator's data+strobe coupling (header
    ; comment, point 2), not a genuine CA1/CB1 control-pin edge.
    lda cur_a
    cmp last_a
    beq keep_ca1
    lda pending_flags
    and #%11111101               ; strip CA1 (bit1)
    sta pending_flags
keep_ca1:
    lda cur_b
    cmp last_b
    beq keep_cb1
    lda pending_flags
    and #%11101111               ; strip CB1 (bit4)
    sta pending_flags
keep_cb1:

    lda pending_flags
    beq check_a
    pha
    lda #'C'
    sta CONSOLE_DATA
    pla
    jsr print_hex_byte

check_a:
    lda cur_a
    cmp last_a
    beq check_b
    sta last_a
    lda #'A'
    sta CONSOLE_DATA
    lda last_a
    jsr print_hex_byte
check_b:
    lda cur_b
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
cur_a: .res 1
cur_b: .res 1
pending_flags: .res 1

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
