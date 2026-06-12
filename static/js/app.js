/* =====================================================
   多模态随心生成 · 前端逻辑
   ===================================================== */

// ============== 全局状态 ==============
const state = {
  currentType: 'image',          // 当前 Tab: image | video | text
  currentFilter: 'all',          // 当前过滤: all | running | success | failed | pending
  tasks: [],                     // 当前 tab 任务（渲染表格用）
  allTasks: [],                  // 全集任务（计算 tab 角标用）
  models: { image: [], video: [], text: [] },
  pollTimer: null,
  currentDetailTask: null,       // 当前详情任务
};

// ============== API 封装 ==============
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json();
  if (!res.ok || data.code !== 0) {
    throw new Error(data.msg || `HTTP ${res.status}`);
  }
  return data.data;
}

// ============== 工具 ==============
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function formatTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function formatDuration(ms) {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms/1000).toFixed(1)}s`;
  return `${Math.floor(ms/60000)}m${Math.floor((ms%60000)/1000)}s`;
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function statusBadge(status) {
  const map = {
    pending: { class: 'badge-pending', label: 'pending', dot: '' },
    running: { class: 'badge-running', label: 'running', dot: '<span class="spinner"></span>' },
    success: { class: 'badge-success', label: 'success', dot: '<span class="badge-dot"></span>' },
    failed: { class: 'badge-failed', label: 'failed', dot: '<span class="badge-dot"></span>' },
  };
  const s = map[status] || map.pending;
  return `<span class="badge ${s.class}">${s.dot}${s.label}</span>`;
}

function showToast(msg, type = 'info', duration = 3000) {
  const container = $('#toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease-in';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

async function copyToClipboard(text, msg) {
  const successMsg = msg || '已复制到剪贴板';
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMsg, 'success');
    return true;
  } catch (e) {
    // Fallback
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast(successMsg, 'success');
      return true;
    } catch (e2) {
      showToast('复制失败', 'error');
      return false;
    }
  }
}

// ============== 任务列表渲染 ==============
function renderTaskTable() {
  const filtered = state.currentFilter === 'all'
    ? state.tasks
    : state.tasks.filter(t => t.status === state.currentFilter);

  if (filtered.length === 0) {
    $('#taskTable').innerHTML = `
      <div class="task-table-empty">
        <div class="task-table-empty-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
        </div>
        <div class="task-table-empty-title">${state.currentFilter === 'all' ? '还没有任务' : '该过滤条件下没有任务'}</div>
        <div class="task-table-empty-desc">点击"新建任务"开始第一次生成</div>
      </div>
    `;
    return;
  }

  const rows = filtered.map(t => {
    const hasResult = t.status === 'success' && t.result_path;
    return `
      <tr data-task-id="${escapeHtml(t.id)}">
        <td class="col-id">${escapeHtml(t.id)}</td>
        <td class="col-name" title="${escapeHtml(t.prompt)}">${escapeHtml(t.name)}</td>
        <td class="col-model">${escapeHtml(t.model)}</td>
        <td>${statusBadge(t.status)}</td>
        <td class="col-time">${formatTime(t.created_at)}</td>
        <td class="col-time">${formatTime(t.finished_at)}</td>
        <td class="col-actions">
          <button class="btn btn-ghost btn-sm" data-action="detail" title="详情">详情</button>
          ${hasResult ? '<button class="btn btn-ghost btn-sm" data-action="preview" title="查看/复制结果">结果</button>' : ''}
          ${t.type === 'video' && (t.status === 'pending' || (t.status === 'running' && t.remote_task_id)) ? '<button class="btn btn-ghost btn-sm" data-action="query" title="主动查询视频生成进展">查询</button>' : ''}
          <button class="btn btn-ghost btn-sm" data-action="copy" title="复制参数新建">复制</button>
          ${t.status === 'failed' ? '<button class="btn btn-ghost btn-sm" data-action="retry" title="重试">重试</button>' : ''}
          <button class="btn btn-ghost btn-sm" data-action="delete" title="删除">删除</button>
        </td>
      </tr>
    `;
  }).join('');

  $('#taskTable').innerHTML = `
    <table>
      <thead>
        <tr>
          <th>任务 ID</th>
          <th>任务名</th>
          <th>模型</th>
          <th>状态</th>
          <th>创建时间</th>
          <th>完成时间</th>
          <th style="text-align: right;">操作</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function updateStats() {
  const stats = { running: 0, success: 0, failed: 0 };
  state.tasks.forEach(t => {
    if (stats[t.status] !== undefined) stats[t.status]++;
  });
  $('#statRunning').textContent = stats.running;
  $('#statSuccess').textContent = stats.success;
  $('#statFailed').textContent = stats.failed;
}

