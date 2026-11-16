// SPDX-License-Identifier: Apache-2.0
'use strict';
'require baseclass';
'require fs';
'require rpc';
'require uci';

var board = rpc.declare({ object: 'system', method: 'board', expect: { '': {} } });
var info = rpc.declare({ object: 'system', method: 'info', expect: { '': {} } });
var device = rpc.declare({ object: 'network.device', method: 'status', params: ['name'], expect: { '': {} } });
var ports = ['pon0', 'lan1', 'lan2', 'lan3', 'lan4'];

function number(value) {
	if ((typeof value !== 'number' && typeof value !== 'string') ||
	    (typeof value === 'string' && value.trim() === '')) return null;
	var n = Number(value);
	return Number.isFinite(n) ? n : null;
}
function object(value) {
	return value != null && typeof value === 'object' && !Array.isArray(value);
}
function boolean(value) {
	return value === true || value === 1 || value === '1' ? true :
		value === false || value === 0 || value === '0' ? false : null;
}
function safe(job, fallback) {
	return Promise.resolve(job).catch(function() { return fallback; });
}
function jsonCommand(path, args) {
	return fs.exec_direct(path, args).then(function(text) {
		var obj = JSON.parse(text);
		if (!obj || typeof obj !== 'object' || Array.isArray(obj)) throw new Error('Invalid status response');
		return { value: obj, error: null };
	}).catch(function() { return { value: {}, error: _('Status temporarily unavailable') }; });
}
function counterText(text) {
	var out = {};
	String(text || '').split(/\r?\n/).forEach(function(line) {
		var match = /^(tcp_total|tcp_npu|udp_total|udp_npu)=([0-9]+)$/.exec(line);
		if (match) out[match[1]] = number(match[2]);
	});
	return ['tcp_total', 'tcp_npu', 'udp_total', 'udp_npu'].every(function(k) { return out[k] != null; }) ? out : null;
}
function configuredLine() {
	return safe(uci.load('pon'), null).then(function() {
		var s = (uci.sections('pon', 'xpon') || []).filter(function(x) { return x.device === 'pon0'; })[0];
		return s ? { section: s['.name'], device: s.device, mode: s.mode || '' } : { section: 'line0', device: 'pon0', mode: '' };
	});
}
function snapshot() {
	return Promise.all([
		jsonCommand('/usr/sbin/ponctl', ['--device', 'pon0', 'status', '--json']),
		jsonCommand('/usr/bin/pondctl', ['status', '--line', 'line0']),
		safe(board(), {}), safe(info(), {}),
		Promise.all(ports.map(function(name) { return safe(device(name), {}).then(function(value) { return { name: name, value: value }; }); })),
		safe(fs.exec_direct('/usr/sbin/ponstat-conn', []).then(counterText), null),
		configuredLine()
	]).then(function(values) {
		var raw = values[0].value, protocol = values[1].value;
		if (raw.schema_version !== 1 || !object(raw.line)) {
			values[0].error = values[0].error || _('Unsupported PON status format'); raw = {};
		}
		['frontend', 'registration', 'datapath', 'counters'].forEach(function(key) {
			if (!object(raw[key])) raw[key] = {};
		});
		if (protocol.protocol_version !== 1) {
			values[1].error = values[1].error || _('Unsupported protocol status format'); protocol = {};
		}
		return { time: Date.now(), pon: raw, ponError: values[0].error, protocol: protocol,
			protocolError: values[1].error, board: values[2], system: values[3], ports: values[4],
			connections: values[5], configured: values[6] };
	});
}
function hardware() {
	return Promise.all([snapshot(), safe(fs.read('/etc/board.json').then(JSON.parse), {}),
		safe(fs.read('/sys/class/net/pon0/xpon/serial_number'), null),
		safe(fs.read('/sys/class/net/pon0/xpon/active_serial_number'), null)
	]).then(function(v) { return { snapshot: v[0], layout: v[1], configuredSerial: v[2], activeSerial: v[3] }; });
}
function mode(s) {
	var line = s.pon.line || {}, active = line.active_mode;
	return active && active !== 'none' ? active : (line.configured_mode || s.configured.mode || '');
}
function health(s) {
	var line = s.pon.line || {}, path = s.pon.datapath || {}, reg = s.pon.registration || {};
	if (s.ponError) return { level: 'unknown', label: _('Status unavailable'), detail: s.ponError };
	if (boolean(line.optical_signal) === false) return { level: 'bad', label: _('No optical signal'), detail: _('Check the optical connection and upstream equipment.') };
	if (line.lifecycle === 'stopped' || line.active_mode === 'none') return { level: 'muted', label: _('PON line stopped'), detail: _('The PON line is not active.') };
	if (line.lifecycle === 'error') return { level: 'bad', label: _('PON line error'), detail: _('Inspect the detailed state and diagnostic information.') };
	if (boolean(path.service_ready) === true) return { level: 'good', label: _('Service ready'), detail: _('The PON backend reports a usable data path. Internet access is a separate check.') };
	if (reg.onu_state === 'O5' || reg.mpcp_state === 'registered') return { level: 'pending', label: _('Registered, service pending'), detail: _('The optical line is registered; service provisioning is not reported ready yet.') };
	if (!line.lifecycle && !reg.onu_state && !reg.mpcp_state && boolean(path.service_ready) == null)
		return { level: 'unknown', label: _('Status unavailable'), detail: _('Registration state has not been reported.') };
	return { level: 'pending', label: _('Waiting for registration'), detail: _('Inspect optical signal, line mode and registration status.') };
}
function format(value, decimals) {
	var n = number(value); return n == null ? '—' : n.toFixed(decimals == null ? 2 : decimals);
}
function rate(before, after, elapsed) {
	var a = number(before), b = number(after);
	return a == null || b == null || b < a || elapsed <= 0 || elapsed > 30 ? null : (b - a) * 8 / elapsed / 1000000;
}
return baseclass.extend({ snapshot: snapshot, hardware: hardware, number: number, boolean: boolean,
	counterText: counterText, mode: mode, health: health, format: format, rate: rate });
