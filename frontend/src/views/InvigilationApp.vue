<template>
  <div class="inv-app">
    <Toast />

    <div v-if="!authenticated" class="login-page">
      <div class="login-card">
        <div class="brand-mark"><i class="pi pi-calendar-clock"></i></div>
        <h1>智能监考排班系统</h1>
        <p>甲监 · 乙监 · 流动监考 · 巡考</p>
        <form @submit.prevent="login" class="login-form">
          <label>用户名</label>
          <InputText v-model="loginForm.username" autocomplete="username" />
          <label>密码</label>
          <Password v-model="loginForm.password" :feedback="false" toggleMask autocomplete="current-password" />
          <div v-if="loginError" class="error-box">{{ loginError }}</div>
          <Button type="submit" label="登录" icon="pi pi-sign-in" :loading="loginLoading" />
        </form>
      </div>
    </div>

    <template v-else>
      <header class="topbar">
        <div>
          <h1>智能监考排班系统</h1>
          <p>本地数据 · 全局约束优化 · 支持锁定与局部重排</p>
        </div>
        <div class="topbar-actions">
          <select v-model="selectedBatchId" class="batch-select" @change="loadBatch">
            <option value="">请选择考试批次</option>
            <option v-for="batch in batches" :key="batch.id" :value="String(batch.id)">
              {{ batch.name }}{{ batch.academic_year ? ` · ${batch.academic_year}` : '' }}
            </option>
          </select>
          <Button label="原系统" icon="pi pi-home" severity="secondary" outlined @click="goHome" />
          <Button label="退出" icon="pi pi-sign-out" severity="secondary" text @click="logout" />
        </div>
      </header>

      <main class="workspace">
        <section class="summary-grid">
          <div class="summary-card">
            <span>考试时段</span><strong>{{ overview?.summary?.session_count ?? 0 }}</strong>
          </div>
          <div class="summary-card">
            <span>考场考试</span><strong>{{ overview?.summary?.exam_room_count ?? 0 }}</strong>
          </div>
          <div class="summary-card">
            <span>监考岗位</span><strong>{{ overview?.summary?.duty_positions ?? 0 }}</strong>
          </div>
          <div class="summary-card">
            <span>参与人员</span><strong>{{ teachers.filter(t => t.active).length }}</strong>
          </div>
        </section>

        <nav class="section-tabs">
          <button v-for="item in tabs" :key="item.key" :class="{ active: activeTab === item.key }" @click="activeTab = item.key">
            <i :class="item.icon"></i>{{ item.label }}
          </button>
        </nav>

        <section v-if="activeTab === 'data'" class="panel-stack">
          <div class="panel">
            <div class="panel-title">
              <div><h2>考试批次</h2><p>先创建一次考试任务，再导入该批次的考试安排。</p></div>
            </div>
            <div class="create-row">
              <InputText v-model="newBatch.name" placeholder="例如：2026-2027 第一学期期末考试" />
              <InputText v-model="newBatch.academic_year" placeholder="学年，如 2026-2027" />
              <InputText v-model="newBatch.term" placeholder="学期，如 第一学期" />
              <Button label="创建批次" icon="pi pi-plus" @click="createBatch" :disabled="!newBatch.name.trim()" />
            </div>
            <DataTable :value="batches" size="small" stripedRows class="mt-16">
              <Column field="name" header="批次名称" />
              <Column field="academic_year" header="学年" />
              <Column field="term" header="学期" />
              <Column field="status" header="状态" />
              <Column header="操作" style="width: 110px">
                <template #body="{ data }">
                  <Button label="选择" size="small" text @click="selectBatch(data.id)" />
                </template>
              </Column>
            </DataTable>
          </div>

          <div class="import-grid">
            <div class="panel import-card">
              <div class="import-icon"><i class="pi pi-users"></i></div>
              <h3>教师与工作人员</h3>
              <p>导入工号、部门、四类岗位资格、场次上限和不可用时间。</p>
              <div class="button-row">
                <Button label="下载人员模板" icon="pi pi-download" severity="secondary" outlined @click="downloadTemplate('teacher-template', '监考人员模板.xlsx')" />
                <label class="upload-label">
                  <i class="pi pi-upload"></i> 导入人员 Excel
                  <input type="file" accept=".xlsx" @change="uploadTeachers" />
                </label>
              </div>
            </div>
            <div class="panel import-card">
              <div class="import-icon"><i class="pi pi-building"></i></div>
              <h3>考试与考场</h3>
              <p>导入日期、时段、课程、校区/考区/楼栋/楼层/考场和四类岗位人数。</p>
              <div class="button-row">
                <Button label="下载考试模板" icon="pi pi-download" severity="secondary" outlined @click="downloadTemplate('exam-template', '考试安排模板.xlsx')" />
                <label class="upload-label" :class="{ disabled: !selectedBatchId }">
                  <i class="pi pi-upload"></i> 导入考试 Excel
                  <input type="file" accept=".xlsx" :disabled="!selectedBatchId" @change="uploadExams" />
                </label>
              </div>
              <small v-if="!selectedBatchId">请先在顶部选择考试批次。</small>
            </div>
          </div>

          <div v-if="lastImport" class="panel">
            <h3>最近一次导入结果</h3>
            <pre class="result-json">{{ JSON.stringify(lastImport, null, 2) }}</pre>
          </div>
        </section>

        <section v-else-if="activeTab === 'solve'" class="panel-stack">
          <div class="panel solver-hero">
            <div>
              <h2>智能自动排班</h2>
              <p>硬约束全部满足后，再优化工作量公平、连续监考和已有排班稳定性。</p>
              <div class="role-pills">
                <span v-for="role in roles" :key="role.id">{{ role.name }} × {{ role.workload_weight }}</span>
              </div>
            </div>
            <div class="solver-actions">
              <Button label="检查能否排开" icon="pi pi-search" severity="secondary" outlined :loading="solving" :disabled="!selectedBatchId" @click="runSolver(false)" />
              <Button label="一键自动排班" icon="pi pi-sparkles" :loading="solving" :disabled="!selectedBatchId" @click="runSolver(true)" />
            </div>
          </div>

          <div v-if="solveResult" class="panel">
            <div class="status-line">
              <Tag :severity="solveSeverity" :value="solveResult.status" />
              <strong>{{ solveResult.message || (solveResult.persisted ? '排班已写入数据库' : '检查完成，尚未写入') }}</strong>
              <span v-if="solveResult.stats">耗时 {{ Number(solveResult.stats.wall_time || 0).toFixed(3) }}s</span>
            </div>
            <div v-if="solveResult.diagnostics?.length" class="diagnostics">
              <div v-for="(item, index) in solveResult.diagnostics" :key="index" class="diagnostic-item">
                <i class="pi pi-exclamation-triangle"></i>
                <div><strong>{{ item.kind }}</strong><p>{{ item.message }}</p></div>
              </div>
            </div>
          </div>

          <div class="panel">
            <div class="panel-title result-header">
              <div><h2>监考安排结果</h2><p>锁定后再次自动排班，该人员和岗位保持不变；其余岗位允许局部重排。</p></div>
              <div class="result-actions">
                <Button icon="pi pi-file-excel" label="导出 Excel" severity="success" outlined @click="downloadReport('xlsx')" :disabled="!selectedBatchId || !assignments.length" />
                <Button icon="pi pi-file-pdf" label="打印版 PDF" severity="danger" outlined @click="downloadReport('pdf')" :disabled="!selectedBatchId || !assignments.length" />
                <Button icon="pi pi-refresh" label="刷新" text @click="loadAssignments" :disabled="!selectedBatchId" />
              </div>
            </div>
            <DataTable :value="assignments" size="small" stripedRows paginator :rows="20" :rowsPerPageOptions="[20, 50, 100]" emptyMessage="当前批次还没有排班结果">
              <Column field="date" header="日期" sortable />
              <Column field="slot_name" header="时段">
                <template #body="{ data }">{{ data.slot_name || data.slot_code }}</template>
              </Column>
              <Column field="location_name" header="范围/考场" sortable />
              <Column field="role_name" header="岗位" sortable>
                <template #body="{ data }"><Tag :value="data.role_name" severity="info" /></template>
              </Column>
              <Column field="teacher_name" header="监考人员" sortable />
              <Column field="source" header="来源" />
              <Column header="锁定" style="width: 90px">
                <template #body="{ data }">
                  <Button :icon="data.locked ? 'pi pi-lock' : 'pi pi-lock-open'" rounded text :severity="data.locked ? 'warning' : 'secondary'" @click="toggleLock(data)" />
                </template>
              </Column>
              <Column header="操作" style="width: 90px">
                <template #body="{ data }">
                  <Button icon="pi pi-trash" rounded text severity="danger" @click="removeAssignment(data)" />
                </template>
              </Column>
            </DataTable>
          </div>
        </section>

        <section v-else-if="activeTab === 'people'" class="panel-stack">
          <div class="panel">
            <div class="panel-title">
              <div><h2>监考人员</h2><p>人员资格可通过 Excel 批量维护，也可通过后端配置接口单独修改。</p></div>
              <span class="count-badge">{{ teachers.length }} 人</span>
            </div>
            <DataTable :value="teachers" size="small" stripedRows paginator :rows="20" emptyMessage="尚未导入人员">
              <Column field="employee_no" header="工号" />
              <Column field="professor_name" header="姓名" sortable />
              <Column field="department" header="部门" sortable />
              <Column field="max_daily_duties" header="每天上限" />
              <Column field="max_total_duties" header="总场次上限" />
              <Column header="状态"><template #body="{ data }"><Tag :value="data.active ? '启用' : '停用'" :severity="data.active ? 'success' : 'secondary'" /></template></Column>
            </DataTable>
          </div>
        </section>

        <section v-else class="panel-stack">
          <div class="panel">
            <div class="panel-title"><div><h2>排班规则</h2><p>修改后会在下一次自动排班时生效。</p></div></div>
            <div class="rules-list">
              <div v-for="rule in rules" :key="rule.key" class="rule-row">
                <div class="rule-info"><strong>{{ rule.key }}</strong><span>{{ rule.description }}</span></div>
                <InputText v-model="ruleDrafts[rule.key]" />
                <Button label="保存" size="small" text @click="saveRule(rule)" />
              </div>
            </div>
          </div>
        </section>
      </main>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Password from 'primevue/password'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'

