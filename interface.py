def render_app() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Totem 族谱管理系统</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    :root {
      --primary: #2563eb;
      --primary-dark: #1d4ed8;
      --bg: #f1f5f9;
      --card: #ffffff;
      --line: #e2e8f0;
      --ink: #1e293b;
      --muted: #64748b;
      --soft: #f8fafc;
      --danger: #ef4444;
      --success: #10b981;
      --violet: #7c3aed;
      --cyan: #0891b2;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
      height: 100vh;
      overflow: hidden;
      letter-spacing: 0;
    }
    button, input, select, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      outline: none;
    }
    input, select, textarea {
      width: 100%;
      padding: 10px;
      background: white;
      color: var(--ink);
      font-size: 13px;
      margin-bottom: 10px;
    }
    textarea { min-height: 76px; resize: vertical; }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 3px;
    }
    button {
      cursor: pointer;
      border: none;
      color: var(--ink);
      background: white;
      transition: 0.18s ease;
      white-space: nowrap;
    }
    button:hover { transform: translateY(-1px); }
    .btn-primary {
      background: var(--primary);
      color: white;
      height: 38px;
      padding: 0 15px;
      border-radius: 6px;
      font-weight: 600;
    }
    .btn-primary:hover { background: var(--primary-dark); }
    .btn-add {
      width: 100%;
      background: var(--success);
      color: white;
      padding: 12px;
      border-radius: 6px;
      font-weight: 700;
    }
    .btn-danger {
      background: var(--danger);
      color: white;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
    }
    .btn-sm {
      background: var(--primary);
      color: white;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
    }
    .btn-ghost {
      background: white;
      border: 1px solid var(--line);
      color: var(--muted);
      border-radius: 4px;
      padding: 5px 10px;
      font-size: 12px;
    }

    #loginOverlay {
      position: fixed;
      inset: 0;
      background: #0f172a;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      padding: 24px;
    }
    .login-card {
      width: 330px;
      background: white;
      padding: 38px;
      border-radius: 12px;
      box-shadow: 0 20px 25px -5px rgba(0,0,0,0.3);
    }
    .login-card h2 {
      text-align: center;
      color: var(--primary);
      margin: 0 0 20px;
      font-size: 24px;
    }
    .login-card p {
      margin: 12px 0 0;
      text-align: center;
      font-size: 12px;
      color: var(--muted);
    }

    #adminContent {
      display: none;
      height: 100vh;
      flex-direction: column;
    }
    .navbar {
      background: white;
      padding: 0 24px;
      height: 60px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
      flex-shrink: 0;
    }
    .brand {
      font-weight: 800;
      color: var(--primary);
      font-size: 1.2rem;
    }
    .nav-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      min-width: 0;
    }
    .mode-switch {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: #475569;
      border: 1px solid var(--line);
      padding: 4px 10px;
      border-radius: 20px;
      background: var(--soft);
      user-select: none;
    }
    .mode-switch input {
      width: auto;
      margin: 0;
    }
    #clanSelect {
      width: 190px;
      margin: 0;
      height: 34px;
      padding: 6px 8px;
    }
    .main-container {
      flex: 1;
      display: flex;
      gap: 15px;
      padding: 15px;
      overflow: hidden;
    }
    .side-panel {
      width: 370px;
      display: flex;
      flex-direction: column;
      gap: 15px;
      height: 100%;
      overflow: hidden;
      flex-shrink: 0;
    }
    .viz-panel {
      flex: 1;
      min-width: 0;
      background: white;
      border-radius: 12px;
      height: 100%;
      position: relative;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.08);
    }
    .card {
      background: white;
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
      min-width: 0;
    }
    .card-title {
      margin: 0 0 10px;
      font-size: 14px;
      color: var(--ink);
      font-weight: 700;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-top: 8px;
    }
    .stat-box {
      background: var(--soft);
      border: 1px solid #f1f5f9;
      border-radius: 8px;
      padding: 8px;
      min-height: 58px;
    }
    .stat-num { font-size: 20px; font-weight: 800; color: var(--primary); }
    .stat-label { color: #94a3b8; font-size: 11px; margin-top: 2px; }
    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 10px;
    }
    .tabs button {
      flex: 1;
      padding: 7px 4px;
      border-radius: 6px;
      background: #e2e8f0;
      color: #475569;
      font-size: 12px;
    }
    .tabs button.active {
      background: var(--primary);
      color: white;
      font-weight: 700;
    }
    .panel-view {
      display: none;
      flex: 1;
      min-height: 0;
      overflow: hidden;
      flex-direction: column;
    }
    .panel-view.active { display: flex; }
    .row { display: flex; gap: 8px; align-items: center; }
    .search-results {
      flex: 1;
      overflow-y: auto;
      margin-top: 10px;
      padding-right: 2px;
    }
    .member-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      padding: 10px 12px;
      border: 1px solid #f1f5f9;
      margin-bottom: 6px;
      border-radius: 8px;
      transition: 0.2s;
      background: white;
    }
    .member-item:hover {
      background: #f8fbff;
      border-color: var(--primary);
    }
    .member-main {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      flex: 1;
    }
    .avatar {
      width: 42px;
      height: 42px;
      border-radius: 8px;
      object-fit: cover;
      border: 2px solid var(--line);
      background: #f1f5f9;
      flex-shrink: 0;
    }
    .member-name { font-weight: 700; font-size: 13px; color: var(--ink); }
    .member-sub { color: #94a3b8; font-size: 11px; margin-top: 2px; }
    .hash {
      max-width: 140px;
      display: inline-block;
      overflow: hidden;
      text-overflow: ellipsis;
      vertical-align: bottom;
      white-space: nowrap;
      font-family: Consolas, monospace;
      font-size: 11px;
      color: #94a3b8;
    }
    .form-scroll {
      overflow-y: auto;
      padding-right: 2px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0 8px;
    }
    .form-grid .full { grid-column: 1 / -1; }
    .notice {
      min-height: 20px;
      font-size: 12px;
      color: var(--muted);
      margin: 7px 0;
    }
    .query-result {
      flex: 1;
      overflow-y: auto;
      border-top: 1px solid #f1f5f9;
      margin-top: 10px;
      padding-top: 8px;
      font-size: 12px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      border: 1px solid #dbeafe;
      background: #eff6ff;
      color: #1e40af;
      border-radius: 999px;
      padding: 5px 9px;
      margin: 3px;
      font-size: 12px;
    }
    .path {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }
    .tree-toolbar {
      height: 48px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      border-bottom: 1px solid #f1f5f9;
      background: white;
    }
    .tree-title {
      font-weight: 800;
      color: var(--ink);
      font-size: 15px;
    }
    #treePreview {
      height: calc(100% - 48px);
      width: 100%;
      overflow: hidden;
      padding: 0;
      background:
        linear-gradient(#f8fafc 1px, transparent 1px),
        linear-gradient(90deg, #f8fafc 1px, transparent 1px);
      background-size: 28px 28px;
    }
    .tree-root {
      display: flex;
      gap: 28px;
      align-items: flex-start;
    }
    .node {
      min-width: 175px;
      border: 1px solid #dbeafe;
      border-left: 5px solid var(--primary);
      border-radius: 10px;
      padding: 10px 12px;
      background: white;
      margin: 8px 0;
      box-shadow: 0 4px 10px rgba(37,99,235,0.08);
    }
    .node strong { color: var(--ink); font-size: 14px; }
    .node .meta { color: #94a3b8; font-size: 11px; margin-top: 4px; }
    .children {
      margin-left: 25px;
      border-left: 1px dashed #bfdbfe;
      padding-left: 16px;
    }
    .user-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .user-table th {
      color: white;
      background: var(--primary);
      text-align: left;
      padding: 7px;
    }
    .user-table td {
      border-bottom: 1px solid #f1f5f9;
      padding: 7px;
      color: #475569;
    }
    @media (max-width: 920px) {
      body { overflow: auto; height: auto; }
      #adminContent { height: auto; min-height: 100vh; }
      .navbar { height: auto; padding: 12px; gap: 10px; align-items: flex-start; flex-direction: column; }
      .nav-actions { flex-wrap: wrap; width: 100%; }
      .main-container { flex-direction: column; height: auto; overflow: visible; }
      .side-panel { width: 100%; height: auto; }
      .viz-panel { min-height: 560px; }
    }
  </style>
</head>
<body>
  <div id="loginOverlay">
    <form class="login-card" id="loginForm">
      <h2>系统登录</h2>
      <input id="loginUser" value="admin" placeholder="账号" autocomplete="username">
      <input id="loginPassword" type="password" value="123456" placeholder="密码" autocomplete="current-password">
      <div class="notice" id="loginMessage" style="text-align:center;color:var(--danger)"></div>
      <button class="btn-add" type="submit">进入系统</button>
      <p>默认演示账号 admin / 123456</p>
    </form>
  </div>

  <div id="adminContent">
    <div class="navbar">
      <div class="brand">族谱管理系统</div>
      <div class="nav-actions">
        <label class="mode-switch" title="显示当前连接信息">
          <input type="checkbox" id="perfModeToggle">
          <span>Totem 模式</span>
        </label>
        <select id="clanSelect" aria-label="族谱"></select>
        <button class="btn-ghost" data-panel="members">成员查询</button>
        <button class="btn-ghost" data-panel="form">添加成员</button>
        <button class="btn-ghost" data-panel="queries">统计查询</button>
        <button class="btn-ghost" data-panel="users">协作者</button>
        <button class="btn-ghost" id="refreshBtn">刷新</button>
      </div>
    </div>

    <div class="main-container">
      <div class="side-panel">
        <div class="card">
          <h4 class="card-title">数据概览</h4>
          <div id="chart-clan-label" style="font-size:11px;color:#94a3b8;margin-bottom:4px;text-align:center;">当前族谱统计</div>
          <div id="stats-chart" style="height:130px"></div>
          <div class="stats-grid">
            <div class="stat-box"><div class="stat-num" id="totalMembers">0</div><div class="stat-label">成员总数</div></div>
            <div class="stat-box"><div class="stat-num" id="genderRatio">0/0</div><div class="stat-label">男 / 女 / 未知</div></div>
            <div class="stat-box"><div class="stat-num" id="collabCount">0</div><div class="stat-label">协作者</div></div>
          </div>
          <div id="oldestMember" class="notice">暂无年长成员数据</div>
        </div>

        <div class="card" style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
          <div class="tabs">
            <button class="active" data-tab="membersPanel">成员查询</button>
            <button data-tab="formPanel">成员编辑</button>
            <button data-tab="queriesPanel">关系查询</button>
            <button data-tab="usersPanel">协作</button>
          </div>

          <section id="membersPanel" class="panel-view active">
            <div class="row">
              <input id="memberSearch" placeholder="输入姓名或编号查询..." style="margin:0">
              <button class="btn-primary" id="searchBtn">查询</button>
            </div>
            <div id="search-msg" class="notice"></div>
            <div class="search-results" id="memberRows"></div>
          </section>

          <section id="formPanel" class="panel-view">
            <h4 class="card-title" id="memberFormTitle">新增成员</h4>
            <form id="memberForm" class="form-scroll">
              <input type="hidden" id="memberId">
              <div class="form-grid">
                <label>姓名<input id="memberName" required></label>
                <label>性别<select id="memberGender"><option value="M">男</option><option value="F">女</option><option value="U">未知</option></select></label>
                <label>出生年<input id="birthYear" type="number"></label>
                <label>死亡年<input id="deathYear" type="number"></label>
                <label>父亲 ID<input id="fatherId" type="number"></label>
                <label>母亲 ID<input id="motherId" type="number"></label>
                <label>世代<input id="generationNum" type="number"></label>
                <label class="full">照片<input id="memberPhoto" type="file" accept="image/*"></label>
                <label class="full">简介<textarea id="memberBio"></textarea></label>
              </div>
              <div class="row">
                <button class="btn-add" type="submit">保存成员</button>
                <button class="btn-ghost" type="button" id="resetMemberForm">清空</button>
              </div>
              <div class="notice">照片只计算 SHA-256 存入数据库，不保存图片文件。</div>
            </form>
          </section>

          <section id="queriesPanel" class="panel-view">
            <h4 class="card-title">人物祖先查询</h4>
            <div class="row">
              <input id="ancestorId" type="number" placeholder="成员 ID" style="margin:0">
              <button class="btn-primary" id="ancestorBtn">查询</button>
            </div>
            <div id="ancestorResult" class="query-result" style="max-height:150px"></div>
            <h4 class="card-title" style="margin-top:12px">亲缘关系通路</h4>
            <input id="sourceId" type="number" placeholder="起点成员 ID">
            <input id="targetId" type="number" placeholder="目标成员 ID">
            <button class="btn-primary" id="relationBtn" style="width:100%">查询亲缘关系</button>
            <div id="relationResult" class="query-result path"></div>
          </section>

          <section id="usersPanel" class="panel-view">
            <h4 class="card-title">邀请编辑</h4>
            <div class="row">
              <input id="inviteUser" placeholder="输入用户账号，例如 editor" style="margin:0">
              <button id="inviteBtn" class="btn-primary">邀请</button>
            </div>
            <p class="notice" id="inviteMessage"></p>
            <h4 class="card-title">用户列表</h4>
            <div style="overflow:auto">
              <table class="user-table">
                <thead><tr><th>ID</th><th>账号</th><th>用户名</th></tr></thead>
                <tbody id="userRows"></tbody>
              </table>
            </div>
          </section>
        </div>
      </div>

      <div class="viz-panel">
        <div class="tree-toolbar">
          <div>
            <div class="tree-title">树形预览</div>
            <div class="member-sub" id="currentUser">未登录</div>
          </div>
          <button class="btn-primary" onclick="loadTree()">全族谱</button>
        </div>
        <div id="treePreview"></div>
      </div>
    </div>
  </div>

  <script>
    const state = { clanId: 1, members: [], dashboard: null, treeChart: null };
    const $ = (id) => document.getElementById(id);
    const api = async (url, options = {}) => {
      const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
      if (!res.ok) throw new Error((await res.json()).detail || "请求失败");
      if (res.status === 204) return null;
      return res.json();
    };
    const num = (value) => value === "" ? null : Number(value);

    $("loginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await api("/api/login", { method: "POST", body: JSON.stringify({ user_id: $("loginUser").value, password: $("loginPassword").value }) });
        $("currentUser").textContent = `${data.user.username || data.user.user_id} | 已登录`;
        $("loginOverlay").style.display = "none";
        $("adminContent").style.display = "flex";
        await boot();
      } catch (error) {
        $("loginMessage").textContent = error.message;
      }
    });

    document.querySelectorAll(".tabs button").forEach((button) => {
      button.addEventListener("click", () => switchTab(button.dataset.tab));
    });
    document.querySelectorAll("[data-panel]").forEach((button) => {
      button.addEventListener("click", () => {
        const map = { members: "membersPanel", form: "formPanel", queries: "queriesPanel", users: "usersPanel" };
        switchTab(map[button.dataset.panel]);
      });
    });

    function switchTab(tabId) {
      document.querySelectorAll(".tabs button").forEach((item) => item.classList.toggle("active", item.dataset.tab === tabId));
      document.querySelectorAll(".panel-view").forEach((view) => view.classList.toggle("active", view.id === tabId));
    }

    $("refreshBtn").addEventListener("click", () => loadAll());
    $("clanSelect").addEventListener("change", () => { state.clanId = Number($("clanSelect").value); loadAll(); });
    $("searchBtn").addEventListener("click", () => loadMembers());
    $("memberSearch").addEventListener("keydown", (event) => { if (event.key === "Enter") loadMembers(); });
    $("resetMemberForm").addEventListener("click", resetMemberForm);
    $("ancestorBtn").addEventListener("click", loadAncestors);
    $("relationBtn").addEventListener("click", loadRelationship);
    $("inviteBtn").addEventListener("click", inviteUser);

    $("memberForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        clan_id: state.clanId,
        name: $("memberName").value,
        gender: $("memberGender").value,
        birth_year: num($("birthYear").value),
        death_year: num($("deathYear").value),
        father_id: num($("fatherId").value),
        mother_id: num($("motherId").value),
        generation_num: num($("generationNum").value),
        bio: $("memberBio").value
      };
      const id = $("memberId").value;
      const saved = await api(id ? `/api/members/${id}` : "/api/members", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
      if ($("memberPhoto").files.length) {
        await uploadMemberPhoto(saved.member_id || id, $("memberPhoto").files[0]);
      }
      resetMemberForm();
      switchTab("membersPanel");
      await loadAll();
    });

    async function boot() {
      const clans = await api("/api/clans");
      $("clanSelect").innerHTML = clans.map((clan) => `<option value="${clan.clan_id}">${clan.title || clan.surname || clan.clan_id}</option>`).join("");
      state.clanId = Number($("clanSelect").value || 1);
      await loadAll();
    }

    async function loadAll() {
      await Promise.all([loadDashboard(), loadMembers(), loadTree(), loadUsers()]);
    }

    async function loadDashboard() {
      const data = await api(`/api/dashboard?clan_id=${state.clanId}`);
      state.dashboard = data;
      $("totalMembers").textContent = data.total_members;
      $("genderRatio").textContent = `${data.gender.M || 0}/${data.gender.F || 0}/${data.gender.U || 0}`;
      $("collabCount").textContent = data.collaborators;
      $("oldestMember").textContent = data.oldest ? `年纪最长：${data.oldest.name}，${data.oldest.birth_year || "生年未知"}，第 ${data.oldest.generation_num || "?"} 代` : "暂无年长成员数据";
      renderStatsChart(data);
    }

    function renderStatsChart(data) {
      if (!window.echarts) return;
      const chart = echarts.init($("stats-chart"));
      chart.setOption({
        tooltip: { trigger: "item" },
        series: [{
          type: "pie",
          radius: ["45%", "72%"],
          avoidLabelOverlap: true,
          label: { fontSize: 11 },
          data: [
            { value: data.gender.M || 0, name: "男" },
            { value: data.gender.F || 0, name: "女" },
            { value: data.gender.U || 0, name: "未知" }
          ],
          color: ["#2563eb", "#ec4899", "#94a3b8"]
        }]
      });
    }

    async function loadMembers() {
      state.members = await api(`/api/members?clan_id=${state.clanId}&q=${encodeURIComponent($("memberSearch").value)}`);
      $("search-msg").textContent = `共找到 ${state.members.length} 位成员`;
      $("memberRows").innerHTML = state.members.map((member) => `
        <div class="member-item">
          <div class="member-main">
            <img class="avatar" src="/resources/defaultpic.jpg" alt="">
            <div style="min-width:0">
              <div class="member-name">${member.name}</div>
              <div class="member-sub">#${member.member_id} · ${member.gender_label || member.gender} · 第 ${member.generation_num || "?"} 代</div>
              <div class="member-sub">${member.birth_year || "生年未知"}${member.death_year ? " - " + member.death_year : ""} · 父/母 ${member.father_id || "-"} / ${member.mother_id || "-"}</div>
              <div class="hash" title="${member.id_pic || ""}">${member.id_pic ? "照片 " + member.id_pic : "默认照片"}</div>
            </div>
          </div>
          <div class="row">
            <button class="btn-sm" onclick="loadTree(${member.member_id})">查看</button>
            <button class="btn-sm" onclick="editMember(${member.member_id})">编辑</button>
            <button class="btn-danger" onclick="deleteMember(${member.member_id})">删除</button>
          </div>
        </div>`).join("") || "<div class='notice'>暂无成员</div>";
    }

    window.editMember = (id) => {
      const member = state.members.find((item) => Number(item.member_id) === Number(id));
      if (!member) return;
      $("memberFormTitle").textContent = `编辑成员 #${id}`;
      $("memberId").value = member.member_id;
      $("memberName").value = member.name || "";
      $("memberGender").value = member.gender || "U";
      $("birthYear").value = member.birth_year || "";
      $("deathYear").value = member.death_year || "";
      $("fatherId").value = member.father_id || "";
      $("motherId").value = member.mother_id || "";
      $("generationNum").value = member.generation_num || "";
      $("memberBio").value = member.bio || "";
      $("memberPhoto").value = "";
      switchTab("formPanel");
    };

    async function uploadMemberPhoto(memberId, file) {
      const form = new FormData();
      form.append("photo", file);
      const res = await fetch(`/api/members/${memberId}/photo`, { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json()).detail || "照片上传失败");
      return res.json();
    }

    window.deleteMember = async (id) => {
      if (!confirm(`确认删除成员 #${id}？`)) return;
      await api(`/api/members/${id}`, { method: "DELETE" });
      await loadAll();
    };

    function resetMemberForm() {
      $("memberForm").reset();
      $("memberId").value = "";
      $("memberFormTitle").textContent = "新增成员";
    }

    async function loadTree(rootId) {
      const rootParam = rootId ? `&root_id=${rootId}` : "";
      const data = await api(`/api/tree?clan_id=${state.clanId}${rootParam}`);
      renderTreeChart(data.roots || [], rootId);
    }

    function renderTreeChart(roots, rootId) {
      if (!window.echarts) {
        $("treePreview").innerHTML = "<p class='notice' style='padding:18px'>ECharts 未加载，无法绘制动态图。</p>";
        return;
      }
      if (!roots.length) {
        if (state.treeChart) state.treeChart.clear();
        $("treePreview").innerHTML = "<p class='notice' style='padding:18px'>暂无树形数据</p>";
        return;
      }
      if (!state.treeChart) {
        $("treePreview").innerHTML = "";
        state.treeChart = echarts.init($("treePreview"));
        window.addEventListener("resize", () => state.treeChart && state.treeChart.resize());
      } else if (state.treeChart.isDisposed && state.treeChart.isDisposed()) {
        $("treePreview").innerHTML = "";
        state.treeChart = echarts.init($("treePreview"));
      }
      const data = roots.map((root) => toChartNode(root, 0));
      state.treeChart.setOption({
        tooltip: {
          trigger: "item",
          triggerOn: "mousemove",
          formatter: (params) => {
            const d = params.data || {};
            return `<b>${d.name}</b><br/>成员ID：${d.member_id || "-"}<br/>世代：${d.generation || "-"}<br/>生年：${d.birth_year || "-"}`;
          }
        },
        series: [{
          type: "tree",
          data: data,
          top: "4%",
          left: "8%",
          bottom: "4%",
          right: "18%",
          symbol: "roundRect",
          symbolSize: [86, 28],
          orient: "LR",
          roam: true,
          expandAndCollapse: true,
          initialTreeDepth: rootId ? 3 : 4,
          animationDuration: 450,
          animationDurationUpdate: 650,
          label: {
            position: "inside",
            verticalAlign: "middle",
            align: "center",
            color: "#ffffff",
            fontSize: 12,
            overflow: "truncate",
            width: 76
          },
          leaves: {
            label: {
              position: "right",
              verticalAlign: "middle",
              align: "left",
              color: "#334155"
            }
          },
          itemStyle: {
            color: "#2563eb",
            borderColor: "#1d4ed8",
            borderWidth: 1
          },
          lineStyle: {
            color: "#93c5fd",
            width: 1.5,
            curveness: 0.35
          },
          emphasis: { focus: "descendant" }
        }]
      }, true);
      setTimeout(() => { try { state.treeChart.resize(); } catch (e) {} }, 50);
    }

    function toChartNode(node, depth) {
      const children = node.children || [];
      return {
        name: node.name || `#${node.member_id}`,
        member_id: node.member_id,
        generation: node.generation_num,
        birth_year: node.birth_year,
        collapsed: depth >= 3 && children.length > 0,
        itemStyle: { color: node.gender === "F" ? "#ec4899" : (node.gender === "U" ? "#94a3b8" : "#2563eb") },
        children: children.map((child) => toChartNode(child, depth + 1))
      };
    }

    async function loadAncestors() {
      const id = $("ancestorId").value;
      if (!id) return;
      const rows = await api(`/api/members/${id}/ancestors`);
      $("ancestorResult").innerHTML = rows.map((member) => `<span class="chip">${member.name} · 向上 ${member.generations_above} 代</span>`).join("") || "<p class='notice'>未找到祖先记录</p>";
    }

    async function loadRelationship() {
      const source = $("sourceId").value;
      const target = $("targetId").value;
      if (!source || !target) return;
      const data = await api(`/api/members/${source}/relationship?target_id=${target}`);
      $("relationResult").innerHTML = data.path.map((member, index) => `${index ? "<span>→</span>" : ""}<span class="chip">${member.name}</span>`).join("") || "<p class='notice'>未找到通路</p>";
    }

    async function loadUsers() {
      const users = await api("/api/users");
      $("userRows").innerHTML = users.map((user) => `<tr><td>${user.id}</td><td>${user.user_id}</td><td>${user.username || ""}</td></tr>`).join("");
    }

    async function inviteUser() {
      try {
        const data = await api("/api/invitations", { method: "POST", body: JSON.stringify({ clan_id: state.clanId, user_id: $("inviteUser").value }) });
        $("inviteMessage").textContent = data.message;
        await loadDashboard();
      } catch (error) {
        $("inviteMessage").textContent = error.message;
      }
    }
  </script>
</body>
</html>"""
