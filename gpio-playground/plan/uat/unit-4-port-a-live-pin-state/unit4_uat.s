; Manual UAT program for emma65-peripherals Unit 4 (live pin-state for Port A
; data pins, emma65-via-playground). Not part of any package -- assembled
; standalone via ca65/ld65 into a ROM image; see README.md alongside this
; file for build/run instructions.
;
; Configures DDRA to $F0 (PA7-4 out, PA3-0 in), matching the playground's
; default --pa-direction, and walks a single bit through PA7-4 once a
; second so the panel's live chevron fill has real traffic to track.
;
; After a few cycles, it flips DDRA to $0F -- the *opposite* of what the
; panel still declares via --pa-direction -- and starts walking the bit
; through PA3-0 instead. This deliberately makes the panel's declared
; direction wrong: PA3-0 are now actually VIA outputs even though the panel
; still draws them as inputs. Since Unit 4 has no local drive of its own
; yet (that's Unit 5), nothing overloads -- but the chevron *fill* for
; PA3-0 should still track the real traffic, proving fill is read from live
; VIA state regardless of what direction the panel assumes.

.setcpu "w65c02"

VIA_BASE = $9000
VIA_ORA  = VIA_BASE + $1
VIA_DDRA = VIA_BASE + $3
VIA_T1CL = VIA_BASE + $4
VIA_T1CH = VIA_BASE + $5
VIA_ACR  = VIA_BASE + $B
VIA_IFR  = VIA_BASE + $D

VIA_T1_IRQ = $40
TIMER_PERIOD = 18432   ; ~10ms at the profiles' usual 1.8432MHz PHI2

.segment "CODE"

.global main
main:
    stz VIA_ACR              ; Timer 1 one-shot mode (re-armed by delay's outer loop)
    lda #$F0
    sta VIA_DDRA              ; PA7-4 out, PA3-0 in -- matches default --pa-direction

    ldx #4                    ; four walking-bit cycles through the upper nibble
    lda #$10
@upper_loop:
    sta VIA_ORA
    pha
    lda #100                 ; ~1s
    jsr delay
    pla
    asl a
    cmp #$00
    bne :+
    lda #$10                 ; wrapped past bit 7 -- restart at bit 4
:   dex
    bne @upper_loop

    lda #$0F
    sta VIA_DDRA              ; now PA3-0 out, PA7-4 in -- opposite of the
                               ; panel's still-declared --pa-direction $F0

    lda #$01
forever:
    sta VIA_ORA
    pha
    lda #100
    jsr delay
    pla
    asl a
    and #$0F
    bne :+
    lda #$01                 ; wrapped past bit 3 -- restart at bit 0
:   bra forever

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