axios.defaults.withCredentials = true
const toast = useToast()

const authenticated = ref(false)
const loginLoading = ref(false)
const loginError = ref('')
const loginForm = reactive({ username: '', password: '' })
const activeTab = ref('data')
const batches = ref([])
const selectedBatchId = ref('')
const overview = ref(null)
const assignments = ref([])
const teachers = ref([])
const roles = ref([])
const rules = ref([])
const ruleDrafts = reactive({})
const solving = ref(false)
const solveResult = ref(null)
const lastImport = ref(null)
const newBatch = reactive({ name: '', academic_year: '', term: '' })

const tabs = [
  { key: 'data', label: '考试数据', icon: 'pi pi-database' },
  { key: 'solve', label: '自动排班', icon: 'pi pi-sparkles' },
  { key: 'people', label: '监考人员', icon: 'pi pi-users' },
  { key: 'rules', label: '规则设置', icon: 'pi pi-sliders-h' },
]

const solveSeverity = computed(() => {
  const status = solveResult.value?.status
  if (['OPTIMAL', 'FEASIBLE'].includes(status)) return 'success'
  if (status === 'INFEASIBLE_PRECHECK' || status === 'INFEASIBLE') return 'danger'
  return 'warning'
})

function notify(severity, summary, detail) {
  toast.add({ severity, summary, detail, life: 4500 })
}

