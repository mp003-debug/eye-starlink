"""Explicit per-session fitting. Never updates a model during interaction.

The old pack supplies same-eye geometry only. Fresh center references are
excluded from fitting, and the resulting pack remains disabled until a separate
positive check and an observed UI test. No camera prompt is measured gaze.
"""
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from .appearance import CoarseAppearanceModel, EyeAnchor
from .appearance_diagnostic import AppearanceDiagnostic
from .fixation import POINTS

FIT_TARGETS = [('center', POINTS['center'], 'session_reference')] + [
    (key, POINTS[key], 'session_fit') for key in CoarseAppearanceModel.LABELS]


def candidate_bytes(recording, manifest_sha256):
    engine = recording.engine
    if list(recording.plan) != FIT_TARGETS:
        raise ValueError('explicit_session_fit_plan_required')
    if (engine.baseline.summary or {}).get('ready') is not True:
        raise ValueError('five_fresh_center_references_required')
    samples = recording.samples
    if len(samples) != 30:
        raise ValueError('complete_thirty_native_samples_required')
    ids = []
    observations = []
    for i, (meta, pixels) in enumerate(samples):
        EyeAnchor._image(pixels)
        step, slot = divmod(i, 5)
        key, point, visit = FIT_TARGETS[step]
        if (meta['step'] != step or meta['slot'] != slot or meta['target'] != key
                or meta['visit'] != visit or tuple(meta['target_normalized']) != point
                or meta['requested_after_present_s'] < 2.
                or not 2. <= meta['copied_after_present_s'] < 6.):
            raise ValueError('session_fit_sample_provenance')
        digest = hashlib.sha256(pixels.tobytes()).hexdigest()
        if digest in ids:
            raise ValueError('duplicate_session_fit_image')
        ids.append(digest)
        if i < 5:
            if meta['frame_index'] not in engine.baseline.ids:
                raise ValueError('unaccepted_center_reference')
            continue
        feature, _ = engine.feature(pixels)
        observations.append(dict(frame_id=digest, target=key, visit='current_fit',
                                 feature=engine.baseline.correct(feature)))
    # This strict fitter rejects overlapping or cross-class accepted examples.
    model = CoarseAppearanceModel.fit(observations, engine.geometry_id, discriminative=True)
    meta = dict(engine.metadata)
    meta.update(template_visit_count=1, training_protocol='current_session_25',
                training_ids=ids[5:], training_counts={k: 5 for k in model.LABELS},
                source_manifest_sha256=manifest_sha256, source_pack_sha256=engine.pack_sha256,
                feature_metric='training_fisher_v1', strict_training_passed=True,
                diagnostic_only=True, actions_enabled=False, calibration_passed=False,
                training_conflicts=[],
                training_rejections=[dict(frame_id=r['frame_id'], target=r['target'])
                                     for r in observations
                                     if model.propose(r['feature'], engine.geometry_id)['target'] is None],
                session_reference_ids=ids[:5],
                protocol='Explicit fresh five-position session fitting; first five center frames excluded. '
                         'A new independent check is required; no action, audio or UART is enabled.')
    data = io.BytesIO()
    np.savez_compressed(data, reference=engine.reference, box=np.array(engine.box),
                        corners=engine.anchor.corners, metric_weights=model.metric_weights,
                        metadata=np.array(json.dumps(meta)),
                        **{'template_' + k: v for k, v in model.templates.items()})
    return data.getvalue(), meta


def save_candidate(recording, output, root):
    """Called only after successful recording and confirmed DMA shutdown."""
    output, root = Path(output), Path(root)
    manifest = output / 'targets/manifest.json'
    saved = json.loads(manifest.read_text(encoding='utf8'))
    if saved.get('completed_run') is not True:
        raise ValueError('completed_fit_capture_required')
    entries = saved.get('samples_detail', [])
    if len(entries) != len(recording.samples):
        raise ValueError('saved_fit_sample_mismatch')
    for entry, (_, pixels) in zip(entries, recording.samples):
        if entry['sha256'] != hashlib.sha256(pixels.tobytes()).hexdigest():
            raise ValueError('saved_fit_sample_mismatch')
    payload, metadata = candidate_bytes(recording, hashlib.sha256(manifest.read_bytes()).hexdigest())
    destination = output / 'session_calibration'
    destination.mkdir(exist_ok=False)
    path = destination / 'model.npz'
    path.write_bytes(payload)
    loaded = AppearanceDiagnostic(path)
    if loaded.model.enabled or loaded.baseline.offset is not None:
        raise ValueError('candidate_must_require_new_check_and_center')
    names = ['src/eye_tracker/' + name for name in
             ('appearance.py', 'appearance_diagnostic.py', 'corner_pair.py', 'session_calibration.py')]
    result = dict(model_pack_sha256=loaded.pack_sha256,
                  model_file=str(path.relative_to(output).as_posix()),
                  strict_fit_passed=True, independent_check_passed=False,
                  actions_enabled=False, audio_enabled=False, uart_enabled=False,
                  training_frames=25, excluded_reference_frames=5,
                  runtime_files={name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names},
                  metadata=metadata)
    (destination/'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    return result
