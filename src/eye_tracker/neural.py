"""Small learned MLP, int8 inference, and read-only appearance integration.

No hardware imports, UI actions, or wireless effects. A neural agreement is
additional evidence, never a bypass of existing alignment/novelty rejection.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from .appearance import CoarseAppearanceModel

LABELS = CoarseAppearanceModel.LABELS
DIMS = (1152, 64, 32, 5)


def quantize(value, scale):
    a = np.asarray(value)
    if not np.isfinite(a).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError('finite_values_and_positive_scale_required')
    # Round-to-nearest ties-to-even, symmetric saturation; no -128 values.
    return np.clip(np.rint(a / scale), -127, 127).astype(np.int8)


class NeuralModel:
    def __init__(self, path, expected_sha256=None):
        raw = Path(path).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and expected_sha256 != self.sha256:
            raise ValueError('neural_model_hash_mismatch')
        with np.load(path, allow_pickle=False) as z:
            self.meta = json.loads(str(z['metadata'].item()))
            self.weights = [z['w'+str(i)].copy() for i in range(3)]
            self.biases = [z['b'+str(i)].copy() for i in range(3)]
            self.qweights = [z['qw'+str(i)].copy() for i in range(3)]
            self.wscale = z['weight_scales'].copy()
            self.ascale = z['activation_scales'].copy()
        if (self.meta.get('schema') != 'eye_mlp_int8_v1'
                or self.meta.get('labels') != list(LABELS)
                or self.meta.get('actions_enabled') is not False):
            raise ValueError('offline_neural_schema_required')
        if self.wscale.shape != (3,) or self.ascale.shape != (3,):
            raise ValueError('three_layer_scales_required')
        if not np.isfinite(self.wscale).all() or not np.isfinite(self.ascale).all() or min(self.wscale.min(), self.ascale.min()) <= 0:
            raise ValueError('invalid_scales')
        for i in range(3):
            shape = (DIMS[i], DIMS[i+1])
            if self.weights[i].shape != shape or self.qweights[i].shape != shape or self.qweights[i].dtype != np.int8 or self.biases[i].shape != (DIMS[i+1],):
                raise ValueError('invalid_layer_shape_or_dtype')
            if not np.isfinite(self.weights[i]).all() or not np.isfinite(self.biases[i]).all():
                raise ValueError('nonfinite_parameters')
            for a in (self.weights[i], self.biases[i], self.qweights[i]): a.setflags(write=False)
        self.wscale.setflags(write=False); self.ascale.setflags(write=False)

    def logits(self, feature, integer=True, accelerator=None):
        x = CoarseAppearanceModel.vector(feature).astype(np.float64) * 2 - 1
        if not integer:
            for i in range(3):
                x = x @ self.weights[i] + self.biases[i]
                if i < 2: x = np.maximum(x, 0)
            return x
        for i in range(3):
            q = quantize(x, self.ascale[i])
            if accelerator is None:
                dot = q.astype(np.int32) @ self.qweights[i].astype(np.int32)
            else:
                if accelerator.model.sha256 != self.sha256:
                    raise ValueError('accelerator_model_mismatch')
                dot = accelerator.dense(i, q)
                if dot.shape != (DIMS[i+1],) or dot.dtype != np.int32:
                    raise ValueError('invalid_accelerator_result')
            x = dot.astype(np.float64) * self.ascale[i] * self.wscale[i] + self.biases[i]
            if i < 2: x = np.maximum(x, 0)
        return x

    def predict(self, feature, integer=True, accelerator=None):
        logits = self.logits(feature, integer, accelerator)
        p = np.exp(logits - logits.max()); p /= p.sum()
        order = np.argsort(p)
        return dict(target=LABELS[int(order[-1])], confidence=float(p[order[-1]]),
                    margin=float(p[order[-1]]-p[order[-2]]), probabilities=p.tolist())

    def guarded(self, feature, legacy_target, accelerator=None):
        result = self.predict(feature, accelerator=accelerator)
        accepted = (legacy_target is not None and result['target'] == legacy_target
                    and result['confidence'] >= .8 and result['margin'] >= .5)
        return dict(result, candidate=result['target'] if accepted else None,
                    reason='agreement' if accepted else 'legacy_or_neural_rejected', actions_enabled=False)


class NeuralAppearanceDiagnostic:
    """Same calibrated alignment/session references; separate neural observation."""
    def __init__(self, appearance_path, neural_path):
        from .appearance_diagnostic import AppearanceDiagnostic
        self.appearance = AppearanceDiagnostic(appearance_path)
        self.neural = NeuralModel(neural_path)
        if self.neural.meta['appearance_sha256'] != self.appearance.pack_sha256:
            raise ValueError('neural_geometry_binding_mismatch')

    def inspect(self, pixels, session_correct=False, accelerator=None):
        try:
            f, metrics = self.appearance.feature(pixels)
            if session_correct: f = self.appearance.baseline.correct(f)
            legacy = self.appearance.model.propose(f, self.appearance.geometry_id)['target']
            return dict(self.neural.guarded(f, legacy, accelerator), legacy_target=legacy, alignment=metrics)
        except (ValueError, self.appearance.cv.error) as exc:
            return dict(candidate=None, actions_enabled=False, reason=str(exc))


class NeuralConsensusClassifier:
    """Drop-in propose() adapter for the existing diagnostic/stability pipeline.

    All old appearance rejection gates run first. A model disagreement or failed
    accelerator rejects this frame. No automatic fallback, threshold relaxation,
    calibration enabling, or change to UI/media/wireless handling is performed.
    """
    enabled=False
    def __init__(self, legacy, neural, accelerator=None):
        self.legacy=legacy;self.neural=neural;self.accelerator=accelerator
        self.geometry_id=legacy.geometry_id

    def propose(self, feature, geometry_id):
        result=dict(self.legacy.propose(feature,geometry_id))
        if result['target'] is None:return result
        try:
            prediction=self.neural.guarded(feature,result['target'],self.accelerator)
            result.update(target=prediction['candidate'],neural=prediction,
                          source='calibrated_appearance_and_int8_mlp',
                          reason='candidate' if prediction['candidate'] else 'neural_disagreement_or_uncertain')
        except (ValueError,RuntimeError,TimeoutError) as exc:
            result.update(target=None,reason='neural_failure',neural_error=str(exc))
        return result


def attach_neural(engine, neural_path, expected_sha256, accelerator=None):
    """Explicit candidate integration, before collecting new session references.

    This is not a deployment entry point and does not establish live acceptance.
    A new engine is required after any reference reset, retaining the same frozen
    model hash. Existing default launcher does not call this opt-in function.
    """
    if engine.baseline.samples or isinstance(engine.model,NeuralConsensusClassifier):
        raise ValueError('attach_before_reference_collection_once')
    model=NeuralModel(neural_path,expected_sha256)
    if model.meta['appearance_sha256']!=engine.pack_sha256:
        raise ValueError('neural_geometry_binding_mismatch')
    if accelerator is not None and accelerator.model.sha256!=model.sha256:
        raise ValueError('accelerator_model_mismatch')
    engine.model=NeuralConsensusClassifier(engine.model,model,accelerator)
    return model