async function checkAuth() {
  try {
    await axios.get('/api/config')
    authenticated.value = true
    await loadBaseData()
  } catch (error) {
    if (error.response?.status === 401) authenticated.value = false
    else notify('error', '连接失败', error.response?.data?.detail || error.message)
  }
}

async function login() {
  loginLoading.value = true
  loginError.value = ''
  try {
    await axios.post('/api/login', loginForm)
    authenticated.value = true
    await loadBaseData()
  } catch (error) {
    loginError.value = error.response?.data?.detail || '登录失败'
  } finally {
    loginLoading.value = false
  }
}

async function logout() {
  await axios.post('/api/logout').catch(() => {})
  authenticated.value = false
}

function goHome() {
  window.location.href = '/'
}

async function loadBaseData() {
  try {
    const [batchRes, teacherRes, roleRes, ruleRes] = await Promise.all([
      axios.get('/api/invigilation/batches'),
      axios.get('/api/invigilation/teachers'),
      axios.get('/api/invigilation/roles'),
      axios.get('/api/invigilation/rules'),
    ])
    batches.value = batchRes.data
    teachers.value = teacherRes.data
    roles.value = roleRes.data
    rules.value = ruleRes.data
    rules.value.forEach(rule => { ruleDrafts[rule.key] = rule.value })
    if (!selectedBatchId.value && batches.value.length) selectedBatchId.value = String(batches.value[0].id)
    if (selectedBatchId.value) await loadBatch()
  } catch (error) {
    if (error.response?.status === 403) notify('warn', '权限不足', '智能监考排班需要管理员权限。')
    else notify('error', '加载失败', error.response?.data?.detail || error.message)
  }
}

