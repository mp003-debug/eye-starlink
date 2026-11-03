# Narrow review of the six RGB565/GRAY8 VDMA hard-FIFO primitive CDC-13 findings.
# Raw report is retained; no severity changes, broad CDC waivers or false paths.
# UG953 FIFO36E1: EN_SYN=0 uses the dedicated independent-clock FIFO mechanism.
proc review_ddr_cdc {cdc reports} {
    set count 0
    foreach line [split $cdc "\n"] {
        if {[regexp {^\s+[0-9]+\s+(CDC-[0-9]+)\s+Critical\s+} $line -> id]} {
            if {$id ne "CDC-13" || ![regexp {False Path\s+(\S+)\s+(\S+)\s*$} $line -> src dst]} {
                error "Unreviewed critical CDC: $line"
            }
            foreach endpoint [list $src $dst] {
                if {![string match {*vdma_0/U0/GEN_SPRT_FOR_*.I_LINEBUFFER_FIFO/fg_builtin_fifo_inst/*} $endpoint]} {
                    error "Critical CDC outside reviewed VDMA hard FIFO: $line"
                }
            }
            incr count
        }
    }
    if {$count != 6} {error "VDMA CDC findings changed ($count instead of 6): review required"}
    set cells [get_cells -hier -filter {REF_NAME == FIFO36E1 && NAME =~ *vdma_0*I_LINEBUFFER_FIFO*}]
    if {[llength $cells] != 6} {error "Expected six reviewed VDMA FIFO36E1 primitives"}
    set mm2s [get_cells -hier -filter {REF_NAME == FIFO36E1 && NAME =~ *vdma_0*GEN_SPRT_FOR_MM2S*I_LINEBUFFER_FIFO*}]
    set s2mm [get_cells -hier -filter {REF_NAME == FIFO36E1 && NAME =~ *vdma_0*GEN_SPRT_FOR_S2MM*I_LINEBUFFER_FIFO*}]
    if {[llength $mm2s] != 4 || [llength $s2mm] != 2} {error "RGB565 FIFO allocation changed; expected MM2S=4 S2MM=2"}
    set f [open [file join $reports cdc_review.txt] w]
    puts $f "Configuration: MM2S RGB565/16-bit, S2MM GRAY8/8-bit, linebuffer_depth=8192 each; MM2S=4 and S2MM=2 dedicated FIFO36E1 primitives."
    puts $f "Reviewed CDC-13 findings: 6, entirely inside VDMA dedicated FIFO36E1 primitives."
    puts $f "Custom RTL critical CDC: 0. Raw report preserved (still reports 6 Critical)."
    foreach c $cells {
        if {[get_property EN_SYN $c] != 0 || [get_property DO_REG $c] != 1} {
            close $f
            error "Hard FIFO is not in the reviewed async/registered configuration: $c"
        }
        puts $f "$c EN_SYN=[get_property EN_SYN $c] DO_REG=[get_property DO_REG $c]"
    }
    puts $f "CDC-6 VSIZE: AMD VDMA internal synchronizer; software changes geometry only while stopped."
    puts $f "CDC-15 diagnostic mailbox: held until next request, 2FF ACK + settle cycle, bounded delay/skew."
    close $f
}