function updateCounts() {
  // 用全集数据计算三个 tab 角标（不依赖当前选中 tab）
  const counts = { image: 0, video: 0, text: 0 };
  const source = state.allTasks || state.tasks || [];
  source.forEach(t => { counts[t.type] = (counts[t.type] || 0) + 1; });
  $('#countImage').textContent = counts.image || 0;
  $('#countVideo').textContent = counts.video || 0;
  $('#countText').textContent = counts.text || 0;
}

// ============== 数据加载 ==============
async function loadModels() {
  const [imgModels, vidModels, textModels] = await Promise.all([
    api('/api/models?type=image'),
    api('/api/models?type=video'),
    api('/api/models?type=text'),
  ]);
  state.models.image = imgModels.models || [];
  state.models.video = vidModels.models || [];
  state.models.text = textModels.models || [];
  updateModelSelect();
}

function updateModelSelect() {
  const sel = $('#modelSelect');
  const models = state.models[state.currentType] || [];
  sel.innerHTML = models.map(m =>
    `<option value="${m.id}"${m.default ? ' selected' : ''}>${escapeHtml(m.name)}</option>`
  ).join('');
}

async function loadTasks() {
  try {
    // 并行拉：当前 tab 任务 + 全集（用于 tab 角标计数）
    const [data, allData] = await Promise.all([
      api(`/api/tasks?type=${state.currentType}&limit=200`),
      api(`/api/tasks?limit=500`),
    ]);
    state.tasks = data.tasks || [];
    state.allTasks = allData.tasks || [];
    renderTaskTable();
    updateStats();
    updateCounts();
  } catch (e) {
    console.error('加载任务失败:', e);
  }
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(loadTasks, 3000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

// ============== Tab 切换 ==============
function setupTabs() {
  $$('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.currentType = tab.dataset.type;
      state.currentFilter = 'all';
      $$('.filter-pill').forEach(p => {
        p.classList.toggle('active', p.dataset.filter === 'all');
      });
      // 切换参数区域
      $('#imageParams').style.display = state.currentType === 'image' ? 'block' : 'none';
      $('#videoParams').style.display = state.currentType === 'video' ? 'block' : 'none';
      $('#textParams').style.display = state.currentType === 'text' ? 'block' : 'none';
      $('#formGroupPrompt').style.display = state.currentType === 'text' ? 'none' : 'block';
      updateModelSelect();
      loadTasks();
    });
  });
}

// ============== 过滤 ==============
function setupFilters() {
  $$('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      $$('.filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      state.currentFilter = pill.dataset.filter;
      renderTaskTable();
    });
  });
}

