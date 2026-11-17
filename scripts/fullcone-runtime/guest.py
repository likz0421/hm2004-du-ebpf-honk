#!/usr/bin/python3
"""Runs only inside the disposable QEMU guest, never on the build host."""
import json
import os
from pathlib import Path
import socket
import subprocess as sp
import sys
import time


def run(args, input=None, ok=True):
    p=sp.run(args,input=input,text=True,capture_output=True,timeout=30)
    if (ok and p.returncode) or p.returncode < 0:
        raise RuntimeError(f'{args}: rc={p.returncode}\n{p.stdout}\n{p.stderr}')
    return p


def rules(ns, command, check=False):
    return run(['ip','netns','exec',ns,'nft',*(['-c'] if check else []),'-f','-'],command)


def ns_setup(ns):
    run(['ip','netns','add',ns]);run(['ip','-n',ns,'link','set','lo','up'])
    run(['ip','netns','exec',ns,'sysctl','-w','net.netfilter.nf_conntrack_events=1'])


RULESET='''table ip fc {
 chain pre { type nat hook prerouting priority -100; policy accept; fullcone; }
 chain post { type nat hook postrouting priority 100; policy accept; fullcone; }
}
'''


def expect_event(ns):
    # Destroy one actual UDP conntrack while both subscribers are registered.
    run(['ip','netns','exec',ns,'conntrack','-D','-p','udp','--dport','19191'],ok=False)
    receiver=sp.Popen(['ip','netns','exec',ns,'python3','-c',"import socket,time;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',19191));s.recvfrom(256);time.sleep(10)"])
    output=open('/tmp/ct-events.log','w+')
    watcher=sp.Popen(['ip','netns','exec',ns,'conntrack','-E','-e','DESTROY','-o','timestamp'],stdout=output,stderr=output,text=True)
    try:
        time.sleep(.2)
        run(['ip','netns','exec',ns,'python3','-c',"import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'test',('127.0.0.1',19191))"])
        run(['ip','netns','exec',ns,'conntrack','-D','-p','udp','--dport','19191'])
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            output.flush();output.seek(0)
            if 'DESTROY' in output.read():
                return
            time.sleep(.05)
        raise AssertionError('ctnetlink destroy event missing after fullcone transaction')
    finally:
        watcher.terminate()
        try:watcher.wait(timeout=3)
        except sp.TimeoutExpired:watcher.kill();watcher.wait()
        receiver.terminate()
        try:receiver.wait(timeout=3)
        except sp.TimeoutExpired:receiver.kill();receiver.wait()
        output.close()


def lifecycle(order):
    # Namespaces have been destroyed before each module unload.
    if order=='ctnetlink-first':
        run(['modprobe','nf_conntrack_netlink']);run(['modprobe','nft_fullcone'])
    else:
        run(['modprobe','nft_fullcone'])
    for ns in ['first','second']:
        ns_setup(ns)
        rules(ns,RULESET,check=True)
        rules(ns,RULESET)
    if order=='fullcone-first':run(['modprobe','nf_conntrack_netlink'])
    expect_event('first');expect_event('second')
    for unused in range(3):
        rules('first','flush ruleset\n')
        rules('first',RULESET,check=True)
        rules('first',RULESET)
        expect_event('first')
    # Removing one namespace must not unsubscribe the other.
    run(['ip','netns','del','first']);expect_event('second')
    p=run(['ip','netns','exec','second','nft','add','rule','ip','fc','post','udp','dport','1234','fullcone','to',':40000-40100'],ok=False)
    if p.returncode==0 or 'Operation not supported' not in p.stderr:
        raise AssertionError('Unsupported port attributes were not rejected: '+p.stderr)
    run(['ip','netns','del','second'])
    run(['rmmod','nft_fullcone']);run(['rmmod','nf_conntrack_netlink'])
    print('PASS lifecycle:',order,flush=True)


def server():
    a=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);a.settimeout(12)
    a.bind(('10.20.0.2',19000))
    data,peer=a.recvfrom(256)
    # Endpoint B has not received any request from the client.
    b=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    b.bind(('10.20.0.3',19001))
    a.sendto(b'A',peer);b.sendto(b'B',peer)
    print('two-endpoint reply sent',flush=True)


def client():
    c=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);c.settimeout(10)
    c.bind(('10.10.0.2',18000));c.sendto(b'open',('10.20.0.2',19000))
    received={c.recvfrom(256)[0],c.recvfrom(256)[0]}
    if received!={b'A',b'B'}:raise AssertionError(received)
    print('PASS UDP replies from requested and unsolicited endpoints',flush=True)


def dataplane():
    run(['modprobe','nf_conntrack_netlink']);run(['modprobe','nft_fullcone'])
    for ns in ['client','router','remote']:ns_setup(ns)
    for left,right,ns1,ns2 in [('c0','lan0','client','router'),('wan0','r0','router','remote')]:
        run(['ip','link','add',left,'type','veth','peer','name',right])
        run(['ip','link','set',left,'netns',ns1]);run(['ip','link','set',right,'netns',ns2])
    for ns,iface,address in [('client','c0','10.10.0.2/24'),('router','lan0','10.10.0.1/24'),('router','wan0','10.20.0.1/24'),('remote','r0','10.20.0.2/24')]:
        run(['ip','-n',ns,'addr','add',address,'dev',iface]);run(['ip','-n',ns,'link','set',iface,'up'])
    run(['ip','-n','remote','addr','add','10.20.0.3/24','dev','r0'])
    run(['ip','-n','client','route','add','default','via','10.10.0.1'])
    run(['ip','netns','exec','router','sysctl','-w','net.ipv4.ip_forward=1'])
    rules('router','''table ip fc {
 chain pre { type nat hook prerouting priority -100; policy accept; iifname "wan0" fullcone; }
 chain post { type nat hook postrouting priority 100; policy accept; oifname "wan0" fullcone; }
}
''')
    listing=run(['ip','netns','exec','router','nft','list','ruleset']).stdout
    if listing.count('fullcone') != 2:raise AssertionError('Fullcone rules missing')
    s=sp.Popen(['ip','netns','exec','remote','python3',__file__,'server'])
    try:
        time.sleep(.3)
        run(['ip','netns','exec','client','python3',__file__,'client'])
        if s.wait(timeout=5)!=0:raise AssertionError('UDP server failed')
    finally:
        if s.poll() is None:s.kill();s.wait()
    for ns in ['client','router','remote']:run(['ip','netns','del',ns])
    run(['rmmod','nft_fullcone']);run(['rmmod','nf_conntrack_netlink'])
    print('PASS real fullcone UDP two-endpoint dataplane',flush=True)


def main():
    if len(sys.argv)>1:
        {'server':server,'client':client}[sys.argv[1]]();return
    if not Path('/run/hm-qemu-guest').exists():
        raise SystemExit('Refusing to run outside disposable QEMU guest')
    lifecycle('ctnetlink-first');lifecycle('fullcone-first');dataplane()
    dmesg=run(['dmesg']).stdout
    for bad in ['BUG:','Oops:','WARNING: CPU:','KASAN:','kernel panic']:
        if bad.lower() in dmesg.lower():raise AssertionError('Kernel diagnostic: '+bad)
    print('HM_FULLCONE_RUNTIME_PASS',flush=True)


if __name__=='__main__':
    main()
