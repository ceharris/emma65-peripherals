; Manual UAT program for emma65-peripherals Unit 8 (PB6 pulse-counting
; layered behavior, emma65-via-playground). Not part of any package --
; assembled standalone via ca65/ld65 into a ROM image; see README.md
; alongside this file for build/run instructions.
;
; Configures DDRA=$00, DDRB=$00 (every Port A/B bit, including PB6, is a VIA
; input) and ACR bit5=1 (Timer 2 pulse-counting mode): T2 counts every
; high-to-low transition on PB6, real 6522 behavior confirmed as emulated by
; emma65's published docs (io-devices.html: "Timer 2 supports one-shot and
; pulse-counting modes"). T2 is reloaded from a small count (5) each time it
; wraps, so a human can walk the counter down to a wrap event with a handful
; of clicks and watch it reload, rather than needing dozens of presses.
;
; Polls and prints to the console whenever any of these change:
;   Txx  - T2's low counter byte (T2C-L) changed to xx (one decrement per
;          PB6 high->low edge -- i.e. per momentary press's leading edge,
;          in both level and pulse mode; releases don't count, since they're
;          low->high)
;   Wxx  - T2 just wrapped (its IFR flag fired) with T2C-L reading xx ($FF,
;          since it undeflowed from 0) -- printed once, then T2 is reloaded
;          (a following Txx line for the reload value always follows)
;   Pxx  - Port B's PB6 bit alone (ORB & $40) changed to xx ($40 = high/idle
;          pulled-up, $00 = low/active)
;
; IFR must be read before T2C-L in each iteration, mirroring Unit 7's IFR-
; before-ORA/ORB ordering lesson: reading T2C-L clears T2's own IFR flag as
; a side effect (same real-6522 behavior as reading ORA/ORB clearing
; CA1/CA2/CB1/CB2), so checking IFR after would silently miss a wrap that
; landed since the last iteration.

.setcpu "w65c02"

VIA_BASE     = $9000
VIA_ORB      = VIA_BASE + $0
VIA_DDRB     = VIA_BASE + $2
VIA_DDRA     = VIA_BASE + $3
VIA_T2CL     = VIA_BASE + $8
VIA_T2CH     = VIA_BASE + $9
VIA_ACR      = VIA_BASE + $B
VIA_PCR      = VIA_BASE + $C
VIA_IFR      = VIA_BASE + $D

CONSOLE_DATA = $9010

T2_RELOAD    = 5    ; small on purpose -- a handful of clicks reaches a wrap

.segment "CODE"

.global main
main:
    stz VIA_DDRA
    stz VIA_DDRB                ; PB0-PB7 all VIA inputs, including PB6
    stz VIA_PCR                 ; not exercised by this UAT; reset default
    lda #%00100000
    sta VIA_ACR                  ; ACR bit5=1: T2 pulse-counting mode
    jsr reload_t2
    lda VIA_IFR
    sta VIA_IFR                  ; clear any flags already latched at reset
    lda #$FF
    sta last_t2                  ; force the first poll to print T2's value
    stz last_pb6

poll_loop:
    lda VIA_IFR
    and #$20                    ; bit5 = T2 -- snapshot before T2C-L read below
    beq check_t2cl               ; auto-clears it (see header comment)
    lda #$20
    sta VIA_IFR                  ; ack (write-1-to-clear) T2's flag
    lda #'W'
    sta CONSOLE_DATA
    lda VIA_T2CL
    jsr print_hex_byte
    jsr reload_t2                ; next Txx line (below) shows the reload

check_t2cl:
    lda VIA_T2CL
    cmp last_t2
    beq check_pb6
    sta last_t2
    lda #'T'
    sta CONSOLE_DATA
    lda last_t2
    jsr print_hex_byte

check_pb6:
    lda VIA_ORB
    and #$40
    cmp last_pb6
    beq poll_loop
    sta last_pb6
    lda #'P'
    sta CONSOLE_DATA
    lda last_pb6
    jsr print_hex_byte
    bra poll_loop

reload_t2:
    lda #<T2_RELOAD
    sta VIA_T2CL
    lda #>T2_RELOAD
    sta VIA_T2CH                 ; latches T2C-L into the counter, clears T2's IFR flag
    rts

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
last_t2: .res 1
last_pb6: .res 1

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