// ============== 抽屉 ==============
function openDrawer(prefill = null) {
  // 防 DOM Event 被当成 prefill 误入（点击事件触发时 MouseEvent 会被传成第一个参数）
  if (prefill instanceof Event || (prefill && prefill.target instanceof Element)) {
    prefill = null;
  }
  // 先重置表单
  $('#newTaskForm').reset();
  // 默认任务类型 = 当前 tab（状态 type），prefill 后面会覆盖
  const defaultType = state.currentType || 'image';
  $$('#typeGroup .radio-card').forEach(c => {
    c.classList.toggle('selected', c.dataset.value === defaultType);
  });
  const typeRadio = $('#newTaskForm').querySelector(`[name="type"][value="${defaultType}"]`);
  if (typeRadio) typeRadio.checked = true;
  $('#imageParams').style.display = defaultType === 'image' ? 'block' : 'none';
  $('#videoParams').style.display = defaultType === 'video' ? 'block' : 'none';
  $('#textParams').style.display = defaultType === 'text' ? 'block' : 'none';
  $('#formGroupPrompt').style.display = defaultType === 'text' ? 'none' : 'block';
  // 同步 required
  const promptTa = $('#newTaskForm').querySelector('[name="prompt"]');
  if (promptTa) promptTa.required = (defaultType !== 'text');
  const inputTextTa = $('#newTaskForm').querySelector('[name="input_text"]');
  if (inputTextTa) inputTextTa.required = (defaultType === 'text');
  // 重置时同步模型下拉（避免 select 还是上一个 tab 的模型）
  updateModelSelect();
  
  // 预填（复制场景）
  if (prefill) {
    if (prefill.name) {
      const nameInput = $('#newTaskForm').querySelector('[name="name"]');
      if (nameInput) nameInput.value = prefill.name;
    }
    if (prefill.type) {
      $$('#typeGroup .radio-card').forEach(c => {
        c.classList.toggle('selected', c.dataset.value === prefill.type);
      });
      $('#imageParams').style.display = prefill.type === 'image' ? 'block' : 'none';
      $('#videoParams').style.display = prefill.type === 'video' ? 'block' : 'none';
      $('#textParams').style.display = prefill.type === 'text' ? 'block' : 'none';
      $('#formGroupPrompt').style.display = prefill.type === 'text' ? 'none' : 'block';
    }
    if (prefill.model) {
      const modelSelect = $('#newTaskForm').querySelector('[name="model"]');
      if (modelSelect) {
        // 改 model 需要刷新选项——但现在模型仅 agnes，直接赋值
        modelSelect.value = prefill.model;
      }
    }
    if (prefill.prompt) {
      const p = $('#newTaskForm').querySelector('[name="prompt"]');
      if (p) p.value = prefill.prompt;
    }
    if (prefill.input_text) {
      const it = $('#newTaskForm').querySelector('[name="input_text"]');
      if (it) it.value = prefill.input_text;
    }
    if (prefill.input_image) {
      const urlInput = $('#newTaskForm').querySelector('[name="input_image"]');
      if (urlInput) {
        urlInput.value = prefill.input_image;
        // 同时加载预览（文本任务用）
        if (prefill.type === 'text') {
          const thumb = $('#refImageThumb');
          const preview = $('#refImagePreview');
          const dropZone = $('#refImageDrop');
          if (thumb && preview && dropZone) {
            // 从 "tasks/texts/_refs/ref_xxx.png" 提取文件名用于图床 URL
            const parts = prefill.input_image.replace(/\\/g, '/').split('/');
            const fname = parts[parts.length - 1];
            const previewUrl = prefill.input_image.startsWith('http')
              ? prefill.input_image
              : (fname ? `/refs/${fname}` : prefill.input_image);
            thumb.alt = prefill.input_image;
            thumb.dataset.url = previewUrl;
            thumb.src = previewUrl;
            preview.style.display = '';
            dropZone.style.display = 'none';
          }
        }
      }
    }
    if (prefill.params) {
      // 逐个填 params
      for (const [k, v] of Object.entries(prefill.params)) {
        const el = $('#newTaskForm').querySelector(`[name="${k}"]`);
        if (!el) continue;
        if (el.type === 'checkbox') {
          el.checked = !!v;
        } else {
          el.value = v;
        }
      }
    }
  }
  
  // 标题
  $('#drawerTitle').textContent = prefill ? `复制任务 - ${prefill.name || '原任务'}` : '新建任务';
  
  $('#drawerOverlay').classList.add('open');
  $('#drawer').classList.add('open');
  document.body.style.overflow = 'hidden';
  
  // 提示一下
  if (prefill) {
    showToast('已复制参数，可调整后提交', 'success');
  }
}

async function copyTask(taskId) {
  try {
    const task = await api(`/api/tasks/${taskId}`);
    if (!task) {
      showToast('未找到任务', 'error');
      return;
    }
    // 如果任务类型与当前 tab 不同，先切 tab（这样 model 列表才能填上）
    if (task.type !== state.currentType) {
      state.currentType = task.type;
      // 同步 tab UI
      $$('.tab-button').forEach(b => {
        b.classList.toggle('active', b.dataset.type === task.type);
      });
      updateModelSelect();
      await loadTasks();
    }
    openDrawer({
      name: `${task.name} (副本)`,  // 默认在名字后加" (副本)"，主人可改
      type: task.type,
      model: task.model,
      prompt: task.prompt,
      input_text: task.input_text || task.prompt || '',
      input_image: task.input_image || '',
      params: task.params || {},
    });
  } catch (e) {
    showToast(`复制失败: ${e.message}`, 'error');
  }
}

function closeDrawer() {
  $('#drawerOverlay').classList.remove('open');
  $('#drawer').classList.remove('open');
  document.body.style.overflow = '';
  // 表单重置在 openDrawer() 里统一处理，这里只关闭层
}

