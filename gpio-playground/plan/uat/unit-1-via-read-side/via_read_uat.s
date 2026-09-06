; Manual UAT program for emma65-peripherals Unit 1 (VIA protocol read-side
; support in emma65_via). Not part of any package -- assembled standalone
; via ca65/ld65 into a ROM image; see README.md alongside this file for
; build/run instructions.
;
; Exercises the VIA peer protocol's data-port and control-pin wire messages
; so `ViaAsciiClient.poll()` has real traffic to decode: toggles Port A's
; data pins between two patterns and CA2 between high/low, forever, pausing
; roughly a second between each change (using VIA Timer 1, polled via IFR).

.setcpu "w65c02"

VIA_BASE = $9000
VIA_ORA  = VIA_BASE + $1
VIA_DDRA = VIA_BASE + $3
VIA_T1CL = VIA_BASE + $4
VIA_T1CH = VIA_BASE + $5
VIA_ACR  = VIA_BASE + $B
VIA_PCR  = VIA_BASE + $C
VIA_IFR  = VIA_BASE + $D

VIA_T1_IRQ = $40
TIMER_PERIOD = 18432   ; ~10ms at the profiles' usual 1.8432MHz PHI2

CA2_MANUAL_HIGH = $0E  ; PCR CA2 control bits (3:1) = 111: manual output, high
CA2_MANUAL_LOW  = $0C  ; PCR CA2 control bits (3:1) = 110: manual output, low

.segment "CODE"

.global main
main:
    stz VIA_ACR              ; Timer 1 one-shot mode (re-armed by delay's outer loop)
    lda #$FF
    sta VIA_DDRA              ; PA0-7 all outputs

loop:
    lda #$55
    sta VIA_ORA
    lda #CA2_MANUAL_HIGH
    sta VIA_PCR
    lda #100                 ; ~1s
    jsr delay

    lda #$AA
    sta VIA_ORA
    lda #CA2_MANUAL_LOW
    sta VIA_PCR
    lda #100
    jsr delay

    bra loop

; Uses VIA Timer 1 to delay for at least A * 10ms.
delay:
    phx
    tax
@outer:
    lda #<TIMER_PERIOD
    sta VIA_T1CL
    lda #>TIMER_PERIOD
    sta VIA_T1CH
@inner:
    lda VIA_IFR
    and #VIA_T1_IRQ
    beq @inner
    dex
    bne @outer
    plx
    rts

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
