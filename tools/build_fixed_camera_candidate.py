"""Build a disabled, isolated paired-corner candidate from a fresh raw capture.

Only the first two predefined visits are fitting data. The third visit never
contributes landmarks, templates, weights, or model selection. Fresh live
positive and invalid-input checks remain required after this pack is frozen.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools/deps/opencv'), str(ROOT/'src')]
import cv2
import numpy as np
from eye_tracker.appearance import CoarseAppearanceModel, appearance_feature
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
from eye_tracker.corner_pair import PairCornerMatcher
from eye_tracker.fixation import APPEARANCE_TARGETS

def sha(data):
    return hashlib.sha256(data).hexdigest()

def inside(path):
    path=Path(path).resolve()
    path.relative_to(ROOT.resolve())
    return path

def read_capture(targets):
    targets=inside(targets)
    raw_manifest=(targets/'manifest.json').read_bytes()
    manifest=json.loads(raw_manifest)
    entries=manifest['samples_detail']
    if manifest.get('completed_run') is not True or manifest.get('source')!='live_camera' or len(entries)!=75:
        raise ValueError('complete_75_sample_capture_required')
    ids=[]
    for i, entry in enumerate(entries):
        target, _, visit=APPEARANCE_TARGETS[i//5]
        if entry['target']!=target or entry['visit']!=visit or entry['step']!=i//5 or entry['slot']!=i%5:
            raise ValueError('predeclared_capture_order_required')
        path=(targets/entry['raw']).resolve()
        path.relative_to(targets)
        data=path.read_bytes()
        if len(data)!=640*480 or sha(data)!=entry['sha256']:
            raise ValueError('native_frame_hash_or_size_mismatch')
        ids.append(entry['sha256'])
    if len(set(ids))!=75:
        raise ValueError('unique_frames_required')
    return entries, sha(raw_manifest)

def build(targets, annotation_path, output):
    cv2.setNumThreads(1)
    targets=inside(targets); annotation_path=inside(annotation_path); output=inside(output)
    # This tool can never target the original deployed profile/model tree.
    output.relative_to(ROOT/'build/fixed_camera_calibration_20261103')
    if output.exists():
        raise ValueError('fresh_candidate_output_required')
    entries, manifest_hash=read_capture(targets)
    annotation_bytes=annotation_path.read_bytes(); annotation=json.loads(annotation_bytes)
    index=annotation['reference_fit_index']
    if type(index) is not int or not 0<=index<50 or entries[index]['target']!='center':
        raise ValueError('reference_must_be_center_training_frame')
    if annotation['reference_sha256']!=entries[index]['sha256']:
        raise ValueError('annotation_reference_mismatch')
    reference=np.frombuffer((targets/entries[index]['raw']).read_bytes(),np.uint8).reshape(480,640).copy()
    box=tuple(annotation['box']); corners=np.asarray(annotation['corners'])
    if len(box)!=4 or any(type(v) is not int for v in box) or corners.shape!=(2,2) or not np.isfinite(corners).all() or not np.equal(corners,np.round(corners)).all():
        raise ValueError('integer_anatomical_landmarks_required')
    corners=corners.astype(np.int32)
    anchor=PairCornerMatcher(reference,box,corners,'eye_support_v1',parallel=False)
    rows=[]; observations=[]
    # No held-out appearance is read into the fitting pipeline.
    for i, entry in enumerate(entries[:50]):
        pixels=np.frombuffer((targets/entry['raw']).read_bytes(),np.uint8).reshape(480,640)
        try:
            patch,metrics=anchor.align(pixels)
            feature=appearance_feature(patch)
            observations.append(dict(frame_id=entry['sha256'],target=entry['target'],visit=entry['visit'],feature=feature))
            rows.append(dict(sample=i,target=entry['target'],visit=entry['visit'],aligned=True,metrics=metrics))
        except (ValueError,cv2.error) as exc:
            rows.append(dict(sample=i,target=entry['target'],visit=entry['visit'],aligned=False,rejection=str(exc)))
    output.mkdir(parents=True)
    audit=dict(manifest_sha256=manifest_hash,annotation_sha256=sha(annotation_bytes),
               fit_rows=rows,fit_count=len(observations),heldout_count=25,
               heldout_used_for_fit=False,actions_enabled=False,calibration_passed=False)
    def save_audit():
        (output/'build_report.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    if len(observations)!=50:
        audit['failure']='not_all_fitting_frames_align';save_audit()
        raise ValueError(audit['failure'])
    geometry=sha(reference.tobytes())
    try:
        model=CoarseAppearanceModel.fit(observations,geometry,discriminative=True)
    except ValueError as exc:
        audit['failure']=str(exc);save_audit();raise
    assert not model.enabled
    meta=dict(feature_crop_mode='eye_support_v1',reference_feature_crop=list(anchor.crop),
              alignment='corners_and_session_reference',corner_search_mode='paired_corners_v1',
              feature_metric='training_fisher_v1',template_visit_count=2,strict_training_passed=True,
              diagnostic_only=True,actions_enabled=False,calibration_passed=False,
              source_manifest_sha256=manifest_hash,annotation_sha256=sha(annotation_bytes),
              training_ids=[o['frame_id'] for o in observations],
              protocol='Two predeclared fitting visits only. Fresh positive and invalid-input checks required.',
              thresholds_unchanged=True)
    path=output/'model.npz'
    np.savez_compressed(path,reference=reference,box=np.asarray(box),corners=corners,
                        metric_weights=model.metric_weights,metadata=np.array(json.dumps(meta)),
                        **{'template_'+k:v for k,v in model.templates.items()})
    engine=AppearanceDiagnostic(path)
    audit.update(candidate_created=True,pack_sha256=engine.pack_sha256,
                 training_support=model.training_support,
                 predictions=[dict(sample=i,target=o['target'],prediction=model.propose(o['feature'],geometry))
                              for i,o in enumerate(observations)])
    save_audit()
    print(json.dumps(dict(candidate=str(path),sha256=engine.pack_sha256,actions_enabled=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--targets',type=Path,required=True)
    p.add_argument('--annotation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();build(args.targets,args.annotation,args.output)
