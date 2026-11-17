#!/usr/bin/env python3
"""Build pinned patched userspace and test JSON redirect in a fresh netns."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess as sp
import urllib.request
import os


def run(args, cwd=None, env=None):
    print('+', ' '.join(map(str,args)), flush=True)
    sp.run(list(map(str,args)), cwd=cwd, env=env, check=True)


def download(url, path, expected):
    with urllib.request.urlopen(url, timeout=60) as src, path.open('wb') as dst:
        while data := src.read(1024*1024):
            dst.write(data)
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f'{path.name}: SHA256 differs: {actual}')
    print('Verified SHA256:',path.name,actual,flush=True)


def prepare(ow, work, pkg):
    recipe=(ow/pkg/'Makefile').read_text()
    def field(key):
        m=re.search(r'^'+key+r':=(.*)$',recipe,re.M)
        if not m: raise ValueError('Missing recipe field '+key)
        return m.group(1).strip()
    name,version,sha=field('PKG_NAME'),field('PKG_VERSION'),field('PKG_HASH')
    filename=f'{name}-{version}.tar.xz'
    archive=work/filename
    download(f'https://netfilter.org/projects/{name}/files/{filename}',archive,sha)
    run(['tar','-xf',archive,'-C',work])
    source=work/f'{name}-{version}'
    for patch in sorted((ow/pkg/'patches').glob('*.patch')):
        run(['patch','--batch','--forward','--fuzz=0','-p1','-i',patch],cwd=source)
    return source


def netns_test(nft):
    # Invoked only after unshare -n; all rules disappear when this process exits.
    def cli(arguments, input=None, success=True):
        p=sp.run([str(nft),*arguments],input=input,text=True,capture_output=True)
        if (success and p.returncode) or p.returncode < 0:
            raise RuntimeError(f'nft {arguments}: rc={p.returncode}\n{p.stdout}\n{p.stderr}')
        return p
    spec={'nftables':[
        {'add':{'table':{'family':'ip','name':'hm_verify'}}},
        {'add':{'chain':{'family':'ip','table':'hm_verify','name':'prerouting','type':'nat','hook':'prerouting','prio':-100,'policy':'accept'}}},
        {'add':{'rule':{'family':'ip','table':'hm_verify','chain':'prerouting','expr':[
            {'match':{'op':'==','left':{'meta':{'key':'l4proto'}},'right':'tcp'}},
            {'redirect':{'port':12345}}
        ]}}}
    ]}
    cli(['-j','-f','-'],json.dumps(spec))
    rules=json.loads(cli(['-j','list','ruleset']).stdout)
    exprs=[e for entry in rules['nftables'] if 'rule' in entry for e in entry['rule']['expr']]
    if not any(e.get('redirect',{}).get('port') == 12345 for e in exprs):
        raise ValueError('JSON redirect did not round-trip')
    unsupported={'nftables':[{'add':{'rule':{'family':'ip','table':'hm_verify','chain':'prerouting','expr':[{'fullcone':None}]}}}]}
    failure=cli(['-j','-f','-'],json.dumps(unsupported),success=False)
    if failure.returncode == 0 or 'Unknown statement' not in failure.stderr:
        raise ValueError('JSON fullcone must be rejected by the parser: '+failure.stderr)
    print('PASS: real JSON redirect round-trip and unsupported fullcone rejection',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('openwrt',type=Path,nargs='?')
    p.add_argument('--work',type=Path)
    p.add_argument('--netns-test',type=Path)
    a=p.parse_args()
    if a.netns_test:
        netns_test(a.netns_test.resolve());return
    ow=a.openwrt.resolve();work=a.work.resolve()
    work.mkdir(parents=True,exist_ok=False)
    prefix=work/'prefix'
    lib=prepare(ow,work,'package/libs/libnftnl')
    nft=prepare(ow,work,'package/network/utils/nftables')
    run(['autoreconf','-fi'],cwd=lib)
    run(['./configure','--prefix='+str(prefix),'--disable-static'],cwd=lib)
    run(['make','-j2'],cwd=lib);run(['make','install'],cwd=lib)
    env=os.environ.copy()
    env['PKG_CONFIG_PATH']=str(prefix/'lib/pkgconfig')
    env['LD_LIBRARY_PATH']=str(prefix/'lib')
    run(['autoreconf','-fi'],cwd=nft,env=env)
    run(['./configure','--prefix='+str(prefix),'--with-json','--with-mini-gmp','--without-cli','--disable-debug','--disable-man-doc','--disable-python'],cwd=nft,env=env)
    # Force parser/scanner regeneration after applying the fullcone grammar.
    for f in ['src/parser_bison.c','src/parser_bison.h','src/scanner.c']:
        (nft/f).unlink(missing_ok=True)
    run(['make','-j2'],cwd=nft,env=env);run(['make','install'],cwd=nft,env=env)
    exe=prefix/'sbin/nft'
    run([exe,'--version'],env=env)
    run(['sudo','unshare','--net','env','LD_LIBRARY_PATH='+env['LD_LIBRARY_PATH'],'python3',Path(__file__).resolve(),'--netns-test',exe])
    (work/'verification.json').write_text(json.dumps({'userspace_build':True,'json_redirect_roundtrip':True,'json_fullcone_rejected':True,'target_kernel_fullcone_runtime':'pending'},indent=2)+'\n')


if __name__=='__main__':
    main()
