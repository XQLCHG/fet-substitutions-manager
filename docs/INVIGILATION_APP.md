# 智能监考排班系统

本分支在原 `fet-substitutions-manager` 基础上新增面向国内高校/学校的独立监考排班工作台。

## 1. Windows 本地版（推荐给教务使用）

GitHub Actions 的 `Windows Desktop Build` 会生成：

```text
SmartInvigilation-Windows-x64
└── SmartInvigilation.exe
```

使用步骤：

1. 双击 `SmartInvigilation.exe`。
2. 第一次启动会弹窗创建本地管理员，用户名固定为 `super_admin`，密码由使用者自己设置，至少 8 位。
3. 程序只监听本机 `127.0.0.1`，随后自动打开浏览器中的智能监考工作台。
4. 第二次以后直接双击即可，不需要安装 Python、Node.js 或 Docker。

本地数据默认保存在：

```text
%LOCALAPPDATA%\SmartInvigilation\
├── secret.key
└── data\
    ├── auth.db
    └── local\
        └── gestor.db
```

其中 `gestor.db` 是监考业务数据，`auth.db` 是本地登录账号。建议考试排班完成后备份整个 `%LOCALAPPDATA%\SmartInvigilation` 文件夹。

> 不要把 `secret.key` 或真实教师数据提交到 GitHub。

## 2. 开发/Web 模式入口

本地 Docker 启动原项目后访问：

```text
http://localhost:8080/invigilation
```

Vite 开发模式访问：

```text
http://localhost:5173/invigilation
```

使用原项目管理员账号登录。

## 3. 支持的岗位

默认内置四类岗位，并允许后续继续新增岗位：

| 代码 | 名称 | 默认作用范围 | 默认工作量权重 |
|---|---|---|---:|
| PRIMARY | 甲监 | 考场 ROOM | 1.2 |
| SECONDARY | 乙监 | 考场 ROOM | 1.0 |
| ROVING | 流动监考 | 楼层 FLOOR | 1.1 |
| INSPECTOR | 巡考 | 考区 AREA | 1.3 |

地点使用层级模型：

```text
校区 → 考区 → 楼栋 → 楼层 → 考场
```

例如：

```text
东校区
└── 第一考区
    └── 第一教学楼
        └── 1层
            ├── A101  甲监1 + 乙监1
            └── A102  甲监1 + 乙监1

1层          流动监考2
第一考区     巡考2
```

## 4. 推荐使用流程

1. 进入“考试数据”，创建考试批次。
2. 下载“监考人员模板.xlsx”。
3. 填写人员、岗位资格、场次上限和不可用时间后导入。
4. 下载“考试安排模板.xlsx”。
5. 填写日期、时段、课程、地点以及甲监/乙监/流动监考/巡考人数后导入。
6. 进入“自动排班”，先点击“检查能否排开”。
7. 若没有硬约束缺口，点击“一键自动排班”。
8. 对已经确认或已经通知的监考安排点击锁定。
9. 有人员临时请假或需要换人时，删除相关未锁定安排或修改不可用数据，然后再次一键排班；锁定项保持不变，其余项局部优化。
10. 导出 Excel 或打印版 PDF。

## 5. 人员 Excel 模板

“人员”工作表支持：

```text
工号
姓名
部门
甲监资格
乙监资格
流动监考资格
巡考资格
最大总场次
每日最大场次
启用
备注
```

“不可用时间”工作表支持：

```text
工号
姓名
日期
时段代码
原因
```

`时段代码` 留空表示整天不可用。

## 6. 考试 Excel 模板

“考试安排”支持：

```text
日期
时段代码
时段名称
开始时间
结束时间
课程代码
课程名称
班级
校区
考区
楼栋
楼层
考场
考场容量
考生人数
任课教师
部门
甲监人数
乙监人数
流动监考人数
巡考人数
备注
```

导入时系统会自动建立校区/考区/楼栋/楼层/考场层级，并生成对应岗位需求。

## 7. 自动排班约束

### 硬约束

- 每个地点、时段、岗位人数必须精确满足。
- 同一人员同一时段最多承担一个岗位。
- 人员必须具备对应岗位资格。
- 整日或指定时段不可用人员不得安排。
- 每日最大场次和总场次上限必须满足。
- 默认情况下，任课教师回避自己课程所在考场的甲监/乙监。
- 已锁定分配必须保持。

### 软约束

- 按岗位工作量权重平衡人员负载。
- 尽量避免连续时段监考。
- 局部重排时尽量保留原有未锁定安排，减少通知变化。

核心求解器使用 Google OR-Tools CP-SAT，不使用随机抽签作为最终排班算法。

## 8. 不可行诊断

在调用 CP-SAT 前会先检查常见硬约束缺口，包括：

- 某个岗位合格/可用人员少于需求。
- 某一考试时段总岗位数大于可用不同人员数。
- 锁定人员已经不符合资格或不可用。
- 锁定人数超过岗位需求。
- 岗位作用范围与地点类型不匹配。

系统会在前端显示具体日期、时段、地点、岗位、需要人数和候选人数，而不是只显示“排班失败”。

## 9. 导出

Excel 报表包含：

- 总监考表
- 按教师明细
- 工作量统计
- 批次信息

PDF 为横向 A4 打印版监考安排表。

## 10. 数据与兼容性

新增数据继续保存在原项目每个机构自己的 `gestor.db` 中，表名统一使用 `invigilation_*` 前缀。原 `vigilancies`、`substitucions` 等表不被迁移或重写，因此旧功能可以继续使用。

## 11. 自动验证

`.github/workflows/invigilation-ci.yml` 验证：

- Python `compileall`
- 监考数据唯一约束
- CP-SAT 可行/不可行场景
- Excel/PDF 导出基础逻辑
- Vue production build

`.github/workflows/windows-desktop.yml` 验证：

- 在真实 Windows runner 构建前端
- PyInstaller 生成 `SmartInvigilation.exe`
- 实际执行 `SmartInvigilation.exe --self-test`
- 检查 FastAPI 路由、SQLite 初始化、OR-Tools native library、中文 PDF 支持和前端资源
- 通过后上传 `SmartInvigilation-Windows-x64` artifact

正式投入真实考试前，仍应使用学校实际规则和脱敏历史数据做一轮验收测试，特别确认甲监/乙监资格、流动监考范围、巡考范围、每日场次上限及任课教师回避规则。
