#!/usr/bin/env node
'use strict';
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict'), path = require('node:path');
const source = process.argv[2] || path.join(__dirname, '..', '..', 'pon-ui', 'status.js');
const base = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/pbs05-schema1.json')));
const clone = x => JSON.parse(JSON.stringify(x));
function node(tag, attrs, children) {
  return {tag, attrs:attrs||{}, children:[children].flat(Infinity).filter(x=>x!=null), open:false,
    getAttribute(k){return this.attrs[k];}, appendChild(c){this.children.push(c);},
    querySelectorAll(q){return walk(this).filter(n => q==='details[data-pon-details]' ? n.tag==='details'&&'data-pon-details' in n.attrs : q==='link[data-pon-stylesheet]' ? n.tag==='link'&&'data-pon-stylesheet' in n.attrs : false);}};
}
function walk(n){return (Array.isArray(n)?n:[n]).flatMap(x=>x&&typeof x==='object'?[x,...walk(x.children||[])]:[]);}
function text(n){return (Array.isArray(n)?n:[n]).map(x=>x&&typeof x==='object'?text(x.children):String(x??'')).join('');}
function row(n,label){for(const p of walk(n)){const c=p.children||[];for(let i=0;i<c.length-1;i++)if(c[i]?.tag==='dt'&&text(c[i])===label)return c[i+1];}throw Error('Missing row '+label);}
function green(n){return walk(n).some(x=>x.attrs['data-state']==='ok');}
function harness(fixture=clone(base), override={}) {
  const polls=[], calls=[];
  const sections={xpon:[{'.name':'line0',device:'pon0',mode:fixture.pon.line?.configured_mode||'xgspon'}],omci:[{'.name':'omci0',line:'line0'}],oam:[{'.name':'oam0',line:'line0'}]};
  let protocol=fixture.pon.line?.active_mode?.startsWith('epon-')?fixture.oam:fixture.omci;
  const head=node('head',{},[]);
  const ctx=vm.createContext({console, components:{stylesheet(){},el:node}, E:node,_:x=>x,view:{extend:x=>x},
    document:{head,querySelector:q=>head.querySelectorAll(q)[0]},
    dom:{content(n,c){n.children=[c].flat(Infinity);}},poll:{add(fn){polls.push(fn);}},
    uci:{load:()=>Promise.resolve(),sections:(p,t)=>sections[t]},
    fs:{exec_direct(cmd,args){calls.push([cmd,args]);if(override.reject)return Promise.reject(Error('unavailable')); return Promise.resolve(cmd.includes('pondctl') ? ('protocol' in override?override.protocol:JSON.stringify(protocol)) : ('pon' in override?override.pon:JSON.stringify(fixture.pon)));}},
    L:{resource:x=>'/luci-static/resources/'+x,resolveDefault:(p,v)=>Promise.resolve(p).catch(()=>v)}});
  const names=['renderLine','renderOmci','renderOam','renderStatus','loadStatus','loadProtocolStatus','loidAuthenticationAdvertised','passwordAuthentication'];
  const src=fs.readFileSync(source,'utf8').replace(/^return view\.extend\(\{/m,`globalThis.api={${names.join(',')}};\nreturn view.extend({`);
  const view=vm.runInContext('(function(){'+src+'\n})()',ctx,{filename:source});
  const data=()=>({lines:[{section:sections.xpon[0],...fixture.pon}],omci:[{section:sections.omci[0],values:fixture.omci}],oam:[{section:sections.oam[0],values:fixture.oam}]});
  return {a:ctx.api,view,fixture,sections,polls,calls,head,data};
}
const cases=[];const test=(name,fn)=>cases.push([name,fn]);
test('schema1 full load/render and read-only exec argv',async()=>{const h=harness();const d=await h.view.load();const root=h.view.render(d);assert.match(text(root),/O5 — Operation/);assert.equal(text(row(root,'Receive optical power')),'-18.50dBm');assert.match(text(root),/18446744073709551615/);assert.equal(h.view.handleSaveApply,null);assert.equal(h.view.handleSave,null);assert.equal(h.view.handleReset,null);assert(h.calls.every(([c,a])=>c==='/usr/sbin/ponctl'?JSON.stringify(a)==='["--device","pon0","status","--json"]':c==='/usr/bin/pondctl'&&JSON.stringify(a)==='["status","--line","line0"]'));});
test('legacy O5 does not imply LOID accepted',()=>{const h=harness();const r=h.a.renderStatus(h.data());assert.equal(text(row(r,'Authentication mode')),'Not reported');const a=row(r,'LOID authentication');assert.equal(text(a),'Not reported');assert(!green(a));});
test('missing advertised flag is not true',()=>{assert.equal(harness().a.loidAuthenticationAdvertised({}),false);});
test('password plus missing advertised flag is not proof',()=>{assert.equal(harness().a.passwordAuthentication({auth_mode:'password'}),false);});
test('all authentication fields absent stays Unknown',()=>{const h=harness();h.fixture.omci={protocol_version:1};const r=h.a.renderStatus(h.data());const a=row(r,'Authentication result');assert.equal(text(a),'Unknown');assert(!green(a));});
for(const meaning of ['accepted','not-authenticated','loid-not-found','password-mismatch','loid-conflict'])test('legacy explicit authentication '+meaning,()=>{const h=harness();h.fixture.omci.authentication_meaning=meaning;const r=row(h.a.renderStatus(h.data()),'LOID authentication');assert.equal(green(r),meaning==='accepted');});
for(const [state,expected,ok] of [['O2_3','Pending',false],['O5','Accepted',true],['O7','Not authenticated',false],['future','Unknown',false]])test('explicit password state '+state,()=>{const h=harness();Object.assign(h.fixture.omci,{auth_mode:'password',ctc_loid_advertised:false});h.fixture.pon.registration.onu_state=state;const r=row(h.a.renderStatus(h.data()),'Password authentication');assert.equal(text(r),expected);assert.equal(green(r),ok);});
test('O2_3 has intelligible combined state',()=>{const h=harness();h.fixture.pon.registration.onu_state='O2_3';assert.equal(text(row(h.a.renderStatus(h.data()),'ONU state')),'O2_3 — Standby / Serial-Number');});
for(const value of [null,'',' ',false,true,'bogus',{},[],NaN,Infinity,-Infinity])test('frontend invalid '+String(value),()=>{const h=harness();h.fixture.pon.frontend.rx_power_dbm=value;const r=row(h.a.renderStatus(h.data()),'Receive optical power');assert.equal(text(r),'Unknown');assert(!green(r));});
for(const value of [0,-40,'-18.5'])test('frontend valid '+value,()=>{const h=harness();h.fixture.pon.frontend.rx_power_dbm=value;assert.equal(text(row(h.a.renderStatus(h.data()),'Receive optical power')),Number(value).toFixed(2)+'dBm');});
test('frontend absent/error distinguish unsupported/read failed',()=>{const h=harness();delete h.fixture.pon.frontend.rx_power_dbm;assert.equal(text(row(h.a.renderStatus(h.data()),'Receive optical power')),'Not supported');h.fixture.pon.frontend.error='io';assert.equal(text(row(h.a.renderStatus(h.data()),'Receive optical power')),'Read failed');});
test('legacy missing multicast action is not inferred from empty VLAN array',()=>{const h=harness();const r=h.a.renderStatus(h.data());assert.equal(text(row(r,'Multicast downstream VLAN IDs')),'Not reported');assert.equal(text(row(r,'Multicast downstream tag action')),'Not reported');});
for(const body of ['null','[]','false','42','"ok"','{','{}','{"protocol_version":2}','{"protocol_version":"1"}'])test('protocol rejects '+body,async()=>{const h=harness(undefined,{protocol:body});const d=await h.view.load();assert(d.omci[0].error);const r=h.view.render(d);assert.match(text(r),/Invalid OMCI status response/);});
for(const body of ['null','[]','{"schema_version":2,"line":{}}','{"schema_version":1,"line":[]}','{"schema_version":1,"line":"ok"}'])test('line rejects '+body,async()=>{const h=harness(undefined,{pon:body});const d=await h.view.load();assert(d.lines[0].error);assert.match(text(h.view.render(d)),/Invalid status response/);});
test('backend offline stays explicit error',async()=>{const h=harness(undefined,{reject:true});const d=await h.view.load();const r=h.view.render(d);assert.match(text(r),/Device unavailable/);assert.match(text(r),/Unable to read OMCI status/);assert(!green(r));});
test('protocol valid minimal object renders unknown fields safely',async()=>{const h=harness(undefined,{protocol:'{"protocol_version":1}'});const d=await h.view.load();assert.equal(d.omci[0].error,null);const r=h.view.render(d);assert.equal(text(row(r,'OMCI channel online')),'Unknown');assert.equal(text(row(r,'Data path state')),'Unknown');assert(!green(row(r,'Data path state')));});
test('missing LOID configuration has no false green indicator',()=>{const h=harness();h.fixture.omci.loid_configured='0';assert(!green(row(h.a.renderStatus(h.data()),'LOID configured locally')));});
for(const [configured,active,title,absent] of [['epon-1g','xgspon','OMCI channel online','LLID OAM channel online'],['xgspon','epon-1g','LLID OAM channel online','OMCI channel online']])test('pending mode '+configured+' -> '+active,async()=>{const f=clone(base);Object.assign(f.pon.line,{configured_mode:configured,active_mode:active,mode_pending:true});const h=harness(f);const d=await h.view.load();const r=h.view.render(d);assert(row(r,title));assert.throws(()=>row(r,absent));assert.match(text(r),/Takes effect after interface restart/);});
test('OAM absent operator does not claim IEEE or inapplicable auth',()=>{const h=harness();h.fixture.pon.line.active_mode='epon-1g';h.fixture.oam={protocol_version:1};const r=h.a.renderStatus(h.data());assert.equal(text(row(r,'CTC discovery')),'Unknown');assert.equal(text(row(r,'LOID authentication')),'Unknown');assert.equal(text(row(r,'Configured OAM profile')),'Unknown');});
test('OAM malformed CTC version cannot render NaN',()=>{const h=harness();h.fixture.pon.line.active_mode='epon-1g';h.fixture.oam.ctc_version='oops';assert.equal(text(row(h.a.renderStatus(h.data()),'CTC version')),'Unknown');});
test('OAM CTC state accepted/denied does not derive from O5',()=>{const h=harness();h.fixture.pon.line.active_mode='epon-1g';h.fixture.oam.authentication_status='not-authenticated';assert(!green(row(h.a.renderStatus(h.data()),'LOID authentication')));h.fixture.oam.authentication_status='accepted';assert(green(row(h.a.renderStatus(h.data()),'LOID authentication')));});
test('empty configuration produces empty-state text',async()=>{const h=harness();for(const t of Object.keys(h.sections))h.sections[t]=[];assert.match(text(h.view.render(await h.view.load())),/No PON instances are configured/);assert.equal(h.calls.length,0);});
test('no device yields error without device command',async()=>{const h=harness();h.sections.xpon[0].device='';const d=await h.view.load();assert.match(text(h.view.render(d)),/No device configured/);assert(!h.calls.some(([c])=>c.includes('ponctl')));});
test('poll preserves expanded details, stylesheet inserted once',async()=>{const h=harness();const d=await h.view.load();const r=h.view.render(d);const fold=r.querySelectorAll('details[data-pon-details]')[0];fold.open=true;await h.polls[0]();const replacement=r.querySelectorAll('details[data-pon-details]')[0];assert.notEqual(replacement,fold);assert.equal(replacement.open,true);h.view.render(d);assert.equal(h.head.children.length,1);});
test('unsupported device and line are visible and never exec',async()=>{const h=harness();h.sections.xpon[0].device='pon1';h.sections.xpon[0]['.name']='line1';h.sections.omci[0].line='line1';const d=await h.view.load();assert.match(text(h.view.render(d)),/Unsupported line/);assert.equal(h.calls.length,0);});
(async()=>{let failed=0;for(const [name,fn] of cases){try{await fn();console.log('PASS '+name);}catch(e){failed++;console.log('FAIL '+name+' :: '+e.message);}}console.log(JSON.stringify({source,tests:cases.length,passed:cases.length-failed,failed}));process.exitCode=failed?1:0;})();
