# Interface contract and portability

`schema: 1`, `platform` (your own precise board/part identifier), `ips` keyed by
Vivado instance path, optional `clocks_hz`, optional paired `artifacts`.
Each IP needs `vlnv`, integer or hex-string `base`, positive `range`, and named
`registers` with byte offsets. Each artifact needs a relative `file` and SHA-256.
Use the metadata exported with the exact bitstream; never infer a pairing from
timestamps. Snapshot clocks require an explicitly supplied measured/configured
value: `ip_dict` alone does not prove clock frequency.

The examples use **fictional interface contracts**, not ready-to-load designs.
Example A and B deliberately vary platform, IP names, address and frequency.
An existing `Overlay(..., download=False)` can parse HWH, but initialization side
effects vary by PYNQ version. Inspect the installed implementation and prefer an
already loaded object's metadata when running an active application.

Reference: [PYNQ overlay design](https://pynq.readthedocs.io/en/latest/overlay_design_methodology/overlay_design.html).
