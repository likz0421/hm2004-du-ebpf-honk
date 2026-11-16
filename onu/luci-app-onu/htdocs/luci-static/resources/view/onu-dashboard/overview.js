// SPDX-License-Identifier: Apache-2.0
'use strict';
'require dom';
'require poll';
'require view';
'require onu-dashboard.data as data';
'require onu-dashboard.components as components';

return view.extend({
	load: function() { return data.snapshot(); },
	render: function(initial) {
		components.stylesheet();
		var samples=[], last=null, current=initial, paused=false, busy=false;
		var area=components.el('div',{'class':'onu-content'}), stamp=components.el('span',{'class':'onu-updated','aria-live':'polite'});
		var pause=components.el('button',{'class':'cbi-button','click':function(){paused=!paused;pause.textContent=paused? _('Resume updates'):_('Pause updates');}},_('Pause updates'));
		var refresh=components.el('button',{'class':'cbi-button cbi-button-action','click':function(){return update(true);}},[components.icon('refresh'),_('Refresh now')]);
		var root=components.el('div',{'class':'cbi-map onu-dashboard'},[
			components.title('ONU / PON',_('ONU Overview'),_('Optical link, service state and forwarding activity in one place.'),[stamp,pause,refresh]),area
		]);
		function portRate(snapshot,name,direction) {
			var a=(last&&last.ports||[]).filter(function(p){return p.name===name;})[0];
			var b=snapshot.ports.filter(function(p){return p.name===name;})[0];
			return a&&b ? data.rate((a.value.statistics||{})[direction+'_bytes'],(b.value.statistics||{})[direction+'_bytes'],(snapshot.time-last.time)/1000) : null;
		}
		function draw(s,append) {
			var f=s.pon.frontend||{},l=s.pon.line||{},r=s.pon.registration||{},d=s.pon.datapath||{},h=data.health(s),proto=s.protocol||{};
			var rx=portRate(s,'pon0','rx'),tx=portRate(s,'pon0','tx');
			if(append){samples.push({time:s.time,rx:rx,tx:tx,light:s.ponError||f.error?null:data.number(f.rx_power_dbm)});if(samples.length>120)samples.shift();}
			var connections=s.connections,total=connections?connections.tcp_total+connections.udp_total:null;
			var offload=connections?connections.tcp_npu+connections.udp_npu:null;
			var hero=components.el('section',{'class':'onu-hero','data-level':h.level},[
				components.el('div',{'class':'onu-hero-main'},[components.el('div',{'class':'onu-eyebrow'},'H3C HM2004-DU'),components.el('div',{'class':'onu-hero-title'},[components.icon('optical'),components.el('h3',{},h.label)]),components.el('p',{},h.detail),components.el('div',{'class':'onu-hero-badges'},[components.badge(data.mode(s).toUpperCase()||_('Mode unavailable')),components.badge(r.onu_state||r.mpcp_state||_('Registration unknown'),h.level),components.badge(s.board.model||'HM2004-DU')])]),
				components.el('div',{'class':'onu-hero-facts'},components.rows([
					[_('Optical signal'),components.bool(l.optical_signal)],[_('Data path'),components.bool(d.data_path_configured)],
					[_('OLT vendor'),proto.olt_vendor_id||'—'],[_('Firmware'),(s.board.release||{}).description||'—']
				]))
			]);
			function reading(field){return s.ponError||f.error?'—':data.format(f[field]);}
			var telemetry=components.el('div',{'class':'onu-metrics'},[
				components.metric(_('Receive optical power'),reading('rx_power_dbm'),'dBm',_('Reported by the optical frontend')),
				components.metric(_('Transmit optical power'),reading('tx_power_dbm'),'dBm',_('Reported by the optical frontend')),
				components.metric(_('Temperature'),reading('temperature_celsius'),'°C',_('Optical frontend temperature')),
				components.metric(_('Supply voltage'),reading('voltage_volts'),'V',_('Optical frontend supply')),
				components.metric(_('Laser bias'),reading('tx_bias_ma'),'mA',_('Optical transmitter current'))
			]);
			var trend=components.panel(_('Live trends'),_('Current browser session · 3-second samples'),[
				components.el('div',{'class':'onu-trends'},[
					components.el('div',{},[components.el('div',{'class':'onu-chart-title'},[_('Receive optical power'),components.el('strong',{},reading('rx_power_dbm')+' dBm')]),components.chart(samples.map(function(x){return x.light;}),'dBm','#5c6de8')]),
					components.el('div',{},[components.el('div',{'class':'onu-chart-title'},[_('PON receive traffic'),components.el('strong',{},data.format(rx)+' Mbps')]),components.chart(samples.map(function(x){return x.rx;}),'Mbps','#1b9b8d')])
				]),components.el('p',{'class':'onu-note'},_('Traffic is measured from interface byte counters. Missing samples and counter resets are not shown as zero. Optical values are not a diagnosis of the upstream network.'))
			]);
			var stats=components.panel(_('Connections and forwarding'),_('Existing connection monitor'),[
				components.el('div',{'class':'onu-metrics onu-metrics-three'},[components.metric(_('Current connections'),total==null?'—':String(total),'',_('TCP + UDP')),components.metric(_('Offloaded connections'),offload==null?'—':String(offload),'',_('OFFLOAD / HW_OFFLOAD flags')),components.metric(_('PON transmit traffic'),data.format(tx),'Mbps',_('Interface transmit rate'))]),
				components.el('p',{'class':'onu-note'},_('Offload counts include software and hardware offload flags; they do not certify that every counted flow is using the NPU.'))
			]);
			var table=components.el('table',{'class':'table onu-port-table'},[components.el('thead',{},components.el('tr',{},[_('Port'),_('Link'),_('Receive'),_('Transmit')].map(function(x){return components.el('th',{},x);}))),
				components.el('tbody',{},s.ports.map(function(p){var up=data.boolean(p.value.carrier);return components.el('tr',{},[
					components.el('td',{},components.el('strong',{},p.name)),components.el('td',{},components.badge(up===true?_('Connected'):up===false?_('Disconnected'):_('Unknown'),up===true?'good':up===false?'muted':'unknown')),
					components.el('td',{},data.format(portRate(s,p.name,'rx'))+' Mbps'),components.el('td',{},data.format(portRate(s,p.name,'tx'))+' Mbps')]);}))]);
			dom.content(area,[hero,telemetry,trend,stats,components.panel(_('Port activity'),_('Physical port and PON interface counters'),components.el('div',{'class':'onu-table-scroll'},table)),components.panel(_('Manage services'),_('Open the installed manager for each service'),components.managers()),components.link(_('Detailed PON status'),_('OLT, GEM/T-CONT, VLAN and protocol counters'),['admin','onu','status'],'chart')]);
			stamp.textContent=(_('Updated')+' '+new Date(s.time).toLocaleTimeString());
			if(append)last=s;
		}
		function update(force) {
			if(busy||(!force&&(paused||document.hidden)))return Promise.resolve();
			busy=true;refresh.disabled=true;
			return data.snapshot().then(function(s){current=s;draw(s,true);}).catch(function(){stamp.textContent=_('Update failed; showing last sample');}).finally(function(){busy=false;refresh.disabled=false;});
		}
		draw(initial,true);poll.add(function(){return update(false);},3);
		return root;
	},
	handleSaveApply:null,handleSave:null,handleReset:null
});
