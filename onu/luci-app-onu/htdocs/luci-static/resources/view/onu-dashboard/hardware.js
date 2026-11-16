// SPDX-License-Identifier: Apache-2.0
'use strict';
'require view';
'require onu-dashboard.data as data';
'require onu-dashboard.components as components';

function serial(value) {
	if (typeof value !== 'string') return '—';
	value = value.trim();
	if (!value || value === 'none' || value === 'default') return _('Not overridden');
	if (!/^[0-9a-f]{16}$/i.test(value)) return value;
	var prefix = '', ok = true;
	for (var i = 0; i < 8; i += 2) {
		var c = parseInt(value.slice(i, i + 2), 16);
		if (c < 32 || c > 126) ok = false;
		prefix += String.fromCharCode(c);
	}
	return ok ? prefix + value.slice(8).toUpperCase() : value.toUpperCase();
}
function size(value) {
	var n = data.number(value);
	return n == null ? '—' : (n / 1048576).toFixed(1) + ' MiB';
}
function uptime(value) {
	var n = data.number(value);
	if (n == null || n < 0) return '—';
	return Math.floor(n / 86400) + 'd ' + Math.floor(n % 86400 / 3600) + 'h ' + Math.floor(n % 3600 / 60) + 'm';
}
return view.extend({
	load: function() { return data.hardware(); },
	render: function(result) {
		components.stylesheet();
		var s = result.snapshot, board = s.board || {}, sys = s.system || {}, layout = result.layout || {};
		var reg = s.pon.registration || {}, front = s.pon.frontend || {}, protocol = s.protocol || {};
		var memory = sys.memory || {}, targets = (layout.identity || {}).targets || {}, stores = layout.pon_data || {};
		var storageCards = Object.keys(stores).map(function(name) {
			var entry = stores[name] || {}, fields = ((targets[name] || {}).fields || {});
			var listing = Object.keys(fields).map(function(field) {
				var definition = fields[field] || {}, offset = data.number(definition.offset);
				return components.el('tr', {}, [components.el('td', {}, field), components.el('td', {}, offset == null ? '—' : '0x' + offset.toString(16)),
					components.el('td', {}, data.number(definition.size) == null ? '—' : String(definition.size)), components.el('td', {}, definition.encoding || '—')]);
			});
			return components.panel(_('Board identity layout') + ' · ' + name, _('Read from this device’s board declaration'), [
				components.rows([[_('Storage type'), entry.type || '—'], [_('Logical capacity'), size(entry.size)], [_('Parent device'), entry.parent || '—']]),
				listing.length ? components.el('div', {'class':'onu-table-scroll'}, components.el('table', {'class':'table'}, [
					components.el('thead', {}, components.el('tr', {}, [_('Field'), _('Offset'), _('Bytes'), _('Encoding')].map(function(x) { return components.el('th', {}, x); }))),
					components.el('tbody', {}, listing)])) : components.el('p', {'class':'onu-note'}, _('No identity fields are declared for this target.'))
			]);
		});
		if (!storageCards.length) storageCards.push(components.panel(_('Board identity layout'), '', components.el('p', {}, _('Board identity layout is unavailable.'))));
		return components.el('div', {'class':'cbi-map onu-dashboard'}, [
			components.title('ONU / HARDWARE', _('ONU Hardware'), _('Hardware identity and optical frontend information, read without changing flash contents.'),
				[components.el('a', {'class':'cbi-button', href:L.url('admin','onu','overview')}, _('Back to overview'))]),
			components.el('div', {'class':'onu-two-column'}, [
				components.panel(_('Device information'), board.model || 'H3C HM2004-DU', components.rows([
					[_('Model'), board.model], [_('Hostname'), board.hostname], [_('System'), board.system], [_('Kernel'), board.kernel],
					[_('Firmware'), (board.release || {}).description], [_('Uptime'), uptime(sys.uptime)],
					[_('Memory total'), size(memory.total)], [_('Memory available'), size(memory.available)]
				])),
				components.panel(_('Current PON identity'), _('Values read from the running driver'), components.rows([
					[_('Active serial number'), serial(result.activeSerial)], [_('Configured serial override'), serial(result.configuredSerial)],
					[_('Serial number configured'), components.bool(reg.serial_configured)],
					[_('Registration-ID configured'), components.bool(reg.registration_id_configured)],
					[_('Line mode'), data.mode(s).toUpperCase() || '—'], [_('OLT vendor'), protocol.olt_vendor_id],
					[_('OLT equipment'), protocol.olt_equipment_id], [_('OLT software'), protocol.olt_version]
				]))
			]),
			components.panel(_('Optical frontend'), _('Current readings from the driver'), components.el('div', {'class':'onu-metrics'}, [
				components.metric(_('Receive optical power'), front.error ? '—' : data.format(front.rx_power_dbm), 'dBm'),
				components.metric(_('Transmit optical power'), front.error ? '—' : data.format(front.tx_power_dbm), 'dBm'),
				components.metric(_('Temperature'), front.error ? '—' : data.format(front.temperature_celsius), '°C'),
				components.metric(_('Supply voltage'), front.error ? '—' : data.format(front.voltage_volts), 'V'),
				components.metric(_('Laser bias'), front.error ? '—' : data.format(front.tx_bias_ma), 'mA')
			])),
			storageCards,
			components.el('p', {'class':'onu-note'}, _('This page reports the declared logical layout. It does not import, export or rewrite a factory partition. Registration passwords are not displayed.')),
			components.link(_('Existing PON hardware manager'), _('Open the installed manager for any deliberate identity change.'), ['admin','network','pon','hardware'], 'chip')
		]);
	},
	handleSaveApply: null, handleSave: null, handleReset: null
});
