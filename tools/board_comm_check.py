"""Explicit synthetic UART/group protocol check; run on PYNQ with no other owner.
Never drives actuators: EVENT packets always use TEST. Takes the project lock,
verifies and downloads the UART overlay, then sets/readbacks the PL clocks.
Operator must first confirm no other hardware owner; display/camera remain stopped.
"""
import argparse
import json
import secrets
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--events', type=int, default=15)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    if not 1 <= args.events <= 50:
        parser.error('events must be 1..50')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import fcntl
    from pynq import MMIO, Overlay, Clocks
    from eye_tracker.hardware_contract import verify_artifacts, configure_overlay_clocks
    owner = open("/var/lock/eye_tracker_system.lock", "a+")
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    initialization = verify_artifacts(args.root)
    overlay = Overlay(str(args.root / "build/fpga/eye_tracker.bit"), download=False)
    overlay.download()
    initialization["clocks"] = configure_overlay_clocks(Clocks)
    from eye_tracker.event_uart import AxiUartLite
    from eye_tracker.event_protocol import Packet, Decoder, HELLO, EVENT, ACK, OK, DUPLICATE, OLD_SEQUENCE, TEST
    memory = MMIO(0x42c00000, 0x10000)
    uart = AxiUartLite(memory)
    decoder = Decoder()
    session = secrets.randbelow(0xffffffff) + 1
    start = time.monotonic()
    rows = []
    result = dict(scope='Synthetic TEST on A group firmware; aggregate ACK is acceptance, not action completion',
                  required_nodes=['B', 'C', 'D'], session=session, passed=False, initialization=initialization)

    def transact(packet, expected, label):
        began = time.monotonic()
        attempts = 0
        sent = None
        while time.monotonic() - began < .6:
            now = time.monotonic()
            for reply in decoder.feed(uart.read()):
                if (reply.kind, reply.session, reply.sequence, reply.code) == (ACK, packet.session, packet.sequence, packet.code):
                    row = dict(label=label, kind=packet.kind, sequence=packet.sequence, code=packet.code,
                               status=reply.detail, expected=expected, attempts=attempts, elapsed_ms=(now-began)*1000)
                    rows.append(row)
                    if reply.detail not in expected:
                        raise RuntimeError('Unexpected ACK status: '+str(row))
                    return
            if attempts < 3 and (sent is None or now-sent >= .18) and uart.try_write(packet.encode()):
                attempts += 1
                sent = now
            time.sleep(.005)
        rows.append(dict(label=label, kind=packet.kind, sequence=packet.sequence, code=packet.code,
                         timeout=True, attempts=attempts, elapsed_ms=(time.monotonic()-began)*1000))
        raise TimeoutError('No matching group ACK: '+label)

    try:
        hello = Packet(HELLO, session, 0, 0, TEST)
        transact(hello, [OK], 'hello')
        for sequence in range(1, args.events+1):
            packet = Packet(EVENT, session, sequence, 1+(sequence-1)%5, TEST)
            transact(packet, [OK], 'new')
            # A may return its still-valid aggregate cache, or endpoint DUPLICATE.
            # Exactly one receiver TEST log per sequence must be audited separately.
            transact(packet, [OK, DUPLICATE], 'duplicate')
        transact(hello, [OK], 'hello_repeat')
        transact(packet, [DUPLICATE], 'duplicate_after_hello')
        transact(Packet(EVENT, session, 0, 1, TEST), [OLD_SEQUENCE], 'old_sequence')
        packet = Packet(EVENT, session, args.events+1, 1, TEST)
        damaged = bytearray(packet.encode())
        damaged[-1] ^= 1
        if not uart.try_write(bytes(damaged)):
            raise RuntimeError('TX busy before CRC injection')
        began = time.monotonic()
        unexpected = []
        while time.monotonic()-began < .3:
            unexpected.extend(decoder.feed(uart.read()))
            time.sleep(.005)
        result['corrupted_frame_no_reply'] = not unexpected
        if unexpected:
            raise RuntimeError('Unexpected reply after invalid CRC')
        transact(packet, [OK], 'valid_after_crc')
        result['passed'] = True
    except Exception as error:
        result['error'] = repr(error)
    finally:
        result.update(seconds=time.monotonic()-start, transactions=rows, reply_crc_errors=decoder.bad_frames,
                      expected_new_events=args.events+1)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        memory.write(12, 3)
    print(json.dumps({k:v for k,v in result.items() if k!='transactions'}))
    print('transactions='+str(len(rows)))
    return 0 if result['passed'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
