; Manual UAT program for emma65-peripherals Unit 5 (Port A data-pin
; interactivity, emma65-via-playground). Not part of any package --
; assembled standalone via ca65/ld65 into a ROM image; see README.md
; alongside this file for build/run instructions.
;
; Configures DDRA to $00 -- all of Port A's data pins are VIA *inputs* --
; so the panel is the sole driver of every PA0-PA7 line via its toggle and
; momentary widgets. The program continuously reads ORA and, whenever the
; level changes, prints it as two hex digits to the console so the human
; reviewer can correlate what they clicked in the panel with what actually
; arrived at the VIA, independent of the pygame window.

.setcpu "w65c02"

VIA_BASE     = $9000
VIA_ORA      = VIA_BASE + $1
VIA_DDRA     = VIA_BASE + $3
VIA_ACR      = VIA_BASE + $B

CONSOLE_DATA = $9010

.segment "CODE"

.global main
main:
    stz VIA_ACR              ; no timer needed here -- this program just polls
    stz VIA_DDRA              ; PA0-7 all inputs -- the panel drives every bit

    lda VIA_ORA
    sta last_level
    jsr print_hex_byte        ; report the initial level before anything changes

poll_loop:
    lda VIA_ORA
    cmp last_level
    beq poll_loop
    sta last_level
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
last_level: .res 1

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
