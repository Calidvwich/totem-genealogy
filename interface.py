def render_app() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>族谱管理系统</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    :root { --primary:#2563eb; --bg:#f1f5f9; --danger:#ef4444; --success:#10b981; --ink:#1e293b; --muted:#64748b; --line:#e2e8f0; --violet:#7c3aed; --cyan:#0891b2; }
    * { box-sizing:border-box; }
    body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; margin:0; background:var(--bg); height:100vh; overflow:hidden; color:var(--ink); }
    button,input,select,textarea { font:inherit; outline:none; }
    input,select,textarea { width:100%; padding:10px; border:1px solid var(--line); border-radius:6px; margin-bottom:10px; font-size:13px; background:white; }
    textarea { min-height:72px; resize:vertical; }
    label { font-size:12px; color:var(--muted); margin-bottom:3px; display:block; }
    button { cursor:pointer; white-space:nowrap; }
    button:disabled { cursor:not-allowed; opacity:.45; }
    #loginOverlay { position:fixed; inset:0; background:#0f172a; display:flex; align-items:center; justify-content:center; z-index:10000; }
    .login-card { background:white; padding:40px; border-radius:12px; width:330px; box-shadow:0 20px 25px -5px rgba(0,0,0,.3); }
    .login-card h2 { text-align:center; color:var(--primary); margin:0 0 20px; }
    .login-card p { text-align:center; font-size:12px; color:var(--muted); margin:14px 0 0; }
    #adminContent { display:none; height:100vh; flex-direction:column; }
    .navbar { background:white; padding:0 24px; height:60px; display:flex; align-items:center; justify-content:space-between; box-shadow:0 1px 2px rgba(0,0,0,.05); gap:12px; }
    .brand { font-weight:800; color:var(--primary); font-size:1.2rem; }
    .nav-actions { display:flex; gap:8px; align-items:center; min-width:0; }
    .mode-switch { display:flex; align-items:center; gap:6px; font-size:13px; color:#475569; border:1px solid var(--line); padding:4px 10px; border-radius:20px; background:#f8fafc; user-select:none; }
    .mode-switch input { width:auto; margin:0; }
    .main-container { flex:1; display:flex; padding:15px; gap:15px; overflow:hidden; }
    .side-panel { width:370px; display:flex; flex-direction:column; gap:15px; height:100%; overflow:hidden; flex-shrink:0; }
    .viz-panel { flex:1; background:white; border-radius:12px; height:100%; position:relative; overflow:hidden; box-shadow:0 4px 6px -1px rgba(0,0,0,.08); }
    .card { background:white; border-radius:12px; padding:16px; box-shadow:0 4px 6px -1px rgba(0,0,0,.1); }
    .btn-primary { background:var(--primary); color:white; border:none; padding:0 15px; border-radius:6px; cursor:pointer; height:38px; }
    .btn-add { width:100%; background:var(--success); color:white; border:none; padding:12px; border-radius:6px; cursor:pointer; font-weight:700; }
    .btn-danger { background:var(--danger); color:white; border:none; padding:5px 10px; border-radius:4px; cursor:pointer; font-size:12px; }
    .btn-sm { background:var(--primary); color:white; border:none; padding:5px 10px; border-radius:4px; cursor:pointer; font-size:12px; }
    .btn-ghost { background:white; border:1px solid var(--line); color:var(--muted); border-radius:4px; padding:5px 10px; font-size:12px; }
    .btn-violet { background:var(--violet); color:white; border:none; padding:5px 10px; border-radius:4px; font-size:12px; }
    .btn-cyan { background:var(--cyan); color:white; border:none; padding:5px 10px; border-radius:4px; font-size:12px; }
    .search-results { flex:1; overflow-y:auto; margin-top:10px; }
    .member-item,.clan-item { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:10px 12px; border:1px solid #f1f5f9; margin-bottom:6px; border-radius:8px; transition:.2s; background:white; }
    .member-item:hover,.clan-item:hover { background:#f8fbff; border-color:var(--primary); }
    .member-item-left { cursor:pointer; flex:1; min-width:0; }
    .sub { color:#94a3b8; font-size:11px; margin-top:2px; }
    .badge { font-size:11px; padding:2px 7px; border-radius:10px; font-weight:600; }
    .badge-owner { background:#fef3c7; color:#92400e; }
    .badge-collab { background:#dbeafe; color:#1e40af; }
    .badge-readonly { background:#f1f5f9; color:#94a3b8; }
    .tabs { display:flex; gap:4px; margin-bottom:10px; }
    .tabs button { flex:1; padding:7px 4px; border:none; border-radius:6px; background:#e2e8f0; color:#475569; font-size:12px; }
    .tabs button.active { background:var(--primary); color:white; font-weight:700; }
    #stats-chart { height:130px; width:100%; }
    #chart-container { width:100%; height:100%; background:linear-gradient(#f8fafc 1px, transparent 1px), linear-gradient(90deg,#f8fafc 1px,transparent 1px); background-size:28px 28px; }
    .tree-tools { position:absolute; top:12px; right:12px; z-index:10; display:flex; gap:6px; }
    .modal-overlay { display:none; position:fixed; inset:0; background:rgba(15,23,42,.48); z-index:9000; align-items:center; justify-content:center; padding:24px; }
    .modal-overlay.active { display:flex; }
    .modal-box { background:white; border-radius:12px; padding:28px; width:430px; box-shadow:0 20px 40px rgba(0,0,0,.2); max-height:86vh; overflow-y:auto; }
    .modal-box.wide { width:660px; max-width:95vw; }
    .modal-box h3 { margin:0 0 18px; color:var(--ink); }
    .modal-footer { display:flex; gap:8px; margin-top:16px; justify-content:flex-end; }
    .btn-cancel { background:#e2e8f0; color:#475569; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; }
    .notice { min-height:18px; font-size:12px; color:var(--muted); margin:7px 0; }
    .table-wrap { overflow:auto; border:1px solid #f1f5f9; border-radius:8px; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th { background:var(--primary); color:white; text-align:left; padding:7px; }
    td { border-bottom:1px solid #f1f5f9; padding:7px; color:#475569; vertical-align:middle; }
    .query-result-table { width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }
    .query-result-table th { background:#2563eb; color:white; padding:6px 8px; text-align:left; font-weight:600; }
    .query-result-table td { padding:5px 8px; border-bottom:1px solid #f1f5f9; color:#475569; }
    .detail-grid { display:grid; grid-template-columns:110px 1fr 110px 1fr; gap:0; border:1px solid #f1f5f9; border-radius:8px; overflow:hidden; margin-bottom:14px; }
    .detail-grid div { padding:8px 10px; border-bottom:1px solid #f1f5f9; font-size:12px; }
    .detail-grid div:nth-child(4n+1), .detail-grid div:nth-child(4n+3) { background:#f8fafc; color:#64748b; font-weight:600; }
    .detail-section-title { margin:12px 0 8px; font-size:13px; font-weight:700; color:#1e293b; }
    @media (max-width:980px) { body { overflow:auto; height:auto; } #adminContent { height:auto; min-height:100vh; } .navbar { height:auto; padding:12px; flex-direction:column; align-items:flex-start; } .nav-actions { flex-wrap:wrap; } .main-container { flex-direction:column; height:auto; overflow:visible; } .side-panel { width:100%; } .viz-panel { min-height:560px; } }
  </style>
</head>
<body>
  <div id="loginOverlay">
    <div class="login-card">
      <div id="loginPanel">
        <h2>系统登录</h2>
        <input type="text" id="login_uid" value="admin" placeholder="账号" autocomplete="username">
        <input type="password" id="login_pwd" value="123456" placeholder="密码" autocomplete="current-password">
        <div id="loginMsg" class="notice" style="text-align:center;color:var(--danger)"></div>
        <button class="btn-add" onclick="handleLogin()">进入系统</button>
        <p>默认账号 admin / 123456，普通测试账号 test01 / 123456</p>
        <p style="margin-top:10px;"><a href="#" onclick="switchToRegister();return false;" style="color:var(--primary);font-size:13px;">没有账号？点此注册</a></p>
      </div>
      <div id="registerPanel" style="display:none;">
        <h2>注册账号</h2>
        <input type="text" id="reg_uid" placeholder="账号（4-20位字母数字）" autocomplete="username">
        <input type="text" id="reg_name" placeholder="显示名称（可选）">
        <input type="password" id="reg_pwd" placeholder="密码" autocomplete="new-password">
        <input type="password" id="reg_pwd2" placeholder="确认密码" autocomplete="new-password">
        <div id="registerMsg" class="notice" style="text-align:center;color:var(--danger)"></div>
        <button class="btn-add" onclick="handleRegister()">注册</button>
        <p style="margin-top:10px;"><a href="#" onclick="switchToLogin();return false;" style="color:var(--primary);font-size:13px;">已有账号？返回登录</a></p>
      </div>
    </div>
  </div>

  <div id="adminContent">
    <div class="navbar">
      <div class="brand">族谱管理系统</div>
      <div id="currentUserLabel" style="color:#64748b;font-size:13px;">未登录</div>
      <div class="nav-actions">
        <label class="mode-switch" title="开启后显示索引性能指标">
          <input type="checkbox" id="perfModeToggle">
          <span>性能模式</span>
        </label>
        <button class="btn-sm" onclick="toggleClanView()">我的族谱</button>
        <button class="btn-sm" style="background:var(--success)" onclick="openImportModal()">导入族谱</button>
        <button class="btn-sm" style="background:var(--cyan)" onclick="openExportModal()">导出族谱</button>
        <button class="btn-cyan" onclick="openQueryModal()">统计查询</button>
        <button id="userManageBtn" class="btn-violet" onclick="toggleUserView()">用户管理</button>
        <button class="btn-ghost" onclick="logout()">退出</button>
      </div>
    </div>

    <div class="main-container">
      <div class="side-panel">
        <div class="card">
          <h4 style="margin:0 0 10px;">数据概览</h4>
          <div id="chart-clan-label" style="font-size:11px;color:#94a3b8;margin-bottom:4px;text-align:center;">全库统计</div>
          <div id="stats-chart"></div>
        </div>

        <div class="card" style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
          <div id="search-view" style="display:flex;flex-direction:column;flex:1;overflow:hidden;">
            <div class="tabs">
              <button id="tab-search" class="active" onclick="switchTab('search')">成员查询</button>
              <button id="tab-relation" onclick="switchTab('relation')">查询关系</button>
            </div>
            <div id="panel-search" style="display:flex;flex-direction:column;flex:1;overflow:hidden;">
              <div style="display:flex;gap:8px">
                <input type="text" id="nameInput" placeholder="输入姓名或编号查询..." style="margin:0">
                <button class="btn-primary" onclick="search()">查询</button>
                <button class="btn-violet" onclick="runExplain()">EXPLAIN</button>
                <button class="btn-primary" style="background:var(--success)" onclick="openAddMember()">添加</button>
              </div>
              <div id="search-msg" class="notice"></div>
              <div class="search-results" id="search-results"></div>
            </div>
            <div id="panel-relation" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
              <input type="number" id="relIdA" placeholder="成员 A ID">
              <input type="number" id="relIdB" placeholder="成员 B ID">
              <button class="btn-primary" onclick="queryRelation()" style="width:100%;margin-bottom:8px;">查询亲缘关系</button>
              <div id="relation-msg" class="notice"></div>
              <div id="relation-result" style="overflow-y:auto;flex:1;"></div>
            </div>
          </div>

          <div id="clan-view" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <span style="font-size:13px;font-weight:600;">族谱管理</span>
              <div>
                <button class="btn-sm" style="background:var(--success)" onclick="openClanModal()">新建</button>
                <button class="btn-ghost" onclick="toggleClanView()">关闭</button>
              </div>
            </div>
            <div id="clan-list" style="overflow-y:auto;flex:1;"></div>
          </div>

          <div id="user-view" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <span style="font-size:13px;font-weight:600;">用户管理</span>
              <div>
                <button class="btn-sm" style="background:var(--success)" onclick="openUserModal()">新建</button>
                <button class="btn-ghost" onclick="toggleUserView()">关闭</button>
              </div>
            </div>
            <div class="notice">仅 admin 可以新建、编辑和删除用户。</div>
            <div id="user-list" style="overflow-y:auto;flex:1;"></div>
          </div>
        </div>
      </div>
      <div class="viz-panel">
        <div class="tree-tools">
          <button class="btn-ghost" onclick="zoomTree(0.82)">缩小</button>
          <button class="btn-ghost" onclick="zoomTree(1.18)">放大</button>
          <button class="btn-primary" onclick="resetTreeView()">重置</button>
        </div>
        <div id="chart-container"></div>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="memberModal">
    <div class="modal-box">
      <h3 id="memberModalTitle">成员信息</h3>
      <input type="hidden" id="member_id">
      <label>族谱</label><select id="member_clan"></select>
      <label>姓名</label><input id="member_name">
      <label>性别</label><select id="member_gender"><option value="M">男</option><option value="F">女</option><option value="U">未知</option></select>
      <label>出生年</label><input type="number" id="member_birth">
      <label>死亡年</label><input type="number" id="member_death">
      <label>父亲姓名</label><input id="member_father_name" placeholder="先输入姓名，重名时再填写确认 ID">
      <label>父亲重名确认 ID</label><input type="number" id="member_father_id" placeholder="只有重名或需要精确指定时填写">
      <label>母亲姓名</label><input id="member_mother_name" placeholder="先输入姓名，重名时再填写确认 ID">
      <label>母亲重名确认 ID</label><input type="number" id="member_mother_id" placeholder="只有重名或需要精确指定时填写">
      <label>添加/确认子女姓名</label><input id="member_child_name" placeholder="编辑已有成员时可按姓名添加子女关系">
      <label>子女重名确认 ID</label><input type="number" id="member_child_id" placeholder="只有重名或需要精确指定时填写">
      <label>世代</label><input type="number" id="member_generation">
      <label>简介</label><textarea id="member_bio"></textarea>
      <label>照片</label><input type="file" id="member_photo" accept="image/*">
      <div id="memberMsg" class="notice" style="color:var(--danger)"></div>
      <div class="modal-footer">
        <button class="btn-cancel" onclick="closeModal('memberModal')">取消</button>
        <button class="btn-primary" onclick="submitMember()">保存</button>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="detailModal">
    <div class="modal-box wide">
      <h3 id="detailTitle">成员详情</h3>
      <div id="detailBody"></div>
      <div class="modal-footer"><button class="btn-cancel" onclick="closeModal('detailModal')">关闭</button></div>
    </div>
  </div>

  <div class="modal-overlay" id="clanModal">
    <div class="modal-box">
      <h3 id="clanModalTitle">族谱信息</h3>
      <input type="hidden" id="clan_id">
      <label>族谱标题</label><input id="clan_title">
      <label>姓氏</label><input id="clan_surname">
      <div id="clanMsg" class="notice" style="color:var(--danger)">创建者默认为当前登录用户。</div>
      <div class="modal-footer">
        <button class="btn-cancel" onclick="closeModal('clanModal')">取消</button>
        <button class="btn-primary" onclick="submitClan()">保存</button>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="userModal">
    <div class="modal-box">
      <h3 id="userModalTitle">用户信息</h3>
      <input type="hidden" id="user_numeric_id">
      <label>账号</label><input id="user_account">
      <label>用户名</label><input id="user_name">
      <label>密码</label><input id="user_password" type="password" placeholder="编辑时留空表示不修改">
      <div id="userMsg" class="notice" style="color:var(--danger)"></div>
      <div class="modal-footer">
        <button class="btn-cancel" onclick="closeModal('userModal')">取消</button>
        <button class="btn-primary" onclick="submitUser()">保存</button>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="userDetailModal">
    <div class="modal-box wide">
      <h3 id="userDetailTitle">用户详情</h3>
      <div id="userDetailBody"></div>
      <div class="modal-footer"><button class="btn-cancel" onclick="closeModal('userDetailModal')">关闭</button></div>
    </div>
  </div>

  <div class="modal-overlay" id="collabModal">
    <div class="modal-box">
      <h3>协作者管理</h3>
      <p style="font-size:13px;color:#64748b;margin-top:0;">族谱 <span id="collab_clan_id_label"></span></p>
      <div style="display:flex;gap:8px;"><input id="grant_user_input" placeholder="输入用户账号" style="margin:0"><button class="btn-primary" onclick="grantAccess()">授权</button></div>
      <div id="grantMsg" class="notice"></div>
      <div id="collabList"></div>
      <div class="modal-footer"><button class="btn-cancel" onclick="closeModal('collabModal')">关闭</button></div>
    </div>
  </div>

  <div class="modal-overlay" id="importModal">
    <div class="modal-box">
      <h3>导入族谱</h3>
      <label>族谱标题</label><input id="import_title" placeholder="例如：张氏导入族谱">
      <label>姓氏</label><input id="import_surname" placeholder="例如：张">
      <label>成员 CSV</label><input type="file" id="import_csv" accept=".csv,text/csv">
      <div class="notice">CSV 至少需要 name/姓名 字段，可选 gender、birth_year、death_year、father_id、mother_id、generation_num、bio。</div>
      <label>导入导出包</label><input type="file" id="import_bundle" accept=".json,application/json">
      <div class="notice">选择导出目录中的 import_bundle.json 可恢复数据库或部分族谱。若存在重复 ID 或账号，导入会停止并提示原因。</div>
      <div id="importMsg" class="notice"></div>
      <div class="modal-footer">
        <button class="btn-cancel" onclick="closeModal('importModal')">取消</button>
        <button class="btn-primary" onclick="submitClanImport()">导入 CSV 新建族谱</button>
        <button class="btn-violet" onclick="submitBundleImport()">导入导出包</button>
        <button class="btn-danger" onclick="submitGeneratedImport()" title="清空现有族谱、成员、婚姻和协作关系后导入生成脚本数据">导入生成数据</button>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="exportModal">
    <div class="modal-box wide">
      <h3>导出族谱</h3>
      <div id="exportClanList" class="table-wrap" style="max-height:300px;overflow:auto;padding:8px;"></div>
      <div id="exportMsg" class="notice"></div>
      <div class="modal-footer">
        <button class="btn-cancel" onclick="closeModal('exportModal')">取消</button>
        <button class="btn-primary" onclick="submitClanExport()">导出所选族谱</button>
        <button class="btn-violet" onclick="submitDatabaseExport()">导出整个数据库</button>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="queryModal">
    <div class="modal-box wide">
      <h3>统计查询</h3>
      <div class="tabs" style="flex-wrap:wrap;">
        <button id="qt-spouse" onclick="switchQueryTab('spouse')" class="active">配偶/子女</button>
        <button id="qt-ancestors" onclick="switchQueryTab('ancestors')">祖先</button>
        <button id="qt-longevity" onclick="switchQueryTab('longevity')">最长寿一代</button>
        <button id="qt-singles" onclick="switchQueryTab('singles')">50+单身男性</button>
        <button id="qt-early" onclick="switchQueryTab('early')">早于均值</button>
        <button id="qt-descendants" onclick="switchQueryTab('descendants')">四代曾孙</button>
      </div>
      <div id="qp-spouse"><input id="q-spouse-name" type="text" placeholder="成员姓名"><input id="q-spouse-id" type="number" placeholder="重名时填写成员 ID"><button class="btn-primary" onclick="runQuery('spouse')" style="width:100%">查询</button><div id="qr-spouse"></div></div>
      <div id="qp-ancestors" style="display:none"><input id="q-ancestors-name" type="text" placeholder="成员姓名"><input id="q-ancestors-id" type="number" placeholder="重名时填写成员 ID"><button class="btn-primary" onclick="runQuery('ancestors')" style="width:100%">查询</button><div id="qr-ancestors"></div></div>
      <div id="qp-longevity" style="display:none"><select id="q-longevity-clan"></select><button class="btn-primary" onclick="runQuery('longevity')" style="width:100%">查询</button><div id="qr-longevity"></div></div>
      <div id="qp-singles" style="display:none"><select id="q-singles-clan"></select><button class="btn-primary" onclick="runQuery('singles')" style="width:100%">查询</button><div id="qr-singles"></div></div>
      <div id="qp-early" style="display:none"><select id="q-early-clan"></select><button class="btn-primary" onclick="runQuery('early')" style="width:100%">查询</button><div id="qr-early"></div></div>
      <div id="qp-descendants" style="display:none"><input id="q-descendants-name" type="text" placeholder="成员姓名"><input id="q-descendants-id" type="number" placeholder="重名时填写成员 ID"><button class="btn-primary" onclick="runQuery('descendants')" style="width:100%">查询</button><div id="qr-descendants"></div></div>
      <div class="modal-footer"><button class="btn-cancel" onclick="closeModal('queryModal')">关闭</button></div>
    </div>
  </div>

  <script>
    let myChart = null, pieChart = null;
    const state = { user:null, logSession:null, clans:[], users:[], currentClanId:0, currentPerm:{can_edit:false,is_owner:false}, currentTreeMemberId:null, currentDetailMemberId:null, treeZoom:1, treeRoots:[] };
    const $ = (id) => document.getElementById(id);
    const esc = (v) => (v == null ? "" : String(v)).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
    const num = (v) => v === "" || v == null ? null : Number(v);
    const formatDate = (v) => v ? String(v).replace("T", " ").slice(0, 19) : "-";
    const actorId = () => state.user ? state.user.user_id : "";
    const actorParam = () => {
      const parts = [`current_user_id=${encodeURIComponent(actorId())}`];
      if (state.logSession) parts.push(`log_session=${encodeURIComponent(state.logSession)}`);
      return parts.join("&");
    };
    function fieldName(name) {
      const map = {user_id:"账号", password:"密码", username:"用户名", title:"标题", name:"姓名"};
      return map[name] || name;
    }
    function formatApiError(detail) {
      if (!detail) return "请求失败";
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail.map(item => {
          const loc = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
          const msg = item.msg || "填写不正确";
          return `${fieldName(loc)}：${msg}`;
        }).join("；");
      }
      if (typeof detail === "object") {
        return detail.message || detail.msg || JSON.stringify(detail);
      }
      return String(detail);
    }
    async function api(url, options={}) {
      const headers = options.body instanceof FormData ? {} : {"Content-Type":"application/json"};
      const res = await fetch(url, {headers, ...options});
      const text = await res.text();
      if (!res.ok) {
        let detail = "请求失败";
        try { detail = JSON.parse(text).detail || detail; } catch(e) { if (text) detail = text; }
        throw new Error(formatApiError(detail));
      }
      if (res.status === 204) return null;
      if (!text.trim()) throw new Error(`服务器返回空响应：${url}`);
      try {
        return JSON.parse(text);
      } catch(e) {
        throw new Error(`服务器返回非 JSON 响应：${text.slice(0, 120)}`);
      }
    }

    async function handleLogin() {
      const msg = $("loginMsg");
      const userId = $("login_uid").value.trim();
      const password = $("login_pwd").value;
      msg.style.color = "var(--danger)";
      if (!userId) return msg.textContent = "请填写账号";
      if (!password) return msg.textContent = "请填写密码";
      try {
        msg.textContent = "验证中...";
        const data = await api("/api/login", {method:"POST", body:JSON.stringify({user_id:userId, password:password})});
        state.user = data.user;
        state.logSession = data.log_session || "";
        $("currentUserLabel").textContent = `${data.user.username || data.user.user_id} | 已登录`;
        $("userManageBtn").style.display = actorId() === "admin" ? "" : "none";
        $("loginOverlay").style.display = "none";
        $("adminContent").style.display = "flex";
        await initApp();
      } catch(e) { msg.textContent = e.message; }
    }
    function switchToRegister() {
      $("loginPanel").style.display = "none";
      $("registerPanel").style.display = "";
      $("registerMsg").textContent = "";
      $("reg_uid").value = "";
      $("reg_name").value = "";
      $("reg_pwd").value = "";
      $("reg_pwd2").value = "";
    }
    function switchToLogin() {
      $("registerPanel").style.display = "none";
      $("loginPanel").style.display = "";
      $("loginMsg").textContent = "";
    }
    async function handleRegister() {
      const msg = $("registerMsg");
      const userId = $("reg_uid").value.trim();
      const username = $("reg_name").value.trim();
      const pwd = $("reg_pwd").value;
      const pwd2 = $("reg_pwd2").value;
      msg.style.color = "var(--danger)";
      if (!userId) return msg.textContent = "请填写账号";
      if (userId.length < 4) return msg.textContent = "账号至少 4 位";
      if (!pwd) return msg.textContent = "请填写密码";
      if (pwd !== pwd2) return msg.textContent = "两次密码不一致";
      try {
        msg.style.color = "#64748b";
        msg.textContent = "注册中...";
        await api("/api/register", {method:"POST", body:JSON.stringify({user_id:userId, password:pwd, username:username||userId})});
        $("login_uid").value = userId;
        $("login_pwd").value = "";
        switchToLogin();
        $("loginMsg").style.color = "var(--success)";
        $("loginMsg").textContent = "注册成功，请使用新账号登录";
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function logout() {
      try {
        if (state.user) await api(`/api/logout?${actorParam()}`, {method:"POST"});
      } catch(e) {}
      state.user = null;
      state.logSession = null;
      state.currentClanId = 0;
      if (myChart) myChart.clear();
      if (pieChart) pieChart.clear();
      $("adminContent").style.display = "none";
      $("loginOverlay").style.display = "flex";
      $("userManageBtn").style.display = "";
      $("login_pwd").value = "";
      $("loginMsg").textContent = "";
    }
    async function initApp() {
      setTimeout(() => {
        if (window.echarts) {
          if (!myChart) myChart = echarts.init($("chart-container"));
          if (!pieChart) pieChart = echarts.init($("stats-chart"));
          window.addEventListener("resize", () => { myChart && myChart.resize(); pieChart && pieChart.resize(); });
          updateDashboard(state.currentClanId);
        }
      }, 80);
      await loadClans();
      await loadUsers();
      await updateDashboard();
      resetSearchPanel();
      renderEmptyTree();
    }

    async function updateDashboard(clanId) {
      const cid = clanId || 0;
      const data = await api(`/api/dashboard?clan_id=${cid}`);
      const M = data.gender.M || 0, F = data.gender.F || 0, U = data.gender.U || 0;
      const total = M + F + U;
      $("chart-clan-label").textContent = cid ? `${currentClanName(cid)} · 共 ${total} 人` : `全库统计 · 共 ${total} 人`;
      if (!window.echarts || !pieChart) return renderPieFallback(M,F,U,total);
      pieChart.setOption({
        tooltip:{trigger:"item", formatter:p=>`${p.name}<br>${p.value} 人 (${p.percent.toFixed(2)}%)`},
        legend:{show:false},
        series:[{type:"pie", radius:["38%","65%"], label:{show:true,fontSize:11,formatter:p=>`${p.name}\\n${p.value}人\\n${p.percent.toFixed(2)}%`}, data:[
          {value:M,name:"男",itemStyle:{color:"#2563eb"}},
          {value:F,name:"女",itemStyle:{color:"#10b981"}},
          ...(U ? [{value:U,name:"未知",itemStyle:{color:"#94a3b8"}}] : [])
        ]}]
      }, true);
      setTimeout(()=>pieChart && pieChart.resize(), 50);
    }
    function renderPieFallback(M,F,U,total) {
      const safe = Math.max(1,total);
      const m = M / safe * 360, f = m + F / safe * 360;
      $("stats-chart").innerHTML = `<div style="height:130px;display:flex;align-items:center;justify-content:center;gap:12px;"><div style="width:100px;height:100px;border-radius:50%;background:conic-gradient(#2563eb 0deg ${m}deg,#10b981 ${m}deg ${f}deg,#94a3b8 ${f}deg 360deg);"></div><div style="font-size:12px;color:#64748b;line-height:1.8">男 ${M}<br>女 ${F}<br>未知 ${U}</div></div>`;
    }

    async function loadClans() {
      state.clans = await api("/api/clans");
      renderClanList();
      fillClanSelects();
    }
    function currentClanName(id) {
      const c = state.clans.find(x => Number(x.clan_id) === Number(id));
      return c ? (c.title || c.surname || `族谱 ${id}`) : `族谱 ${id}`;
    }
    function fillClanSelects() {
      const options = state.clans.map(c => `<option value="${c.clan_id}">${esc(c.title || c.clan_id)}</option>`).join("");
      ["member_clan","q-longevity-clan"].forEach(id => { if ($(id)) $(id).innerHTML = options; });
      ["q-singles-clan","q-early-clan"].forEach(id => { if ($(id)) $(id).innerHTML = `<option value="0">全部族谱</option>${options}`; });
    }

    function resetSearchPanel() {
      const msg = $("search-msg"), results = $("search-results");
      if (msg) {
        msg.style.color = "#64748b";
        msg.textContent = "请输入姓名或编号后查询";
      }
      if (results) results.innerHTML = "";
    }

    async function search() {
      const msg = $("search-msg"), results = $("search-results");
      const q = $("nameInput").value.trim();
      if (!q) {
        resetSearchPanel();
        return;
      }
      msg.style.color = "#64748b";
      msg.textContent = "查询中...";
      try {
        const perf = $("perfModeToggle").checked;
        const data = await api(`/api/members/search-performance?clan_id=0&q=${encodeURIComponent(q)}&performance_mode=${perf}&${actorParam()}`);
        const found = data.ok && Number(data.count || 0) > 0;
        msg.style.color = found ? "var(--success)" : "var(--danger)";
        const modeText = data.mode === "performance" ? "性能模式/索引前缀搜索" : "普通模式/全表包含扫描";
        msg.textContent = `${found ? "搜索成功" : "搜索失败，未检索到对象"} | ${modeText} | 用时 ${data.elapsed_ms} ms | 内存 ${data.memory_kb} KB | 结果 ${data.count} 条${data.error ? " | " + data.error : ""}`;
        results.innerHTML = found
          ? (data.rows || []).map(m => renderMemberItem(m)).join("")
          : "<div class='notice' style='color:var(--danger)'>没有检索到对象</div>";
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = "查询失败：" + e.message;
        results.innerHTML = "";
      }
    }
    async function runExplain() {
      const msg = $("search-msg");
      const q = $("nameInput").value.trim();
      if (!q) {
        resetSearchPanel();
        return;
      }
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在生成 EXPLAIN...";
        const result = await api(`/api/performance/explain?${actorParam()}`, {
          method:"POST",
          body:JSON.stringify({q, clan_id:0, performance_mode:$("perfModeToggle").checked})
        });
        msg.style.color = "var(--success)";
        msg.textContent = `EXPLAIN 已保存：${result.output_file}`;
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    function renderMemberItem(m) {
      return `<div class="member-item">
        <div class="member-item-left" onclick="loadMemberTree(${m.member_id}, ${m.clan_id})">
          <strong>${esc(m.name)}</strong>
          <small style="margin-left:8px;color:#94a3b8;">#${m.member_id} · 族谱 ${m.clan_id} · 第${m.generation_num || "?"}代</small>
        </div>
        <div style="display:flex;gap:4px;align-items:center;">
          <button class="btn-sm" onclick="loadMemberTree(${m.member_id}, ${m.clan_id})">查看</button>
          <button class="btn-sm" style="background:#7c3aed" onclick="openDetail(${m.member_id})">详情</button>
          <button class="btn-sm" onclick="openEditMember(${m.member_id})">编辑</button>
          <button class="btn-danger" onclick="deleteMember(${m.member_id})">删除</button>
        </div>
      </div>`;
    }

    async function loadMemberTree(memberId, clanId) {
      state.currentClanId = Number(clanId || 0);
      state.currentTreeMemberId = memberId;
      const perm = await api(`/api/clans/${state.currentClanId}/permission?${actorParam()}`);
      state.currentPerm = perm;
      await updateDashboard(state.currentClanId);
      const detail = await api(`/api/members/${memberId}/detail`);
      const ancestors = await api(`/api/members/${memberId}/ancestors`);
      const treeData = buildAncestorHierarchy(detail.member, ancestors);
      renderTree(treeData ? [treeData] : []);
    }
    function renderEmptyTree() {
      if (window.echarts && myChart) {
        myChart.dispose();
        myChart = null;
      }
      $("chart-container").innerHTML = "<p class='notice' style='padding:18px'>点击左侧成员，右侧展示其祖先树。鼠标滚轮缩放，拖拽平移。</p>";
    }
    function buildAncestorHierarchy(member, ancestors) {
      const byId = {};
      [member].concat(ancestors || []).forEach(x => { if (x && x.member_id) byId[Number(x.member_id)] = x; });
      const build = (item, seen=new Set()) => {
        if (!item || seen.has(Number(item.member_id))) return null;
        const next = new Set(seen); next.add(Number(item.member_id));
        return {...item, children:[item.father_id, item.mother_id].map(id => id ? build(byId[Number(id)], next) : null).filter(Boolean)};
      };
      return build(member);
    }
    function treeGenderColor(g) {
      return g === "F" ? "#ec4899" : g === "M" ? "#2563eb" : "#94a3b8";
    }
    function toChartNode(n) {
      const color = treeGenderColor(n.gender);
      return {
        name:n.name || `#${n.member_id}`,
        member_id:n.member_id,
        gender:n.gender,
        generation:n.generation_num,
        birth_year:n.birth_year,
        collapsed:n.collapsed === true,
        itemStyle:{color, borderColor:"#ffffff", borderWidth:2},
        label:{borderColor:color},
        children:(n.children || []).map(toChartNode)
      };
    }
    function findTreeNode(nodes, memberId) {
      for (const node of nodes || []) {
        if (Number(node.member_id) === Number(memberId)) return node;
        const found = findTreeNode(node.children || [], memberId);
        if (found) return found;
      }
      return null;
    }
    function isTreeLabelClick(params) {
      let target = params && params.event ? params.event.target : null;
      while (target) {
        if (target.type === "text") return true;
        target = target.parent;
      }
      return false;
    }
    function applyTreeOption() {
      if (!myChart) return;
      myChart.setOption({
        tooltip:{trigger:"item",triggerOn:"mousemove",formatter:p=>`<b>${esc(p.data.name)}</b><br>成员ID：${p.data.member_id || "-"}<br>性别：${genderLabel(p.data.gender)}<br>世代：${p.data.generation || "-"}<br>生年：${p.data.birth_year || "-"}`},
        series:[{
          type:"tree",
          data:state.treeRoots,
          top:"8%",
          left:"12%",
          bottom:"8%",
          right:"12%",
          orient:"RL",
          roam:true,
          zoom:state.treeZoom,
          expandAndCollapse:false,
          initialTreeDepth:12,
          symbol:"circle",
          symbolSize:14,
          label:{position:"right", align:"left", verticalAlign:"middle", color:"#334155", backgroundColor:"rgba(255,255,255,.92)", borderColor:"#dbeafe", borderWidth:1.5, borderRadius:6, padding:[5,9], cursor:"pointer"},
          leaves:{label:{position:"left", align:"right"}},
          lineStyle:{color:"#93c5fd", width:1.5, curveness:.35},
          emphasis:{focus:"ancestor"}
        }]
      }, true);
    }
    function renderTree(roots) {
      if (!window.echarts) return;
      if (!myChart || (myChart.isDisposed && myChart.isDisposed())) {
        $("chart-container").innerHTML = "";
        myChart = echarts.init($("chart-container"));
      }
      state.treeZoom = 1;
      state.treeRoots = roots.map(toChartNode);
      applyTreeOption();
      myChart.off("click");
      myChart.on("click", p => {
        if (!p.data || !p.data.member_id) return;
        if (isTreeLabelClick(p)) {
          openDetail(p.data.member_id);
          return;
        }
        const node = findTreeNode(state.treeRoots, p.data.member_id);
        if (node && node.children && node.children.length) {
          node.collapsed = !node.collapsed;
          applyTreeOption();
        }
      });
      setTimeout(()=>myChart && myChart.resize(), 50);
    }
    function zoomTree(factor) {
      if (!myChart) return;
      state.treeZoom = Math.max(0.25, Math.min(3.5, state.treeZoom * factor));
      myChart.setOption({series:[{zoom:state.treeZoom}]});
    }
    async function resetTreeView() {
      if (state.currentTreeMemberId) {
        await loadMemberTree(state.currentTreeMemberId, state.currentClanId);
      } else {
        renderEmptyTree();
      }
    }

    function switchTab(tab) {
      const searchTab = tab === "search";
      $("panel-search").style.display = searchTab ? "flex" : "none";
      $("panel-relation").style.display = searchTab ? "none" : "flex";
      $("tab-search").classList.toggle("active", searchTab);
      $("tab-relation").classList.toggle("active", !searchTab);
    }
    async function queryRelation() {
      const a = $("relIdA").value, b = $("relIdB").value;
      if (!a || !b) return $("relation-msg").textContent = "请输入两个成员 ID";
      try {
        const data = await api(`/api/members/${a}/relationship?target_id=${b}`);
        $("relation-msg").textContent = data.path.length ? "查询成功" : "未找到通路";
        $("relation-result").innerHTML = data.path.map(m => `<span class="badge badge-collab">${esc(m.name)} #${m.member_id}</span>`).join(" → ");
      } catch(e) { $("relation-msg").textContent = e.message; }
    }

    function toggleClanView() {
      const open = $("clan-view").style.display !== "flex";
      $("clan-view").style.display = open ? "flex" : "none";
      $("search-view").style.display = open ? "none" : "flex";
      $("user-view").style.display = "none";
      if (open) loadClans();
    }
    function toggleUserView() {
      if (actorId() !== "admin") return;
      const open = $("user-view").style.display !== "flex";
      $("user-view").style.display = open ? "flex" : "none";
      $("search-view").style.display = open ? "none" : "flex";
      $("clan-view").style.display = "none";
      if (open) loadUsers();
    }
    function renderClanList() {
      $("clan-list").innerHTML = state.clans.map(c => {
        const isOwner = c.creator_user_id === actorId();
        return `<div class="clan-item">
          <div style="min-width:0">
            <strong>${esc(c.title)}</strong><div class="sub">#${c.clan_id} · 姓氏 ${esc(c.surname || "-")} · 创建者 ${esc(c.creator_user_id || "-")} · 协作者 ${c.collaborators || 0}</div>
          </div>
          <div style="display:flex;gap:4px;">
            <button class="btn-sm" onclick="selectClan(${c.clan_id})">统计</button>
            <button class="btn-violet" onclick="openCollabModal(${c.clan_id})" ${isOwner ? "" : "disabled"}>协作</button>
            <button class="btn-sm" onclick="openClanModal(${c.clan_id})" ${isOwner ? "" : "disabled"}>编辑</button>
            <button class="btn-danger" onclick="deleteClan(${c.clan_id})" ${isOwner ? "" : "disabled"}>删除</button>
          </div>
        </div>`;
      }).join("") || "<div class='notice'>暂无族谱</div>";
    }
    async function selectClan(id) { state.currentClanId = id; await updateDashboard(id); renderEmptyTree(); }
    function openClanModal(id) {
      const c = id ? state.clans.find(x => Number(x.clan_id) === Number(id)) : null;
      $("clan_id").value = c ? c.clan_id : "";
      $("clan_title").value = c ? c.title || "" : "";
      $("clan_surname").value = c ? c.surname || "" : "";
      $("clanModalTitle").textContent = c ? `编辑族谱 #${c.clan_id}` : "新建族谱";
      $("clanMsg").textContent = c ? `创建者：${c.creator_user_id}（不可修改）` : `创建者默认为当前登录用户：${actorId()}`;
      openModal("clanModal");
    }
    async function submitClan() {
      try {
        const id = $("clan_id").value;
        const payload = {title:$("clan_title").value, surname:$("clan_surname").value};
        await api(id ? `/api/clans/${id}?${actorParam()}` : `/api/clans?${actorParam()}`, {method:id ? "PUT" : "POST", body:JSON.stringify(payload)});
        closeModal("clanModal"); await loadClans(); await updateDashboard(state.currentClanId);
      } catch(e) { $("clanMsg").textContent = e.message; }
    }
    async function deleteClan(id) {
      if (!confirm(`确认删除族谱 #${id}？`)) return;
      await api(`/api/clans/${id}?${actorParam()}`, {method:"DELETE"});
      await loadClans(); await updateDashboard();
    }

    async function loadUsers() {
      state.users = await api(`/api/users?${actorParam()}`);
      $("user-list").innerHTML = state.users.map(u => `<div class="member-item">
        <div class="member-item-left" onclick="openUserDetail(${u.id})">
          <strong>${esc(u.username || u.user_id)}</strong>
          <div class="sub">#${u.id} · 账号 ${esc(u.user_id)} · ${esc(formatDate(u.created_at))}</div>
        </div>
        <div style="display:flex;gap:4px;">
          <button class="btn-sm" onclick="openUserDetail(${u.id})">详情</button>
          <button class="btn-sm" onclick="openUserModal(${u.id})" ${actorId()==="admin" ? "" : "disabled"}>编辑</button>
          <button class="btn-danger" onclick="deleteUser(${u.id})" ${actorId()==="admin" ? "" : "disabled"}>删除</button>
        </div>
      </div>`).join("") || "<div class='notice'>暂无用户</div>";
    }
    function renderUserClanRows(rows, emptyText) {
      if (!rows || !rows.length) return `<div class="notice">${emptyText}</div>`;
      return rows.map(c => `<div class="clan-item">
        <div style="min-width:0">
          <strong>${esc(c.title)}</strong>
          <div class="sub">#${c.clan_id} · 姓氏 ${esc(c.surname || "-")} · 创建者 ${esc(c.creator_user_id || "-")} · 协作者 ${c.collaborators || 0}</div>
        </div>
        <button class="btn-sm" onclick="closeModal('userDetailModal'); selectClan(${c.clan_id});">查看</button>
      </div>`).join("");
    }
    async function openUserDetail(id) {
      try {
        const data = await api(`/api/users/${id}/detail?${actorParam()}`);
        const u = data.user || {};
        $("userDetailTitle").textContent = `${u.username || u.user_id || "用户"} #${u.id}`;
        $("userDetailBody").innerHTML = `
          <div class="detail-grid">
            <div>账号</div><div>${esc(u.user_id || "-")}</div>
            <div>用户名</div><div>${esc(u.username || "-")}</div>
            <div>数字 ID</div><div>${esc(u.id || "-")}</div>
            <div>创建时间</div><div>${esc(formatDate(u.created_at))}</div>
          </div>
          <div class="detail-section-title">创建的族谱</div>
          ${renderUserClanRows(data.owned_clans, "暂无创建的族谱")}
          <div class="detail-section-title">协作族谱</div>
          ${renderUserClanRows(data.collaborated_clans, "暂无协作族谱")}
        `;
        openModal("userDetailModal");
      } catch(e) {
        $("user-list").insertAdjacentHTML("afterbegin", `<div class="notice" style="color:var(--danger)">${esc(e.message)}</div>`);
      }
    }
    function openUserModal(id) {
      const u = id ? state.users.find(x => Number(x.id) === Number(id)) : null;
      $("user_numeric_id").value = u ? u.id : "";
      $("user_account").value = u ? u.user_id : "";
      $("user_account").disabled = !!u;
      $("user_name").value = u ? u.username || "" : "";
      $("user_password").value = "";
      $("userModalTitle").textContent = u ? `编辑用户 #${u.id}` : "新建用户";
      $("userMsg").textContent = "";
      openModal("userModal");
    }
    async function submitUser() {
      if (actorId() !== "admin") return $("userMsg").textContent = "只有 admin 可以管理用户";
      try {
        const id = $("user_numeric_id").value;
        const payload = {username:$("user_name").value};
        if (!id) payload.user_id = $("user_account").value;
        if ($("user_password").value) payload.password = $("user_password").value;
        await api(id ? `/api/users/${id}?${actorParam()}` : `/api/users?${actorParam()}`, {method:id ? "PUT" : "POST", body:JSON.stringify(payload)});
        closeModal("userModal"); await loadUsers();
      } catch(e) { $("userMsg").textContent = e.message; }
    }
    async function deleteUser(id) {
      if (actorId() !== "admin") return;
      if (!confirm(`确认删除用户 #${id}？`)) return;
      await api(`/api/users/${id}?${actorParam()}`, {method:"DELETE"});
      await loadUsers();
    }

    async function openDetail(id) {
      try {
        const d = await api(`/api/members/${id}/detail`);
        const m = d.member || {};
        state.currentDetailMemberId = Number(m.member_id || id);
        $("detailTitle").textContent = `${m.name || "成员"} #${m.member_id}`;
        const photoUrl = `/api/members/${m.member_id}/photo?v=${encodeURIComponent(m.id_pic || "default")}`;
        $("detailBody").innerHTML = `<div style="display:flex;gap:16px;align-items:flex-start;margin-bottom:12px;">
          <img src="${photoUrl}" alt="成员照片" style="width:128px;height:128px;object-fit:cover;border-radius:8px;border:1px solid #e2e8f0;background:#f8fafc;">
          <table style="flex:1"><tbody>
          <tr><td>性别</td><td>${genderLabel(m.gender)}</td><td>族谱</td><td>${esc((d.clan && d.clan.title) || m.clan_id || "-")}</td></tr>
          <tr><td>出生</td><td>${m.birth_year || "-"}</td><td>死亡</td><td>${m.death_year || "-"}</td></tr>
          <tr><td>父亲</td><td>${d.father ? esc(d.father.name) + " #" + d.father.member_id : "-"}</td><td>母亲</td><td>${d.mother ? esc(d.mother.name) + " #" + d.mother.member_id : "-"}</td></tr>
          <tr><td>简介</td><td colspan="3">${esc(m.bio || "")}</td></tr>
        </tbody></table>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin:10px 0;">
          <button class="btn-violet" onclick="exportCurrentMember()">导出该对象</button>
          <span id="detailExportMsg" class="notice"></span>
        </div>
        <h4>婚姻关系</h4>
        <div style="display:grid;grid-template-columns:1fr 1fr 110px auto;gap:6px;align-items:start;margin-bottom:8px;">
          <input id="marriage_spouse_id" type="number" placeholder="配偶 ID" style="margin:0">
          <input id="marriage_spouse_name" placeholder="或配偶姓名" style="margin:0">
          <input id="marriage_year" type="number" placeholder="结婚年" style="margin:0">
          <button class="btn-primary" onclick="addMarriageForDetail()">登记</button>
        </div>
        <div id="marriageMsg" class="notice"></div>
        <div id="marriageList"></div>
        <h4>配偶</h4>${chips(d.spouses || [])}<h4>子女</h4>${chips(d.children || [])}`;
        openModal("detailModal");
        await loadMarriageList(state.currentDetailMemberId);
      } catch(e) { alert(e.message); }
    }
    function chips(rows) { return rows.length ? rows.map(x => `<span class="badge badge-collab" style="margin:3px;display:inline-block">${esc(x.name)} #${x.member_id}</span>`).join("") : "<div class='notice'>暂无记录</div>"; }
    function genderLabel(g) { return g === "M" ? "男" : g === "F" ? "女" : "未知"; }

    async function loadMarriageList(memberId) {
      const list = $("marriageList");
      if (!list) return;
      try {
        const rows = await api(`/api/members/${memberId}/marriages?${actorParam()}`);
        list.innerHTML = rows.length ? rows.map(m => `
          <div class="member-item">
            <div>
              <strong>${esc(m.spouse_name || "")}</strong>
              <div class="sub">#${m.spouse_id} · 结婚 ${m.marry_year || "-"} · 离婚 ${m.divorce_year || "-"}</div>
            </div>
            <div style="display:flex;gap:4px;align-items:center;">
              <input id="divorce_${m.marriage_id}" type="number" placeholder="离婚年" value="${m.divorce_year || ""}" style="width:86px;margin:0;padding:5px;">
              <button class="btn-sm" onclick="setDivorceYear(${m.marriage_id})">保存</button>
              <button class="btn-danger" onclick="deleteMarriageRecord(${m.marriage_id})">删除</button>
            </div>
          </div>
        `).join("") : "<div class='notice'>暂无婚姻记录</div>";
      } catch(e) {
        list.innerHTML = `<div class="notice" style="color:var(--danger)">${esc(e.message)}</div>`;
      }
    }
    async function exportCurrentMember() {
      const msg = $("detailExportMsg");
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在导出...";
        const result = await api(`/api/export/members/${state.currentDetailMemberId}?${actorParam()}`, {method:"POST"});
        msg.style.color = "var(--success)";
        msg.textContent = `导出成功：${result.output_dir}`;
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function addMarriageForDetail() {
      const msg = $("marriageMsg");
      const memberId = state.currentDetailMemberId;
      const spouseId = num($("marriage_spouse_id").value);
      const spouseName = $("marriage_spouse_name").value.trim();
      if (!spouseId && !spouseName) {
        msg.style.color = "var(--danger)";
        msg.textContent = "请输入配偶 ID 或配偶姓名";
        return;
      }
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在登记...";
        await api(`/api/marriages?${actorParam()}`, {
          method:"POST",
          body:JSON.stringify({member_id:memberId, spouse_id:spouseId, spouse_name:spouseName || null, marry_year:num($("marriage_year").value)})
        });
        msg.style.color = "var(--success)";
        msg.textContent = "婚姻登记成功";
        $("marriage_spouse_id").value = "";
        $("marriage_spouse_name").value = "";
        $("marriage_year").value = "";
        await loadMarriageList(memberId);
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function setDivorceYear(marriageId) {
      const msg = $("marriageMsg");
      try {
        await api(`/api/marriages/${marriageId}/divorce?${actorParam()}`, {
          method:"PUT",
          body:JSON.stringify({divorce_year:num($("divorce_" + marriageId).value)})
        });
        msg.style.color = "var(--success)";
        msg.textContent = "离婚年份已更新";
        await loadMarriageList(state.currentDetailMemberId);
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function deleteMarriageRecord(marriageId) {
      if (!confirm(`确认删除婚姻记录 #${marriageId}？`)) return;
      const msg = $("marriageMsg");
      try {
        await api(`/api/marriages/${marriageId}?${actorParam()}`, {method:"DELETE"});
        msg.style.color = "var(--success)";
        msg.textContent = "婚姻记录已删除";
        await loadMarriageList(state.currentDetailMemberId);
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }

    async function openAddMember() {
      $("memberModalTitle").textContent = "添加成员";
      clearMemberForm();
      fillClanSelects();
      openModal("memberModal");
    }
    async function openEditMember(id) {
      try {
        const d = await api(`/api/members/${id}/detail`);
        const m = d.member;
        $("memberModalTitle").textContent = `编辑成员 #${id}`;
        $("member_id").value = m.member_id;
        $("member_clan").value = m.clan_id;
        $("member_clan").disabled = true;
        $("member_name").value = m.name || "";
        $("member_gender").value = m.gender || "U";
        $("member_birth").value = m.birth_year || "";
        $("member_death").value = m.death_year || "";
        $("member_father_name").value = d.father ? d.father.name || "" : "";
        $("member_father_id").value = "";
        $("member_mother_name").value = d.mother ? d.mother.name || "" : "";
        $("member_mother_id").value = "";
        $("member_child_name").value = "";
        $("member_child_id").value = "";
        $("member_generation").value = m.generation_num || "";
        $("member_bio").value = m.bio || "";
        $("member_photo").value = "";
        $("memberMsg").textContent = "";
        openModal("memberModal");
      } catch(e) { alert(e.message); }
    }
    function clearMemberForm() {
      ["member_id","member_name","member_birth","member_death","member_father_name","member_father_id","member_mother_name","member_mother_id","member_child_name","member_child_id","member_generation","member_bio"].forEach(id => $(id).value = "");
      $("member_gender").value = "U";
      $("member_clan").disabled = false;
      $("member_photo").value = "";
      $("memberMsg").textContent = "";
    }
    async function resolveMemberByName(clanId, name, confirmId, role, gender) {
      const keyword = (name || "").trim();
      const explicitId = num(confirmId);
      if (!keyword && !explicitId) return null;
      let matches = [];
      if (explicitId) {
        try {
          const detail = await api(`/api/members/${explicitId}/detail`);
          const m = detail.member || {};
          if (Number(m.clan_id) !== Number(clanId)) throw new Error(`${role}确认 ID 不属于当前族谱`);
          if (gender && m.gender !== gender) throw new Error(`${role}性别不符合要求`);
          if (keyword && m.name !== keyword) throw new Error(`${role}确认 ID 对应姓名为 ${m.name}，不是 ${keyword}`);
          return Number(m.member_id);
        } catch(e) {
          throw new Error(`${role}确认 ID 无效：${e.message}`);
        }
      }
      matches = await api(`/api/members?clan_id=${encodeURIComponent(clanId)}&q=${encodeURIComponent(keyword)}`);
      matches = matches.filter(m => m.name === keyword && (!gender || m.gender === gender));
      if (!matches.length) throw new Error(`未找到${role}：${keyword}`);
      if (matches.length > 1) {
        const choices = matches.slice(0, 8).map(m => `${m.name} #${m.member_id}（${genderLabel(m.gender)}，第${m.generation_num || "-"}代）`).join("；");
        throw new Error(`${role}存在重名，请填写确认 ID：${choices}`);
      }
      return Number(matches[0].member_id);
    }
    async function attachChildIfNeeded(parentId, parentGender, clanId) {
      const childName = $("member_child_name").value.trim();
      const childConfirmId = $("member_child_id").value;
      if (!childName && !childConfirmId) return;
      if (!parentId) throw new Error("添加子女关系需要先保存当前成员");
      if (parentGender !== "M" && parentGender !== "F") throw new Error("当前成员性别未知，无法判断应作为父亲还是母亲");
      const childId = await resolveMemberByName(clanId, childName, childConfirmId, "子女", "");
      if (Number(childId) === Number(parentId)) throw new Error("子女不能是当前成员本人");
      const childDetail = await api(`/api/members/${childId}/detail`);
      const child = childDetail.member || {};
      const update = {
        name: child.name,
        gender: child.gender,
        birth_year: num(child.birth_year),
        death_year: num(child.death_year),
        father_id: num(child.father_id),
        mother_id: num(child.mother_id),
        generation_num: num(child.generation_num),
        bio: child.bio || ""
      };
      if (parentGender === "M") update.father_id = Number(parentId);
      if (parentGender === "F") update.mother_id = Number(parentId);
      await api(`/api/members/${childId}?${actorParam()}`, {method:"PUT", body:JSON.stringify(update)});
    }
    async function submitMember() {
      try {
        const id = $("member_id").value;
        const clanId = Number($("member_clan").value);
        const fatherId = await resolveMemberByName(clanId, $("member_father_name").value, $("member_father_id").value, "父亲", "M");
        const motherId = await resolveMemberByName(clanId, $("member_mother_name").value, $("member_mother_id").value, "母亲", "F");
        const payload = {clan_id:clanId, name:$("member_name").value, gender:$("member_gender").value, birth_year:num($("member_birth").value), death_year:num($("member_death").value), father_id:fatherId, mother_id:motherId, generation_num:num($("member_generation").value), bio:$("member_bio").value};
        const saved = await api(id ? `/api/members/${id}?${actorParam()}` : `/api/members?${actorParam()}`, {method:id ? "PUT" : "POST", body:JSON.stringify(payload)});
        const memberId = saved.member_id || (saved.member && saved.member.member_id) || id;
        if (!memberId) throw new Error("保存后未返回成员 ID，无法继续更新照片或子女关系");
        await attachChildIfNeeded(memberId, payload.gender, clanId);
        if ($("member_photo").files.length) {
          const form = new FormData(); form.append("photo", $("member_photo").files[0]);
          await api(`/api/members/${memberId}/photo?${actorParam()}`, {method:"POST", body:form});
        }
        closeModal("memberModal"); await search();
      } catch(e) { $("memberMsg").textContent = e.message; }
    }
    async function deleteMember(id) {
      if (!confirm(`确认删除成员 #${id}？`)) return;
      await api(`/api/members/${id}?${actorParam()}`, {method:"DELETE"});
      await search();
      renderEmptyTree();
    }

    async function openCollabModal(clanId) {
      $("collab_clan_id_label").textContent = clanId;
      $("grantMsg").textContent = "";
      openModal("collabModal");
      await loadCollaborators(clanId);
    }
    async function loadCollaborators(clanId) {
      const rows = await api(`/api/clans/${clanId}/collaborators`);
      $("collabList").innerHTML = rows.map(u => `<div class="member-item"><div>${esc(u.user_id)} · ${esc(u.username || "")}</div><button class="btn-danger" onclick="revokeAccess(${clanId}, '${esc(u.user_id)}')">撤销</button></div>`).join("") || "<div class='notice'>暂无协作者</div>";
    }
    async function grantAccess() {
      const clanId = Number($("collab_clan_id_label").textContent);
      const userId = $("grant_user_input").value.trim();
      if (!userId) {
        $("grantMsg").textContent = "请输入用户账号";
        return;
      }
      try {
        await api(`/api/collaborations?${actorParam()}`, {method:"POST", body:JSON.stringify({clan_id:clanId, user_id:userId})});
        $("grant_user_input").value = ""; $("grantMsg").textContent = "授权成功"; await loadCollaborators(clanId); await loadClans();
      } catch(e) { $("grantMsg").textContent = e.message; }
    }
    async function revokeAccess(clanId, userId) {
      try {
        await api(`/api/collaborations/revoke?${actorParam()}`, {method:"POST", body:JSON.stringify({clan_id:clanId, user_id:userId})});
        $("grantMsg").textContent = "撤销成功";
        await loadCollaborators(clanId); await loadClans();
      } catch(e) {
        $("grantMsg").textContent = e.message;
      }
    }

    function openImportModal() {
      $("import_title").value = "";
      $("import_surname").value = "";
      $("import_csv").value = "";
      $("importMsg").style.color = "#64748b";
      $("importMsg").textContent = "";
      openModal("importModal");
    }
    async function submitClanImport() {
      const msg = $("importMsg");
      const file = $("import_csv").files[0];
      if (!file) {
        msg.style.color = "var(--danger)";
        msg.textContent = "请选择 CSV 文件";
        return;
      }
      if (!$("import_title").value.trim()) {
        msg.style.color = "var(--danger)";
        msg.textContent = "请输入族谱标题";
        return;
      }
      const form = new FormData();
      form.append("csv_file", file);
      form.append("title", $("import_title").value.trim());
      form.append("surname", $("import_surname").value.trim());
      form.append("current_user_id", actorId());
      if (state.logSession) form.append("log_session", state.logSession);
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在导入...";
        const result = await api("/api/import/clan-csv", {method:"POST", body:form});
        msg.style.color = "var(--success)";
        msg.textContent = `导入成功：族谱 #${result.clan_id}，成员 ${result.members} 人，婚姻 ${result.marriages} 条`;
        await loadClans();
        await updateDashboard();
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function submitGeneratedImport() {
      if (actorId() !== "admin") {
        $("importMsg").style.color = "var(--danger)";
        $("importMsg").textContent = "只有 admin 可以导入生成脚本的整库数据";
        return;
      }
      if (!confirm("确认清空现有族谱、成员、婚姻和协作数据，并导入 generate_data.py 生成的数据？")) return;
      try {
        $("importMsg").style.color = "#64748b";
        $("importMsg").textContent = "正在导入生成数据...";
        const result = await api(`/api/import/generated?${actorParam()}`, {method:"POST"});
        $("importMsg").style.color = "var(--success)";
        $("importMsg").textContent = `导入完成：${result.members_file || ""}`;
        await loadClans();
        await updateDashboard();
        resetSearchPanel();
        renderEmptyTree();
      } catch(e) {
        $("importMsg").style.color = "var(--danger)";
        $("importMsg").textContent = e.message;
      }
    }
    async function submitBundleImport() {
      const file = $("import_bundle").files[0];
      const msg = $("importMsg");
      if (actorId() !== "admin") {
        msg.style.color = "var(--danger)";
        msg.textContent = "只有 admin 可以导入导出包";
        return;
      }
      if (!file) {
        msg.style.color = "var(--danger)";
        msg.textContent = "请选择导出目录中的 import_bundle.json";
        return;
      }
      if (!confirm("导入会在发现任何重复 ID、账号或协作关系时停止。确认继续？")) return;
      const form = new FormData();
      form.append("bundle_file", file);
      form.append("current_user_id", actorId());
      if (state.logSession) form.append("log_session", state.logSession);
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在导入导出包...";
        const result = await api("/api/import/bundle", {method:"POST", body:form});
        msg.style.color = "var(--success)";
        msg.textContent = `导入完成：users ${result.inserted.users || 0}，族谱 ${result.inserted.genealogies || 0}，成员 ${result.inserted.members || 0}`;
        await loadClans();
        await updateDashboard();
        resetSearchPanel();
        renderEmptyTree();
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function openExportModal() {
      await loadClans();
      $("exportMsg").style.color = "#64748b";
      $("exportMsg").textContent = "";
      $("exportClanList").innerHTML = state.clans.map(c => `
        <label style="display:flex;gap:8px;align-items:center;margin:6px 0;color:#1e293b;">
          <input type="checkbox" class="export-clan-check" value="${c.clan_id}" style="width:auto;margin:0">
          <span>#${c.clan_id} ${esc(c.title || "")} · ${esc(c.surname || "-")}</span>
        </label>
      `).join("") || "<div class='notice'>暂无族谱可导出</div>";
      openModal("exportModal");
    }
    async function submitClanExport() {
      const ids = Array.from(document.querySelectorAll(".export-clan-check:checked")).map(x => Number(x.value));
      const msg = $("exportMsg");
      if (!ids.length) {
        msg.style.color = "var(--danger)";
        msg.textContent = "请选择至少一个族谱";
        return;
      }
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在导出...";
        const result = await api(`/api/export/clans?${actorParam()}`, {method:"POST", body:JSON.stringify({clan_ids:ids})});
        msg.style.color = "var(--success)";
        msg.textContent = `导出成功：${result.output_dir}`;
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }
    async function submitDatabaseExport() {
      const msg = $("exportMsg");
      if (actorId() !== "admin") {
        msg.style.color = "var(--danger)";
        msg.textContent = "只有 admin 可以导出整个数据库";
        return;
      }
      try {
        msg.style.color = "#64748b";
        msg.textContent = "正在导出整个数据库...";
        const result = await api(`/api/export/database?${actorParam()}`, {method:"POST"});
        msg.style.color = "var(--success)";
        msg.textContent = `导出成功：${result.output_dir}`;
      } catch(e) {
        msg.style.color = "var(--danger)";
        msg.textContent = e.message;
      }
    }

    function openQueryModal() { fillClanSelects(); switchQueryTab("spouse"); openModal("queryModal"); }
    function switchQueryTab(tab) {
      ["spouse","ancestors","longevity","singles","early","descendants"].forEach(t => {
        $("qp-" + t).style.display = t === tab ? "block" : "none";
        $("qt-" + t).classList.toggle("active", t === tab);
      });
    }
    function table(headers, rows, empty) {
      if (!rows.length) return `<p class="notice">${empty}</p>`;
      return `<table class="query-result-table"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c == null || c === "" ? "—" : c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }
    function queryMemberParams(type, label) {
      const nameEl = $(`q-${type}-name`);
      const idEl = $(`q-${type}-id`);
      const name = nameEl ? nameEl.value.trim() : "";
      const explicitId = idEl ? num(idEl.value) : null;
      if (explicitId) {
        const parts = [`member_id=${encodeURIComponent(explicitId)}`];
        if (name) parts.push(`name=${encodeURIComponent(name)}`);
        return parts.join("&");
      }
      if (!name) throw new Error(`请输入${label}姓名`);
      return `name=${encodeURIComponent(name)}`;
    }
    async function runQuery(type) {
      const out = $("qr-" + type);
      out.innerHTML = "<p class='notice'>查询中...</p>";
      try {
        let data;
        if (type === "spouse") {
          data = await api(`/api/query/spouse_children?${queryMemberParams("spouse", "成员")}`);
          out.innerHTML = "<h4>配偶</h4>" + table(["姓名","性别","出生年"], data.spouses.map(s=>[s.name, genderLabel(s.gender), s.birth_year]), "暂无配偶") + "<h4>子女</h4>" + table(["姓名","性别","出生年","世代"], data.children.map(c=>[c.name, genderLabel(c.gender), c.birth_year, c.generation_num]), "暂无子女");
        } else if (type === "ancestors") {
          data = await api(`/api/query/ancestors?${queryMemberParams("ancestors", "成员")}`);
          out.innerHTML = table(["姓名","性别","出生年","世代","距离"], data.map(r=>[r.name, genderLabel(r.gender), r.birth_year, r.generation_num, r.generations_above]), "无祖先数据");
        } else if (type === "longevity") {
          data = await api(`/api/query/longevity?clan_id=${$("q-longevity-clan").value}`);
          out.innerHTML = table(["世代","平均寿命","人数"], data.map(r=>[r.generation_num, r.avg_lifespan, r.member_count]), "暂无数据");
        } else if (type === "singles") {
          const c = $("q-singles-clan").value;
          data = await api(`/api/query/singles${Number(c) ? "?clan_id=" + c : ""}`);
          out.innerHTML = table(["ID","姓名","出生年","年龄","族谱"], data.map(r=>[r.member_id, r.name, r.birth_year, r.age, r.clan_id]), "无符合条件成员");
        } else if (type === "early") {
          const c = $("q-early-clan").value;
          data = await api(`/api/query/early_birth${Number(c) ? "?clan_id=" + c : ""}`);
          out.innerHTML = table(["ID","姓名","族谱","世代","出生年","本代均值","提前"], data.map(r=>[r.member_id, r.name, r.clan_id, r.generation_num, r.birth_year, r.avg_birth_year, r.years_before_avg]), "无符合条件成员");
        } else if (type === "descendants") {
          data = await api(`/api/query/great_grandchildren?${queryMemberParams("descendants", "成员")}`);
          out.innerHTML = table(["ID","姓名","性别","世代","出生年"], data.map(r=>[r.member_id, r.name, genderLabel(r.gender), r.generation_num, r.birth_year]), "无第四代后代");
        }
      } catch(e) { out.innerHTML = `<p style="color:var(--danger);font-size:12px;">${esc(e.message)}</p>`; }
    }

    function openModal(id) { $(id).classList.add("active"); }
    function closeModal(id) { $(id).classList.remove("active"); }
    $("nameInput").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
  </script>
</body>
</html>
"""
