#!/usr/bin/env python3
"""Download the exact failed-verification candidate, without rebuilding or publishing."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def main():
    repo = Path(__file__).resolve().parents[1]
    pin = json.loads((repo / 'configs/hm2004-candidate.json').read_text())
    prefix = f"repos/{pin['repository']}"
    run = api(f"{prefix}/actions/runs/{pin['run_id']}")
    assert run['head_sha'] == pin['build_commit'], 'source run commit differs'
    assert run['head_branch'] == 'hm-fttr-next', 'source branch differs'
    assert run['path'] == '.github/workflows/build-ponwrt.yml', 'source workflow differs'
    assert run['status'] == 'completed', 'source build has not finished'
    jobs = api(f"{prefix}/actions/runs/{pin['run_id']}/jobs")['jobs']
    builds = [j for j in jobs if j['name'] == 'build']
    assert len(builds) == 1, 'expected one firmware build job'
    steps = {s['name']: s for s in builds[0]['steps']}
    assert steps['Compile the firmware']['conclusion'] == 'success', 'firmware compilation did not pass'
    artifact = api(f"{prefix}/actions/artifacts/{pin['artifact_id']}")
    assert artifact['name'] == pin['artifact_name'] and not artifact['expired'], 'candidate artifact unavailable'
    assert artifact['workflow_run']['id'] == pin['run_id'], 'candidate is from another run'
    assert artifact['workflow_run']['head_sha'] == pin['build_commit'], 'candidate commit differs'
    assert artifact['digest'] == 'sha256:' + pin['artifact_sha256'], 'artifact digest changed'
    root = repo / 'candidate'
    root.mkdir(exist_ok=True)
    archive = root / 'candidate.zip'
    with archive.open('wb') as stream:
        subprocess.run(['gh', 'api', f"{prefix}/actions/artifacts/{pin['artifact_id']}/zip"], stdout=stream, check=True, timeout=180)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == pin['artifact_sha256'], 'downloaded archive checksum differs'
    output = root / 'bin/targets/airoha/an7581'
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename)
            assert len(name.parts) == 1 and name.name not in ('.', '..'), 'unexpected artifact layout'
            with z.open(info) as src, (output / name.name).open('wb') as dst:
                shutil.copyfileobj(src, dst)
    images = list(output.glob('*h3c_hm2004-du-squashfs-sysupgrade.itb'))
    assert len(images) == 1, 'expected one sysupgrade image'
    actual = hashlib.sha256(images[0].read_bytes()).hexdigest()
    assert actual == pin['sysupgrade_sha256'], 'firmware payload checksum differs'
    (root / 'candidate-source.json').write_text(json.dumps(pin, indent=2) + '\n')
    print(f"PASS exact artifact and unchanged sysupgrade payload: {actual}", flush=True)


if __name__ == '__main__':
    main()
