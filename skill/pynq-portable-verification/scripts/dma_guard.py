"""Polling guard for an already configured simple AXI DMA; caller owns buffers."""
import math,time

class DmaFailure(RuntimeError):
    def __init__(self, reason, buffers, quiescent, recovery_error=None):
        super().__init__(reason)
        self.buffers=buffers
        self.quiescent=quiescent
        self.recovery_error=recovery_error

def transfer(dma, send, receive, *, send_bytes, receive_bytes, word_bytes,
             max_bytes, timeout_s, quiesce=None, clock=time.monotonic, sleep=time.sleep):
    """Flush -> arm RX -> start TX -> bounded poll -> invalidate.

    quiesce() must stop the upstream producer and both channels within its own
    deadline and return True only after observing quiescence. On failure this
    function NEVER frees memory. Keep the exception/buffers until safe recovery.
    MMIO access must itself be responsive; a Python deadline cannot interrupt a
    kernel hang. No overlapping transfer or coherent aliasing of these buffers.
    """
    if not math.isfinite(timeout_s) or timeout_s<=0:raise ValueError('positive finite timeout required')
    if any(not isinstance(n,int) or isinstance(n,bool) or n<=0 for n in (send_bytes,receive_bytes,word_bytes,max_bytes)):
        raise ValueError('positive integer sizes required')
    if send_bytes>min(send.nbytes,max_bytes) or receive_bytes>min(receive.nbytes,max_bytes):
        raise ValueError('buffer or DMA maximum exceeded')
    if send_bytes%word_bytes or receive_bytes%word_bytes:raise ValueError('unaligned transfer length')
    for b,n in ((send,send_bytes),(receive,receive_bytes)):
        if b.device_address%word_bytes:raise ValueError('unaligned device address')
    a,b=send.device_address,receive.device_address
    if max(a,b)<min(a+send_bytes,b+receive_bytes):raise ValueError('overlapping physical buffers')
    started=False;deadline=clock()+timeout_s
    try:
        for channel in (dma.sendchannel,dma.recvchannel):
            # PYNQ simple DMA allows the first transfer after start even while
            # idle is low. Keep this version-specific adaptation explicit.
            if not channel.running:raise ValueError('DMA channel not running')
            if not channel.idle and not getattr(channel,'_first_transfer',False):
                raise ValueError('DMA already active')
        if dma.sendchannel.error or dma.recvchannel.error:raise ValueError('DMA has a pre-existing error')
        send.flush()
        # RX buffer may hold dirty CPU cache lines. Flush before device ownership.
        receive.flush()
        started=True
        dma.recvchannel.transfer(receive,nbytes=receive_bytes)
        dma.sendchannel.transfer(send,nbytes=send_bytes)
        while True:
            if dma.sendchannel.error or dma.recvchannel.error:raise RuntimeError('DMA error status')
            if dma.sendchannel.idle and dma.recvchannel.idle:break
            if clock()>=deadline:raise TimeoutError('DMA deadline exceeded; check TLAST/length/backpressure')
            sleep(min(0.001,max(0,deadline-clock())))
        receive.invalidate()
        return {'completed':True,'send_bytes':send_bytes,'receive_bytes':receive_bytes}
    except BaseException as exc:
        if not started:raise
        quiet=False;recovery_error=None
        if quiesce is not None:
            try:quiet=quiesce() is True
            except BaseException as recovery:recovery_error=repr(recovery)
        raise DmaFailure(str(exc),(send,receive),quiet,recovery_error) from exc