function setupDrawer() {
  $('#btnNewTask').addEventListener('click', () => openDrawer());
  $('#drawerClose').addEventListener('click', closeDrawer);
  $('#drawerCancel').addEventListener('click', closeDrawer);
  $('#drawerOverlay').addEventListener('click', closeDrawer);

  // 类型选择
  $$('#typeGroup .radio-card').forEach(card => {
    card.addEventListener('click', () => {
      $$('#typeGroup .radio-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      const val = card.dataset.value;
      card.querySelector('input').checked = true;
      // 同步全局状态 + 模型下拉
      state.currentType = val;
      updateModelSelect();
      // 切换参数区域
      $('#imageParams').style.display = val === 'image' ? 'block' : 'none';
      $('#videoParams').style.display = val === 'video' ? 'block' : 'none';
      $('#textParams').style.display = val === 'text' ? 'block' : 'none';
      $('#formGroupPrompt').style.display = val === 'text' ? 'none' : 'block';
      // 切换时同步更新 prompt 的 required
      const promptTa = $('#newTaskForm').querySelector('[name="prompt"]');
      if (promptTa) promptTa.required = (val !== 'text');
      // 同步 input_text 的 required
      const inputTextTa = $('#newTaskForm').querySelector('[name="input_text"]');
      if (inputTextTa) inputTextTa.required = (val === 'text');
    });
  });

  // 提交：点击按钮 + 拦截 form submit 事件（防止页面刷新）
  $('#drawerSubmit').addEventListener('click', submitNewTask);
  $('#newTaskForm').addEventListener('submit', (e) => {
    e.preventDefault();
    submitNewTask();
  });

  // 参考图上传（仅 text 任务用）
  initRefImageUpload();
}

// ============== 参考图上传 ==============
function initRefImageUpload() {
  const dropZone = $('#refImageDrop');
  const fileInput = $('#refImageFile');
  const preview = $('#refImagePreview');
  const thumb = $('#refImageThumb');
  const clearBtn = $('#refImageClear');
  const urlInput = $('#refImageUrl');

  if (!dropZone || !fileInput) return;

  // 点击 dropzone → label 元素原生会触发 file input.click()，不要在这里拦截
  //（如果需要可以只加业务逻辑）

  // 拖拽高亮
  ['dragenter', 'dragover'].forEach(evt => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragging');
    });
  });
  ['dragleave', 'drop'].forEach(evt => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragging');
    });
  });

  // 拖拽放下 → 上传
  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files && files[0]) uploadRefImage(files[0]);
  });

  // 文件选择 → 上传
  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) uploadRefImage(e.target.files[0]);
  });

  // 清除
  clearBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    fileInput.value = '';
    thumb.src = '';
    preview.style.display = 'none';
    dropZone.style.display = '';
    if (urlInput) urlInput.value = '';
  });

  // URL 输框与 file 互斥：手动输 URL 时清掉预览
  if (urlInput) {
    urlInput.addEventListener('input', () => {
      if (urlInput.value.trim()) {
        preview.style.display = 'none';
        dropZone.style.display = '';
        fileInput.value = '';
      }
    });
  }

  async function uploadRefImage(file) {
    // 客户端预检
    if (!file.type.startsWith('image/')) {
      showToast('只支持图片文件', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast('图片不能超过 10MB', 'error');
      return;
    }

    // 缩略图预览
    const reader = new FileReader();
    reader.onload = (e) => { thumb.src = e.target.result; };
    reader.readAsDataURL(file);

    // 异步上传
    const fd = new FormData();
    fd.append('file', file);
    const oldText = clearBtn.textContent;
    clearBtn.textContent = '上传中...';
    clearBtn.disabled = true;

    try {
      const r = await fetch('/api/upload/image', { method: 'POST', body: fd });
      const data = await r.json();
      if (!r.ok || data.code !== 0) {
        throw new Error(data.msg || `HTTP ${r.status}`);
      }
      const url = data.data.url;
      const path = data.data.path;
      // 写入 URL 输入框（用 server 路径，scheduler 能读到）+ 显示预览区
      if (urlInput) urlInput.value = path || url;
      preview.style.display = '';
      dropZone.style.display = 'none';
      showToast('图片上传成功', 'success');
    } catch (err) {
      showToast(`上传失败: ${err.message}`, 'error');
      // 回滚预览
      thumb.src = '';
      preview.style.display = 'none';
      dropZone.style.display = '';
    } finally {
      clearBtn.textContent = oldText;
      clearBtn.disabled = false;
    }
  }
}

