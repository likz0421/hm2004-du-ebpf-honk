'use strict';
'require view';
'require rpc';
'require ui';
'require poll';

var callStatus = rpc.declare({ object: 'luci.ota', method: 'status', expect: {} });
var callCheck = rpc.declare({ object: 'luci.ota', method: 'check', expect: {} });
var callUpgrade = rpc.declare({ object: 'luci.ota', method: 'upgrade', params: [ 'keep' ], expect: {} });

function fmtSize(n) {
	n = parseInt(n) || 0;
	if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
	if (n >= 1024) return (n / 1024).toFixed(0) + ' KB';
	return n + ' B';
}

return view.extend({
	load: function() {
		return callStatus();
	},

	render: function(st) {
		st = st || {};

		var tdCurrent = E('td', {}, [ st.current || '—' ]);
		var tdInstalled = E('td', {}, [ st.installed_tag || '—' ]);
		var tdLatest = E('td', {}, [ '—' ]);
		var tdSize = E('td', {}, [ '—' ]);
		var tdPublished = E('td', {}, [ '—' ]);
		var tdState = E('td', {}, [ st.state || 'idle' ]);
		var tdFree = E('td', {}, [ fmtSize((st.free_kb || 0) * 1024) ]);

		var msg = E('p', { 'class': 'cbi-value-description' }, []);
		var keep = E('input', { 'type': 'checkbox', 'checked': 'checked' });
		var btnCheck = E('button', { 'class': 'cbi-button cbi-button-action' }, [ _('检查更新') ]);
		var btnUp = E('button', { 'class': 'cbi-button cbi-button-negative' }, [ _('下载并升级') ]);

		function setMsg(text, isErr) {
			msg.textContent = text || '';
			msg.style.color = isErr ? '#c00' : '';
		}

		function applyCheck(r) {
			if (!r || r.ok === false) {
				setMsg((r && r.error) || _('检查失败'), true);
				return;
			}
			tdLatest.textContent = r.latest_tag || '—';
			tdSize.textContent = fmtSize(r.size);
			tdPublished.textContent = r.published || '—';
			setMsg(r.has_update
				? _('发现新版本：%s').format(r.latest_tag)
				: _('已是最新版本（%s）').format(r.latest_tag), false);
		}

		function applyStatus(r) {
			if (!r)
				return;
			if (r.current) tdCurrent.textContent = r.current;
			if (r.installed_tag) tdInstalled.textContent = r.installed_tag;
			tdState.textContent = r.state || 'idle';
			tdFree.textContent = fmtSize((r.free_kb || 0) * 1024);

			if (r.state === 'error')
				setMsg(r.error || _('升级失败'), true);
			else if (r.state === 'downloading')
				setMsg(_('正在下载升级包…'), false);
			else if (r.state === 'verified')
				setMsg(_('校验通过，正在写入并重启…'), false);

			var busy = (r.state === 'queued' || r.state === 'downloading' || r.state === 'verified');
			btnCheck.disabled = busy;
			btnUp.disabled = busy;
		}

		btnCheck.addEventListener('click', function() {
			btnCheck.disabled = true;
			setMsg(_('正在检查…'), false);
			return callCheck().then(applyCheck).catch(function(e) {
				setMsg(e.message || _('检查失败'), true);
			}).finally(function() {
				btnCheck.disabled = false;
			});
		});

		btnUp.addEventListener('click', function() {
			if (!window.confirm(_('确认下载并安装最新固件？设备会重启，过程中不要断电。')))
				return;
			return callUpgrade(keep.checked ? 'true' : 'false').then(function(r) {
				if (!r || r.ok === false) {
					setMsg((r && r.error) || _('启动失败'), true);
					return;
				}
				setMsg(_('已开始下载，请保持供电…'), false);
			}).catch(function(e) {
				setMsg(e.message || _('启动失败'), true);
			});
		});

		poll.add(function() {
			return callStatus().then(applyStatus).catch(function() {});
		}, 3);

		return E([], [
			E('h2', {}, [ _('在线升级') ]),
			E('div', { 'class': 'cbi-section' }, [
				E('table', { 'class': 'table' }, [
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('当前版本') ]), tdCurrent ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('已安装升级标签') ]), tdInstalled ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('最新版本') ]), tdLatest ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('升级包大小') ]), tdSize ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('发布时间') ]), tdPublished ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('状态') ]), tdState ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('可用内存') ]), tdFree ])
				]),
				E('p', { 'class': 'cbi-value-description' }, [
					_('升级包先下载到内存（约 40 MB），至少需要 110 MB 可用内存；内存不足请先关闭插件。')
				]),
				E('div', { 'class': 'cbi-value' }, [
					E('label', { 'class': 'cbi-value-title' }, [ _('保留配置') ]),
					E('div', { 'class': 'cbi-value-field' }, [ keep ])
				]),
				E('div', { 'style': 'margin:12px 0' }, [ btnCheck, ' ', btnUp ]),
				msg
			])
		]);
	}
});
