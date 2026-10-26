[English](GUIDE.md) · [返回首页](../README.md)

# ID 雷达

在本机识别昵称列表，检查多个平台的同名情况，选出一套能实际使用的昵称与 handle 方案。

**本工具不调用任何 AI，不需要 API 密钥。** 起名交给你自己常用的 AI，再把回复粘回来。

![ID 雷达演示（中文）](images/demo-zh.png)

## 安装与启动

先从 [python.org](https://www.python.org/downloads/) 安装 **Python 3.11+**，Windows 安装时勾选 “Add Python to PATH”。真实浏览器查重还需要本机 Microsoft Edge 或 Google Chrome；工具使用已安装的浏览器，不要执行 `playwright install`。

1. 下载仓库，Windows **双击 `start.bat`**。
2. macOS / Linux 在仓库目录执行 `bash start.sh`。
3. 首次启动自动创建 `.venv` 并安装 `requirements.txt`，以后复用环境；首次安装需要联网。Windows 启动出错时窗口保留错误提示。

普通模式就绪后自动打开 <http://127.0.0.1:8765>，只允许本机访问。没有自动打开时手动访问；终端按 `Ctrl+C` 停止。端口被占用时先关闭旧实例。

也可手动安装：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m idradar
```

macOS / Linux 用 `python3 -m venv .venv`，后两条命令的 Python 路径改成 `.venv/bin/python`。**运行工具不需要 Node.js、npm 或前端构建。**

## 快速开始

1. 复制第 1 步提示词，粘到你常用的 ChatGPT、Claude、DeepSeek、豆包等 AI。
2. 回答它一次提出的五个问题，获得名字建议。
3. 整段粘回第 1 步，点“识别名字”；也可每行手写一个名字。
4. 检查第 2 步候选和可编辑的 handle。默认只勾前 10 个，连同已勾选项合计不超过 10；已有同名候选更新非空的新 handle。
5. 选择平台并查重。超过 10 个时按每批最多 10 行接着查；浏览器验证暂停该平台，等你处理，HTTP 限流仍停止后续请求。
6. 有冲突的行自动给两种推荐。采用推荐后，可在“我的 ID 方案”复制最终用名、打开注册/改名入口；所有平台都没冲突的原名，点“就用它”直接复制名字。结果表里名字和 handle 旁的复制图标也能一键复制。

推荐粘贴格式：

```text
百号工具人 | albertwu
造轮子百回 | zaolunzi
```

支持代码块、普通/全角竖线、编号、项目符号和引号；解释行会丢弃。有竖线格式时，其余行只收光秃秃的名字。按归一化名字去重，每次最多识别 30 个，候选总数上限 300。查重前请检查识别结果。

提示词要求 handle 只用小写字母和数字、5～15 位。缺省时仅在拼音兜底不超过 15 位时使用，否则留空。GitHub、X 遇空 handle 不发请求，直接显示不合规则。“复制补 handle 提示词”可交给自己的 AI；回复粘回后会更新已有候选。

## 语言与平台

顶栏醒目的“中文 | EN”即时切换文案，不清空候选、勾选、结果和采用的方案。首次跟随浏览器语言，之后记住选择。英文默认显示 GitHub、X 和自定义网站；中文默认显示全部内置平台，隐藏的平台可以随时恢复。

| 平台 | 方式 | 能查到什么程度 |
| --- | --- | --- |
| B站 | 不登录，浏览器搜索用户 | 本次页面的同名和相近账号；只有模糊相关结果时仍判没搜到同名，最多列 3 个相关账号参考。 |
| GitHub | 不登录，HTTP | 只查 handle：404 没账号、200 被占用；保留用户名仍可能不能注册。 |
| X | 不登录，HTTP 请求 `x.com/<handle>` | 只查 handle：404 没主页、200 被占用；封禁或停用账号仍可能保留名字。不查可重名的显示名。 |
| 抖音 | 在专用浏览器自行登录 | 依赖网页搜索、会话 Cookie 和选择器，平台改版后可能需要维护。 |
| 小红书 | 在专用浏览器自行登录 | 同上；收集的昵称唯一性资料尚无官方定论，以平台提示为准。 |
| 视频号 | 仅手动 | 微信 → 发现 → 视频号 → 搜索，或创建/改名时直接试填；工具不自动操作微信。 |

**没搜到同名不等于一定能注册。** 手动、未登录、出错和违规既不算冲突，也不算确认可用。原名行的“全平台可用”统计自动平台；统一变体必须在所有已选平台都可用，因此选了手动平台就无法自动确认该方案。

## ID 雷达专用浏览器

B站、抖音、小红书共用一个有界面的持久化浏览器，目录为 `~/.idradar/browser-profile`，启动后一直放在屏幕外，每个平台复用一个固定标签页，普通查询不主动移回前台。关闭窗口后下次查询或登录会自动重开。每 2 秒刷新登录状态，判断不了显示“未确认”。小红书只认已登录侧栏个人主页入口，不能把游客的 `web_session` 当登录；抖音可用登录后才有的会话 Cookie。同平台首次返回需要登录后，后续格子直接短路；查重中途扫码登录成功，后面的格子会照常查。

点“扫码登录”后，网页显示平台页面已经呈现的二维码图片。沿用实测过的小红书 `img.qrcode-img`、抖音 `img[aria-label="二维码"]`，等图片加载完成再读取已显示的 data URL，或截取该图片；图片只在内存中，120 秒倒计时，过期可换一张，手机端提示截图后从相册扫码。确认登录后卡片 1.5 秒收起。取不到二维码时保存本机快照并把窗口移到屏幕中央；自行登录后点“我登录完了，继续”隐藏窗口，也可点“打开窗口登录”再次显示。

浏览器平台遇验证时（例如抖音滑块、小红书“扫码验证身份”）自动弹出窗口，页面顶部同时闪烁提示，暂停当前格，其他平台可继续。自行完成验证后，工具每秒检测已有验证标记，消失后再等一秒复查，随后收起窗口并重查暂停的格子；“我验证完了，继续查”保留作备用。多个平台要验证时排队，同一时间只显示一个。程序不自动过验证、不伪装指纹、不使用 stealth。验证卡未结束前，不要为同一平台另开登录流程。

查重中可点“停止查重”中断流并取消剩余查询和变体。完成格子保留，未完成格子显示“已停止”，历史记 `stopped: true`，正在显示的验证窗口也会收起。再次开始会整批重查。查重范围里的抖音、小红书尚未确认登录时，页面顶部会显示带扫码按钮的提示条，闪烁三次后常亮；系统开启减弱动态效果时不闪。“先跳过”后本页面暂不再提示，点开始查重时会重新提醒。

为什么不用你平时的浏览器：程序只能控制自己打开的窗口；读取日常浏览器登录信息有安全风险，所以不做。在专用窗口自行登录一次，之后会记住。

加载失败或识别不了的页面，会尽可能保存 HTML 和整页 PNG 到 `probe/`，格子详情给出完整路径。**快照可能包含账号信息。** 文件仅留本机、不上传，由你决定是否交给开发者；页面已关闭等情况可能无法完整保存。

## 自己添加网站、移除平台

点“+ 添加网站”，填 1～12 字网站名、包含 `{name}` 或 `{handle}` 的 HTTP(S) 网址，代入时自动 URL 编码。最多 10 个。

- **个人主页地址**：HTTP GET，跟随跳转，超时 10 秒。仅 404 判没人用，200 判被占用；其他 HTTP 状态需手动确认。连接失败显示查询出错和代理提示。有的网站登录页、错误页也返回 200，应打开核对。
- **搜索页**：不发请求；格子直接在新标签页打开代入后的网址，由你自己看。

自定义网站规则未知，存入已忽略的 `custom_platforms.json`，新增默认勾选。“×”删除前会确认。

删除按钮用内联 SVG 画“×”，不依赖字体。内置平台和自定义网站都先弹页面内确认卡，确认后才移除；内置平台可从“恢复内置平台”加回，自定义网站会删除设置，至少留一个。中文/英文隐藏列表分别存 `idradar.hidden.zh`、`idradar.hidden.en`，语言存 `idradar.lang`。存储不可用时本页仍能操作，已有矩阵保留开始查询时的平台配置。平台标签和格子状态带平台图标，结果矩阵纵向滚动时表头吸顶。

## 取名规则与自动找相似

“取名规则”显示长度、字符类别、唯一性、改名限制和来源可信度。资料来自 2026-10-26 的[本地调研](platform_naming_rules.md)，可能有矛盾或缺失；**注册时以平台当前提示为准。** 只有确定违反格式才拦截请求，未知或冲突只提示。例如视频号汉字按 2 计；X 仅在 4 位提示长度资料冲突，超过 15 位明确拒绝。

所有原名（含后续批次）先查完，再按“可用平台数多、占用平台数少、原顺序”评分。全次查询排名前三的行加“推荐”，仅这三行中有冲突的自动找变体；其余冲突行点“找可用变体”才查。

变体是“名字 + handle”成对值。查名字的平台冲突就换名字；GitHub、X、个人主页型自定义网站冲突就换 handle。加词、加数字交替取，跳过违规对；每行每轮最多 4 个，全部已选平台都查，找到全平台可用的一对就停。英文名用后缀 `dev`、`hq`、`lab`、`builds`、`official` 或前缀 `real`、`its`、`the`，中文名保留中文词表，数字从 `001` 开始。

- **只换有冲突的平台**：每个冲突平台选第一个查过可用的，其余保留原名。
- **所有平台统一换成一个名字**：选第一个在所有已选平台都查过可用的组合。

没找到对应方案时按钮禁用。“换一批再查”从上次实际查过的位置继续。想要同音字或中英混写时，复制下方提示词给自己的 AI。

采用后结论变“已定”，格子显示最终用名，可撤销。Markdown / CSV 每个平台增加“最终用名”列。方案卡支持单项/全部复制及注册/改名入口，自定义网站打开域名首页；多个已定行可在卡内切换。采用状态仅在当前页面保留；历史保存查询结果和自动推荐。

## 系统代理

GitHub、X、个人主页型自定义网站的 HTTP 请求优先读取环境代理（`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY`），Windows 再通过 `urllib.request.getproxies()` 获取系统设置；本机地址绕过代理。使用 Clash 等软件时，按需打开它的“系统代理”。浏览器查询遵循浏览器的系统设置。连不上时详情注明平台和域名、建议开代理重试；工具不会配置你的代理软件。

## 离线演示

```powershell
.venv\Scripts\python -m idradar --demo
```

也可 `start.bat --demo` / `bash start.sh --demo`。自行打开 <http://127.0.0.1:8765>；演示模式不自动打开浏览器。标题旁显示“演示模式”，第 1 步有“粘贴示例回复”；中英样本均可产生可用、占用、相近和推荐行。

演示查询用固定假 checker，不对外联网、不启动专用浏览器、不读取真实网站配置或登录状态、不写历史；演示中增删的网站只放内存。本机页面/API 仍通过 localhost 通信。注册链接是真实入口，点击属于另外的手动操作。

## 本地数据与使用守则

- 粘贴回复仅在本机解析，不发给 AI；真实查重会把名字或 handle 发给所选平台。
- 会话：`~/.idradar/browser-profile`；历史：`~/.idradar/history.jsonl`；网站：`custom_platforms.json`；错误快照：`probe/`。
- 不收集遥测、不自动上传。请按私人资料保管会话和截图；清除历史或浏览器目录前先停止工具。
- 低频、个人使用。同平台串行，HTTP 平台间隔随机 0.3～0.8 秒，浏览器平台 1～2 秒，平台间并行，批次与变体沿用间隔。识别按 0.2 秒轮询、上限 8 秒。整体进度条和剩余时间先预留最多三行自动变体工作量，跳过不必要工作时收缩；人工验证等待不计入耗时样本。
- 不绕过验证，不自动注册、不冒充账号、不批量扫号；能否注册最终由平台决定。

## 开发

运行工具不需要 Node.js；**开发测试需要 Python 依赖和 Node.js 18+**，用于运行 `tests/frontend_plans.cjs`、`tests/frontend_components.cjs`，不需要 npm 包。最小 DOM 测试验证逻辑，不能代替视觉验收。

```powershell
.venv\Scripts\python -X utf8 -m pytest -q tests
.venv\Scripts\python -X utf8 -c "import idradar.server, idradar.parse_names, idradar.variants, idradar.browser, idradar.probe"
.venv\Scripts\python -X utf8 scripts/check_i18n.py
.venv\Scripts\python -X utf8 scripts/verify_ui.py
```

pytest 禁止真实网络：平台使用样本和假 HTTP/浏览器，提示词逐字对照 [docs/PROMPTS.md](PROMPTS.md)。UI 脚本用本机 Edge、假二维码、假验证和隔离演示服务；使用轮询，不用受 CSP 限制的动态等待，也不读取浏览器 SSE 响应体。截图存 `.test-artifacts/ui/`，含 `v5-desktop-zh.png`、`v5-desktop-en.png`、`v5-mobile-en.png` 和验证/扫码卡。运行环境须允许 Playwright 启动子进程；`--serve-only` 只启动假平台预览。

可选真实 B站/GitHub 冒烟和抓页独立于 pytest：

```powershell
.venv\Scripts\python -X utf8 scripts/smoke_live.py "AI包工头" --handle ai-toolman
.venv\Scripts\python -X utf8 -m idradar.probe douyin "百号工具人"
```

probe 优先复用正在运行的工具窗口，服务没启动才自行开专用窗口。快照可能含私人信息，请勿提交。

## 本机接口

每个请求传 `?lang=zh` 或 `?lang=en`，默认中文。说明附双语副本，页面切换时不必重新查平台。基址 `http://127.0.0.1:8765`，完整字段见 `/docs`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/prompt` | 当前语言提示词、演示标记与样本 |
| GET | `/api/platforms` | 内置/自定义平台、登录及窗口状态 |
| GET / POST | `/api/custom-platforms` | 列出/新增网站：`label`、`url_template`、`kind`（`profile` / `search`） |
| DELETE | `/api/custom-platforms/{id}` | 删除自定义网站 |
| POST | `/api/parse-names` | 解析 `text`，按 `existing` 更新 handle，分别计数 |
| GET / POST | `/api/rules`、`/api/rules/check` | 规则资料 / 候选校验与补 handle 提示词 |
| POST / GET / DELETE | `/api/login/{platform}` | 开始/刷新扫码、轮询状态、关闭登录卡；演示模式禁用 |
| POST | `/api/login/{platform}/window`、`/api/login/{platform}/continue` | 再次显示窗口登录 / 确认登录并隐藏窗口 |
| POST | `/api/probe/{platform}` | 专用浏览器抓页；演示模式禁用 |
| POST | `/api/check` | 最多 300 候选、每批 10 行；SSE `result`、`batch`、`ranking`、`progress`、`recommendation`、`verification`、`verification_resumed`、`done` |
| POST | `/api/check/{run_id}/{platform}/show`、`/api/check/{run_id}/{platform}/continue` | 显示验证 / 继续同一格，传当前 `pause_id` |
| POST | `/api/variants`、`/api/variants/check` | 预览/查后续最多 4 对，参数 `candidate`、`original`、`platforms`、`offset` |
| GET | `/api/history` | 本机历史；演示模式为空 |

许可为 [MIT](../LICENSE)。
