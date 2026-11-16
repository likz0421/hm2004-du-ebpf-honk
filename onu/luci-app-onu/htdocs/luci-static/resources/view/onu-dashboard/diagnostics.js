// SPDX-License-Identifier: Apache-2.0
'use strict';
'require view';
'require dom';
'require onu-dashboard.data as data';
'require onu-dashboard.components as components';

function check(label, value, good, bad, hint) {
	return components.el('div', {'class':'onu-check'}, [components.icon('shield'), components.el('div', {}, [components.el('strong', {}, label), components.el('p', {}, hint)]),
		components.badge(value === true ? good : value === false ? bad : _('Unknown'), value === true ? 'good' : value === false ? 'pending' : 'unknown')]);
}
function diagnosticCards(s) {
	var line = s.pon.line || {}, path = s.pon.datapath || {}, reg = s.pon.registration || {}, p = s.protocol || {}, counters = s.pon.counters || {};
	var isEpon = data.mode(s).indexOf('epon-') === 0;
	var registered = isEpon ? (reg.mpcp_state == null ? null : reg.mpcp_state === 'registered') :
		(reg.onu_state == null ? null : reg.onu_state === 'O5');
	return [
		components.panel(_('Read-only health checks'), _('No interface is restarted by these checks'), [
			check(_('PON status interface'), !s.ponError, _('Available'), _('Unavailable'), s.ponError || _('The running driver exposes the expected status format.')),
			check(_('Optical signal'), data.boolean(line.optical_signal), _('Detected'), _('Not detected'), _('Check the fibre connection before changing registration settings.')),
			check(_('Line registration'), registered, _('Registered'), _('Pending'), _('Registration is separate from Internet access and service provisioning.')),
			check(_('Service data path'), data.boolean(path.service_ready), _('Ready'), _('Not ready'), _('A registered line can still be waiting for GEM/LLID and VLAN configuration.')),
			check(_('Protocol agent'), !s.protocolError, _('Available'), _('Unavailable'), s.protocolError || _('OMCI or OAM status is responding.'))
		]),
		components.el('div', {'class':'onu-two-column'}, [
			components.panel(_('Recovery counters'), _('Reported by the running driver'), components.rows([
				[_('Last start error'), line.last_start_error], [_('Receiver activation count'), counters.rx_start_count],
				[_('Synchronization losses'), counters.sync_losses], [_('Recovery attempts'), counters.recoveries],
				[_('Full reinitializations'), counters.full_reinitializations], [_('MPCP timeouts'), counters.mpcp_timeouts]
			])),
			components.panel(_('Protocol and service'), isEpon ? 'OAM / MPCP' : 'OMCI / PLOAM', components.rows([
				[_('Line mode'), data.mode(s).toUpperCase() || '—'], [_('Registration state'), isEpon ? reg.mpcp_state : reg.onu_state],
				[_('Backend state'), p.backend_state], [_('Backend error'), p.backend_error],
				[_('Received messages'), p.rx_messages], [_('Transmitted messages'), p.tx_messages], [_('Parse errors'), p.parse_errors]
			]))
		]),
		components.panel(_('Diagnostic tools'), _('Use the existing PON manager for capture and restart'), [
			components.el('p', {'class':'onu-note'}, _('Packet capture, diagnostic downloads and PON restarts remain in the installed diagnostic manager. These operations may interrupt the line or include private network information in an export.')),
			components.link(_('Open PON diagnostic tools'), _('Capture configuration, diagnostic download and explicit restart controls'), ['admin','network','pon','diagnostics'], 'chart'),
			components.link(_('Detailed PON status'), _('Inspect OLT, GEM/T-CONT, VLAN and protocol counters'), ['admin','onu','status'], 'optical')
		])
	];
}
return view.extend({
	load: function() { return data.snapshot(); },
	render: function(initial) {
		components.stylesheet();
		var area = components.el('div', {}, diagnosticCards(initial));
		var stamp = components.el('span', {'class':'onu-updated', 'aria-live':'polite'}, _('Updated') + ' ' + new Date(initial.time).toLocaleTimeString());
		var button = components.el('button', {'class':'cbi-button cbi-button-action', 'click':function() {
			button.disabled = true;
			return data.snapshot().then(function(s) { dom.content(area, diagnosticCards(s)); stamp.textContent = _('Updated') + ' ' + new Date(s.time).toLocaleTimeString(); })
				.catch(function() { stamp.textContent = _('Update failed; showing last sample'); })
				.finally(function() { button.disabled = false; });
		}}, [components.icon('refresh'), _('Run checks again')]);
		return components.el('div', {'class':'cbi-map onu-dashboard'}, [
			components.title('ONU / DIAGNOSTICS', _('ONU Diagnostics'), _('Locate optical, registration and service problems without changing configuration.'), [stamp, button]), area
		]);
	},
	handleSaveApply: null, handleSave: null, handleReset: null
});
