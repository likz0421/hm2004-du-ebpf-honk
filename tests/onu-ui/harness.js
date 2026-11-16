// SPDX-License-Identifier: Apache-2.0
'use strict';
const vm = require('node:vm'), fs = require('node:fs'), path = require('node:path');
const resources = path.resolve(__dirname, '../../onu/luci-app-onu/htdocs/luci-static/resources');
const base = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/pbs05-schema1.json')));
function node(tag, attrs, children) {
  if (Array.isArray(tag)) return node('fragment', {}, tag);
  if (children === undefined && (typeof attrs !== 'object' || Array.isArray(attrs))) { children = attrs; attrs = {}; }
  const n = {tag, attrs:attrs || {}, children:[children].flat(Infinity).filter(x=>x!=null), open:false,
    getAttribute(k){ return this.attrs[k]; },setAttribute(k,v){this.attrs[k]=String(v);},appendChild(c){this.children.push(c);return c;},
    querySelectorAll(q){return walk(this).filter(x=>q==='details[data-pon-details]'? x.tag==='details'&&'data-pon-details' in x.attrs :
      q==='link[data-pon-stylesheet]'? x.tag==='link'&&'data-pon-stylesheet' in x.attrs :
      q==='link[data-onu-dashboard]'? x.tag==='link'&&'data-onu-dashboard' in x.attrs : false);}
  };
  Object.defineProperty(n,'textContent',{set(v){this.children=[String(v)];},get(){return text(this);}});
  return n;
}
function walk(n){return (Array.isArray(n)?n:[n]).flatMap(x=>x&&typeof x==='object'?[x,...walk(x.children||[])]:[]);}
function text(n){return (Array.isArray(n)?n:[n]).map(x=>x&&typeof x==='object'?text(x.children):String(x??'')).join('');}
function harness(options={}) {
  const fixture=JSON.parse(JSON.stringify(base));
  fixture.pon.frontend.voltage_volts=3.3;fixture.pon.frontend.tx_bias_ma=12.5;
  const calls=[], polls=[], head=node('head',{},[]), config=[{'.name':'line0',device:'pon0',mode:'xgspon'}];
  const state={fixture,config,protocol:null,offline:false,portBytes:1000000};
  const context=vm.createContext({console, E:node,_:x=>x,view:{extend:x=>x},baseclass:{extend:x=>x},
    document:{head,hidden:false,querySelector:q=>head.querySelectorAll(q)[0],createElementNS(ns,tag){const n=node(tag,{},[]);n.namespaceURI=ns;return n;}},
    dom:{content(n,c){n.children=[c].flat(Infinity);}},poll:{add(fn){polls.push(fn);}},
    uci:{load:()=>Promise.resolve(),sections:(p,t)=>t==='xpon'?state.config: t==='omci'?[{'.name':'omci0',line:'line0'}]:[{'.name':'oam0',line:'line0'}]},
    fs:{exec_direct(cmd,args){calls.push({cmd,args:[...args]});if(state.offline)return Promise.reject(Error('offline'));
      if(cmd.includes('ponstat'))return Promise.resolve('tcp_total=40\ntcp_npu=18\nudp_total=10\nudp_npu=6\n');
      return Promise.resolve(JSON.stringify(cmd.includes('pondctl')?(state.protocol||state.fixture.omci):state.fixture.pon));},
      read(p){calls.push({read:p});if(p==='/etc/board.json')return Promise.resolve(JSON.stringify({pon_data:{factory:{type:'ubi',size:1048576,parent:'ubi'}},identity:{targets:{factory:{fields:{pon_sn:{offset:96,size:12,encoding:'pon-ascii12'}}}}}}));
        return Promise.resolve('4857544331323334\n');}},
    rpc:{declare(spec){return (...args)=>{calls.push({rpc:spec.object+'.'+spec.method,args});
      if(spec.method==='board')return Promise.resolve({model:'H3C HM2004-DU',hostname:'OpenWrt',kernel:'6.18.60',release:{description:'PonWrt SNAPSHOT test'}});
      if(spec.method==='info')return Promise.resolve({uptime:3600,memory:{total:536870912,available:222298112}});
      return Promise.resolve({carrier:true,statistics:{rx_bytes:state.portBytes,tx_bytes:state.portBytes/2}});};}},
    L:{resource:x=>'/luci-static/resources/'+x,url:(...p)=>'/cgi-bin/luci/'+p.join('/'),resolveDefault:(p,v)=>Promise.resolve(p).catch(()=>v)}
  });
  function load(relative,aliases={}) {Object.assign(context,aliases);const src=fs.readFileSync(path.join(resources,relative),'utf8');return vm.runInContext('(function(){'+src+'\n})()',context,{filename:relative});}
  const data=load('onu-dashboard/data.js'),components=load('onu-dashboard/components.js');
  return {loadView:name=>load('view/onu-dashboard/'+name+'.js',{data,components}),data,components,calls,polls,context,state,head};
}
module.exports={harness,node,text,walk,resources};
