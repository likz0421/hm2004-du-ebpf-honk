// SPDX-License-Identifier: Apache-2.0
'use strict';
'require baseclass';

// LuCI interprets scalar children as HTML. Array children are text-safe.
function element(tag, attrs, children) {
	if (children != null && typeof children !== 'object') children = [String(children)];
	return E(tag, attrs, children);
}

function stylesheet() {
	if (document.querySelector('link[data-onu-dashboard]')) return;
	document.head.appendChild(element('link', { rel: 'stylesheet', href: L.resource('view/onu-dashboard/onu.css'), 'data-onu-dashboard': '' }));
	document.head.appendChild(element('link', { rel: 'stylesheet', href: L.resource('view/onu-dashboard/dashboard.css'), 'data-onu-dashboard': '' }));
}
function icon(name) {
	var paths = { optical: 'M12 3v6m-7 3h14M5 12v8m7-8v8m7-8v8M8 3h8M3 20h4m3 0h4m3 0h4',
		chart: 'M3 3v18h18M6 15l4-6 4 3 5-7', shield: 'M12 3l8 4v6c0 4-5 7-8 8-3-1-8-4-8-8V7zM8 12l3 3 5-6',
		ports: 'M3 7h18v13H3zM7 7V3h10v4M7 12v4m5-4v4m5-4v4', chip: 'M6 6h12v12H6zM9 9h6v6H9zM9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4',
		arrow: 'M5 12h14m-5-5l5 5-5 5', refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1' };
	var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
	[['viewBox','0 0 24 24'],['fill','none'],['stroke','currentColor'],['stroke-width','1.6'],['stroke-linecap','round'],['stroke-linejoin','round'],['aria-hidden','true'],['class','onu-icon']].forEach(function(a) { svg.setAttribute(a[0],a[1]); });
	var p = document.createElementNS(svg.namespaceURI, 'path'); p.setAttribute('d',paths[name] || paths.optical); svg.appendChild(p); return svg;
}
function badge(text, level) { return element('span', { 'class': 'onu-badge', 'data-level': level || 'muted' }, [element('i', {'aria-hidden':'true'}), text]); }
function title(kicker, text, description, actions) {
	return element('header', {'class':'onu-heading'}, [element('div',{},[element('span',{'class':'onu-eyebrow'},kicker),element('h2',{},text),element('p',{},description)]), element('div',{'class':'onu-actions'},actions || [])]);
}
function panel(heading, subtitle, children) { return element('section',{'class':'onu-panel'},[element('div',{'class':'onu-panel-head'},[element('h3',{},heading),subtitle ? element('span',{},subtitle):'']),element('div',{'class':'onu-panel-body'},children)]); }
function metric(label, value, unit, subtitle) { return element('div',{'class':'onu-metric'},[element('span',{'class':'onu-label'},label),element('div',{'class':'onu-reading'},[value,element('small',{},unit || '')]),element('span',{'class':'onu-caption'},subtitle || '')]); }
function rows(items) {
	return element('dl',{'class':'onu-facts'},items.reduce(function(a,row) { return a.concat([element('dt',{},row[0]),element('dd',{},row[1] == null || row[1] === '' ? '—' : row[1])]); },[]));
}
function link(label, description, path, glyph) { return element('a',{'class':'onu-link',href:L.url.apply(L,path)},[icon(glyph || 'arrow'),element('span',{},[element('strong',{},label),element('small',{},description)]),icon('arrow')]); }
function managers() { return element('div',{'class':'onu-links'},[
	link(_('PON authentication'),_('Line mode and existing registration settings'),['admin','network','pon','config'],'shield'),
	link(_('Network interfaces'),_('WAN, LAN and IPv6 configuration'),['admin','network','network'],'ports'),
	link(_('IPTV'),_('Existing IPTV service manager'),['admin','network','iptv'],'optical'),
	link(_('NAT mode'),_('Keep the existing forwarding policy'),['admin','network','natmode'],'ports'),
	link(_('IGMP Proxy'),_('Existing multicast routing manager'),['admin','services','igmpproxy'],'optical'),
	link(_('FTTR'),_('Downstream optical network management'),['admin','network','fttr'],'optical')
]); }
function chart(values, unit, color) {
	var valid = values.filter(function(x) { return x != null && Number.isFinite(x); });
	if (valid.length < 2) return element('div',{'class':'onu-chart-empty'},_('Collecting samples…'));
	var low=Math.min.apply(null,valid),high=Math.max.apply(null,valid),span=Math.max(high-low,unit==='dBm'?0.4:0.1),pad=span*0.2;
	low-=pad;high=low+span+pad*2;
	var svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
	svg.setAttribute('viewBox','0 0 400 84');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('role','img');
	svg.setAttribute('aria-label',_('Recent measurements')+' '+unit);svg.setAttribute('class','onu-chart');
	var segment=[];
	function flush() {
		if(segment.length<2){segment=[];return;}
		var p=document.createElementNS(svg.namespaceURI,'polyline');
		p.setAttribute('points',segment.join(' '));p.setAttribute('fill','none');p.setAttribute('stroke',color || '#4f72e8');
		p.setAttribute('stroke-width','2.4');p.setAttribute('vector-effect','non-scaling-stroke');svg.appendChild(p);segment=[];
	}
	values.forEach(function(v,i){if(v==null || !Number.isFinite(v)){flush();return;}segment.push((i*400/(values.length-1)).toFixed(1)+','+(76-(v-low)/(high-low)*68).toFixed(1));});flush();
	return element('div',{},[svg,element('div',{'class':'onu-chart-scale'},[element('span',{},low.toFixed(1)+' '+unit),element('span',{},high.toFixed(1)+' '+unit)])]);
}
function bool(value) { return value === true || value === 1 || value === '1' ? _('Yes') : value === false || value === 0 || value === '0' ? _('No') : _('Unknown'); }
return baseclass.extend({ el:element, stylesheet:stylesheet, icon:icon, badge:badge, title:title, panel:panel, metric:metric, rows:rows, link:link, managers:managers, chart:chart, bool:bool });