// ============== 提交新任务 ==============
async function submitNewTask() {
  const form = $('#newTaskForm');
  const formData = new FormData(form);
  const data = {
    name: formData.get('name'),
    type: formData.get('type'),
    model: formData.get('model'),
    prompt: formData.get('prompt'),
    params: {},
  };

  if (!data.name || (!data.prompt && data.type !== 'text')) {
    showToast(data.type === 'text' ? '请填写任务名' : '请填写任务名和提示词', 'error');
    return;
  }

  // 收集参数
  if (data.type === 'image') {
    data.params.size = formData.get('size');
    data.params.count = parseInt(formData.get('count')) || 1;
    const customName = (formData.get('custom_name') || '').trim();
    if (customName) data.params.custom_name = customName;
    if (formData.get('send_feishu')) data.params.send_feishu = true;
  } else if (data.type === 'video') {
    data.params.width = parseInt(formData.get('width')) || 1152;
    data.params.height = parseInt(formData.get('height')) || 768;
    data.params.num_frames = parseInt(formData.get('num_frames')) || 121;
    data.params.frame_rate = parseInt(formData.get('frame_rate')) || 24;
    const neg = formData.get('negative_prompt');
    if (neg) data.params.negative_prompt = neg;
  } else if (data.type === 'text') {
    // 提示词任务：input_text 才是主输入（同步到 prompt 字段以兼容后端）
    const inputText = (formData.get('input_text') || '').trim();
    if (!inputText) {
      showToast('请填写需求描述', 'error');
      return;
    }
    data.input_text = inputText;
    data.prompt = inputText;
    const inputImage = (formData.get('input_image') || '').trim();
    if (inputImage) data.input_image = inputImage;
    data.params.temperature = parseFloat(formData.get('temperature')) || 0.7;
    data.params.max_tokens = parseInt(formData.get('max_tokens')) || 1024;
    if (formData.get('thinking')) data.params.thinking = true;
  }

  const submitBtn = $('#drawerSubmit');
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner"></span> 提交中...';

  try {
    const task = await api('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    showToast(`任务已提交: ${task.name}`, 'success');
    closeDrawer();
    // 同步 tab UI 为提交任务的类型（处理在抽屉 typeGroup 切换后未同步的场景）
    if (state.currentType !== task.type) {
      state.currentType = task.type;
    }
    $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.type === task.type));
    updateCounts();
    loadTasks();
  } catch (e) {
    showToast(`提交失败: ${e.message}`, 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> 提交任务`;
  }
}

// ============== 任务操作 ==============
function setupTaskActions() {
  $('#taskTable').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const tr = btn.closest('tr');
    const taskId = tr.dataset.taskId;
    const action = btn.dataset.action;

    if (action === 'detail') {
      showDetail(taskId);
    } else if (action === 'copy') {
      copyTask(taskId);
    } else if (action === 'preview') {
      showPreview(taskId);
    } else if (action === 'query') {
      await queryTask(taskId, btn);
    } else if (action === 'retry') {
      await retryTask(taskId);
    } else if (action === 'delete') {
      await deleteTask(taskId);
    }
  });
}

// queryTask: 主动查询视频生成进展（1分钟限频）
const queryState = {};  // { taskId: { lastAt, pending } }
async function queryTask(taskId, btn) {
  const now = Date.now();
  const s = queryState[taskId] || { lastAt: 0, pending: false };

  // 限频：同一任务 1 分钟内只能查一次
  if (s.pending) {
    showToast('查询中，请稍候', 'info');
    return;
  }
  if (now - s.lastAt < 60000) {
    const wait = Math.ceil((60000 - (now - s.lastAt)) / 1000);
    showToast(`${wait}s 后才能再查询`, 'info');
    return;
  }

  // 锁定状态
  queryState[taskId] = { lastAt: now, pending: true };
  const oldText = btn.textContent;
  btn.textContent = '查询中...';
  btn.disabled = true;

  try {
    const d = await api(`/api/tasks/${taskId}/query`, { method: 'POST' });
    // api() 已解构为 data.data，d 包含 {status, progress, msg, ...}
    if (d.status === 'completed') {
      showToast(`视频已生成！进度 100%`, 'success');
    } else if (d.status === 'failed') {
      showToast('Agnes 视频生成失败', 'error');
    } else {
      // queued / in_progress / 其他
      showToast(d.msg || '暂无进展', 'info');
    }
    // 刷新列表
    await loadTasks();
  } catch (e) {
    showToast('查询失败: ' + e.message, 'error');
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
    // pending 状态保持 3 秒（给网络请求 + 反馈显示用）
    setTimeout(() => {
      if (queryState[taskId]) queryState[taskId].pending = false;
    }, 3000);
  }
}

async function showDetail(taskId) {
  try {
    const task = await api(`/api/tasks/${taskId}`);
    state.currentDetailTask = task;
    
    const paramsStr = JSON.stringify(task.params || {}, null, 2);
    const errorHtml = task.error_msg
      ? `<div class="detail-label">错误信息</div><div class="detail-value" style="color: var(--danger);">${escapeHtml(task.error_msg)}</div>`
      : '';

    $('#detailBody').innerHTML = `
      <div class="detail-grid">
        <div class="detail-label">任务 ID</div>
        <div class="detail-value">${escapeHtml(task.id)}</div>
        
        <div class="detail-label">任务名</div>
        <div class="detail-value" style="font-family: var(--font-sans);">${escapeHtml(task.name)}</div>
        
        <div class="detail-label">类型</div>
        <div class="detail-value">${escapeHtml(task.type)}</div>
        
        <div class="detail-label">模型</div>
        <div class="detail-value">${escapeHtml(task.model)}</div>
        
        <div class="detail-label">状态</div>
        <div class="detail-value">${statusBadge(task.status)}</div>
        
        <div class="detail-label">参数</div>
        <div class="detail-value"><pre style="margin: 0; white-space: pre-wrap;">${escapeHtml(paramsStr)}</pre></div>
        
        <div class="detail-label">创建时间</div>
        <div class="detail-value">${formatTime(task.created_at)}</div>
        
        ${task.started_at ? `<div class="detail-label">开始时间</div><div class="detail-value">${formatTime(task.started_at)}</div>` : ''}
        
        ${task.finished_at ? `<div class="detail-label">完成时间</div><div class="detail-value">${formatTime(task.finished_at)} (${formatDuration(task.duration_ms)})</div>` : ''}
        
        ${task.result_path ? `<div class="detail-label">结果文件</div><div class="detail-value">${escapeHtml(task.result_path)}</div>` : ''}
        
        ${errorHtml}
      </div>
      
      <div style="margin-top: var(--space-5);">
        <div class="detail-label" style="margin-bottom: var(--space-2);">提示词</div>
        <div class="detail-prompt">${escapeHtml(task.prompt)}</div>
      </div>
    `;
    $('#detailModal').classList.add('open');
  } catch (e) {
    showToast(`加载详情失败: ${e.message}`, 'error');
  }
}

function closeDetail() {
  $('#detailModal').classList.remove('open');
  state.currentDetailTask = null;
}

async function showPreview(taskId) {
  try {
    const task = await api(`/api/tasks/${taskId}`);
    if (task.type === 'text') {
      // 文本/提示词任务：渲染 result_text 全文 + 复制 + 下载
      const content = task.result_text || '';
      $('#previewTitle').textContent = `提示词结果 - ${task.name}`;
      $('#previewBody').innerHTML = `
        <div class="text-result">
          <div class="text-result-toolbar">
            <span class="text-result-meta">${content.length} 字符 · ${task.model || ''}</span>
            <div class="text-result-actions">
              <button class="btn btn-secondary" id="textResultCopy">复制全文</button>
              <a class="btn btn-secondary" href="/api/tasks/${taskId}/result" target="_blank" download>下载 .txt</a>
            </div>
          </div>
          <pre class="text-result-content">${escapeHtml(content)}</pre>
        </div>
      `;
      const copyBtn = $('#textResultCopy');
      if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
          // 主人要求：只复制生成的提示词，不要需求描述
          const ok = await copyToClipboard(content, '提示词已复制');
          if (ok !== false) {
            const orig = copyBtn.textContent;
            copyBtn.textContent = '✓ 已复制';
            copyBtn.classList.add('btn-success-flash');
            setTimeout(() => {
              copyBtn.textContent = orig;
              copyBtn.classList.remove('btn-success-flash');
            }, 2000);
          }
        });
      }
      $('#previewModal').classList.add('open');
      return;
    }
    if (!task.result_path) {
      showToast('该任务没有结果', 'error');
      return;
    }
    const files = (task.result_paths && task.result_paths.length)
      ? task.result_paths
      : [task.result_path];
    $('#previewTitle').textContent = `结果预览 - ${task.name} (${files.length} 张)`;
    if (task.type === 'image') {
      if (files.length === 1) {
        $('#previewBody').innerHTML = `<img src="/api/tasks/${taskId}/result?index=0" alt="${escapeHtml(task.name)}">`;
      } else {
        // 多图网格
        const imgs = files.map((_, i) => `<div class="preview-grid-item"><img src="/api/tasks/${taskId}/result?index=${i}" alt="图 ${i+1}"><div class="preview-grid-label">第 ${i+1} 张</div></div>`).join('');
        $('#previewBody').innerHTML = `<div class="preview-grid">${imgs}</div>`;
      }
    } else {
      $('#previewBody').innerHTML = `<video src="/api/tasks/${taskId}/result" controls autoplay></video>`;
    }
    $('#previewModal').classList.add('open');
  } catch (e) {
    showToast(`加载预览失败: ${e.message}`, 'error');
  }
}

function closePreview() {
  $('#previewModal').classList.remove('open');
  $('#previewBody').innerHTML = '';
}

// ============== 自建 confirm 弹窗（千面风格，Promise 接口） ==============
function showConfirm({ title = '确认操作', message = '', okText = '确定', cancelText = '取消', danger = false } = {}) {
  return new Promise((resolve) => {
    // 移除旧弹窗
    const old = $('#customConfirm');
    if (old) old.remove();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay open';
    overlay.id = 'customConfirm';
    overlay.innerHTML = `
      <div class="modal" style="width: 420px;">
        <div class="modal-header">
          <div class="modal-title">${title}</div>
        </div>
        <div class="modal-body" style="padding: 20px 24px; color: var(--color-text-secondary); line-height: 1.6;">${message}</div>
        <div class="modal-footer">
          <button class="btn btn-ghost" data-confirm="cancel">${cancelText}</button>
          <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-confirm="ok">${okText}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const cleanup = (val) => { overlay.remove(); resolve(val); };
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) cleanup(false);
      const a = e.target.dataset.confirm;
      if (a === 'ok') cleanup(true);
      if (a === 'cancel') cleanup(false);
    });
  });
}

