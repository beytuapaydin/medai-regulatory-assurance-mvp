#!/usr/bin/env python3
"""Research-only prediction from 72 pre-extracted features; no waveform/holdout reader."""
import argparse, json, math
from pathlib import Path
from final_model_freeze_v1 import digest,validate_model,model_score

def score(model_dir, features_file):
    model_dir=Path(model_dir)
    manifest=json.loads((model_dir/'final_model_manifest.json').read_text(encoding='utf-8'))
    for name,sha in manifest['files_sha256'].items():
        if digest(model_dir/name)!=sha:raise ValueError('FAIL_CLOSED: model artifact hash mismatch: '+name)
    if manifest.get('status')!='LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION':raise ValueError('FAIL_CLOSED: invalid manifest status')
    model=json.loads((model_dir/'candidate_model.json').read_text(encoding='utf-8'))
    validate_model(model)
    x=json.loads(Path(features_file).read_text(encoding='utf-8'))
    if not isinstance(x,list):raise ValueError('FAIL_CLOSED: feature input must be a list of 72 floats')
    p=model_score(model,x)
    return {'status':'RESEARCH_ONLY_NOT_CLINICAL','probability':p,'predicted_mi_superclass':int(p>=model['decision_threshold']), 'threshold':model['decision_threshold']}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model-dir',type=Path,required=True)
    ap.add_argument('--features-json',type=Path,required=True)
    a=ap.parse_args()
    try: print(json.dumps(score(a.model_dir,a.features_json),sort_keys=True))
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as e:ap.exit(2,'FAIL_CLOSED: '+str(e)+'\n')
