"""Explicit, bounded helper-driven reference collection; never generates actions."""
from .trial_limits import EventHistory


def assisted_reference(session,renderer,trial,mmio,buttons,clock,deadline):
    """Preview -> BTN0 -> the unchanged 6..10s / five-reference check.

    Caller has stopped music/speech and muted output. The same capture owner is
    retained. No classifier runs in preview and no controller.feed runs here.
    At most four reference attempts (initial + three retries) per entire run.
    """
    events=trial.summary.setdefault('reposition_events',EventHistory(limit=64))
    trial.controller.invalidate_calibration()
    phase='limit' if trial.setup_attempts>=4 else 'preview';shown=None
    def event(name,**fields):
        events.append(dict(event=name,monotonic=clock(),attempt=trial.setup_attempts,**fields))
    def read_command():return buttons.update(int(mmio.read(0x20))&15,clock()*1000)
    event('preview')
    while clock()<deadline and not trial.controller.closed:
        command=read_command()
        pixels=session.capture_once();info=session.last_capture
        # Exit always wins if another press arrived during capture.
        after=read_command()
        if after=='stop' or command is None:command=after
        if command=='stop':
            trial.command('stop',clock());event('stopped');return False
        if command in ('cancel','invalidate_calibration'):
            trial.command('invalidate_calibration',clock());phase='preview';shown=None
            event('cancelled',helper=command)
        elif command=='toggle_pause' and phase!='collecting':
            if trial.setup_attempts>=4:
                phase='limit';event('retry_limit')
            else:
                if trial.reference.frames:trial.reset_reference()
                trial.setup_attempts+=1;trial.reference.clock=clock
                phase='collecting'
                session.present(renderer.position_frame(pixels,'collecting',0))
                shown=clock();event('collecting')
                continue  # This capture preceded the center prompt; never a reference.
        if phase=='collecting':
            trial.reference.observe(pixels,session.capture_index,info['requested_at_monotonic'],
                                    info['copied_at_monotonic'],shown,0)
            count=len(trial.engine.baseline.samples)
            elapsed=clock()-shown
            if elapsed>=10. or (elapsed>=6. and count>=5):
                try:trial.begin_visual()
                except ValueError as exc:
                    trial.controller.invalidate_calibration();phase='failed';shown=None
                    event('rejected',reason=str(exc),reference=trial.engine.baseline.summary)
                else:
                    event('ready',reference=trial.engine.baseline.summary,
                          neighborhood=trial.summary['current_neighborhood'])
                    return True
        count=len(trial.engine.baseline.samples) if phase=='collecting' else 0
        if clock()>=deadline:break
        session.present(renderer.position_frame(pixels,phase,count))
    trial.controller.invalidate_calibration();event('timeout')
    return False