async function retryTask(taskId) {
  if (!await showConfirm({ title: '重试任务', message: '确定要重试这个任务吗？', okText: '重试' })) return;
  try {
    await api(`/api/tasks/${taskId}/retry`, { method: 'POST' });
    showToast('任务已重新加入队列', 'success');
    loadTasks();
  } catch (e) {
    showToast(`重试失败: ${e.message}`, 'error');
  }
}

async function deleteTask(taskId) {
  if (!await showConfirm({ title: '删除任务', message: '确定要删除这个任务吗？结果文件也会被删除。', okText: '删除', danger: true })) return;
  try {
    await api(`/api/tasks/${taskId}`, { method: 'DELETE' });
    showToast('任务已删除', 'success');
    loadTasks();
  } catch (e) {
    showToast(`删除失败: ${e.message}`, 'error');
  }
}

// ============== 模态框关闭 ==============
function setupModals() {
  $('#detailClose').addEventListener('click', closeDetail);
  $('#detailCloseBtn').addEventListener('click', closeDetail);
  $('#detailCopyPrompt').addEventListener('click', () => {
    if (state.currentDetailTask) {
      copyToClipboard(state.currentDetailTask.prompt);
    }
  });
  $('#detailModal').addEventListener('click', (e) => {
    if (e.target.id === 'detailModal') closeDetail();
  });

  $('#previewClose').addEventListener('click', closePreview);
  $('#previewModal').addEventListener('click', (e) => {
    if (e.target.id === 'previewModal') closePreview();
  });

  // ESC 关闭
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDrawer();
      closeDetail();
      closePreview();
    }
  });
}

// ============== 初始化 ==============
async function init() {
  setupTabs();
  setupFilters();
  setupDrawer();
  setupTaskActions();
  setupModals();

  await loadModels();
  await loadTasks();
  startPolling();
  
  console.log('🎨 多模态随心生成 已就绪');
}

// 启动
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
