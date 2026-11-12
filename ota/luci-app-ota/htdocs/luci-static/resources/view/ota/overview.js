'use strict';
'require view';
'require rpc';
'require ui';
'require poll';

var callStatus = rpc.declare({ object: 'luci.ota', method: 'status', expect: {} });
var callCheck = rpc.declare({ object: 'luci.ota', method: 'check', expect: {} });
var callUpgrade = rpc.declare({ object: 'luci.ota', method: 'upgrade', params: [ 'keep' ], expect: {} });
var callCancel = rpc.declare({ object: 'luci.ota', method: 'cancel', expect: {} });
var callSave = rpc.declare({ object: 'luci.ota', method: 'save', params: [ 'proxy', 'api', 'token' ], expect: {} });

function fmtSize(n) {
	n = parseInt(n) || 0;
	if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
	if (n >= 1024) return (n / 1024).toFixed(0) + ' KB';
	return n + ' B';
}

var STATE_TEXT = {
	idle: '空闲',
	queued: '排队中',
	downloading: '下载中',
	verified: '校验通过，正在升级',
	error: '失败'
};

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
		var tdState = E('td', {}, [ STATE_TEXT[st.state] || st.state || '空闲' ]);
		var tdFree = E('td', {}, [ fmtSize((st.free_kb || 0) * 1024) ]);

		var barInner = E('div', { 'style': 'height:8px;width:0%;background:#3b82f6;transition:width .3s' });
		var bar = E('div', { 'style': 'height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;margin:8px 0' }, [ barInner ]);

		var msg = E('p', { 'class': 'cbi-value-description' }, []);
		var keep = E('input', { 'type': 'checkbox', 'checked': 'checked' });
		var btnCheck = E('button', { 'class': 'cbi-button cbi-button-action' }, [ _('检查更新') ]);
		var btnUp = E('button', { 'class': 'cbi-button cbi-button-negative' }, [ _('下载并升级') ]);
		var btnCancel = E('button', { 'class': 'cbi-button' }, [ _('取消下载') ]);

		var inpProxy = E('input', { 'type': 'text', 'value': st.proxy || '', 'placeholder': 'https://ghfast.top/', 'style': 'width:100%' });
		var inpApi = E('input', { 'type': 'text', 'value': st.api || 'https://api.github.com', 'style': 'width:100%' });
		var inpToken = E('input', { 'type': 'password', 'placeholder': st.token_set ? '已配置（留空不改）' : '可选：GitHub PAT，提高 API 限额', 'style': 'width:100%' });
		var btnSave = E('button', { 'class': 'cbi-button cbi-button-positive' }, [ _('保存设置') ]);

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
			// 已装 tag 与最新 tag 一致 → 视为最新，禁用"下载并升级"
			var same = (r.installed_tag === r.latest_tag);
			btnUp.disabled = !r.has_update || same;
			setMsg(r.has_update
				? _('发现新版本：%s').format(r.latest_tag)
				: _('已是最新版本（%s）').format(r.installed_tag || r.latest_tag), false);
		}

		function applyStatus(r) {
			if (!r)
				return;
			if (r.current) tdCurrent.textContent = r.current;
			tdInstalled.textContent = r.installed_tag || '—';
			tdState.textContent = STATE_TEXT[r.state] || r.state || '空闲';
			tdFree.textContent = fmtSize((r.free_kb || 0) * 1024);

			var pct = parseInt(r.progress) || 0;
			barInner.style.width = pct + '%';

			if (r.state === 'error')
				setMsg(r.error || _('升级失败'), true);
			else if (r.state === 'downloading')
				setMsg(_('正在下载升级包… %s%%').format(pct), false);
			else if (r.state === 'verified')
				setMsg(_('校验通过，正在写入并重启…'), false);
			else if (r.state === 'idle' && !msg.textContent)
				setMsg('', false);

			var busy = (r.state === 'queued' || r.state === 'downloading' || r.state === 'verified');
			btnCheck.disabled = busy;
			btnUp.disabled = busy;
			btnCancel.disabled = !(r.state === 'downloading' || r.state === 'queued');
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

		btnCancel.addEventListener('click', function() {
			return callCancel().then(function() {
				setMsg(_('已取消下载'), false);
			}).catch(function(e) {
				setMsg(e.message || _('取消失败'), true);
			});
		});

		btnSave.addEventListener('click', function() {
			return callSave(inpProxy.value.trim(), inpApi.value.trim(), inpToken.value).then(function(r) {
				if (!r || r.ok === false) {
					setMsg((r && r.error) || _('保存失败'), true);
					return;
				}
				inpToken.value = '';
				setMsg(_('设置已保存'), false);
			}).catch(function(e) {
				setMsg(e.message || _('保存失败'), true);
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
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('状态') ]), tdState ]),
					E('tr', { 'class': 'tr' }, [ E('th', { 'class': 'th' }, [ _('可用内存') ]), tdFree ])
				]),
				bar,
				E('p', { 'class': 'cbi-value-description' }, [
					_('升级包先下载到内存（约 40 MB），至少需要 110 MB 可用内存；内存不足请先关闭插件。')
				]),
				E('div', { 'class': 'cbi-value' }, [
					E('label', { 'class': 'cbi-value-title' }, [ _('保留配置') ]),
					E('div', { 'class': 'cbi-value-field' }, [ keep ])
				]),
				E('div', { 'style': 'margin:12px 0' }, [ btnCheck, ' ', btnUp, ' ', btnCancel ]),
				msg
			]),
			E('h3', {}, [ _('网络与加速（国内环境）') ]),
			E('div', { 'class': 'cbi-section' }, [
				E('div', { 'class': 'cbi-value' }, [
					E('label', { 'class': 'cbi-value-title' }, [ _('下载代理') ]),
					E('div', { 'class': 'cbi-value-field' }, [ inpProxy,
						E('div', { 'class': 'cbi-value-description' }, [
							_('拼接为 <代理>/<原始 GitHub 地址>。例如 https://ghfast.top/ 或 https://gh-proxy.com/；留空=直连。')
						])
					])
				]),
				E('div', { 'class': 'cbi-value' }, [
					E('label', { 'class': 'cbi-value-title' }, [ _('API 地址') ]),
					E('div', { 'class': 'cbi-value-field' }, [ inpApi,
						E('div', { 'class': 'cbi-value-description' }, [ _('默认 https://api.github.com；有镜像时填镜像根地址。') ])
					])
				]),
				E('div', { 'class': 'cbi-value' }, [
					E('label', { 'class': 'cbi-value-title' }, [ _('GitHub Token') ]),
					E('div', { 'class': 'cbi-value-field' }, [ inpToken,
						E('div', { 'class': 'cbi-value-description' }, [ _('可选。匿名 API 限 60 次/小时，Token 提高到 5000 次/小时。') ])
					])
				]),
				E('div', { 'style': 'margin:12px 0' }, [ btnSave ]),
				E('p', { 'class': 'cbi-value-description' }, [
					_('无论是否走代理，都会用 Release 提供的 sha256 校验镜像；校验不过不会安装。')
				])
			])
		]);
	}
});
