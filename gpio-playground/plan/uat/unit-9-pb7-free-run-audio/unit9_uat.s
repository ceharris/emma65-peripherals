; Manual UAT program for emma65-peripherals Unit 9 (PB7 free-run indicator
; and audio output, emma65-via-playground). Not part of any package --
; assembled standalone via ca65/ld65 into a ROM image; see README.md
; alongside this file for build/run instructions.
;
; Configures DDRA=$00, DDRB=$00 (every Port A/B bit, including PB7, is a
; declared VIA input) and ACR bits 7,6 = 1 (Timer 1 free-run mode with PB7
; square-wave output). Confirmed against emma65-rust's own
; src/emulator/device/via6522.rs before writing this, not guessed:
;   - ACR_T1_PB7_OUTPUT (bit 7, $80) makes T1 toggle PB7's internal state on
;     every underflow; T1_MODE_FREE_RUN (bit 6, $40) makes T1 reload from its
;     latch and keep running instead of stopping after one underflow. Both
;     bits are needed together for a continuous audible square wave.
;   - read_port_b()'s own comment confirms this "takes priority over
;     input/output mode selected by DDRB bit 7" -- i.e. PB7's output is
;     genuinely independent of DDRB7, exactly as the design doc claims. This
;     ROM deliberately declares DDRB7 as an input (DDRB=$00) to demonstrate
;     that, rather than declaring it an output to match.
;   - Writing T1C-H ($9005) loads the counter from both latches, starts the
;     timer, and immediately drives PB7 low -- writing T1C-L ($9004) first
;     just primes the low latch without starting anything, standard 6522
;     two-register start sequence.
;
; T1 counts down once per clock cycle, toggling PB7 every time it reaches
; zero and then reloading from the latch (free-run) -- so PB7's half-period
; is T1_RELOAD clock cycles. At this ROM's emulator.toml clock-speed-hz
; (1843200), T1_RELOAD=2095 gives:
;   frequency = clock / (2 * T1_RELOAD) = 1843200 / 4190 ~= 439.9 Hz
; i.e. close to musical A4 (440 Hz).
;
; Once configured, T1's free-run/PB7-toggle mode needs no further CPU
; involvement -- the tone keeps playing entirely in VIA hardware, so this
; ROM prints one confirmation line to the console and then idles forever.

.setcpu "w65c02"

VIA_BASE     = $9000
VIA_DDRB     = VIA_BASE + $2
VIA_DDRA     = VIA_BASE + $3
VIA_T1CL     = VIA_BASE + $4
VIA_T1CH     = VIA_BASE + $5
VIA_ACR      = VIA_BASE + $B
VIA_PCR      = VIA_BASE + $C

CONSOLE_DATA = $9010

T1_RELOAD    = 2095   ; ~439.9 Hz square wave -- see header comment

.segment "CODE"

.global main
main:
    stz VIA_DDRA
    stz VIA_DDRB                 ; PB0-PB7 all declared VIA inputs, including
                                  ; PB7 -- see header comment on DDR independence
    stz VIA_PCR                  ; not exercised by this UAT; reset default
    lda #%11000000
    sta VIA_ACR                  ; ACR bits 7,6 = 1: T1 free-run + PB7 square-wave output
    lda #<T1_RELOAD
    sta VIA_T1CL                 ; T1 low-order latch (does not start the timer)
    lda #>T1_RELOAD
    sta VIA_T1CH                 ; loads the counter from both latches, starts
                                  ; T1, and drives PB7 low immediately

    ldx #0
print_banner:
    lda banner, x
    beq idle
    sta CONSOLE_DATA
    inx
    bra print_banner

idle:
    bra idle                     ; T1 free-run needs no further CPU involvement
                                  ; from here -- the VIA hardware keeps toggling
                                  ; PB7 on its own

.segment "RODATA"
banner: .byte "T1 free-run: ACR=C0 T1=082F", $0D, $0A, 0

.segment "MACHVECS"
    .word main   ; NMI (unused)
    .word main   ; RESET
    .word main   ; IRQ/BRK (unused -- IER is never enabled, so this never fires)