async function loadBatch() {
  solveResult.value = null
  if (!selectedBatchId.value) {
    overview.value = null
    assignments.value = []
    return
  }
  await Promise.all([loadOverview(), loadAssignments()])
}

async function loadOverview() {
  if (!selectedBatchId.value) return
  const response = await axios.get(`/api/invigilation/overview/${selectedBatchId.value}`)
  overview.value = response.data
}

async function loadAssignments() {
  if (!selectedBatchId.value) return
  const response = await axios.get('/api/invigilation/assignments', { params: { batch_id: selectedBatchId.value } })
  assignments.value = response.data
}

function selectBatch(id) {
  selectedBatchId.value = String(id)
  loadBatch()
}

async function createBatch() {
  try {
    const response = await axios.post('/api/invigilation/batches', {
      name: newBatch.name.trim(), academic_year: newBatch.academic_year.trim() || null,
      term: newBatch.term.trim() || null, status: 'DRAFT', notes: null,
    })
    newBatch.name = ''; newBatch.academic_year = ''; newBatch.term = ''
    await loadBaseData()
    selectBatch(response.data.id)
    notify('success', '已创建', '考试批次创建成功。')
  } catch (error) {
    notify('error', '创建失败', error.response?.data?.detail || error.message)
  }
}

async function downloadTemplate(endpoint, filename) {
  try {
    const response = await axios.get(`/api/invigilation/import/${endpoint}`, { responseType: 'blob' })
    saveBlob(response.data, filename)
  } catch (error) {
    notify('error', '下载失败', error.response?.data?.detail || error.message)
  }
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function downloadReport(format) {
  if (!selectedBatchId.value) return
  try {
    const response = await axios.get(`/api/invigilation/export/${selectedBatchId.value}/${format}`, { responseType: 'blob' })
    const selected = batches.value.find(batch => String(batch.id) === String(selectedBatchId.value))
    const base = selected?.name || `监考安排_${selectedBatchId.value}`
    saveBlob(response.data, `${base}_监考安排.${format}`)
  } catch (error) {
    let detail = error.message
    if (error.response?.data instanceof Blob) {
      try {
        const text = await error.response.data.text()
        detail = JSON.parse(text)?.detail || detail
      } catch (_) {}
    } else {
      detail = error.response?.data?.detail || detail
    }
    notify('error', '导出失败', detail)
  }
}

async function uploadFile(file, url, params = {}) {
  const form = new FormData(); form.append('file', file)
  const response = await axios.post(url, form, { params, headers: { 'Content-Type': 'multipart/form-data' } })
  lastImport.value = response.data
  if (response.data.errors?.length) notify('warn', '导入完成但有错误', `共 ${response.data.errors.length} 行未导入，请查看结果。`)
  else notify('success', '导入成功', 'Excel 数据已写入本地数据库。')
  await loadBaseData()
}

async function uploadTeachers(event) {
  const file = event.target.files?.[0]; event.target.value = ''
  if (!file) return
  try { await uploadFile(file, '/api/invigilation/import/teachers') }
  catch (error) { notify('error', '人员导入失败', error.response?.data?.detail || error.message) }
}

async function uploadExams(event) {
  const file = event.target.files?.[0]; event.target.value = ''
  if (!file || !selectedBatchId.value) return
  try { await uploadFile(file, '/api/invigilation/import/exams', { batch_id: selectedBatchId.value }) }
  catch (error) { notify('error', '考试导入失败', error.response?.data?.detail || error.message) }
}

async function runSolver(persist) {
  if (!selectedBatchId.value) return
  solving.value = true
  try {
    const response = await axios.post(`/api/invigilation/solve/${selectedBatchId.value}`, { persist, replace_unlocked: true })
    solveResult.value = response.data
    if (['OPTIMAL', 'FEASIBLE'].includes(response.data.status)) {
      notify('success', persist ? '排班完成' : '检查通过', persist ? `已生成 ${response.data.assignment_count} 个监考岗位。` : '当前数据存在可行排班。')
      if (persist) await loadAssignments()
    } else {
      notify('warn', '当前无法完成排班', response.data.message || '请查看冲突诊断。')
    }
  } catch (error) {
    notify('error', '求解失败', error.response?.data?.detail || error.message)
  } finally {
    solving.value = false
  }
}

async function toggleLock(row) {
  try {
    await axios.put(`/api/invigilation/assignments/${row.id}/lock`, { locked: !row.locked })
    await loadAssignments()
  } catch (error) {
    notify('error', '操作失败', error.response?.data?.detail || error.message)
  }
}

async function removeAssignment(row) {
  if (!window.confirm(`确定移除 ${row.teacher_name} 的 ${row.role_name} 任务吗？`)) return
  try {
    await axios.delete(`/api/invigilation/assignments/${row.id}`)
    await loadAssignments()
  } catch (error) {
    notify('error', '删除失败', error.response?.data?.detail || error.message)
  }
}

async function saveRule(rule) {
  try {
    await axios.put(`/api/invigilation/rules/${encodeURIComponent(rule.key)}`, {
      value: String(ruleDrafts[rule.key] ?? ''), value_type: rule.value_type, description: rule.description,
    })
    notify('success', '规则已保存', rule.key)
    await loadBaseData()
  } catch (error) {
    notify('error', '保存失败', error.response?.data?.detail || error.message)
  }
}

onMounted(checkAuth)
</script>

<style scoped>
:global(body) { margin: 0; background: #f5f7fb; color: #182230; font-family: Inter, "Microsoft YaHei", system-ui, sans-serif; }
.inv-app { min-height: 100vh; }
.login-page { min-height: 100vh; display: grid; place-items: center; background: linear-gradient(145deg, #eef4ff, #f7f9fc 52%, #eef8f4); }
.login-card { width: min(420px, calc(100vw - 40px)); background: #fff; border: 1px solid #e4e9f0; border-radius: 20px; padding: 38px; box-shadow: 0 24px 70px rgba(30, 45, 70, .12); }
.login-card h1 { margin: 14px 0 6px; font-size: 28px; }
.login-card > p { margin: 0 0 28px; color: #667085; }
.brand-mark { width: 52px; height: 52px; border-radius: 15px; display: grid; place-items: center; background: #eaf2ff; color: #2563eb; font-size: 24px; }
.login-form { display: grid; gap: 10px; }
.login-form label { font-size: 13px; font-weight: 700; color: #475467; margin-top: 6px; }
.error-box { background: #fff1f1; color: #b42318; border-radius: 8px; padding: 10px 12px; font-size: 13px; }
.topbar { background: #fff; border-bottom: 1px solid #e6eaf0; min-height: 88px; padding: 14px 30px; display: flex; align-items: center; justify-content: space-between; gap: 20px; position: sticky; top: 0; z-index: 20; }
.topbar h1 { margin: 0; font-size: 22px; }
.topbar p { margin: 5px 0 0; color: #667085; font-size: 13px; }
.topbar-actions { display: flex; gap: 10px; align-items: center; }
.batch-select { min-width: 300px; height: 42px; border: 1px solid #d0d5dd; border-radius: 8px; padding: 0 12px; background: #fff; }
.workspace { width: min(1480px, calc(100% - 40px)); margin: 24px auto 60px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.summary-card { background: #fff; border: 1px solid #e5e9ef; border-radius: 14px; padding: 18px 20px; display: flex; justify-content: space-between; align-items: baseline; }
.summary-card span { color: #667085; font-size: 13px; }
.summary-card strong { font-size: 28px; }
.section-tabs { display: flex; gap: 6px; background: #e9edf3; width: fit-content; padding: 5px; border-radius: 10px; margin-bottom: 18px; }
.section-tabs button { border: 0; background: transparent; padding: 10px 16px; border-radius: 7px; color: #475467; font-weight: 650; cursor: pointer; display: flex; gap: 8px; align-items: center; }
.section-tabs button.active { background: #fff; color: #1d4ed8; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.panel-stack { display: grid; gap: 16px; }
.panel { background: #fff; border: 1px solid #e5e9ef; border-radius: 14px; padding: 22px; }
.panel h2, .panel h3 { margin: 0; }
.panel p { color: #667085; margin: 6px 0 0; }
.panel-title { display: flex; justify-content: space-between; align-items: center; gap: 15px; }
.result-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.create-row { display: grid; grid-template-columns: 2fr 1fr 1fr auto; gap: 10px; margin-top: 18px; }
.mt-16 { margin-top: 16px; }
.import-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.import-card { min-height: 170px; }
.import-icon { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 10px; background: #eef4ff; color: #2563eb; margin-bottom: 14px; }
.button-row { display: flex; gap: 10px; align-items: center; margin-top: 18px; flex-wrap: wrap; }
.upload-label { height: 40px; display: inline-flex; align-items: center; gap: 8px; border-radius: 7px; padding: 0 14px; background: #2563eb; color: #fff; cursor: pointer; font-size: 14px; font-weight: 600; }
.upload-label input { display: none; }
.upload-label.disabled { opacity: .45; cursor: not-allowed; }
.result-json { white-space: pre-wrap; background: #f7f8fa; padding: 14px; border-radius: 8px; max-height: 280px; overflow: auto; font-size: 12px; }
.solver-hero { display: flex; align-items: center; justify-content: space-between; gap: 20px; background: linear-gradient(135deg, #fff, #f6f9ff); }
.solver-actions { display: flex; gap: 10px; }
.role-pills { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.role-pills span { background: #edf4ff; color: #1849a9; border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 700; }
.status-line { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.status-line span:last-child { color: #667085; font-size: 13px; }
.diagnostics { display: grid; gap: 8px; margin-top: 16px; }
.diagnostic-item { display: flex; gap: 12px; background: #fff6ed; border: 1px solid #fedfbd; padding: 12px; border-radius: 9px; color: #b54708; }
.diagnostic-item p { margin: 3px 0 0; color: #7a2e0e; }
.count-badge { background: #f2f4f7; border-radius: 999px; padding: 6px 10px; font-size: 13px; }
.rules-list { display: grid; margin-top: 12px; }
.rule-row { display: grid; grid-template-columns: minmax(300px, 1fr) 260px 80px; gap: 12px; align-items: center; padding: 14px 0; border-bottom: 1px solid #eef0f3; }
.rule-info { display: grid; gap: 4px; }
.rule-info span { color: #667085; font-size: 12px; }
@media (max-width: 900px) {
  .topbar { align-items: flex-start; flex-direction: column; }
  .topbar-actions { width: 100%; flex-wrap: wrap; }
  .batch-select { min-width: 0; flex: 1; }
  .summary-grid { grid-template-columns: 1fr 1fr; }
  .import-grid { grid-template-columns: 1fr; }
  .create-row { grid-template-columns: 1fr; }
  .solver-hero, .result-header { align-items: flex-start; flex-direction: column; }
  .result-actions { justify-content: flex-start; }
  .rule-row { grid-template-columns: 1fr; }
}
</style>
