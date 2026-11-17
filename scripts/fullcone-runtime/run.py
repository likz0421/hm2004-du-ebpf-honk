#!/usr/bin/env python3
"""Build a minimal fixed Linux guest; never load test modules into the host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess as sp
import urllib.request

VERSION='6.12.116'
LINUX_SHA256='cb3ed3dfdd47e6ade49dc933db334fd86e24cadee920da612c262b0e9b6a511b'


def run(args,cwd=None,env=None,stdout=None):
    print('+',' '.join(map(str,args)),flush=True)
    return sp.run(list(map(str,args)),cwd=cwd,env=env,stdout=stdout,check=True)


def fetch(url,path,sha):
    with urllib.request.urlopen(url,timeout=90) as src,path.open('wb') as out:
        while data:=src.read(1024*1024):out.write(data)
    if hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=sha:
        raise ValueError('Source hash mismatch: '+str(path))


def copy_binary(binary,root):
    # Dereference symlinks; preserve ELF interpreter paths recorded by ldd.
    binary=Path(binary)
    target=root/str(binary).lstrip('/')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(binary,target,follow_symlinks=True)
    result=sp.run(['ldd',str(binary)],text=True,capture_output=True)
    for lib in re.findall(r'(/[^\s()]+)',result.stdout):
        f=Path(lib)
        if f.is_file():
            dst=root/lib.lstrip('/');dst.parent.mkdir(parents=True,exist_ok=True)
            if not dst.exists():shutil.copy2(f,dst,follow_symlinks=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('openwrt',type=Path);p.add_argument('--native-prefix',required=True,type=Path)
    p.add_argument('--work',required=True,type=Path);a=p.parse_args()
    ow=a.openwrt.resolve();prefix=a.native_prefix.resolve();work=a.work.resolve()
    work.mkdir(parents=True,exist_ok=False)
    kernel=work/('linux-'+VERSION)
    archive=work/('linux-'+VERSION+'.tar.xz')
    fetch('https://cdn.kernel.org/pub/linux/kernel/v6.x/'+archive.name,archive,LINUX_SHA256)
    run(['tar','-xf',archive,'-C',work])
    chain=ow/'target/linux/generic/hack-6.12/952-net-conntrack-events-support-multiple-registrant.patch'
    run(['patch','--batch','--forward','--fuzz=0','-p1','-i',chain],cwd=kernel)
    run(['make','tinyconfig'],cwd=kernel)
    builtins=['64BIT','X86_64','PRINTK','BUG','BINFMT_ELF','BINFMT_SCRIPT','ELF_CORE','POSIX_TIMERS','ADVISE_SYSCALLS','FILE_LOCKING','MEMBARRIER','RSEQ','MULTIUSER','FUTEX','EPOLL','SIGNALFD','TIMERFD','EVENTFD','NAMESPACES','NET_NS','NET','UNIX','INET','IPV6','PACKET','NETFILTER','NETFILTER_ADVANCED','NF_CONNTRACK','NF_CONNTRACK_EVENTS','NF_CONNTRACK_CHAIN_EVENTS','NF_CONNTRACK_ZONES','NF_NAT','NF_TABLES','NF_TABLES_INET','NFT_NAT','NFT_MASQ','NFT_REDIR','NFT_CT','NETDEVICES','NET_CORE','VETH','MODULES','MODULE_UNLOAD','PROC_FS','SYSFS','SHMEM','TMPFS','DEVTMPFS','DEVTMPFS_MOUNT','BLK_DEV_INITRD','RD_GZIP','TTY','SERIAL_8250','SERIAL_8250_CONSOLE','UNIX98_PTYS','SYSCTL','PROC_SYSCTL']
    config=[str(kernel/'scripts/config')]
    for symbol in builtins:config+=['--enable',symbol]
    config+=['--module','NF_CT_NETLINK','--disable','DEBUG_INFO','--disable','MODULE_SIG','--set-str','LOCALVERSION','-hm-fullcone-test']
    run(config,cwd=kernel);run(['make','olddefconfig'],cwd=kernel)
    effective=(kernel/'.config').read_text()
    for symbol in ['NF_CONNTRACK_EVENTS','NF_CONNTRACK_CHAIN_EVENTS','NF_TABLES','NET_NS','VETH']:
        if f'CONFIG_{symbol}=y\n' not in effective:raise ValueError('Missing runtime kernel option '+symbol)
    if 'CONFIG_NF_CT_NETLINK=m\n' not in effective:raise ValueError('ctnetlink must remain unloadable')
    run(['make','-j2','bzImage','modules'],cwd=kernel)
    recipe=(ow/'package/network/utils/fullconenat-nft/Makefile').read_text()
    date=re.search(r'^PKG_SOURCE_DATE:=(.+)$',recipe,re.M).group(1)
    revision=re.search(r'^PKG_SOURCE_VERSION:=(.+)$',recipe,re.M).group(1)
    sha=re.search(r'^PKG_MIRROR_HASH:=(.+)$',recipe,re.M).group(1)
    name='fullconenat-nft-'+date.replace('-','.')+'~'+revision[:8]
    module_archive=work/(name+'.tar.zst')
    fetch('https://sources.immortalwrt.org/'+module_archive.name,module_archive,sha)
    run(['tar','-xf',module_archive,'-C',work]);module=work/name
    for patch in sorted((ow/'package/network/utils/fullconenat-nft/patches').glob('*.patch')):
        run(['patch','--batch','--forward','--fuzz=0','-p1','-i',patch],cwd=module)
    run(['make','-C',kernel,'M='+str(module/'src'),'-j2','modules'])
    root=work/'root';root.mkdir()
    for d in ['bin','sbin','usr/bin','usr/sbin','usr/lib','etc','lib','proc','sys','dev','run','tmp']:(root/d).mkdir(parents=True,exist_ok=True)
    release=sp.check_output(['make','-s','kernelrelease'],cwd=kernel,text=True).strip()
    run(['make','modules_install','INSTALL_MOD_PATH='+str(root),'INSTALL_MOD_STRIP=1'],cwd=kernel)
    moddir=root/'lib/modules'/release/'extra';moddir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(module/'src/nft_fullcone.ko',moddir/'nft_fullcone.ko')
    run(['depmod','-b',root,release])
    # PID 1 needs an initial console before /init can mount devtmpfs.
    for name,major,minor in [('console',5,1),('null',1,3)]:
        run(['sudo','mknod','-m','666',root/'dev'/name,'c',major,minor])
    busybox=Path(shutil.which('busybox'));shutil.copy2(busybox,root/'bin/busybox')
    for app in ['sh','mount','umount','mkdir','sysctl','dmesg','reboot','cat','echo','touch','modprobe','insmod','rmmod','lsmod','sleep']:
        (root/'bin'/app).symlink_to('busybox')
    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(prefix/'lib')
    # ldd must resolve the freshly built nft library rather than distro libnftnl.
    saved=os.environ.get('LD_LIBRARY_PATH');os.environ['LD_LIBRARY_PATH']=str(prefix/'lib')
    try:
        for b in [prefix/'sbin/nft',Path('/usr/bin/python3'),Path(shutil.which('conntrack')),Path(shutil.which('ip'))]:copy_binary(b,root)
    finally:
        if saved is None:os.environ.pop('LD_LIBRARY_PATH',None)
        else:os.environ['LD_LIBRARY_PATH']=saved
    shutil.copy2(prefix/'sbin/nft',root/'bin/nft')
    # Native build prefixes may live under /tmp, which becomes a tmpfs in guest.
    for library in (prefix/'lib').glob('*.so*'):
        if library.is_file():shutil.copy2(library,root/'usr/lib'/library.name,follow_symlinks=True)
    (root/'bin/conntrack').symlink_to(str(Path(shutil.which('conntrack'))))
    (root/'bin/ip').symlink_to(str(Path(shutil.which('ip'))))
    (root/'bin/python3').symlink_to('/usr/bin/python3')
    for libdir in Path('/usr/lib').glob('python3.*'):
        if not libdir.is_dir():continue
        shutil.copytree(libdir,root/'usr/lib'/libdir.name,ignore=shutil.ignore_patterns('__pycache__','test','tests','ensurepip'),symlinks=False)
        for extension in libdir.glob('lib-dynload/*.so'):copy_binary(extension,root)
    shutil.copy2(Path(__file__).with_name('guest.py'),root/'guest.py')
    (root/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\n')
    (root/'etc/group').write_text('root:x:0:\n')
    init='''#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
export LD_LIBRARY_PATH=NATIVE_LIB
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
touch /run/hm-qemu-guest
python3 /guest.py
rc=$?
if [ "$rc" != 0 ]; then echo HM_FULLCONE_RUNTIME_FAIL; dmesg; fi
reboot -f
'''.replace('NATIVE_LIB','/usr/lib')
    (root/'init').write_text(init);(root/'init').chmod(0o755)
    paths=['.']+[str(f.relative_to(root)) for f in root.rglob('*')]
    cpio=work/'initramfs.cpio'
    with cpio.open('wb') as out:
        sp.run(['cpio','--null','-o','--format=newc','--owner=0:0'],cwd=root,input='\0'.join(paths).encode()+b'\0',stdout=out,check=True)
    run(['gzip','-1',cpio]);image=work/'initramfs.cpio.gz'
    cmd=['qemu-system-x86_64','-accel','tcg','-m','768','-smp','1','-nodefaults','-no-reboot','-nographic','-serial','stdio','-nic','none','-kernel',kernel/'arch/x86/boot/bzImage','-initrd',image,'-append','console=ttyS0 rdinit=/init panic=-1']
    log=work/'console.log'
    with log.open('w') as out:
        result=sp.run(list(map(str,cmd)),stdout=out,stderr=sp.STDOUT,timeout=240)
    text=log.read_text();print(text,flush=True)
    if result.returncode or 'HM_FULLCONE_RUNTIME_PASS' not in text or 'HM_FULLCONE_RUNTIME_FAIL' in text:
        raise RuntimeError('QEMU fullcone verification failed; inspect console.log')
    (work/'verification.json').write_text(json.dumps({'kernel':VERSION,'kernel_sha256':LINUX_SHA256,'isolated_qemu':True,'passed':True,'scope':'notifier lifecycle, parameter rejection, IPv4 UDP fullcone; hardware untested'},indent=2)+'\n')


if __name__=='__main__':main()
